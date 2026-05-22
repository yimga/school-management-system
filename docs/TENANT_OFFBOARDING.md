# Tenant offboarding (control plane + self-service)

Operator-grade and school-admin–initiated tenant removal on **manager.runmycampus.com** and **tenant host** — no Render Shell required for routine flows.

## Journeys

### Platform operator (manager)

1. **Offboarding queue** — `/super/offboarding/` (scheduled / self-service requests)
2. **Tenant 360** — `/super/tenants/<uuid>/360/#offboarding` (freeze → export → legal hold → schedule → typed-slug purge)
3. **CLI** — `tenant_purge`, `tenant_wind_down`, `tenant_offboarding_run_scheduled_purges`

### School administrator (tenant host)

1. **School Studio → Close account** — `/school/studio/offboarding/`
2. Export portability ZIP (unlimited students)
3. **Request account closure** — deactivates immediately; schedules purge after grace period
4. **Cancel** — before purge date (unless legal hold)

School admins **cannot** immediate purge — only platform operators or the auto-purge job after the grace period.

## Environment policy

| Variable | Default | Purpose |
|----------|---------|---------|
| `TENANT_SELF_SERVICE_OFFBOARDING_ENABLED` | `1` | Tenant `/school/studio/offboarding/` |
| `TENANT_AUTO_PURGE_ENABLED` | `0` | Nightly Celery `schools.run_scheduled_tenant_purges` |
| `TENANT_AUTO_PURGE_GRACE_DAYS` | `30` | Days after self-service request before purge |
| `TENANT_PURGE_REQUIRE_DUAL_APPROVAL` | `0` | Operator purge requires `dual_approved` |
| `TENANT_OFFBOARDING_S3_CLEANUP_ENABLED` | `1` | Invoke S3 delete on purge (when boto3 + bucket configured) |
| `AWS_STORAGE_BUCKET_NAME` | — | S3 media bucket for object cleanup |
| `TENANT_OFFBOARDING_EMAIL_ENABLED` | `1` | Send closure/purge notification emails |
| `TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS` | `1` | Email school ADMIN members on self-service closure |
| `TENANT_OFFBOARDING_PLATFORM_EMAILS` | — | Comma-separated ops inbox (falls back to `OPERATOR_ALERT_EMAIL` / `ADMINS`) |

## APIs

### Control plane (`/super/api/...`)

| Method | Path |
|--------|------|
| GET | `schools/<uuid>/offboarding/` |
| POST | `.../export/`, `.../deactivate/`, `.../hold/`, `.../purge/` |
| POST | `.../dual-approve/` — `{"step":"primary"}` or second approval via purge with `dual_approved: true` |
| POST | `.../schedule/` — operator `scheduled_purge_at` |
| GET | `.../export/download/` |
| POST | `/super/api/offboarding/run-scheduled/` |

### Tenant (`/api/school/offboarding/...`)

Snapshot, export, request-closure, cancel, export download — school **admin** RBAC (`has_school_permission(..., "admin")`).

## Storage & S3 lifecycle

- **Local:** `media/tenants/<slug>/`, `media/tenant_archives/<slug>/` (archives retained after purge)
- **S3:** `apps/compliance/tenant_offboarding_storage.py` lists/deletes keys under `tenants/<slug>/` (not archives)
- **Recommended bucket policy** (apply in AWS/Terraform — not auto-applied by app):

```python
python -c "from apps.compliance.tenant_offboarding_storage import lifecycle_policy_document; import json; print(json.dumps(lifecycle_policy_document(), indent=2))"
```

Rules: transition `tenant_archives/` to IA/Glacier; expire `tenants/` uploads after offboarding tag (operator applies tag policy separately).

## Django admin

- **Delete disabled** on `School` — `has_delete_permission` → `False`
- Delete action opens **guided** template linking to Tenant 360 offboarding
- Bulk delete removed from admin actions

## Data model

Offboarding state lives in `School.settings["offboarding"]` JSON (no extra table):

- `self_service_status`, `scheduled_purge_at`, `last_export_zip_path`, `legal_hold_until`, …

`SchoolProvisioningEvent` types include `OFFBOARDING_*`, `OFFBOARDING_SELF_SERVICE_*`, `OFFBOARDING_AUTO_PURGE_*` (migration `0053`).

## Platform integration (nothing orphaned)

| Surface | Entry |
|---------|--------|
| Control plane nav | Tenants → **Offboarding queue** |
| Outcome center | Tenants & Schools → Offboarding queue |
| Config hub tiles | Offboarding queue |
| Command palette | Offboarding queue (`manager_urls`) |
| Schools list | Offboarding queue button + lifecycle filter + per-row Offboarding |
| Tenant 360 | `#offboarding` panel + queue link |
| School Studio | **Close school account** |
| Django admin | Delete → guided → Tenant 360 |
| Celery beat | `schools.run_scheduled_tenant_purges` when `TENANT_AUTO_PURGE_ENABLED=1` |

## Dual approval (optional policy)

When `TENANT_PURGE_REQUIRE_DUAL_APPROVAL=1`:

1. Operator A clicks **Record first approval** on Tenant 360.
2. Operator B checks **I am the second approver** and runs permanent delete (must be a different account).
3. Scheduled auto-purge only runs if `settings.offboarding.dual_approved` is already true.

## Email notifications

`apps/schools/tenant_offboarding_notifications.py` sends via `apps.communication.notification_service.send_email`:

- Self-service closure requested → platform ops + school ADMIN emails
- Closure cancelled → platform ops
- Operator scheduled purge → platform ops
- Purge completed / scheduled batch summary → platform ops

## Verification

```bash
python scripts/verify_tenant_offboarding_surface.py
python scripts/run_sqlite_memory_tests.py \
  apps.schools.tests.test_tenant_offboarding_api \
  apps.schools.tests.test_tenant_offboarding_extended \
  apps.schools.tests.test_tenant_offboarding_integration \
  apps.schools.tests.test_tenant_offboarding_optional \
  apps.compliance.tests.test_tenant_purge_and_hmac_rotation.TenantPurgeCommandTests
npm run sweep:abrupt-end:routes
```

Migrations: `0052` + `0053` on `schools` (`SchoolProvisioningEvent` offboarding types).

## Production deletes (gilead-future / gilead-tech)

Enable auto-purge only after export + legal review:

```bash
export TENANT_AUTO_PURGE_ENABLED=1
python manage.py tenant_offboarding_run_scheduled_purges --dry-run
python manage.py tenant_offboarding_run_scheduled_purges --limit=5
```

Or operator purge via Tenant 360 / `tenant_purge --apply`. See [RENDER_SHELL_AFTER_DEPLOY.md](RENDER_SHELL_AFTER_DEPLOY.md).
