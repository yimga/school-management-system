# Dominance Sweep checklist (A3, A5, A6, A7)

Short reference for blueprint items already implemented or documented.

| Item | Status | Where |
|------|--------|--------|
| **A3 Isolation** | Done / Doc | [cache_keys.md](cache_keys.md): tenant-scoped cache keys. Media/static: ensure upload_to includes school_id. Celery: @tenant_task in apps/tenancy/tasks.py. [audit_branching_and_isolation.md](audit_branching_and_isolation.md) (C3). |
| **A5 Security** | Done / Doc | Rate limiting: apps/api/rate_limit.py, TenantApiQuotaMiddleware. MFA: django_otp, RequireMFAMiddleware. Audit: compliance AuditLog, AccessLog. CI: scripts/security_ci.sh, docs/security_baseline.md. |
| **A6 Data governance** | Done | apps/compliance: RetentionRule, ConsentRecord, ExportJob, EraseRequest; policy-driven via Policy Registry. |
| **A7 Accessibility / i18n** | Partial | RTL and terminology from Policy Registry (get_effective_policy). WCAG: siteconfig/tests/test_accessibility.py. Plural/locale: use Django i18n; terminology from policy. |
