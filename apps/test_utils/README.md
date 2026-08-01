# apps/test_utils

> Shared HTTP test clients that log a user into the manager (control-plane) host
> or a tenant host with the MFA + session guards already satisfied — so a test
> can reach the page under test instead of re-deriving the auth dance each time.

**Type:** support library — **not** an installed Django app. It has no models, no
schema, and no `AppConfig`, and it does not appear in `INSTALLED_APPS`. It is a
test-only helper package imported by test modules across the suite.

## What this app owns

`test_utils` owns the *correct* way to obtain an authenticated `django.test.Client`
for each host class, because getting there is genuinely non-trivial: operator
pages sit behind `RequireMFAMiddleware` (a confirmed TOTP device **and** a
per-session `mfa_verified` flag), the manager host reads a separate session cookie
(`MANAGER_SESSION_COOKIE_NAME`), and a tenant-admin reaching a control-plane page
rendered on the tenant shell must also pass `OperatorTenantConfinementMiddleware`
(which redirects a control-plane user with no `SchoolMembership` away to
`manager/super/`). Each helper encodes exactly those preconditions so tests assert
behaviour, not boilerplate — and so a middleware change breaks one helper instead
of a hundred tests.

## Key modules

| Module | Purpose |
| --- | --- |
| `http_clients.py` | `login_manager_client` (MFA-armed operator on the manager host), `login_tenant_client` (tenant user, optional `mfa_verified`), `login_tenant_admin_client` (tenant-host admin with a `SchoolMembership` + confirmed device, for operator pages on the tenant shell). |

## Before you change this

- **These helpers mirror live middleware; keep them in step.** They exist because
  the real request path enforces MFA, session pinning, manager-cookie binding, and
  operator/tenant confinement. If those guards change, fix the helper — do not
  weaken it to make a test pass.
- **Default the admin role via the `User.Role.ADMIN` constant, not a `"ADMIN"`
  literal.** This keeps a role rename refactor-safe and the role-string ratchet
  clean.
- **`login_tenant_admin_client` gives a superuser the break-glass path** (no
  membership required); a non-superuser gets a `SchoolMembership` so
  `user_has_control_plane_access` resolves correctly. Preserve that split.
- **Test-only.** Nothing here may be imported by application code under `apps/`
  outside a `tests/` package.
