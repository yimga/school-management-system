# Async jobs readiness plan (no Celery requirement)

## Candidates for background work

| Work unit | Why async | Idempotency | Audit |
| --- | --- | --- | --- |
| Large PDF / report generation | CPU + memory | Job id + content hash | Log start/end + tenant |
| Bulk letters send | Rate limits | Dedupe by campaign id + recipient | Store send receipts |
| Scheduled report delivery | Cron volume | Unique (schedule, window) | Use existing schedule models |
| CSV / EMIS exports | IO bound | Export request id | Download token |
| Long imports | Timeout risk | Import batch id | Row-level error file |

## Retry rules (when a worker exists)

- Exponential backoff for external HTTP.
- Hard cap on retries for payment side-effects.

## Deployment assumptions

- `render.yaml` and `docs/deployment/` describe process models; Celery is **not** assumed in this repository snapshot.
- If workers are added later, they must reuse Django ORM with `school` / `tenant` context set the same as HTTP requests.

No background worker code is added by this governance batch.
