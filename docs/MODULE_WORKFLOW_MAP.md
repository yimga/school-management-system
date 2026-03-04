# Module and workflow map (concise)

Part 3.1 / 5. Single reference: key URL → view → template; Celery tasks and management commands per area. Cross-check with FEATURE_GATE_PATH_MAP ([apps/schools/middleware.py](../apps/schools/middleware.py)) and [ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md](ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md).

## Public / marketing

| URL / path | View / handler | Template |
|------------|----------------|----------|
| `/` | marketing_landing | schools/marketing_landing.html |
| `/product/`, `/pricing/`, `/about/`, `/features/`, `/blog/`, `/contact/`, `/privacy/`, `/terms/` | marketing_page (page_slug) | schools/marketing_page.html |
| `/discover/`, `/find/` | global_login_discovery, find_school | section8 + school finder |
| `/signup/`, `/verify-signup/`, `/onboard/` | signup_school, verify_signup, onboarding_wizard | signup_views |
| `/book-demo/` | marketing_page (book-demo) | marketing_page.html |

## Tenant backend (prefixes)

| Prefix | Purpose | Key apps |
|--------|---------|----------|
| `/backend/` | School admin dashboard | siteconfig, people, academics, finance, evals, reports |
| `/portal/` | Parent/student/teacher portal | portal |
| `/authentication/` | Login, MFA | accounts |
| `/super/` | Super-admin | super_views |
| `/siteconfig/` | Feature control, theme, settings | siteconfig |
| `/admin/` | Django admin (tenant or public) | admin |

## Feature-gated paths (sample)

See `FEATURE_GATE_PATH_MAP` in apps/schools/middleware.py (e.g. design_studio, transport, library). Paths in the map require `is_feature_enabled(school, code)`.

## Celery tasks (sample)

| Task | App | Purpose |
|------|-----|---------|
| provision_school_task | schools | Tenant provisioning (schema, seed) |
| calculate_monthly_revenue_stats | siteconfig | Revenue snapshot |
| send_payment_reminders | finance | Payment reminders |
| migrate_tenant_schemas_one_by_one | (management command) | Per-tenant migrations |

## Management commands (sample)

| Command | App | Purpose |
|---------|-----|---------|
| migrate_tenant_schemas_one_by_one | schools | Run migrations per tenant; on failure continue |
| seed_global_regions | siteconfig | Populate RegionConfig per country |
| verify_region_coverage | siteconfig | Verify region coverage |
| attach_audit_triggers | people | Attach audit triggers to extra tables per tenant |

Full list: see apps/*/management/commands/ and ALL_MODULES_DEPENDENCIES_AUTOMATION_GAPS.md.
