# Phase H — manual QA checklist (§11)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11 Phase H. Use with [UX_PAGE_AUDIT_CHECKLIST.md](UX_PAGE_AUDIT_CHECKLIST.md) and Trust center links.

## Preconditions

- Fresh migrated DB (avoid corrupted local SQLite test DB: remove stale `.django_test_dbs` if migrations fail mid-way).
- `python manage.py test` green on CI or local after migrate.
- North-star slice (no DB): `python manage.py test apps.dashboard.tests.test_north_star_guidance --noinput`
- Broader: add `apps.platform_runtime.tests.test_celery_task_events apps.marketplace.tests.test_install_impact` when DB is healthy.

## Marketplace N17 (install impact)

1. **Tenant:** App catalog → **Review impact & install** → modal shows scopes/compatibility → Confirm posts to sandbox install.
2. **Control plane:** App catalog → select school → **Preview impact** → Confirm matches selected school.
3. **API:** `GET /super/marketplace/apps/install-impact-preview/?app_id=&school_id=` (superuser).

## Tier 4 events

- Trust center **Platform events** (or logs): after bulk jobs, expect `celery_task_*` / `marketplace_app_installed` in `PlatformEventLog` when workers run.

## Pass criteria

- No broken primary nav links on backend + portal bases.
- Responsive: catalog cards stack; modal scrolls on small viewports.
- i18n: new strings use `{% trans %}` where added.
