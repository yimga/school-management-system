# Dashboard & Site Settings — Link Reference

Use this when walking through dashboards or fixing links. All links should use `{% url 'namespace:name' %}` (or `{% url 'name' %}` for root URLs) so they work under any URL prefix.

---

## 1. Admin (`/admin/`)

### Sidebar (templates/admin/sidebar_inner.html → app_list.html)

| Item | URL name | Notes |
|------|----------|--------|
| Dashboard | `admin:index` | Admin home |
| Site settings | `admin:siteconfig_sitesettings_changelist` | Superuser only |
| App groups | `app.app_url` (e.g. `admin:auth_user_changelist`) | From `available_apps`; model links use `model.admin_url` |

### Admin index / dashboard cards

| Link | URL name |
|------|----------|
| Site Settings | `admin:siteconfig_sitesettings_changelist` |
| User permissions | `admin:accounts_user_changelist` |
| Master Sheet | `analytics:master_sheet` |
| Deadlines | `analytics:deadlines` |
| Publish Reports | `reports:publish_term_results` |
| Clear preview | `siteconfig:clear_preview` |
| Toggle sandbox | `siteconfig:toggle_preview_mode` (with `?next={{ request.path }}`) |

### Admin Site Settings (single-object form)

| Target | URL name |
|--------|----------|
| Change form | `admin:siteconfig_sitesettings_change` with `SITE_SETTINGS.pk\|default_if_none:1` |
| Region config list | `admin:siteconfig_regionconfig_changelist` |

Site Settings **sidebar** is in-app only: anchors `#section-{slug}` (e.g. `#section-theme-experience`). Section slugs come from `SETTINGS_NAV_GROUPS` in `apps/siteconfig/admin.py`. Form submits to the same change form URL.

---

## 2. Site Settings (Customizer & related)

| Page | URL name |
|------|----------|
| Customizer (theme/branding) | `siteconfig:customizer` |
| Clear preview | `siteconfig:clear_preview` |
| Theme colors | `siteconfig:theme_colors` |
| User preferences | `siteconfig:user_preferences` |
| Report Library | `siteconfig:report_library` |
| Report download | `siteconfig:report_download` with `report.slug` |
| Bulk letters | `siteconfig:bulk_letters` |
| Report card builder | `siteconfig:reportcard_builder` |
| Report card style preview | `siteconfig:reportcard_style_preview` with `style.slug` |
| Report card style PDF | `siteconfig:reportcard_style_pdf` with `style.slug`, `report_type` |
| Feature control panel | `siteconfig:feature_control_panel` |
| Feature control export | `siteconfig:feature_control_export` |
| Feature control audit | `siteconfig:feature_control_audit` |
| Preview from form | `siteconfig:preview_from_form` (used in JS) |
| Update theme (AJAX) | `siteconfig:update_theme` |

---

## 3. Portal sidebar (Parent / Teacher / Backend)

Rendered by `templates/partials/portal_sidebar.html`. Items come from **PORTAL_SIDEBAR_ITEMS** (from Site Settings) or the **fallback** block below.

### Fallback sidebar links (when no config)

| Label | URL name |
|-------|----------|
| Dashboard | `accounts:redirect` |
| My Profile | `accounts:user_profile` |
| Preferences | `siteconfig:user_preferences` |
| Notifications | `accounts:user_notifications` |
| Knowledge Base | `kb:kb_home` |
| Messages | `accounts:user_messages` |
| Message Groups | `communication:group_list` |
| Announcements | `communication:announcement_create` |
| Contact School | `portal:parent_contact_school` |
| Teacher: My Workflow | `portal:teacher_workflow` |
| Teacher: Enter Marks | `evals:teacher_marks_entry` |
| Teacher: Marks History | `evals:teacher_marks_list` |
| Teacher: Attendance | `portal:teacher_attendance` |
| Teacher: Payslips / Leave / Pay History | `payroll:employee_payslips`, `payroll:employee_leave` |
| Parent: My Workflow | `portal:parent_workflow` |
| Parent: My Children | `portal:parent_dashboard` |
| Parent: Finance & Fees | `portal:parent_finance` |
| Parent: Link Child / Claim Invite | `portal:link_child`, `portal:claim_invite` |
| Parent: Academic Stats | `portal:portal_stats` |
| Staff: Contact Requests | `portal:staff_contact_request_list` |
| Document Library Manager | `portal:document_library_manage` |
| Signature Requests | `portal:signature_requests_manage` |
| Documents | `portal:portal_feature` with `'documents'` |
| Student Profiles | `accounts:backend_student_list` |
| Student Guardians | `admin:people_studentguardian_changelist` |
| Authentication Groups | `admin:auth_group_changelist` |
| RBAC & Access Control | `accounts:rbac` |
| Evaluation Admin | `evals:evaluation_admin` |
| Class / School Ranking | `evals:class_ranking`, `evals:school_ranking` |
| Publish Results | `reports:publish_term_results` |
| Certification & Exams | `accounts:certification_home` |
| Finance Dashboard | `finance:dashboard` |
| Payroll | `payroll:dashboard` |
| Analytics | `analytics:dashboard` |
| Report Library / Report Card Builder | `siteconfig:report_library`, `siteconfig:reportcard_builder` |
| Portal Stats | `portal:portal_stats` |
| Backend Console | `accounts:backend_dashboard` |
| Workflow Center | `accounts:workflow_center` |
| Approval Hub | `accounts:approval_workflow_hub` |
| Import Hub | `accounts:import_hub` |
| Feature Control / Audit | `siteconfig:feature_control_panel`, `siteconfig:feature_control_audit` |
| Customizer | `siteconfig:customizer` |
| Site Settings (admin) | `admin:siteconfig_sitesettings_change` with `SITE_SETTINGS.pk\|default_if_none:1` |
| Region Configuration | `admin:siteconfig_regionconfig_changelist` |
| Configuration Engine | `admin:index` |

Dashboard Layout link uses `dashboard_layout_link` from context (backend only).

---

## 4. Backend dashboard (`/authentication/` → accounts:backend_dashboard)

Uses **portal_base** and **portal_sidebar**; quick actions and cards use the same URL names as above (e.g. `siteconfig:customizer`, `siteconfig:reportcard_builder`, `siteconfig:set_default_dashboard_view`, `accounts:workflow_center`).

---

## 5. Root / shared

| Purpose | URL name |
|---------|----------|
| Home (unauthenticated → login, authenticated → redirect) | `home` |
| API health (observability) | `api_health` |
| Back to dashboard (generic) | `home` or `accounts:redirect` depending on context |

---

## 6. Evals (teacher)

| Label | URL name |
|-------|----------|
| Teacher dashboard | `evals:teacher_dashboard` |
| Teacher marks entry | `evals:teacher_marks_entry` |
| Teacher marks list | `evals:teacher_marks_list` |

---

## 7. Portal (parent / reports)

| Label | URL name |
|-------|----------|
| Parent dashboard | `portal:parent_dashboard` |
| Back to parent | `portal:parent_dashboard` |

---

## Quick checklist for a full walkthrough

1. **Admin**: Open `/admin/` → click Dashboard, Site settings (if superuser), then one model per app. Check Quick access and header buttons (Site Settings, Master Sheet, Deadlines, Publish Reports).
2. **Site Settings**: Open Site Settings → change form; use left sidebar to jump to sections; save form; open Customizer from link/card.
3. **Portal**: Log in as Parent → check every sidebar item under fallback. Same for Teacher and Backend (staff).
4. **No hardcoded paths**: Search templates for `href="/` and `action="/` and replace with `{% url ... %}` where applicable. For JS-built URLs (e.g. evals extend_deadline, EMIS download), set `window.*_URL_BASE` from Django and use in template literals.

**JS-backed URLs (already fixed):**
- Evals compliance extend deadline: `window.EVALS_EXTEND_DEADLINE_URL_BASE` from `{% url 'evals:extend_deadline' 0 %}`.
- EMIS download: `window.EMIS_DOWNLOAD_URL_BASE` from `{% url 'emis:download' 0 %}`.
