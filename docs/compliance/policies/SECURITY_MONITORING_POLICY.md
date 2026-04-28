# Security monitoring policy (application)

## What the product emits

- Structured logs with request IDs (see logging configuration in `config/settings.py` and middleware).
- Security-relevant audits: `docs/generated/security_surface_audit.json`, `docs/generated/admin_gravity_audit.json`, `docs/generated/sitesettings_python_surface_audit.json`.

## What operators should monitor

1. Spike in `403`/`401` on manager host and `/api/search/`.
2. New `csrf_exempt` or `AllowAny` hits in product paths (diff `security_surface_audit.json`).
3. Raw SQL outside migrations (`scripts/audit_raw_sql_usage.py`, `scripts/lint_raw_sql_usage.py`).

## Alerting

Routing alerts (PagerDuty, email) is **deployment-specific** — not configured in this repo.
