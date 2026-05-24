# EdOS Ecosystem, API, Marketplace, and Extension OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_ECOSYSTEM_EXTENSION_OS_READY`

## Scope

Refactors apicenter + api + integrations_marketplace + marketplace + interop + automation + orchestration. Open Educational Core API + API docs + REST/GraphQL safety + webhooks + developer portal + app install/uninstall + app permission scopes + app review workflow + revenue share readiness + partner sandbox + workflow builder + no-code rules + tenant extension boundaries + self-healing integration sandbox + integration schema drift detection + fallback version posture + API Center operator alerts.

## Sections

### Ecosystem primitives

- Open Educational Core API — apps.api REST surface + OpenAPI spec
- GraphQL safety — narrow schema, introspection disabled in prod, rate limit + Content-Type + method restriction, staff-gated resolvers (verified in Prompt 1 Phase 2)
- Webhooks — apps.integrations_marketplace webhook adapter with HMAC signature + replay window
- Developer portal — apps.api developer_portal_routes
- App install/uninstall — apps.integrations_marketplace.AppInstall + uninstall reverse hook
- App permission scopes — apps.security app_scope_registry per app
- App review workflow — apps.marketplace app_review_pipeline (operator-gated publish)
- Revenue share — apps.marketplace.template_monetization_manifest (counsel-pending Wave E+ blocker preserved)
- Partner sandbox — apps.marketplace.template_partner_manifest
- Workflow builder — apps.automation no-code workflow rules
- Tenant extension boundaries — tenant cannot install apps requiring operator-only scopes; gated
- Self-healing integration sandbox — apps.interop self_healing_integration_sandbox (schema drift detection + fallback version)
- API Center operator alerts — apps.observability + apps.apicenter alert_router

## Repo evidence (anchor paths)

- `apps/apicenter/`
- `apps/api/`
- `apps/integrations_marketplace/`
- `apps/marketplace/`
- `apps/interop/`
- `apps/automation/`
- `apps/orchestration/`

## Tests

- `apps/api/tests/test_edos_open_api_contract.py`
- `apps/integrations_marketplace/tests/test_edos_app_install_uninstall.py`
- `apps/interop/tests/test_edos_self_healing_sandbox.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.
