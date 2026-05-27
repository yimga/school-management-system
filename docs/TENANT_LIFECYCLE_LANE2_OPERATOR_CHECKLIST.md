# Tenant lifecycle — Lane 2 operator checklist (Render)

Repo gates (run after deploy):

```bash
python scripts/verify_lifecycle_post_deploy_smoke.py
```

Bundled gates: back-to-top, scroll contract, lifecycle completion/full/aggressive, `render.yaml` Lane 2 env defaults.

## 1. Deploy + cache

1. Deploy `main` to Render (includes SW bump — hard-refresh manager + tenant hosts).
2. Confirm `collectstatic` completed without blocking errors.
3. **Navigation smoke:** sidebar **Tenants** → Offboarding queue, Rapid create, Provisioning jobs; tenant Studio spine → Lifecycle / Offboarding / Provisioning.
4. **Back-to-top:** on any long manager or tenant page, confirm floating control bottom-right (dim at top, full after scroll).

`render.yaml` now ships explicit `TENANT_*` defaults on web + worker + beat (`TENANT_AUTO_PURGE_ENABLED=0` until legal signoff). Override secrets in the Render Dashboard only when policy changes.

## 2. Signup → verification email (live)

**Render env vars (canonical table):** [TENANT_OFFBOARDING.md § Render (Lane 2) — A. Signup verification email](TENANT_OFFBOARDING.md#render-lane-2--deploy-email-purge)

| Check | Action |
|-------|--------|
| Render env | Set `EMAIL_BACKEND` + `DEFAULT_FROM_EMAIL` + provider keys per offboarding doc § A (not console backend) |
| Email delivery | `https://manager.runmycampus.com/super/email/health/` — resolved config + **Run SMTP probe** |
| Signup diagnostics | `https://manager.runmycampus.com/super/signup/diagnostics/` — reachability + last attempts |
| Async send | Signup uses `send_transactional(..., async_send=True)` — monitor **Email delivery** for `EmailDeliveryEvent` → `ok=True` within ~2 min |
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

**Render env vars (canonical table):** [TENANT_OFFBOARDING.md § Render (Lane 2) — B. Offboarding + scheduled purge](TENANT_OFFBOARDING.md#render-lane-2--deploy-email-purge)

| Check | URL / action |
|-------|----------------|
| Offboarding queue | `https://manager.runmycampus.com/super/offboarding/` |
| Auto-purge banner | Shows **disabled** until `TENANT_AUTO_PURGE_ENABLED=1` (explicit `0` on Render until legal signoff) |
| Self-service | Tenant `/school/studio/offboarding/` → request closure → school appears in queue with **Due** when date passed |
| Dry-run | Queue → **Dry-run scheduled purges** |
| Manual apply | **Apply due purges (operator)** + confirm `purge-due-tenants` (when auto-purge off) |
| Tenant 360 | `/super/tenants/<uuid>/360/#offboarding` — export → schedule → typed-slug purge |

## 5. Optional production auto-purge

Only after export + legal review — set on Render (see [TENANT_OFFBOARDING.md § B](TENANT_OFFBOARDING.md#render-lane-2--deploy-email-purge)):

| Variable | Value |
|----------|--------|
| `TENANT_AUTO_PURGE_ENABLED` | `1` |
| `TENANT_AUTO_PURGE_GRACE_DAYS` | `30` (or policy) |
| `CELERY_BROKER_URL` | Redis (required for nightly beat) |

Celery beat `schools.run_scheduled_tenant_purges` runs nightly. Until then, keep `TENANT_AUTO_PURGE_ENABLED=0` and use operator manual apply.

## Evidence to file

Store screenshots or JSON under `var/evidence/tenant-lifecycle-lane2/<YYYY-MM-DD>/`:

- `signup-verify-redirect.json` (final URL after verify)
- `lifecycle-hub-percent.json` (API `GET /api/school/lifecycle/hub/`)
- `offboarding-queue-dry-run.json` (queue dry-run response)
