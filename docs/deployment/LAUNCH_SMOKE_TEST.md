# Launch smoke test (staging / production)

Run with a **known test user** on the **target host** (school subdomain for tenant paths). Record pass/fail and timestamp. Complements `PRODUCTION_DEPLOYMENT_CHECKLIST.md`.

Paths below use the **tenant** URLConf (`config/tenant_urls.py`); all are prefix paths on the school host (e.g. `https://<subdomain>.runmycampus.com/...`) unless noted (manager host for some CCC / platform flows).

| Step | Area | What to verify |
|------|------|----------------|
| 1 | **Login** | Session established; no 500 on login → redirect for authenticated user. |
| 2 | **Logout** | Session cleared; next protected page requires login. (Re-login before remaining steps as needed.) |
| 3 | **Portal / role home** | After login, land on the expected dashboard for the test role (parent/teacher/staff). |
| 4 | **Backend dashboard** | Open `/backend/` — staff operator path (`accounts:backend_dashboard`); 200/302 as expected. |
| 5 | **CCC (Configuration Control Center)** | `GET /siteconfig/console/` (or console hub URL your deployment uses) — **CCC** loads. |
| 6 | **Evidence (read-only)** | Spot-check **200** (or documented 403 if feature-gated) for each sub-area the tenant is entitled to: **academic years** `/siteconfig/reports/academic-years-setup/`, **departments** `/siteconfig/reports/departments-setup/`, **term publish** `/siteconfig/reports/term-publish-status/`, **config mutation** `/siteconfig/metadata/config-mutation-audit/`, **report templates catalog** `/siteconfig/reports/report-templates-catalog/`, **tenant report schedules (evidence)** `/siteconfig/reports/tenant-schedules-evidence/`, **output history** `/siteconfig/reports/output-history-evidence/`. (Smallest pass: at least one row from this set + confirm others 200/403 as expected for plan.) |
| 7 | **Bulk letters (operator)** | `GET /siteconfig/reports/bulk-letters/` when bulk letters are in scope for the tenant/plan (feature-gated; expect 403/redirect if not entitled — record which). |
| 8 | **Student 360** | `GET /portal/student/<student_id>/360/` for a `student_id` the user is allowed to see (find id from student list in your seed). |
| 9 | **Scheduled reports** | `GET /siteconfig/reports/scheduled/` (scheduled report delivery hub). |
| 10 | **Marketplace catalog** | `GET /settings/app-catalog/` (tenant app catalog; installed/catalog UX). |
| 11 | **Studio OS** | e.g. `GET /studio/experience/` (Customizer / Studio experience shell). |
| 12 | **Report library (optional)** | `GET /studio/output/` or legacy redirect `GET /siteconfig/reports/` for Output Studio. |
| 13 | **Advanced / Admin fallback** | As superuser or staff, open **`/admin/`** on the **tenant** host — **tenant** admin (academics registered there); product path should be sufficient; admin is escape hatch. |
| 14 | **Permission denied / blocked paths** | As a user **without** `settings.manage` (or other restricted role), `GET` a protected control-plane or evidence URL (e.g. academic years or departments evidence) — expect **403** (or product redirect to login/portal), not a silent 200 with data the user should not see. Optional: same user attempts `/super/`-class path — expect block if not `SUPERADMIN`. |

**Watch during smoke**

- 500/502/504 responses.
- Tenant resolution warnings in logs (`request.school` / middleware).
- CSRF errors on POST (check `CSRF_TRUSTED_ORIGINS` vs actual browser origin).

**Related:** `docs/deployment/DEPLOYMENT_ROLLBACK.md` if any step fails.  
**Rollback / recovery:** `docs/deployment/DEPLOYMENT_ROLLBACK.md` (redeploy previous build; DB restore only per runbook).  
**Release / launch bundle:** `docs/deployment/RELEASE_NOTES_LAUNCH.md`.

## Route map (smoke — tenant host)

| Step | HTTP path (prefix) | Name / view source |
|------|--------------------|--------------------|
| 4 | `/backend/` | Redirect → `accounts:backend_dashboard` (`config/tenant_urls.py`) |
| 5 | `/siteconfig/console/` | `siteconfig:console_domains_hub` → `views_console_domains` |
| 6 | `/siteconfig/reports/term-publish-status/` | `siteconfig:term_publish_status_evidence` |
| 6 | `/siteconfig/reports/academic-years-setup/` | `siteconfig:academic_years_setup_evidence` |
| 6 | `/siteconfig/reports/departments-setup/` | `siteconfig:departments_setup_evidence` |
| 6 | `/siteconfig/metadata/config-mutation-audit/` | `siteconfig:config_mutation_audit_evidence` |
| 6 | `/siteconfig/reports/report-templates-catalog/` | `siteconfig:report_templates_catalog_evidence` |
| 6 | `/siteconfig/reports/tenant-schedules-evidence/` | `siteconfig:tenant_report_schedules_evidence` |
| 6 | `/siteconfig/reports/output-history-evidence/` | `siteconfig:report_output_history_evidence` |
| 7 | `/siteconfig/reports/bulk-letters/` | `siteconfig:bulk_letters` |
| 8 | `/portal/student/<id>/360/` | `portal:student_360_page` |
| 9 | `/siteconfig/reports/scheduled/` | `scheduled_reports_delivery_hub` |
| 10 | `/settings/app-catalog/` | `tenant_app_catalog` (view in `marketplace/views`) |
| 11 | `/studio/experience/` | `studio_os:experience` |
| 12 | `/studio/output/` or `/siteconfig/reports/` | `studio_os:output` or redirect to output (`legacy_report_library_redirect`) |
| 13 | `/admin/` | `tenant_admin_site` (`config/tenant_urls.py`) |
