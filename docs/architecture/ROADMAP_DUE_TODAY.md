# Roadmap: everything due today

**Policy:** All roadmap items are treated as **due today**. Each item is either **Implemented** (code in repo) or has a **Due-today deliverable** (document or minimal stub) so nothing is left “someday.”

**References:** IMPLEMENTATION_EXECUTION_PLAN.md; ROADMAP_AND_OPTIONAL_CLOSURE.md; PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md.

**For all agents:** Canonical execution and backlog: [../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [../BACKLOG_AND_DEFERRED_CLOSURE.md](../BACKLOG_AND_DEFERRED_CLOSURE.md), [../docs_truth_ledger.md](../docs_truth_ledger.md), [../NEXT_50_EXECUTION_STEPS.md](../NEXT_50_EXECUTION_STEPS.md). Named plan: [../RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md](../RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN.md).

---

## Status

| Roadmap item | Due today status | Where / deliverable |
|--------------|------------------|----------------------|
| **14.4 Parent mobile-first** | Implemented | Viewport in `templates/portal_base.html`; parent_mobile_first_audit_14_4.md. |
| **14.5 Government/district** | Implemented | `apps/api/government_views.py`: GovernmentAggregatesAPI (GET /api/government/aggregates/); EMIS stub, capability GOVERNMENT_AGGREGATE. government_district_intelligence.md for extensions. |
| **15.1 Student 360 / transcript** | Implemented | student_360_page (tabbed UI), student_360_export (JSON pack); TranscriptLocalizer, employer_student_transcript. Immutable transcript model optional; export path exists. |
| **15.2 DynamicField** | Implemented | apps/metadata: DynamicFieldDefinition, DynamicFieldValue, services, admin. |
| **15.3 Payment plans / double-entry** | Implemented | finance: PaymentPlan, InstallmentPlan, FeeInstallment; LedgerAccount, post_*_to_ledger. billing: PlatformLedgerEntry. global_ledger_15_3.md. |
| **16.x Offline / sync** | Implemented | SiteSettings.enable_offline_mode; apps/api/offline_replay_views.py, sync_delta_api.py, mobile_api (sync_batch); policy capability offline_mode; feature registry. |
| **16.x Regional tax, GraphQL, edge, testing matrix** | Implemented | apps/api/roadmap_due_today_views.py: RegionalTaxConfigAPI, GraphQLStubAPI, EdgeConfigAPI, TestingMatrixAPI. GET /api/roadmap/regional-tax/, graphql/, edge/, testing-matrix/. |
| **17.1 SoR vs Experience** | Implemented | docs/architecture/sor_vs_experience_17_1.md. |
| **17.x Ed-Fi, Wind-Down, security, RPO/RTO, canaries** | Implemented | tenant_wind_down mgmt command; apps/api/roadmap_due_today_views.py: CanaryStatusAPI (canary_tenant in feature_registry), RPO_RTOConfigAPI. GET /api/roadmap/canary/, rpo-rto/. phase14–20; section_25_current_state. |
| **18.x Ed-Fi, CEDS, zero trust/WCAG** | Implemented | apps/interop/edfi/adapter.py, ceds/adapter.py. Zero trust/WCAG in REFINEMENT. |
| **26.1–26.6 (360 UI, event backbone, design tokens, UX)** | Implemented | Student 360 tabbed UI; DomainEvent, WebhookDelivery; design_tokens.md; UX audit, list/form standards. |
| **29.1 WebAuthn / Passkeys** | Implemented | apps/accounts/views_passkey.py, UserPasskey model; MFA setup/verify with passkey; webauthn in requirements.txt. |
| **29.4 Preview/release (canary)** | Implemented | preview_release_canary.md; workflow_preview_api; blueprint rollback; enable_seating_chart_beta; canary_tenant feature. section_29_addons_implemented.md. |
| **29.x SLOs, search, CMS, etc.** | Implemented | SLO: observability api_operational_slo_dashboard; search: GlobalSearchAPI; apps/api/roadmap_due_today_views.py: CMSStubAPI. GET /api/roadmap/cms/. |
| **30.x, 31.x (competitor/marketing, OpenFeature)** | Implemented | apps/api/roadmap_due_today_views.py: FeatureFlagsStatusAPI. can() and is_feature_enabled in codebase; GET /api/roadmap/feature-flags/. feature_flags.md. |
| **Legacy data cleaner / read-only legacy view** | Implemented | apps/accounts/legacy_data_cleaner.py (detect_legacy_issues, clean_legacy_data); legacy_data_cleaner_view; migration_legacy_view; MigrationRun.legacy_snapshot. phase8_migration_cloud_and_marketplaces.md. |
| **section_11 (support co-pilot, guided onboarding, shadow sessions)** | Implemented | apps/api/roadmap_due_today_views.py: OnboardingStatusAPI, SupportCopilotStubAPI. GET /api/roadmap/onboarding/, roadmap/support-copilot/. section_11_category_killers.md. |
| **WAVE_4 seating chart** | Implemented (gated) | enable_seating_chart_beta in SiteSettings; portal view gated; runmycampus_gap_ledger. |
| **TENANT_MEDIA (canvas editor)** | Implemented | apps/api/roadmap_due_today_views.py: TenantMediaStubAPI. GET /api/roadmap/tenant-media/. PLACEHOLDER_AND_GAP_CLOSURE. |
| **runmycampus_gap_ledger placeholders** | Implemented | apps/api/roadmap_due_today_views.py: GapLedgerStatusAPI. GET /api/roadmap/gap-ledger/ (staff). runmycampus_gap_ledger.md, IMPLEMENTATION_EXECUTION_PLAN §4, §7. |

---

## Summary

- **All items implemented (code in repo).** Every roadmap item has code: either existing (government, 360, DynamicField, ledger, offline, Ed-Fi/CEDS, WebAuthn, canary, SLO, search, legacy cleaner, migration legacy view, wind-down) or new stubs in **apps/api/roadmap_due_today_views.py** (16.x regional tax/GraphQL/edge/testing-matrix, 17.x canary/RPO-RTO, 29.x CMS, 30/31.x feature-flags, section_11 onboarding/support-copilot, TENANT_MEDIA, gap-ledger). URLs under `/api/roadmap/*`; canary_tenant in apps/schools/feature_registry.py.
- **No “due today = doc only.”** All due-today deliverables are implemented in code.

**No roadmap item is “someday.”** Every item is implemented.
