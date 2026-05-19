# RunMyCampus Migration Cloud — Webhook Signature Verification

The platform signs every outbound webhook payload with **HMAC-SHA256**
over the **canonical JSON** form (sorted keys, no whitespace, UTF-8).
The signature ships in the `X-RunMyCampus-Signature` request header in
the form:

    sha256=<lowercase-hex-digest>

You verify it on the receiver side.

## Header family migration (v3.35.0, dual-emit through 2026-08-18)

The dispatcher currently emits **both** header families on every
delivery — the new canonical `X-RunMyCampus-*` family *and* the legacy
`X-Migration-Cloud-*` family — during a 90-day deprecation window
ending 2026-08-18. The signature bytes are byte-identical across both
families; only the header *names* differ.

After 2026-08-18 (RunMyCampus v3.40.0), the legacy family will be
removed. New integrations should use `X-RunMyCampus-Signature`.

A `X-RunMyCampus-Header-Deprecation` header is also emitted during the
window pointing at the removal date. See
[`docs/WEBHOOK_HEADER_MIGRATION_2026.md`](../../../../docs/WEBHOOK_HEADER_MIGRATION_2026.md)
for the full migration timeline and customer action items.

### SDK `verify(..., accept_legacy=)` parameter (v3.37.0)

Both the Python (`runmycampus-webhook-verifier`) and JavaScript
(`@runmycampus/webhook-verifier`) SDKs ship a new high-level
`verify(headers, body, secret, *, accept_legacy=True)` entry point that
accepts the FULL header map and resolves the correct signature
automatically:

```python
# Python — Flask example
from runmycampus_webhook_verifier import verify

result = verify(request.headers, raw_body, SECRET, accept_legacy=True)
if not result.valid:
    abort(401)
if result.used_legacy_header_family:
    log.warning("legacy webhook header family in use — migrate before 2026-08-18")
```

```ts
// Node — Express example
import { verify } from "@runmycampus/webhook-verifier";

const result = await verify(req.headers, req.body, SECRET, {
  acceptLegacy: true,
});
if (!result.valid) return res.status(401).end();
if (result.usedLegacyHeaderFamily) {
  console.warn("legacy webhook header family in use; migrate before 2026-08-18");
}
```

Preference order: the canonical `X-RunMyCampus-Signature` is consulted
first; the legacy `X-Migration-Cloud-Signature` is the fallback IFF
`accept_legacy=True` (Python) / `acceptLegacy: true` (JS). Set the
flag to `False` after the 2026-08-18 cutover to fail-closed on any
legacy-only deliveries.

The returned result carries non-sensitive diagnostics
(`used_legacy_header_family` / `usedLegacyHeaderFamily`, a short
non-sensitive `reason` string on failure) — safe to log. Signature
bytes and secret material are never echoed.

## Install (recommended)

Use the official packaged SDKs — they ship typed-error strict mode,
clock-skew enforcement, and exported canonical-JSON helpers:

```bash
# Python
pip install runmycampus-webhook-verifier

# JavaScript / TypeScript
npm install @runmycampus/webhook-verifier
```

* Python source: [`packages/runmycampus-webhook-verifier-py/`](../../../../packages/runmycampus-webhook-verifier-py/)
* JS source: [`packages/runmycampus-webhook-verifier-js/`](../../../../packages/runmycampus-webhook-verifier-js/)

The two packages are byte-for-byte interoperable; a CI fixture file
asserts both produce identical canonical bytes for the same input.

## Vendored copy (legacy)

For air-gapped environments and customers who can't reach
PyPI / npm, the original single-file standalone SDKs remain
available. They will be supported through v4.0.0.

| Surface | File | Runtime |
|---|---|---|
| Python | `webhook_verifier_sdk.py` (DEPRECATED) | CPython 3.8+ (stdlib only) |
| JavaScript | `runmycampus_webhook_verifier.js` (DEPRECATED) | Browser + Node 16+ |

> **Constant-time compare** is non-negotiable. Both SDKs use
> `hmac.compare_digest` (Python) or a manual XOR fold (JS). Do not
> reimplement the compare with `==`.

> **Use the raw body**, not a re-serialized JSON. Re-serializing
> reorders keys and inserts whitespace, which the signature will not
> match.

---

## Example 1 — Python (Flask)

```python
from flask import Flask, request, abort
from webhook_verifier_sdk import verify_signature

app = Flask(__name__)
SECRET = "REPLACE_WITH_THE_SECRET_RUNMYCAMPUS_GAVE_YOU_ONCE_AT_SUBSCRIPTION_TIME"

@app.route("/hooks/runmycampus", methods=["POST"])
def receive_webhook():
    raw_body = request.get_data()  # raw bytes — do NOT use request.json
    header = request.headers.get("X-RunMyCampus-Signature", "")
    if not verify_signature(raw_body, header, SECRET):
        abort(401)
    # Body is now trustworthy. Parse JSON for routing.
    event = request.get_json(force=True)
    # ... process event ...
    return "", 204
```

Operational notes:

* `request.get_data()` returns the body bytes exactly as the platform
  signed them. `request.get_json()` decodes UTF-8 and reparses, which
  loses the canonical byte form.
* Return any 2xx response within 15 seconds. Slower receivers will be
  retried per the platform's exponential schedule (1m → 5m → 30m → 2h
  → 12h → 24h → exhausted).
* Idempotency: the same delivery may arrive more than once after a
  transient failure. Key your handler on the `X-Migration-Cloud-Delivery`
  header to dedupe.

---

## Example 2 — Node.js (Express)

```js
const express = require("express");
const { verifySignature } = require("./runmycampus_webhook_verifier");

const app = express();
const SECRET = process.env.WEBHOOK_SECRET; // received once at subscription time

app.post(
  "/hooks/runmycampus",
  // CRITICAL: capture the raw body, not the parsed JSON.
  express.raw({ type: "*/*", limit: "5mb" }),
  async (req, res) => {
    const header = req.headers["x-runmycampus-signature"];
    const ok = await verifySignature(req.body, header, SECRET);
    if (!ok) return res.status(401).end();

    let event;
    try {
      event = JSON.parse(req.body.toString("utf8"));
    } catch (_) {
      return res.status(400).end();
    }
    // ... process event ...
    res.status(204).end();
  },
);

app.listen(8080);
```

Operational notes:

* `express.raw()` MUST come before any `express.json()` body parser
  for this route — otherwise you receive the decoded JSON object and
  cannot recover the bytes the platform signed.
* The header name normalizes to lowercase under Node — both
  `req.headers["x-runmycampus-signature"]` and the canonical-case
  string are accepted by the SDK.

---

## Example 3 — Raw HTTP (no framework)

If you operate behind a thin reverse proxy or in an edge runtime
without Express/Flask, the signature verification reduces to:

1. Read the raw request body as bytes — `n` bytes per `Content-Length`.
2. Read the `X-RunMyCampus-Signature` header.
3. Compute `HMAC-SHA256(secret, body)` and compare in constant time
   against the hex after `sha256=`.

A minimal stdlib Python receiver:

```python
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = b"REPLACE_WITH_THE_SECRET_RUNMYCAMPUS_GAVE_YOU"

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        header = (self.headers.get("X-RunMyCampus-Signature") or "").strip()
        if not header.startswith("sha256="):
            self.send_response(401); self.end_headers(); return
        expected = "sha256=" + hmac.new(
            SECRET, body, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, header):
            self.send_response(401); self.end_headers(); return
        # body trustworthy — handle and respond
        self.send_response(204); self.end_headers()

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
```

A minimal Node `http` receiver:

```js
const http = require("http");
const crypto = require("crypto");

const SECRET = process.env.WEBHOOK_SECRET;

http.createServer((req, res) => {
  if (req.method !== "POST") { res.statusCode = 405; return res.end(); }
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const body = Buffer.concat(chunks);
    const header = String(req.headers["x-runmycampus-signature"] || "").trim();
    if (!header.startsWith("sha256=")) {
      res.statusCode = 401; return res.end();
    }
    const expected = "sha256=" + crypto
      .createHmac("sha256", SECRET)
      .update(body)
      .digest("hex");
    const a = Buffer.from(expected, "utf8");
    const b = Buffer.from(header, "utf8");
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
      res.statusCode = 401; return res.end();
    }
    res.statusCode = 204; res.end();
  });
}).listen(8080);
```

---

## Frequently Asked Questions

**Q. The signature never matches — what's wrong?**
The most common cause is re-serializing the JSON before verifying.
Verify the **raw bytes** of the request body. The platform signs the
canonical-JSON encoding (sorted keys, no whitespace), and your HTTP
framework's JSON parser will reorder keys or insert spaces by default.

**Q. Why constant-time compare?**
A `==` comparison short-circuits on the first mismatched byte, leaking
the prefix-match length through timing. A constant-time compare always
touches every byte. This is industry standard (Stripe, GitHub, Twilio,
Anthropic — every webhook SDK does this).

**Q. Can I trust the `X-RunMyCampus-Event` header?**

(The legacy `X-Migration-Cloud-Event` is the same value, byte-identical,
during the 2026-05-18 → 2026-08-18 migration window — see
[`docs/WEBHOOK_HEADER_MIGRATION_2026.md`](../../../../docs/WEBHOOK_HEADER_MIGRATION_2026.md).)

**Q. Can I trust the `X-Migration-Cloud-Event` header?**
Only after a successful signature check. Until the body is verified,
treat every header (including the event type and delivery id) as
untrusted.

**Q. What if the secret leaks?**
Open the operator console at `/super/migration/operator/webhooks/`,
deactivate the subscription, and re-register. The platform never
re-displays a secret after the create response; rotation = revoke +
re-subscribe.

**Q. Are signatures versioned?**
Yes. The `sha256=` prefix identifies the digest algorithm. A future
`sha512=` rollout will be announced ≥90 days in advance and old
verifiers will fail closed (return `false`) rather than silently
accepting.
