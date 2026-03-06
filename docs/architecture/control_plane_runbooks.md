# Control Plane Runbooks (12.7, Section 25.4)

**Purpose:** Operator and SRE procedures for the manager/super control plane. Aligns with Section 25.4 (Observability/SRE) and Checklist 12.7 (control plane hardening).

**Audience:** Super Admins, operators, support.

---

## 1. Access and security

- **Who can use /super/:** Users with `is_superuser=True` or `role == 'SUPERADMIN'`.
- **Defense in depth:** All super views are wrapped with `require_super_access` (see `apps/schools/control_plane.py`); `TenantSuperAdminRequiredMiddleware` enforces the same rule at middleware level.
- **Rate limiting:** `/super/` is limited to **120 requests per user per minute** (cache key `super_rl:{user_id}:{YYYYMMDDHHMM}`). When exceeded, responses are **429 Too Many Requests** with `Retry-After: 60`.
- **Audit:** Sensitive actions are written to `AuditLog` (app_label `schools`): school approve, school create, impersonation switch, sync repair force overwrite.

---

## 2. Approve a school

**When:** A school has been created (e.g. via Create School wizard or API) and is pending approval (`is_approved=False`), and you need to approve it.

**Steps:**

1. Log in as a Super Admin and open the control plane (e.g. `/super/`).
2. Go to Command Center or the school’s timeline (e.g. from dashboard or Create School flow).
3. Use the **Approve** action for the school (e.g. POST to `/super/api/schools/<school_id>/approve/`).
4. Confirm the school’s `is_approved` is set to `True` (e.g. in Django admin or timeline).

**Audit:** Action `APPROVE` on model `School` is logged to `AuditLog` with sensitivity HIGH.

**Rollback:** Manually set `school.is_approved = False` and save (use admin or shell). Re-audit if required by policy.

---

## 3. Create a school

**When:** You need to provision a new tenant school via the control plane.

**Steps:**

1. Log in as Super Admin; go to `/super/create/` (Create School wizard).
2. Fill required fields (e.g. name, contact email, region/country, education profile). Optional: slug, subdomain, plan, addons, custom domain.
3. Submit. The app creates a `School` row (typically `is_active=False` until provisioning completes) and enqueues provisioning (Celery or sync fallback).
4. Check timeline: `/super/api/schools/<school_id>/timeline/` (or link from dashboard) for events (REQUEST_RECEIVED, QUEUED, etc.).
5. If approval workflow is enabled, approve the school (see **Approve a school** above).

**Audit:** Action `CREATE` on model `School` is logged to `AuditLog` with sensitivity HIGH.

**Troubleshooting:** Check `SchoolProvisioningEvent` for the school; check Celery logs if provisioning is async. For duplicate slug/subdomain, fix input and retry create.

---

## 4. Switch to tenant (impersonation)

**When:** You need to act in the context of a specific school (e.g. support or debugging).

**Steps:**

1. Log in as Super Admin; ensure the school is active and (if `JIT_IMPERSONATION_REQUIRE_CONSENT` is True) that the school has granted impersonation consent and it has not expired.
2. From the super dashboard or command center, use **Switch to tenant** (e.g. POST to `/super/switch-to-tenant/` with `school_id`).
3. You are redirected to the tenant’s impersonation entry URL with a short-lived signed token. An `ImpersonationLog` entry (action SWITCH) is created, and an `AuditLog` entry (VIEW on School, reason “Impersonation switch”) with sensitivity CRITICAL is written.
4. To stop impersonating, use the tenant UI’s “Exit impersonation” (or equivalent) to return to the control plane.

**Audit:** Impersonation is logged in `ImpersonationLog` and in `AuditLog` (control plane action).

**Security:** Impersonation is restricted to Super Admins; consent and optional expiry are configurable.

---

## 5. Sync repair (force overwrite conflict)

**When:** A school has sync conflicts (e.g. client vs server data) and you have decided to apply the client version.

**Steps:**

1. Log in as Super Admin (sync repair also requires `is_superuser`).
2. Open `/super/sync-repair/<school_id>/`.
3. Review the list of pending conflicts (entity type, client vs server data).
4. For the chosen conflict, submit **Force Overwrite** (POST with `conflict_id`). The app applies `client_data` to the entity and marks the conflict RESOLVED_CLIENT inside a transaction.
5. An `AuditLog` entry is written (UPDATE on `SyncConflict`, sensitivity HIGH, reason “Sync repair force overwrite (client applied)”).

**Rollback:** Not automatic. Restore from backup or correct data manually if the overwrite was wrong; document in your change process.

---

## 6. Rate limit 429 on /super/

**Symptom:** User receives **429 Too Many Requests** when using `/super/` (browser or API).

**Cause:** More than 120 requests in one clock-minute for that user (SuperAdminRateLimitMiddleware).

**Actions:**

- Wait 60 seconds and retry (response includes `Retry-After: 60`).
- If legitimate high usage is required, consider increasing `SuperAdminRateLimitMiddleware.MINUTE_LIMIT` in `apps/schools/middleware.py` and redeploy, or introduce a separate limit for specific endpoints.

---

## 7. Disable Super Admin UI

**When:** You want to turn off access to the super admin UI (e.g. for compliance or maintenance).

**Steps:**

1. In Django admin (or data migration), open **Site settings** (singleton).
2. Set `backend_feature_flags.enable_super_admin_ui` to `false`.
3. Save. `TenantSuperAdminRequiredMiddleware` will return 403 for all `/super/` paths except `/super/parent-tenant/` (which may still be allowed for parent-tenant users).

**Re-enable:** Set `enable_super_admin_ui` back to `true`.

---

## 8. Marketplace (blueprint / app) actions

**Where:** `/super/marketplace/`, `/super/marketplace/blueprints/`, `/super/marketplace/apps/`.

**Access:** Same Super Admin requirement; marketplace views use their own `_control_plane_access` and permission checks.

**Procedures:** Apply blueprint pack, preview, rollback, and app catalog actions are documented in the marketplace and blueprint docs (e.g. phase6 marketplace, blueprint registry). Sensitive actions there should be audited per your audit policy (extend `log_control_plane_action` if needed).

---

## 10. RPO/RTO and restore testing (Part F 17.5)

**RPO (Recovery Point Objective):** Maximum acceptable data loss (e.g. 4 hours). Backups and WAL/streaming replication should support this.

**RTO (Recovery Time Objective):** Maximum acceptable downtime (e.g. 1 hour). Restore and failover procedures must complete within this.

**Configuration:** Document target RPO/RTO in deployment runbook (e.g. `RPO_HOURS=4`, `RTO_HOURS=1`). Restore testing: run from backup at least quarterly; record results in audit/runbook log.

**DR playbooks:** For database restore, use provider-specific procedures (e.g. PostgreSQL PITR, managed DB restore). For tenant schema restore, use schema provisioning job and tenant-aware migrations.

---

## 11. References

- **Checklist 12.7:** Control plane hardening (permission checks, rate limiting, audit logging, runbooks).
- **Section 25.4:** Observability/SRE — logging, metrics, tracing, SLOs, runbooks, synthetic monitoring.
- **Section 25.5:** Security baseline — rate limiting, audit.
- **Code:** `apps/schools/control_plane.py`, `apps/schools/super_views.py`, `apps/schools/super_urls.py`, `apps/schools/middleware.py` (TenantSuperAdminRequiredMiddleware, SuperAdminRateLimitMiddleware), `apps/compliance/models_audit.py` (AuditLog).
