# Tenant offboarding (control plane + self-service)

Operator-grade and school-admin–initiated tenant removal on **manager.runmycampus.com** and **tenant host** — no Render Shell required for routine flows.

## Journeys

### Platform operator (manager)

1. **Offboarding queue** — `/super/offboarding/` (scheduled / self-service requests)
2. **Tenant 360** — `/super/tenants/<uuid>/360/#offboarding` (freeze → export → legal hold → schedule → typed-slug purge)
3. **CLI** — `tenant_purge`, `tenant_wind_down`, `tenant_offboarding_run_scheduled_purges`

### School administrator (tenant host)

1. **School Studio → Close account** — `/school/studio/offboarding/`
2. Export portability ZIP (unlimited students; includes switching pack README + validation report)
3. **Submit offboarding request** (default) — stays active until platform operator approves
4. **Withdraw request** — while status is `requested` (operator-only mode)

When `TENANT_SELF_SERVICE_OFFBOARDING_ENABLED=1` (legacy Shopify-style), step 3 deactivates immediately and schedules purge after grace.

School admins **cannot** immediate purge — only platform operators or the auto-purge job after approval + grace period.

### Operator approval (default platform mode)

1. Tenant submits request → status `requested`
2. Operator **Approve** on `/super/offboarding/` or Tenant 360 → wind-down + grace schedule + export
3. Operator **Reject** → status `rejected` (tenant may re-request later)
4. Purge gates include `operator_approval_required` until `operator_approved_at` is set

## Environment policy

| Variable | Default | Purpose |
|----------|---------|---------|
| `TENANT_SELF_SERVICE_OFFBOARDING_ENABLED` | `0` | `0` = operator-only (export + request); `1` = legacy self-close |
| `TENANT_AUTO_PURGE_ENABLED` | `0` | Nightly Celery `schools.run_scheduled_tenant_purges` |
| `TENANT_AUTO_PURGE_GRACE_DAYS` | `30` | Days after self-service request before purge |
| `TENANT_PURGE_REQUIRE_DUAL_APPROVAL` | `0` | Operator purge requires `dual_approved` |
| `TENANT_OFFBOARDING_S3_CLEANUP_ENABLED` | `1` | Invoke S3 delete on purge (when boto3 + bucket configured) |
| `AWS_STORAGE_BUCKET_NAME` | — | S3 media bucket for object cleanup |
| `TENANT_OFFBOARDING_EMAIL_ENABLED` | `1` | Send closure/purge notification emails |
| `TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS` | `1` | Email school ADMIN members on self-service closure |
| `TENANT_OFFBOARDING_PLATFORM_EMAILS` | — | Comma-separated ops inbox (falls back to `OPERATOR_ALERT_EMAIL` / `ADMINS`) |

## Render (Lane 2) — deploy, email, purge

Repo gates prove **Lane 1** wiring. **Lane 2** is operator proof on Render after deploy (hard-refresh manager + tenant hosts for the service-worker bump). Step-by-step URLs and evidence filenames: [TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md](TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md). DNS/SPF/DKIM detail: [EMAIL_DELIVERABILITY.md](EMAIL_DELIVERABILITY.md).

### Render environment checklist

Set these on the **web** service (and **worker** when Celery beat/tasks run purges or bulk mail). Values are examples — use your provider’s real secrets.

#### A. Signup verification email (live SMTP / Anymail)

Signup calls `send_transactional(..., async_send=True)` in `apps/schools/signup_views.py`. The HTTP response returns immediately; a **daemon thread** runs SMTP retries and writes an `EmailDeliveryEvent` row. **Celery is not required** for signup mail, but misconfigured `EMAIL_*` still yields `ok=False` in the audit log.

| Render env var | Required | Notes |
|----------------|----------|--------|
| `EMAIL_BACKEND` | **Yes** | Must **not** be `django.core.mail.backends.console.EmailBackend` in production. Use Anymail (recommended) or `django.core.mail.backends.smtp.EmailBackend`. |
| `DEFAULT_FROM_EMAIL` | **Yes** | Verified sender, e.g. `noreply@runmycampus.com` — must match SPF/DKIM on the sending domain. |
| `SERVER_EMAIL` | Recommended | Bounce/admin errors; often same as `DEFAULT_FROM_EMAIL`. |
| **Anymail (pick one provider)** | If using Anymail | Set `EMAIL_BACKEND` to the matching backend, e.g. `anymail.backends.mailgun.EmailBackend`, plus provider API keys via `ANYMAIL` JSON or provider-specific env vars documented in [integrations/COMMUNICATION_PROVIDERS_CONNECTION_GUIDE.md](integrations/COMMUNICATION_PROVIDERS_CONNECTION_GUIDE.md). |
| `ANYMAIL_MAILGUN_API_KEY` | Mailgun | When `EMAIL_BACKEND=anymail.backends.mailgun.EmailBackend`. |
| `ANYMAIL_SENDGRID_API_KEY` | SendGrid | When `EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend`. |
| `ANYMAIL_POSTMARK_SERVER_TOKEN` | Postmark | When `EMAIL_BACKEND=anymail.backends.postmark.EmailBackend`. |
| **SMTP relay (alternative)** | If not Anymail | `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_USE_TLS=True`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`. |
| `EMAIL_TIMEOUT` | Optional | Per-attempt socket timeout (default `10`). |
| `SCHOOLOPS_EMAIL_DELIVERY_SYNC_BUDGET_SECONDS` | Optional | Sync callers only (default `8`); signup uses async path. |
| `SCHOOLOPS_EMAIL_DELIVERY_TENANT_HOURLY_CAP` | Optional | Per-tenant rate cap (default `200`/hr). |

**Lane 2 proof (signup email):**

1. Deploy `main` → confirm `collectstatic` finished.
2. Open **Email delivery** — `https://manager.runmycampus.com/super/email/health/` — panel **Resolved SMTP config** must show a production backend (not “Django console (dev)”). Use **Run SMTP probe** → expect success.
3. Open **Signup diagnostics** — `https://manager.runmycampus.com/super/signup/diagnostics/` — outbound reachability + last signup attempts.
4. Submit a real `/signup/` on production → within ~2 minutes, **Email delivery** stats should show a transactional row moving to **`ok=True`** (or a clear `error_kind` if DNS/credentials are wrong).
5. Open the verification link → `/verify-signup/?token=…` → school `is_active=True` → tenant `/school/studio/provisioning/` progresses.

Until steps 2–5 pass on Render, **Lane 2 signup email is not complete** — repo tests only mock `send_transactional`.

#### B. Offboarding + scheduled purge (operator default)

| Render env var | Required | Notes |
|----------------|----------|--------|
| `TENANT_AUTO_PURGE_ENABLED` | **Yes (set explicitly)** | **`0`** (default) — nightly Celery **does not** delete tenants; use `/super/offboarding/` dry-run + **Apply due purges (operator)** with confirm `purge-due-tenants`. Set **`1`** only after export + legal review. |
| `TENANT_AUTO_PURGE_GRACE_DAYS` | When auto on | Default `30` — days after self-service closure before purge eligibility. |
| `TENANT_SELF_SERVICE_OFFBOARDING_ENABLED` | **Yes (set explicitly)** | **`0`** (default) — tenants export + submit requests; operators approve on `/super/offboarding/`. Set **`1`** only for legacy self-close. |
| `TENANT_OFFBOARDING_EMAIL_ENABLED` | Recommended | `1` — closure/purge notification emails (same SMTP/Anymail stack as § A). |
| `TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS` | Optional | `1` — email school admins on self-service request. |
| `TENANT_OFFBOARDING_PLATFORM_EMAILS` | Recommended | Comma-separated ops inbox for purge summaries. |
| `TENANT_PURGE_REQUIRE_DUAL_APPROVAL` | Optional | `0` unless counsel requires two-operator purge. |
| `TENANT_OFFBOARDING_S3_CLEANUP_ENABLED` | Optional | `1` when `AWS_STORAGE_BUCKET_NAME` is set. |
| `AWS_STORAGE_BUCKET_NAME` | When S3 cleanup on | Media bucket for `tenants/<slug>/` key deletion on purge. |

**Lane 2 proof (offboarding queue):**

1. `/super/offboarding/` — banner **Auto-purge: disabled** when `TENANT_AUTO_PURGE_ENABLED=0`.
2. Tenant requests closure → school appears with **Due** when `scheduled_purge_at` ≤ today.
3. **Dry-run scheduled purges** → JSON summary; file as `offboarding-queue-dry-run.json`.
4. **Apply due purges (operator)** + `purge-due-tenants` only after export sign-off.

#### C. Celery / Redis (auto-purge + bulk mail only)

| Render env var | Required | Notes |
|----------------|----------|--------|
| `CELERY_BROKER_URL` | When beat/tasks | Redis URL; required for `schools.run_scheduled_tenant_purges` when `TENANT_AUTO_PURGE_ENABLED=1`. |
| `CELERY_RESULT_BACKEND` | Recommended | Usually same Redis. |
| `CELERY_BEAT_ENABLED` | Optional | `1` on beat worker; schedule includes purge task only when auto-purge is on. |

Signup verification email does **not** depend on Celery; offboarding **nightly** auto-purge does.

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

## Unified lifecycle (onboarding + offboarding)

Canonical phases: `draft` → `provisioning` → `activating` → `live` → `wind_down` → `closed` → `purged`

| Path | Creation marker | First landing after verify/create |
|------|-----------------|-----------------------------------|
| Self-serve signup | `settings.lifecycle.creation_path=self_serve` | `/school/studio/provisioning/` |
| Operator rapid / API create | `settings.lifecycle.creation_path=operator` | School Studio + lifecycle timeline |

Tenant surfaces: `/school/studio/` (launch rail + fast path), `/school/studio/fast-path/`, `/school/studio/provisioning/`.  
Operator offboarding checklist: Tenant 360 `#offboarding` (`data-rmc-offboarding-checklist`).

```bash
python scripts/verify_tenant_lifecycle_unified.py
```

### Wind-down commerce guard

While `wind_down_mode` or scheduled self-service closure is active, these write paths return **403**:

- `finance:generate_fees` (POST)
- `finance` split allocation (POST)
- `people` backend student create (POST)
- DRF `InvoiceViewSet.create` / `PaymentViewSet.create`

Operator rapid create (`/super/schools/rapid/`) dispatches provisioning and surfaces tenant URLs:

- `/school/studio/provisioning/` on the school subdomain
- `/school/studio/` (launch rail)

## Lifecycle command center (tenant)

Unified checklist for registration, enrollment, onboarding, and offboarding:

- **URL:** `/school/studio/lifecycle/` on the school tenant host
- **API:** `GET /api/school/lifecycle/hub/`
- **Exit status panel:** read-only `data-rmc-offboarding-exit-status` (phase, scheduled purge, export readiness) — destructive closure stays on `/school/studio/offboarding/`
- **Parent data rights:** `/portal/parent/data-rights/` (child JSON export + EraseRequest queue)
- **Public SLA:** `https://runmycampus.com/trust-center/offboarding/`
- **Gate:** `python scripts/verify_tenant_lifecycle_completion.py`

School Studio links **Open lifecycle command center** from the hub landing.

## Offboarding queue (auto-purge disabled by default)

`/super/offboarding/` lists schools with self-service or operator-scheduled purge.

When **`TENANT_AUTO_PURGE_ENABLED=0`** (default):

- Scheduled dates are stored; schools show **Due** when the date is on or before today.
- Nightly Celery does **not** delete tenants.
- Operators use **Dry-run scheduled purges** or **Apply due purges (operator)** with confirm phrase `purge-due-tenants`.

Lane 2 env vars and proof dashboards: **§ Render (Lane 2)** above. URL checklist: [TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md](TENANT_LIFECYCLE_LANE2_OPERATOR_CHECKLIST.md).

## Verification

```bash
python scripts/verify_tenant_lifecycle_completion.py
python scripts/audit_tenant_lifecycle_full.py
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
