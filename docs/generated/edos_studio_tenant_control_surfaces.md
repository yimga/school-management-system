# EdOS Studio OS and Tenant Studio Control Surfaces

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_STUDIO_CONTROL_SURFACES_READY`

## Scope

Studio OS becomes operator/tenant design-and-control environment. Tenant Studio becomes simple tenant operating cockpit. Both consume the existing 200x polish + experience template fold + Setup Studio onboarding step + Playwright spec at 3 breakpoints + audit/rollback wiring.

## Sections

### Studio OS surface (operator)

- Overview — apps.studio_os.dashboard with platform pulse snapshot
- Experience — apps.studio_os.experience_fold (templates + palettes + previews)
- Automation — apps.studio_os.automation_canvas (workflow builder, no-code rules)
- Output — apps.studio_os.output_panel (reports, exports, audit ledger)
- Launch — apps.studio_os.launch_checklist (school readiness, billing readiness, migration readiness)
- Control — apps.studio_os.control_plane (operator-only quota override, impersonation, audit)
- Live previews — Playwright spec at 390/768/1366 breakpoints (shipped batch 1401)
- No horizontal overflow — design-tokens responsive grid
- Operator/tenant mode — explicit mode flag; tenant cannot see operator surfaces
- Audit/rollback — apps.platform_runtime.pack_rollback wiring; every change emits audit event
- AI guidance — apicenter.ai_helpers operator-only oracle (tenant never sees platform internals)
- Template marketplace integration — 98 templates (75 + 23 local-first specialized)
- Local-first templates — 50 local-first + 25 LocalExperienceProfile registry
- PWA/offline preview posture — service-worker.js + tenant_cache_key

### Tenant Studio surface (tenant)

- Launch path — apps.setup_studio onboarding wizard with select_experience_template step
- Setup essentials — apps.setup_studio core_setup_checklist
- Readiness — apps.lifecycle SchoolLifecycleStage progression dashboard
- Migration — apps.migration_cloud entry point with visual data cleanup
- Templates — apps.brand_experience tenant template marketplace (operator-gated 404 on operator-only templates)
- Data quality — apps.migration_cloud + apps.evals data_quality_warnings
- Billing readiness — apps.billing readiness dashboard
- Help/feedback — apps.feedback voice-of-customer router
- AI guidance — apicenter.ai_helpers tenant-safe (DATA DEFAULTER / FEATURE CODESPACE DISCONNECT fallbacks)
- PWA install guidance — install prompt orchestrated by rmc-service-worker-registration.js
- Low-data mode — CountryRegistry.cockpit_payload.low_bandwidth_class
- Offline readiness labels — apps.platform_runtime.stale_banner

## Repo evidence (anchor paths)

- `apps/studio_os/`
- `apps/setup_studio/`
- `apps/brand_experience/`
- `apps/lifecycle/`
- `apps/migration_cloud/`
- `apps/billing/`
- `apps/feedback/`
- `services/ai_helpers.py`
- `static/js/rmc-service-worker-registration.js`

## Tests

- `apps/studio_os/tests/test_edos_operator_studio_control_v2.py`
- `apps/setup_studio/tests/test_edos_tenant_setup_essentials.py`
- `apps/lifecycle/tests/test_edos_readiness_progression.py`

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
