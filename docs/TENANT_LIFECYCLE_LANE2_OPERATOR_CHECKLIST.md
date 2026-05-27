# Tenant lifecycle — Lane 2 operator checklist (Render)

Repo gates (run after deploy):

```bash
python scripts/verify_tenant_lifecycle_completion.py
python scripts/audit_tenant_lifecycle_full.py
```

## 1. Deploy + cache

1. Deploy `main` to Render (includes SW bump — hard-refresh manager + tenant hosts).
2. Confirm `collectstatic` completed without blocking errors.

## 2. Signup → verification email (live)

| Check | Action |
|-------|--------|
| SMTP / Anymail | `DEFAULT_FROM_EMAIL`, Mailgun/SendGrid/Postmark env vars set on Render |
| Async send | Signup uses `send_transactional(..., async_send=True)` — check **Email delivery** / signup diagnostics for `queued` → `sent` |
| Verify link | Complete `/signup/` → open email → `/verify-signup/?token=…` → school `is_active=True` |
| Provision | Tenant `/school/studio/provisioning/` shows progress; reaches **live** or **activating** |

## 3. First enrollment (tenant)

| Check | URL |
|-------|-----|
| Lifecycle hub | `https://<slug>.runmycampus.com/school/studio/lifecycle/` |
| Applicants | Backend → applicants list; move one past **Lead** |
| Student | Convert to student / create student profile |
| Guardian invite | Backend → guardians; issue invite; parent claims `/parent/claim-invite/<token>/` |
| Fees | At least one invoice or fee catalog entry |

Command center **Enrollment** % should rise as each workflow state is satisfied.

## 4. Offboarding + purge (operator)

| Check | URL / action |
|-------|----------------|
| Offboarding queue | `https://manager.runmycampus.com/super/offboarding/` |
| Auto-purge banner | Shows **disabled** until `TENANT_AUTO_PURGE_ENABLED=1` |
| Self-service | Tenant `/school/studio/offboarding/` → request closure → school appears in queue with **Due** when date passed |
| Dry-run | Queue → **Dry-run scheduled purges** |
| Manual apply | **Apply due purges (operator)** + confirm `purge-due-tenants` (when auto-purge off) |
| Tenant 360 | `/super/tenants/<uuid>/360/#offboarding` — export → schedule → typed-slug purge |

## 5. Optional production auto-purge

Only after export + legal review:

```bash
TENANT_AUTO_PURGE_ENABLED=1
TENANT_AUTO_PURGE_GRACE_DAYS=30
```

Celery beat `schools.run_scheduled_tenant_purges` runs nightly. Until then, operator manual apply is supported.

## Evidence to file

Store screenshots or JSON under `var/evidence/tenant-lifecycle-lane2/<YYYY-MM-DD>/`:

- `signup-verify-redirect.json` (final URL after verify)
- `lifecycle-hub-percent.json` (API `GET /api/school/lifecycle/hub/`)
- `offboarding-queue-dry-run.json` (queue dry-run response)
