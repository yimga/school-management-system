# Data retention and purge (GDPR/FERPA/NDPR)

## Retention policy (settings)

Retention windows are controlled by `DATA_RETENTION` in Django settings, e.g.:

```python
DATA_RETENTION = {
    "audit_log_days": 730,
    "access_log_days": 365,
    "session_days": 90,
    "report_days": 365,
}
```

Optional per-region overrides (when running `purge_compliance_data --region=GDPR`):

```python
DATA_RETENTION = {
    "audit_log_days": 730,
    "GDPR_audit_log_days": 730,
    "GDPR_access_log_days": 365,
    "FERPA_audit_log_days": 365,
    # ...
}
```

## Scheduled purge

Run periodically (e.g. cron):

- `python manage.py purge_compliance_data` — uses default keys
- `python manage.py purge_compliance_data --region=GDPR` — uses GDPR_* keys
- `python manage.py purge_compliance_data --dry-run` — show counts only

## Per-region masking

Use `apps.compliance.privacy.mask_pii_for_region(value, region)` when displaying PII in a compliance_region-aware context (e.g. School.compliance_region). Regions: `GDPR`, `FERPA`, `NDPR`.
