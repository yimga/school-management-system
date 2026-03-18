# Deploy, migrations, seeding, and UX assurance

**Reality check:** No automated pass can prove “every button, dashboard, and frame” is perfect. This doc separates **what CI/pre-deploy already enforces** from **what still needs human or Playwright QA**.

## What is already enforced (merge/deploy safety)

| Layer | Command / artifact | What it guards |
|--------|-------------------|----------------|
| Django | `python manage.py check` | Settings, models, URL wiring sanity |
| Migrations | `python manage.py makemigrations --check --dry-run` | No forgotten model changes |
| Pre-deploy gate | `bash scripts/pre_deploy_gate.sh` | Lints, smoke URLs, Phase H, theme matrix, core workflows, multi-tenant tests, UX completion markers, SOT evidence |
| Render predeploy | `bash scripts/release/render_predeploy.sh` | Shared + tenant migrations, seeds, `seed_render_users`, static, health check |
| Tenant model | `python manage.py audit_tenant_models --strict` | SHARED vs TENANT app boundaries |

Run the full gate before merge when changing routing, templates, or tenant code:

```bash
SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh   # skip Playwright if no browser
bash scripts/pre_deploy_gate.sh                   # includes visual QA when Playwright installed
```

## Tenant `Client` model (critical for Render)

`TENANT_MODEL` is **`customers.Client`** (`apps.customers.models.Client`).  
**Do not** import `Client` from `django_tenants.models` — that symbol is not guaranteed; it breaks `seed_render_users`, Celery tenant tasks, and any code that resolves tenants by ORM.

Use:

```python
from apps.customers.models import Client
```

## Seeding and first deploy

- **Render:** Set `DATABASE_URL` (Postgres), `SECRET_KEY`, `ADMIN_PASSWORD`, optional `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` for full catalog seed. See [DEPLOY_RENDER.md](./DEPLOY_RENDER.md), [SEEDING_BOOTSTRAP_AUDIT.md](./SEEDING_BOOTSTRAP_AUDIT.md).
- **Users:** Predeploy runs `seed_render_users` (super-admin `admin`/`admin`, tenant admin, demo users when `ADMIN_PASSWORD` is set).

## UI/UX “high-end” — what to verify manually

| Area | How to verify |
|------|----------------|
| No overflow / framing | Resize browser; check Studio, admin, portal; gate runs `phase_h_audit.py` + responsive advisory lints |
| Labels & structure | i18n `{% trans %}` on user-facing strings; page archetypes per [PAGE_ARCHETYPES.md](./ui/PAGE_ARCHETYPES.md) |
| Broken links | Smoke tests + `test_admin_sidebar_child_links_are_resolvable`; spot-check new URLs |
| 500s | Server logs + Sentry if configured; gate tests catch many view regressions |

## After merge: minimal production smoke

1. Open `/`, login, `/backend`, one portal role, `/super/` (if enabled).
2. Manager: one control-plane link from sidebar.
3. Tenant: app catalog or dashboard load without 500.

---

**Summary:** Keep using **pre_deploy_gate + Render predeploy** as the bar for “gels on deploy.” Use this doc + manual smoke for subjective UX polish.
