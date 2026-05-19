# runmycampus-webhook-verifier (Python)

Official Python verifier for **RunMyCampus Migration Cloud** webhook signatures.

* **Stdlib only.** Zero third-party runtime dependencies. Works in
  air-gapped / locked-down environments.
* **Constant-time HMAC compare** via `hmac.compare_digest`.
* **Replay defense** via optional clock-skew window on
  `X-RunMyCampus-Timestamp`.
* **Byte-for-byte parity** with the [`@runmycampus/webhook-verifier`
  JavaScript twin](../runmycampus-webhook-verifier-js) — verified in
  CI against a shared fixture file.
* **Python 3.8+**, CPython.

## Install

```bash
pip install runmycampus-webhook-verifier
```

## Quickstart

```python
from runmycampus_webhook_verifier import verify_signature

ok = verify_signature(
    body=raw_request_body_bytes,
    signature_header=request.headers.get("X-RunMyCampus-Signature"),
    secret="whsec_REPLACE_WITH_YOUR_SECRET",
)
if not ok:
    return 401, "unauthorized"
# body is now trustworthy; parse + dispatch
```

### Critical rules

1. **Pass the raw bytes** the platform signed. Do NOT re-serialize the
   JSON or change key ordering — your framework's JSON parser will
   reorder keys and insert whitespace, breaking the signature.
2. **Treat the secret as opaque material.** Never log it, never embed
   it in code, never echo it in error messages. Load it from a secret
   manager / env var.
3. **Always use constant-time compare.** This package does so
   internally via `hmac.compare_digest`. Don't reimplement.

## Framework examples

### Flask

```python
from flask import Flask, request, abort
from runmycampus_webhook_verifier import verify_signature

app = Flask(__name__)
SECRET = os.environ["RMC_WEBHOOK_SECRET"]

@app.route("/hooks/runmycampus", methods=["POST"])
def receive():
    raw = request.get_data()  # raw bytes — do NOT use request.json
    if not verify_signature(
        raw,
        request.headers.get("X-RunMyCampus-Signature"),
        SECRET,
        timestamp_header=request.headers.get("X-RunMyCampus-Timestamp"),
    ):
        abort(401)
    event = request.get_json(force=True)
    # ... handle event ...
    return "", 204
```

### Django

```python
import os
import json
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from runmycampus_webhook_verifier import verify_signature

SECRET = os.environ["RMC_WEBHOOK_SECRET"]

@csrf_exempt
def runmycampus_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    if not verify_signature(
        request.body,
        request.META.get("HTTP_X_RUNMYCAMPUS_SIGNATURE"),
        SECRET,
        timestamp_header=request.META.get("HTTP_X_RUNMYCAMPUS_TIMESTAMP"),
    ):
        return HttpResponseForbidden()
    event = json.loads(request.body.decode("utf-8"))
    # ... handle event ...
    return HttpResponse(status=204)
```

### FastAPI

```python
import os
from fastapi import FastAPI, Header, HTTPException, Request
from runmycampus_webhook_verifier import verify_signature

app = FastAPI()
SECRET = os.environ["RMC_WEBHOOK_SECRET"]

@app.post("/hooks/runmycampus")
async def receive(
    request: Request,
    x_runmycampus_signature: str = Header(None),
    x_runmycampus_timestamp: str = Header(None),
):
    body = await request.body()
    if not verify_signature(
        body, x_runmycampus_signature, SECRET,
        timestamp_header=x_runmycampus_timestamp,
    ):
        raise HTTPException(status_code=401)
    event = await request.json()
    # ... handle event ...
    return {"ok": True}
```

## Strict mode (typed errors)

For deeper logging / metrics — without leaking secret material — use
the strict variant:

```python
from runmycampus_webhook_verifier import (
    verify_signature_strict,
    MissingHeaderError, BadSignatureError,
    ClockSkewError, UnsupportedAlgorithmError,
)

try:
    verify_signature_strict(
        body,
        request.headers.get("X-RunMyCampus-Signature"),
        SECRET,
        timestamp_header=request.headers.get("X-RunMyCampus-Timestamp"),
    )
except MissingHeaderError:
    log.warning("webhook missing signature header")
    abort(401)
except UnsupportedAlgorithmError:
    log.error("webhook signature algorithm not supported by this verifier version")
    abort(400)
except BadSignatureError:
    log.warning("webhook signature mismatch")
    abort(401)
except ClockSkewError as e:
    log.warning("webhook timestamp outside tolerance skew_seconds=%s", e.skew_seconds)
    abort(401)
```

All exceptions derive from `VerificationError`, so one `except` catches them all.

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
* No whitespace between tokens (separators `(",", ":")`).
* UTF-8 output; non-ASCII characters emitted literally (not
  `\uXXXX`-escaped).
* `NaN` / `Infinity` / `-Infinity` are NOT representable — these
  raise `ValueError`.

```python
from runmycampus_webhook_verifier import canonicalize
canonical_bytes = canonicalize({"b": 2, "a": 1})
# => b'{"a":1,"b":2}'
```

This package's `canonicalize()` is **byte-for-byte identical** to the
JavaScript twin (`@runmycampus/webhook-verifier`). Parity is verified
in CI against a shared `canonical-cases.json` fixture.

## SemVer policy

* `0.x.y` — pre-1.0 development. **Breaking changes are possible in
  any `0.y` bump.** We will avoid them; we will not promise they're
  impossible.
* `1.0.0` — cut once the API has been stable for 90 days without
  breaking changes.
* `1.x.y` onward — strict SemVer. Breaking changes only in major
  bumps.

The signature **wire format** (`sha256=<hex>` + canonical-JSON body)
is versioned separately via the `X-RunMyCampus-Version` header and is
NOT bound to this package's version.

## Security

Report vulnerabilities to `security@runmycampus.com`. Please do not
file public GitHub issues for security reports.

This package never logs secret material. If you find a code path that
might leak secret bytes (HMAC key, signature value before verification,
raw header containing the signature) — that's a bug. Please report it.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

## Changelog

### 0.1.0 — 2026-05-18

* Initial release. Extracted from the vendored
  `apps/migration_cloud/api/webhook_verifier_sdk.py` shipped in
  RunMyCampus v3.33.0.
* Adds typed-exception strict-mode entry point
  (`verify_signature_strict`).
* Adds optional clock-skew enforcement via `timestamp_header`.
* Adds exported canonical-JSON serializer (`canonicalize`) with
  byte-for-byte parity with the JS twin.
