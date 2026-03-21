# Developer public API (§0.3 Pillar 2 / 4)

| Surface | URL / path |
|---------|------------|
| **Discovery manifest** | `GET /api/v1/manifest.json` — OneRoster base, health, LTI JWKS hint, webhook idempotency policy. |
| **API Center (public page)** | `GET /developers/api-docs/` — Links to manifest, OpenAPI note, sandbox; marketing base template. |
| **OpenAPI (staff)** | `GET /api/schema/` — JWT or session as configured. |
| **Sandbox** | Site config → **App sandbox** (`/siteconfig/app-sandbox/`) for marketplace install testing. |
| **Auth** | Tenant JWT: `POST /api/auth/token/`; OneRoster: Bearer per school integration. |

Versioning: non-breaking additive changes without bump; breaking changes per manifest policy.

## Webhooks (inbound)

- **Finance / payments:** HMAC-signed POST; idempotency — see [WEBHOOK_DEAD_LETTER.md](WEBHOOK_DEAD_LETTER.md) and manifest `webhook` policy in `GET /api/v1/manifest.json`.
- **OneRoster roster (district):** `POST /api/oneroster/v1p1/roster-webhook` — signed payload; [ONEROSTER_ROSTER_WEBHOOK.md](ONEROSTER_ROSTER_WEBHOOK.md).
- **Outbound** integrations: use `X-Webhook-Idempotency-Key` where documented per adapter.

## OpenAPI & schema

- **Staff/authenticated:** `GET /api/schema/` (drf-spectacular or project default).
- **Contract tests:** `apps/api/tests/test_api_v1_route_contract.py`, `test_sot_0155_openapi_schema_access` (see runbooks).

## Rate limits (429)

- Prefer the **`Retry-After`** response header (seconds).
- JSON APIs (OneRoster, EdFi stubs, CEDS, JWT auth, interop discovery, etc.) often include:
  - `message` — operator-facing guidance
  - `retry_after` — integer seconds (mirror of header where present)
- **SCIM 2.0** returns SCIM Error `detail` plus `Retry-After`; do not assume non-SCIM JSON fields on SCIM paths.
