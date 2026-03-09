# SINGLE_TENANT Flag — Multi-Tenant Production

**Purpose:** Document the `SINGLE_TENANT` setting so operators never enable it in multi-tenant production.

---

## What it does

- **Where:** `apps.schools.middleware` (`_get_single_tenant_school`), `apps.schools.tenant_url.py`.
- **Effect:** When `SINGLE_TENANT=1` (or `true`/`yes`), the app resolves the **only** active school on the main URL (no subdomain required). Used for backward-compatible single-school deployments and tests.
- **Risk:** In a **multi-tenant** deployment, if `SINGLE_TENANT` is enabled, the main host will always resolve to one school and other schools may be inaccessible or behaviour becomes undefined.

---

## Rule for production

**For multi-tenant production (more than one school on the platform):**

- Set **`SINGLE_TENANT=0`** (or leave it unset / false).
- Do **not** set `SINGLE_TENANT=1` or `true` on any environment where multiple tenants (schools) are expected.

**For single-school or test environments only:**

- `SINGLE_TENANT=1` is acceptable when there is exactly one active school and you want the main domain to map to that school without a subdomain.

---

## Verification

- Check `.env` and deployment config: `SINGLE_TENANT` must not be `1`/`true`/`yes` in multi-tenant production.
- Optional: add a deployment or health check that fails if `SINGLE_TENANT` is set and more than one active school exists.

---

**See also:** `QUICK_REFERENCE_MULTI_TENANT.md`, `apps/schools/middleware.py`, `PLATFORM_TRANSITION_FORENSIC_REPORT.md`.
