# Program work not closed by a single code drop

Canonical checklist: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` (§398+ Wave 8, §467 honest status).

| Area | Why it is multi-sprint |
|------|-------------------------|
| **SOC 2 / N16** | Requires control design, evidence collection, auditor engagement, and attestation—not implementable as one PR. |
| **N1–N29 full bars** | N10 (perf CI gates), N17 (dependency graph UI depth), N18 (sandbox/DX), N20–N24, N28 analytics depth, etc. are product + infra programs. |
| **First-party ops (Wave 4)** | New operational surfaces and ownership, not only URL wiring. |
| **SiteSettings split** | Large refactor; needs migration plan and regression matrix. |
| **DoesNotExist sweep** | Ongoing hardening across hundreds of views; use typed exceptions per §2.4. |
| **csrf_exempt cleanup** | Each endpoint needs contract review (webhooks, SCIM, SAML, GraphQL). Allowlist: `scripts/allowlists/csrf_exempt_allowlist.json`. |

**Closed in-repo when this doc is added:** Studio rail tile URL audit (all targets in `deep_links._PATHS`, per-tile resolution, tests). See `STUDIO_RAIL_CONTROL_PLANE_URLS.md`.
