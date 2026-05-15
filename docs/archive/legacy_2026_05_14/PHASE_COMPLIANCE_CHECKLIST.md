# Phase Compliance — Audits & GDPR (plan 3.9)

## Implemented

- **RegionFeatureCompliance** (`apps.compliance.models`): Maps region → feature_code → status (ENABLED/DISABLED/RESTRICTED). Admin: list/filter by region and status.
- **ComplianceGuardMiddleware** (`apps.compliance.middleware`): For `request.school.default_region`, loads rules; if path is in `COMPLIANCE_GUARD_PATH_MAP` and rule is DISABLED/RESTRICTED, returns 403 (JSON or HTML). Add path → feature_code entries in `middleware.COMPLIANCE_GUARD_PATH_MAP` when you have region-restricted actions (e.g. EU blocks bulk export).
- **Data residency:** Use `School.default_region_id` (or add `data_residency` field if needed) for tenant region; provisioning can pin tenant to regional cell.
- **GDPR stubs** (`apps.compliance.gdpr_services`):
  - `gdpr_scrub_student(school_id, student_id, dry_run=…)`: Right to Erasure stub; implement cascade delete, anonymize, media wipe in schema context.
  - `export_student_data_portability(school_id, student_id, format=…)`: Data Portability stub; implement CEDS export; enforce MFA in view before calling.

## Optional / follow-up

- **Right to Erasure flow:** Request → audit log; optional admin approval; call `GDPRScrubService` / `gdpr_scrub_student` in schema context.
- **Data Portability:** CEDS-compliant JSON/CSV export; MFA before export; optional direct transfer (token School A → School B).
- **Compliance Auditor:** Celery Beat periodic cross-schema checks (portability accessed, erasure request age, under-13 consent); Compliance Health Score per school; Super Admin map (green/red by region).
- **Automated Violation Resolver:** On audit failure, auto-apply configured fix (snapshot before fix; rollback on 500; transparency log).
