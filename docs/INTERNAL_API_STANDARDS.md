# Internal API standards (§0.3 pillar 5)

## Conventions

| Concern | Rule |
|---------|------|
| **Auth** | Session or `Authorization: Bearer` internal service token; never trust `X-School-Id` without auth. |
| **Errors** | JSON `{"error": "code", "detail": "..."}`; 4xx client, 5xx server. |
| **Pagination** | `?limit=&offset=` or cursor; max limit 500 default 50. |
| **Versioning** | Path `/api/internal/...` stable; breaking changes → new path suffix `_v2`. |

## Event-driven (baseline)

**PlatformEventLog** stores `emit_platform_event` payloads (pack apply, payments, etc.). Heavy jobs still use Celery; see `EVENT_DRIVEN_FLOWS.md`.

## Shared error helper

New internal views should return:
`JsonResponse({"error": {"code": "NOT_FOUND", "detail": "..."}}, status=404)` — align with table above.

## Registered routes (`apps/api/urls.py`)

| Path prefix | Purpose |
|-------------|---------|
| `internal/teacher-hover/` | Teacher context hover |
| `internal/insight-anomalies/` | Insight anomalies |
| `internal/analytics-viz/overview/` | Unified analytics viz `TenantOverview` bundle (`?tenant=&from=&to=&compare=1`; session auth) |
| `internal/br/slo-targets/` | SLO targets |
| `internal/br/compliance/validate-enrollment/` | Enrollment validation |
| `internal/br/compliance/validate-attendance/` | Attendance validation |
| `internal/br/migration-diff-preview/` | SIS migration diff |
| `internal/br/ews/` | Early warning signals |
| `internal/br/nl-admin-query/` | Governed NL admin |
| `internal/br/messaging-retention/` | Retention policy |
| `internal/br/legacy-sis-readonly/` | Legacy SIS stub |
| `internal/br/tenant-registries-effective/` | Effective registries |
| `internal/north-star/event-catalog/` | Platform event catalog |
| `internal/north-star/wedge-playbook/` | Wedge playbook |
| `internal/north-star/package-impact/` | Package impact preview |
| `internal/learning-wedge-benchmarks/` | Learning benchmarks (router) |
| `internal/br/demographic-insights/` | Enrollment / classroom distribution snapshot (staff; `?school_id=`) |
| `internal/br/climate-reporting-hooks/` | Sustainability reporting extension hooks (staff) |

Add new internal endpoints only under `/api/internal/` with session/Bearer auth and documented purpose in this table.
