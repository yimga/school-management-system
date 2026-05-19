# @runmycampus/webhook-verifier (JavaScript / TypeScript)

Official JS verifier for **RunMyCampus Migration Cloud** webhook signatures.

* **Zero runtime dependencies.** Bundle is one self-contained file.
* **Dual-runtime:** WebCrypto (browsers, Node 19+, Edge runtimes) with a
  `node:crypto` fallback for Node 16–18.
* **Constant-time HMAC compare** via Node `crypto.timingSafeEqual` where
  available, manual XOR fold elsewhere.
* **Replay defense** via optional clock-skew window on
  `X-RunMyCampus-Timestamp`.
* **Byte-for-byte parity** with the Python twin
  [`runmycampus-webhook-verifier`](../runmycampus-webhook-verifier-py) —
  verified in CI against a shared fixture file.
* **Dual ESM + CommonJS** build, `.d.ts` typings shipped.
* **TypeScript 5.x** sources; compiles to ES2020.

## Install

```bash
npm install @runmycampus/webhook-verifier
```

```bash
pnpm add @runmycampus/webhook-verifier
```

```bash
yarn add @runmycampus/webhook-verifier
```

## Quickstart

```ts
import { verifySignature } from "@runmycampus/webhook-verifier";

const ok = await verifySignature(
  rawBodyBytes,
  request.headers["x-runmycampus-signature"],
  process.env.RMC_WEBHOOK_SECRET!,
);
if (!ok) return reply.code(401).send();
// body is now trustworthy
```

### Critical rules

1. **Pass the raw bytes** the platform signed. Do NOT re-serialize the
   JSON — your framework's JSON parser will reorder keys and insert
   whitespace, breaking the signature.
2. **Treat the secret as opaque material.** Never log it, never embed
   it in code, never echo it in error messages.
3. **Always use constant-time compare.** This package does so
   internally. Don't roll your own.

## Framework examples

### Express

```ts
import express from "express";
import { verifySignature } from "@runmycampus/webhook-verifier";

const app = express();
const SECRET = process.env.RMC_WEBHOOK_SECRET!;

app.post(
  "/hooks/runmycampus",
  // CRITICAL: capture the raw body, NOT parsed JSON.
  express.raw({ type: "*/*", limit: "5mb" }),
  async (req, res) => {
    const ok = await verifySignature(
      req.body,
      req.headers["x-runmycampus-signature"] as string | undefined,
      SECRET,
      {
        timestampHeader: req.headers["x-runmycampus-timestamp"] as string | undefined,
      },
    );
    if (!ok) return res.status(401).end();
    const event = JSON.parse(req.body.toString("utf8"));
    // ... handle event ...
    res.status(204).end();
  },
);
```

### Fastify

```ts
import Fastify from "fastify";
import { verifySignature } from "@runmycampus/webhook-verifier";

const app = Fastify();
const SECRET = process.env.RMC_WEBHOOK_SECRET!;

// Capture raw body for signature verification.
app.addContentTypeParser(
  "application/json",
  { parseAs: "buffer" },
  (_req, body, done) => done(null, body),
);

app.post("/hooks/runmycampus", async (req, reply) => {
  const ok = await verifySignature(
    req.body as Buffer,
    req.headers["x-runmycampus-signature"] as string | undefined,
    SECRET,
    {
      timestampHeader: req.headers["x-runmycampus-timestamp"] as string | undefined,
    },
  );
  if (!ok) return reply.code(401).send();
  const event = JSON.parse((req.body as Buffer).toString("utf8"));
  // ... handle event ...
  return reply.code(204).send();
});
```

### Next.js (Edge runtime)

```ts
// app/api/webhooks/runmycampus/route.ts
import { verifySignature } from "@runmycampus/webhook-verifier";

export const runtime = "edge";

export async function POST(req: Request) {
  const body = new Uint8Array(await req.arrayBuffer());
  const ok = await verifySignature(
    body,
    req.headers.get("x-runmycampus-signature"),
    process.env.RMC_WEBHOOK_SECRET!,
    {
      timestampHeader: req.headers.get("x-runmycampus-timestamp"),
    },
  );
  if (!ok) return new Response(null, { status: 401 });
  const event = JSON.parse(new TextDecoder().decode(body));
  // ... handle event ...
  return new Response(null, { status: 204 });
}
```

## Strict mode (typed errors)

```ts
import {
  verifySignatureStrict,
  MissingHeaderError,
  BadSignatureError,
  ClockSkewError,
  UnsupportedAlgorithmError,
  VerificationError,
} from "@runmycampus/webhook-verifier";

try {
  await verifySignatureStrict(body, header, SECRET, { timestampHeader: ts });
} catch (e) {
  if (e instanceof MissingHeaderError)        log.warn("missing signature header");
  else if (e instanceof UnsupportedAlgorithmError) log.error("verifier outdated");
  else if (e instanceof BadSignatureError)    log.warn("signature mismatch");
  else if (e instanceof ClockSkewError)       log.warn("skew", { skew: e.skewSeconds });
  else if (e instanceof VerificationError)    log.warn("unknown verification error");
  return reply.code(401).send();
}
```

## Browser usage

The verifier works in browsers (WebCrypto). However, **secrets should
not live in the browser** — if the verifier secret is exposed to
untrusted code, an attacker can sign payloads that look authentic to
your server.

**Recommended:** run verification on a server / edge function. Use the
browser as a thin proxy.

If you have a legitimate browser use-case (e.g. verifying a server's
signed broadcast inside a trusted-context PWA), import normally:

```ts
import { verifySignature } from "@runmycampus/webhook-verifier";

const ok = await verifySignature(bodyBytes, header, sessionScopedSecret);
```

## Header reference

| Header | Meaning |
|---|---|
| `X-RunMyCampus-Signature` | `sha256=<lowercase-hex-digest>` — REQUIRED |
| `X-RunMyCampus-Timestamp` | Unix seconds — OPTIONAL but recommended for replay defense |
| `X-RunMyCampus-Event` | Dotted event class (e.g. `migration.bundle.completed`) |
| `X-RunMyCampus-Version` | Signature format version (`v1` today) |

## Canonical JSON

The platform signs the **canonical JSON** form of the payload:

* Object keys sorted lexicographically (UTF-16 code-unit order).
* No whitespace between tokens.
* UTF-8 output; non-ASCII characters emitted literally.
* `NaN` / `Infinity` / `-Infinity` are NOT representable — throw.

```ts
import { canonicalize, canonicalizeToString } from "@runmycampus/webhook-verifier";

const bytes = canonicalize({ b: 2, a: 1 }); // Uint8Array
const text = canonicalizeToString({ b: 2, a: 1 });
// => '{"a":1,"b":2}'
```

This module's `canonicalize()` is **byte-for-byte identical** to the
Python twin (`runmycampus-webhook-verifier`). Parity is verified in CI
against a shared `canonical-cases.json` fixture.

## SemVer policy

* `0.x.y` — pre-1.0 development. **Breaking changes are possible in
  any `0.y` bump.** We will avoid them; we will not promise they're
  impossible.
* `1.0.0` — cut once the API has been stable for 90 days without
  breaking changes.
* `1.x.y` onward — strict SemVer. Breaking changes only in major
  bumps.

The signature **wire format** (`sha256=<hex>` + canonical-JSON body)
is versioned separately via the `X-RunMyCampus-Version` header.

## Security

Report vulnerabilities to `security@runmycampus.com`. Please do not
file public GitHub issues for security reports.

This package never logs secret material. If you find a code path that
might leak secret bytes — that's a bug. Please report it.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

## Changelog

### 0.1.0 — 2026-05-18

* Initial release. Extracted from the vendored
  `apps/migration_cloud/api/static/runmycampus_webhook_verifier.js`
  shipped in RunMyCampus v3.33.0.
* Adds typed-error strict-mode entry point (`verifySignatureStrict`).
* Adds optional clock-skew enforcement via `timestampHeader`.
* Adds exported canonical-JSON serializer (`canonicalize`) with
  byte-for-byte parity with the Python twin.
* TypeScript 5 sources, dual ESM + CJS output, `.d.ts` typings.
