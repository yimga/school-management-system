# Global-Local Ed-OS Gap Closure — Code-Truth Inventory (Phase 0)

**Batch:** 1488 · **SW:** `sms-v3.85.0-global-local-gap-closure-2026-05-24` · **Generated:** 2026-05-24

**Verdict:** INVENTORY_COMPLETE_REPO_SCOPE

## Platform Floor at Open

| Field | Value |
|---|---|
| Current SW | `sms-v3.84.7-theme-platform-wide-dual-plane-2026-05-24` |
| Last shipped batch | 1487 |
| Last shipped verdict | Theme experience final platform sweep |
| GEOS matrix overall | repo 100% / live 100% / composite 100% |
| GEOS pillars | 8 |

External blockers tracked at open (preserved, not erased by this batch):
- live Stripe/Paystack settlement
- Render deploy SHA refresh after each release
- SOC2 auditor PDF (counsel/auditor turnaround)
- production `live_cloud` AI probe with LITELLM keys
- Multi-corridor pilot ingestion (Lane 2 register `sfdp_lane2_pilot_corridors`)
- PSP live settlement reconciliation (counsel + KYC pending)
- MAA v2.0 promotion (counsel signoff PDF pending)
- FACTS/Skyward write-path unblock (CFAA/DMCA counsel docket)

## App Inventory

**51 apps present** in `apps/` — every domain named by the 23-phase audit is represented except `dportal` (deprecated; never created in repo). Full list captured in JSON sibling.

## PWA / Mobile

| Item | State |
|---|---|
| Service worker | present at [service-worker.js](../../static/js/service-worker.js) (~131 KB) |
| Registration | [rmc-service-worker-registration.js](../../static/js/rmc-service-worker-registration.js) |
| Manifest per shell | all 4 shells emit manifests |
| CI gate | `scan_pwa_manifest_coverage.py` baseline 0 |
| Offline queue client | present (portal forms `data-rmc-offline-form`) |
| Offline conflicts view | `/portal/offline/conflicts/` |
| **Native iOS/Android** | **ZERO** (PWA-first; companion siblings are operator tooling) |

## Local-First Template Marketplace

| Item | Value |
|---|---|
| Templates shipped | 98 (50 local-first subset) |
| Memory source | `project_local_first_template_marketplace_waves_bcde_v3_64_0_2026_05_23.md` (batches 1400/1401) |
| Registry | [pack_contract.py](../../apps/platform_runtime/pack_contract.py) `pack_type="experience_template"` |
| Profile registry | [local_experience_profiles.py](../../apps/siteconfig/local_experience_profiles.py) — 25 profiles |
| AI recommender | [template_ai_recommender.py](../../apps/brand_experience/template_ai_recommender.py) routes via `services.ai_helpers` only |

## Security Surface (Real Findings)

| Item | Count | Notes |
|---|---|---|
| `@csrf_exempt` real decorators | **13** | All are recognized integration boundaries (SAML, SCIM, webhooks, telemetry, CSP report, GraphQL gateway). Earlier audit count of 87 was inflated by docstring/comment mentions. |
| `AllowAny` permission classes | **4** | All are public catalog/docs endpoints (marketplace catalog, webhook catalog list, migration API docs, schools public API). No tenant write surfaces under AllowAny. |
| GraphQL files | 3 | Active endpoint at [graphql_view.py](../../config/graphql_view.py) — Phase 2 must verify introspection/depth/auth/tenant scoping. |

CSRF-exempt files (all to be classified in Phase 2):
- [accounts/views_saml.py](../../apps/accounts/views_saml.py) — SAML ACS
- [api/oneroster_roster_webhook.py](../../apps/api/oneroster_roster_webhook.py)
- [api/scim_views.py](../../apps/api/scim_views.py)
- [billing/api_views.py](../../apps/billing/api_views.py)
- [finance/views_payments.py](../../apps/finance/views_payments.py)
- [integrations_marketplace/webhooks.py](../../apps/integrations_marketplace/webhooks.py)
- [observability/views_friction.py](../../apps/observability/views_friction.py)
- [orchestration/api.py](../../apps/orchestration/api.py)
- [platform_runtime/views_rum.py](../../apps/platform_runtime/views_rum.py)
- [portal/views_office.py](../../apps/portal/views_office.py)
- [schools/section8_views.py](../../apps/schools/section8_views.py)
- [security/csp_report_view.py](../../apps/security/csp_report_view.py)
- [config/graphql_view.py](../../config/graphql_view.py)

## AI Gateway Boundary

App code MUST NOT import `services.ai_gateway` directly; must use `services.ai_helpers`. Enforced by `scripts/scan_ai_gateway_boundary.py` (CI baseline 0). Compliance: honest.

## Verifier Scripts Present
- [verify_greatest_education_os_matrix.py](../../scripts/verify_greatest_education_os_matrix.py)
- [verify_doc_plan_density_discipline.py](../../scripts/verify_doc_plan_density_discipline.py)
- [verify_sot_pillar_evidence.py](../../scripts/verify_sot_pillar_evidence.py)
- [verify_sot_batch_id_uniqueness.py](../../scripts/verify_sot_batch_id_uniqueness.py)
- [run_northstar_audit.py](../../scripts/run_northstar_audit.py)
- [run_kill_test.py](../../scripts/run_kill_test.py)

## Repo-Side Gaps to Close in Batch 1488
1. **Phase 1:** Extend GEOS matrix scoring with `pwa_pct` + `native_deferred_pct` dimensions
2. **Phase 2:** Write `security_exception_register` documenting all 13 CSRF-exempt routes + 4 AllowAny endpoints + GraphQL view
3. **Phases 3-17:** Write 15 audit artifact pairs documenting repo-scope completeness and external blockers per gap category
4. **Phase 22:** Update SOT with batch 1488, SW v3.85.0, honest verdict

## Native Mobile Stance
**ZERO native iOS/Android code in repo.** PWA-first stance fully preserved. Companion siblings (Tauri desktop, Docker, MV3 extension) are operator-side tooling — not consumer mobile apps. Audit requirement satisfied.

## Out of Scope (Follow-on Session)
Prompt 2 Education OS next-realm re-architecture deferred per its own sequencing rule.
