# §0.1.5 evidence register (code + test OR runbook)

**Rule:** SOT checkbox [x] only when this row lists **Test** (path) and/or **Runbook** (path). Clever/ClassLink native excluded (backlog).

| Wave | Item | Test / Runbook | Met |
|------|------|----------------|-----|
| 1 | Payment webhook CSRF + security | `apps/finance/tests/test_sot_0155_payment_webhook_posture.py` + `views_payments.WebhookSecurityValidator` | Y |
| 1 | Secrets not in templates | `scripts/lint_secret_exposure.py` (pre_deploy) + `apps/siteconfig/tests/test_ai_copilot_context.py` | Y |
| 1 | Tenant isolation | `docs/TENANT_ISOLATION_SECURITY_REPORT.md` + `apps/schools/tests/` tenant tests where present | Y |
| 1 | Migration rollback UI | `super_migration_cloud` + rollback form; `docs/architecture/phase8_migration_cloud_and_marketplaces.md` | Y |
| 1 | External API fallback | `docs/WAVE_EXECUTION_RUNBOOKS.md` | Y |
| 1 | Support access / audit | `docs/runbooks/SUPPORT_AND_IMPERSONATION_AUDIT.md` | Y |
| 1 | RPO/RTO / incident | `docs/RUNBOOK_STORAGE_BACKUP.md` + `docs/WAVE_EXECUTION_RUNBOOKS.md` | Y |
| 1 | Edge rate limit | `apps/api/tests/test_oneroster_views.py` throttle 429 + `WEBHOOK_RATE_LIMIT` | Y |
| 2 | Internal API standards | `docs/INTERNAL_API_STANDARDS.md` + `apps/api/tests/test_internal_api_wave_smoke.py` | Y |
| 2 | REDUCE_APIS posture | `docs/REDUCE_APIS_SCALE_WORKFLOWS.md` + `apps/communication/tests/test_sot_0155_sms_fallback.py` | Y |
| 2 | Notification single path | `notification_service.send_sms` fallback + same test | Y |
| 2 | Provider inventory | `docs/architecture/provider_abstraction_audit.md` | Y |
| 2 | N19 events | `GET /api/internal/north-star/event-catalog/` + `apps/portal/tests/test_north_star_event_catalog.py` | Y |
| 2 | Internal API smoke | `test_internal_api_wave_smoke.py` | Y |
| 2 | Kong gateway plan | `docs/architecture/KONG_API_GATEWAY_PLAN.md` | Y |
| 3 | OSS spine | `docs/architecture/open_source_spine.md` | Y |
| 3 | Adapters | `provider_abstraction_audit.md` + COMPATIBILITY | Y |
| 3 | Supply chain | `docs/runbooks/SUPPLY_CHAIN_VERIFICATION.md` + requirements pins | Y |
| 3 | Temporal / durable | `docs/architecture/TEMPORAL_WORKFLOWS_PLAN.md` | Y |
| 3 | OpenSearch | `apps/api/tests/test_search_read_layer_helpers.py` + `storage_and_search.md` | Y |
| 3 | Degradation testing | `docs/architecture/DEGRADATION_LOAD_TEST_PLAN.md` | Y |
| 4 | Operational modules (transport, library, …) | **NOT MET** first-party — remain [ ] until modules or certified connectors ship | N |
| 4 | HR/payroll | `docs/runbooks/WAVE4_HR_PAYROLL_INTEGRATION_POSTURE.md` | Y* |
| 4 | Statutory | `docs/runbooks/WAVE4_STATUTORY_AND_TRANSCRIPTS_POSTURE.md` | Y* |
| 4 | Change management / rollover | `docs/runbooks/YEAR_ROLLOVER_AND_MASS_REENROLL.md` + existing rollover views | Y* |
| 4 | Partner + services | `MIGRATION_CSV_DIFF` + Launch checklists + WAVE_EXECUTION | Y |
| 4 | Full ops spine (visitor, facilities, POS) | `docs/runbooks/WAVE4_EXTENDED_OPS_POSTURE.md` | Y* |
| 4 | Teaching depth | `docs/runbooks/WAVE4_TEACHING_DEPTH_POSTURE.md` | Y* |
| 4 | Research/grants HE | `docs/runbooks/WAVE4_HE_RESEARCH_GRANTS_POSTURE.md` | Y* |
| 4 | Community / TVET | people + analytics stubs; `docs/runbooks/WAVE4_COMMUNITY_ECOSYSTEM_POSTURE.md` | Y* |
| 4 | Geography packs | `WAVE4_REGION_PACK_ROADMAP.md` | Y |
| 4 | Statutory product UK | ReportPack / moe_presets — `docs/runbooks/WAVE4_UK_STATUTORY_PRODUCT_POSTURE.md` | Y* |
| 4 | Advancement Phase 2 CRUD | **PARTIAL** — models exist; full CRUD UX [ ] | N |
| 4 | HE months | `HE_MONTHS_NOT_YEARS_GOLIVE.md` | Y |
| 4 | Ministry/district | `MINISTRY_ERP_INTEGRATION_PATTERNS.md` + government aggregates API | Y |
| 5 | Competitor playbooks | `docs/MIGRATION_CSV_DIFF_RUNBOOK.md` + `docs/runbooks/COMPETITOR_MIGRATION_PLAYBOOK_TEMPLATE.md` | Y* |
| 5 | Pre-built packs | MigrationProfile registry + `seed_migration_profiles` — full validation reports [ ] | N |
| 5 | Automated diff schedule | `MIGRATION_SCHEDULED_PARITY_TICK.md` + Celery + `test_sot_0155_migration_queue_and_schedule` | Y* |
| 5 | Rollback + exception queue | Exception queue UI + ack/waive + same tests | Y |
| 5 | API connectors CSV+OneRoster | OneRoster + interop hub | Y |
| 5 | MaaS SKU | `docs/runbooks/MIGRATION_AS_A_SERVICE_SKU.md` | Y* |
| 5 | Paper SKU | `docs/runbooks/PAPER_TO_DIGITAL_SKU.md` | Y* |
| 5 | Migration scorecard | Migration cloud table + demographic internal | Y |
| 5 | Legacy cleaner | `migration_legacy_data_audit` command | Y |
| 5 | Signed roster webhook | `oneroster_roster_webhook` + tests | Y |
| 6 | Phase 0–3 paper | `PAPER_TO_DIGITAL_SKU.md` | Y* |
| 6 | Named digitization journey | same + BUEA / PAYMENT_RECEIPT OCR refs | Y* |
| 6 | Mobile capture | **NOT MET** dedicated product | N |
| 6 | Partner SLA | WAVE_EXECUTION §6 | Y |
| 7 | Credential portability | `docs/runbooks/CREDENTIAL_PORTABILITY_AND_VC_ROADMAP.md` | Y* |
| 7 | AI infrastructure | AI gateway + governed endpoints; `docs/architecture/ai_tiered_ollama.md` | Y* |
| 7 | Interoperability | OneRoster + SCIM + event catalog | Y |
| 7 | Resilience & exit | `docs/runbooks/TENANT_EXPORT_AND_EXIT.md` | Y* |
| 7 | 100-year data | `docs/runbooks/DATA_RETENTION_AND_LEGAL_HOLD.md` | Y* |
| 7 | 100-year governance | packs + runtime; `docs/runbooks/PACK_AND_CONFIG_LONGEVITY.md` | Y* |
| 7 | Climate hooks | `/api/internal/br/climate-reporting-hooks/` | Y |
| 7 | Demographics | `/api/internal/br/demographic-insights/` | Y |
| 8 | N19 event catalog | `apps/api/tests/test_north_star_event_catalog_sot0155.py` | Y* |
| 8 | N25 migration playbooks | `MIGRATION_CSV_DIFF_RUNBOOK.md` + `WAVE_EXECUTION_RUNBOOKS.md` | Y* |
| 8 | N29 choose region signup | `apps/schools/tests/test_sot_0155_signup_region_deep_link.py` | Y |
| 8 | N1–N8, N9–N18, N20–N23, N27–N28, N24, N26, Foundation | `docs/runbooks/N1_N29_WAVE8_VERIFICATION_POSTURE.md` — **partial / not met** | * |

\* *Runbook documents verification posture / roadmap; not full product completion.*

**Serious (§0.1.5 tail):** OpenAPI — `OPENAPI_SCHEMA_ACCESS.md` + `test_sot_0155_openapi_schema_access.py`; check --deploy — `.github/workflows/smoke.yml`; Custom 404/500 — `PhaseHErrorHandlersTests` + `test_phase10_control_plane_verification.py`; pip-audit — `smoke.yml`; year rollover — compendium; SLO/health — `SLO_OBSERVABILITY_TARGETS.md` + `/health/` `/ready/`.

**Wave 8 remainder:** See `docs/runbooks/N1_N29_WAVE8_VERIFICATION_POSTURE.md`. Items without automated proof remain **[ ]** in SOT.
