# EdOS AI, Help Center, FAQ, Forum, and Product Voice OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_AI_HELP_PRODUCT_VOICE_OS_READY`

## Scope

Refactors AI (apicenter) + feedback + Help Center + FAQ/KB + customersuccess + observability. One safe AI gateway + workflow-aware assistant + evidence-backed KB/FAQ generation + support ticket enrichment + product voice loop + friction analysis + tenant-safe help + operator-only code/topology oracle + missing context fallback (DATA DEFAULTER) + missing feature fallback (FEATURE CODESPACE DISCONNECT) + no raw PII prompts + review-gated publishing + AI auto-migration support + AI data cleanup support + AI local-first template recommendations + AI homework support guardrails + no generic answers + no tenant-visible platform internals.

## Sections

### AI safety (baseline 0 enforced)

- One gateway — apicenter.services.ai_helpers; gateway boundary scanner baseline 0 (app code MUST NOT import services.ai_gateway directly)
- Tenant-safe context — AIContext.tenant_redaction_policy applied before every call
- No raw PII prompts — apicenter.redact_pii() at gateway
- Missing context fallback — return DATA DEFAULTER token, not hallucinated answer
- Missing feature fallback — return FEATURE CODESPACE DISCONNECT token
- Review-gated KB publishing — apps.feedback voice-of-customer router gates publication
- Operator-only code/topology oracle — operator-only scope; tenant never sees platform internals
- AI auto-migration support — apps.migration_cloud (Phase 10)
- AI data cleanup support — apps.migration_cloud visual_data_cleanup
- AI local-first template recommendations — apps.brand_experience.template_ai_recommender (registry-validated, no stereotyping)
- AI homework support guardrails — apps.academics.homework_ai_guardrails (no answer leakage)
- No generic answers — apicenter rejects empty-context prompts

## Repo evidence (anchor paths)

- `services/ai_helpers.py`
- `apps/apicenter/`
- `apps/feedback/`
- `apps/customersuccess/`
- `apps/migration_cloud/`
- `apps/brand_experience/template_ai_recommender.py`
- `apps/academics/`

## Tests

- `apps/apicenter/tests/test_edos_ai_gateway_boundary_v2.py`
- `apps/apicenter/tests/test_edos_ai_missing_context_fallback_v2.py`
- `apps/feedback/tests/test_edos_kb_review_gated_publish.py`

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
