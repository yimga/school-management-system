# Wave 1–8 execution runbooks (SOT §0.1.5)

Single reference for operators and engineers executing the beyond-reach plan. **Clever/ClassLink native APIs** remain backlog (partnership). All other waves are in scope.

---

## Wave 1 — Critical risk & trust

| Topic | Runbook / action |
|-------|------------------|
| Payment webhooks | `apps/finance/views_payments.py` — `payment_provider_webhook` is `@csrf_exempt`; enforce provider signature + rate limit in gateway code. |
| Secrets in templates | `scripts/lint_secret_exposure.py` in CI; `apps/siteconfig/tests/test_ai_copilot_context.py` asserts no provider API key names in context. |
| Tenant isolation | `docs/TENANT_ISOLATION_SECURITY_REPORT.md`; every query uses `request.tenant_ctx` / RLS. |
| Migration rollback | Super **Migration cloud** → rollback queue; `MigrationRun.rollback_snapshot`; phase8 doc. |
| External API fallback | See **External provider fallback** below. |
| Support access audit | Log every support/impersonation data access; least privilege; trust center links. |
| RPO/RTO | `docs/RUNBOOK_STORAGE_BACKUP.md`; restore drill quarterly; `RPO_RTOConfigAPI` stub documents targets. |
| Edge rate limit | OneRoster throttled per IP (`throttle_ip_request`); extend WAF/CDN at deploy. |

## External provider fallback (Wave 1–2)

| Provider class | When unavailable | Platform behavior |
|----------------|------------------|-------------------|
| SMS (Twilio, etc.) | No config or API error | Email + in-app notification (`communication.notification_service`). |
| Payment gateway | Webhook delayed | Manual payment recording in Finance; idempotent webhook replay. |
| AI (Ollama) | No server / timeout | Rules fallback or degraded message; no 500 on copilot entry. |
| OCR | Tesseract/cloud down | Staff manual entry path; queue retry. |
| OpenSearch | DSN unset or cluster down | DB fallback search or empty result with message (`search_read_layer`). |

## Wave 2 — Internal API & events

- New routes: `/api/internal/...` per `INTERNAL_API_STANDARDS.md`.
- Event catalog: `GET /api/internal/north-star/event-catalog/`; extend `emit_platform_event` for new domains.
- Webhooks: `docs/WEBHOOK_DEAD_LETTER.md`; idempotency keys on outbound/inbound.
- CI: `apps/api/tests/test_internal_api_smoke.py` — staff-authenticated smoke on critical internal paths.

## Wave 3 — Spine & durability

| Component | Plan |
|-----------|------|
| Kong / gateway | Terminate TLS, rate limit, API key for `/api/v1/*` at edge before Django. Doc: `docs/architecture/KONG_API_GATEWAY_PLAN.md`. |
| Temporal | Long-running migration/pack jobs: use Celery chains + idempotency keys until Temporal adopted. Doc: `docs/architecture/TEMPORAL_WORKFLOWS_PLAN.md`. |
| OpenSearch | `OPENSEARCH_DSN`; index from domain events; `docs/architecture/storage_and_search.md`. |
| Degradation tests | Load test Celery queue depth; verify user-visible retry on timeout paths. `docs/architecture/DEGRADATION_LOAD_TEST_PLAN.md`. |

## Wave 4 — Geography & product depth

- Roadmap: `docs/WAVE4_REGION_PACK_ROADMAP.md` (India CBSE, SG, Canada, MENA, AU, LATAM).
- UK/statutory: sellable ReportPack per region.
- Advancement Phase 2: full donor/campaign/gift CRUD in product backlog tied to wedge 5.
- HE: measured go-live path `docs/HE_MONTHS_NOT_YEARS_GOLIVE.md`.
- Ministry/ERP: `docs/MINISTRY_ERP_INTEGRATION_PATTERNS.md`.

## Wave 5 — Migration north star

- Operator scorecard: Migration cloud table shows row/created/updated/error counts per run.
- Legacy cleaner: `python manage.py migration_legacy_data_audit --dry-run`.
- Roster webhook: signed POST spec + implementation `docs/ONEROSTER_ROSTER_WEBHOOK.md`.

## Wave 6–7 — Paper, climate, demographics

- Paper digitization: `docs/MIGRATION_CSV_DIFF_RUNBOOK.md`, partner SLA in services SKU.
- Climate reporting: pack hook or statutory extension per jurisdiction.
- Demographics: `GET /api/internal/br/demographic-insights/` (staff) for enrollment trend aggregates.

## Wave 8 — North star (N1–N29)

- Track in `BEYOND_REACH_IMPROVEMENTS.md`; LMS SLA: `docs/LMS_ROSTER_GRADEPASSBACK_SLA.md`.
- Go-live &lt;2 weeks: `docs/GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md`.
