# Developer public API (§0.3 Pillar 2 / 4)

| Surface | URL / path |
|---------|------------|
| **Discovery manifest** | `GET /api/v1/manifest.json` — OneRoster base, health, LTI JWKS hint, webhook idempotency policy. |
| **API Center (public page)** | `GET /developers/api-docs/` — Links to manifest, OpenAPI note, sandbox; marketing base template. |
| **OpenAPI (staff)** | `GET /api/schema/` — JWT or session as configured. |
| **Sandbox** | Site config → **App sandbox** (`/siteconfig/app-sandbox/`) for marketplace install testing. |
| **Auth** | Tenant JWT: `POST /api/auth/token/`; OneRoster: Bearer per school integration. |

Versioning: non-breaking additive changes without bump; breaking changes per manifest policy.
