# Deploy, migrations, seeding, and UX assurance

## UX / dashboards — **closed bar**

Subjective “every pixel” polish is still a product call, but **connectivity, framing (no horizontal overflow), manager vs tenant hosts, and core portal paths** are now **automated**:

| Bar | Command |
|-----|---------|
| **Full release UX + gate** | `bash scripts/full_ux_assurance.sh` |
| **Playwright only** | `bash scripts/run_visual_qa.sh` |
| **Gate without browser** | `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` |

Details: [VISUAL_AND_DASHBOARD_UX_BAR.md](./VISUAL_AND_DASHBOARD_UX_BAR.md), [DASHBOARDS_AND_LINKS.md](./DASHBOARDS_AND_LINKS.md) (manual spot checklist).

## What is already enforced (merge/deploy safety)

| Layer | Command / artifact | What it guards |
|--------|-------------------|----------------|
| Django | `python manage.py check` | Settings, models, URL wiring sanity |
| Migrations | `python manage.py makemigrations --check --dry-run` | No forgotten model changes |
| Pre-deploy gate | `bash scripts/pre_deploy_gate.sh` | Lints, smoke URLs, Phase H, theme matrix, core workflows, multi-tenant tests, UX completion markers, SOT evidence |
| Render predeploy | `bash scripts/release/render_predeploy.sh` | Shared + tenant migrations, seeds, `seed_render_users`, static, health check |
| Tenant model | `python manage.py audit_tenant_models --strict` | SHARED vs TENANT app boundaries |

## Tenant `Client` model (critical for Render)

`TENANT_MODEL` is **`customers.Client`** (`apps.customers.models.Client`).  
**Do not** import `Client` from `django_tenants.models`.

```python
from apps.customers.models import Client
```

## Seeding and first deploy

- **Render:** `DATABASE_URL`, `SECRET_KEY`, **`ADMIN_PASSWORD`** (enables teacher1 / Parent1 for QA and demos). See [DEPLOY_RENDER.md](./DEPLOY_RENDER.md), [SEEDING_BOOTSTRAP_AUDIT.md](./SEEDING_BOOTSTRAP_AUDIT.md).

## Summary

- **Merge/deploy:** pre_deploy_gate + Render predeploy.  
- **Release sign-off:** `full_ux_assurance.sh` on Postgres when tenant demo users exist.  
- **Staging smoke:** DASHBOARDS_AND_LINKS manual checklist.
