# Control matrix (internal)

Status values: **implemented** | **partial** | **not implemented** (in-repo product only; operations may still cover the gap).

| Control | Status | Evidence | Tests / verifiers | Gap |
| --- | --- | --- | --- | --- |
| Access control | partial | `apps/accounts/models.py`, roles, CP gates | `apps/schools/tests/test_control_plane_boundary.py` | Formal quarterly access review |
| Authentication | implemented | Django auth + MFA modules | `apps/accounts/tests/` | IdP-specific DR |
| Authorization (API) | partial | DRF + custom decorators | `scripts/audit_security_surface.py` | Document each `AllowAny` |
| Tenant isolation | implemented | `TenantMiddleware`, host routing | `apps/schools/tests/test_tenant_middleware.py`, `scripts/audit_tenant_isolation.py` | 1000+ tenant scale — `docs/scaling/1000_TENANT_SCALE_CHECKLIST.md` |
| Audit logging | partial | Config mutation audit, activity logs | `apps/siteconfig/tests/test_config_mutation_audit_evidence.py` | Central SIEM export |
| Change management | partial | Git, SOT §11.4, `CONTRIBUTING.md` | `verify_doc_plan_density_discipline.py` | External CAB |
| Deployment review | partial | `docs/deployment/*`, `render.yaml` | Release scripts in `scripts/` | Customer-specific staging gates |
| Incident response | partial | `INCIDENT_RESPONSE_POLICY.md`, platform incidents app | Support queue tests | PagerDuty playbooks external |
| Backup / restore | partial | `BACKUP_AND_RESTORE_POLICY.md`, DB docs | `test_db_liveness` (release gate) | Verified restore drills |
| Vendor / integrations | partial | `VENDOR_RISK_POLICY.md`, integration settings | `audit_sitesettings_python_surface.py` | Vendor SOC reports filed externally |
| Data retention | partial | `DATA_RETENTION_POLICY.md` | — | Automated purge jobs |
| Security monitoring | partial | `SECURITY_MONITORING_POLICY.md`, logging | `audit_security_surface.py` | 24/7 monitoring contract |
