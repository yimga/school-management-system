# Platform superadmin access, break-glass, and account recovery

_Last updated 2026-07-05. Companion to `docs/OPERATOR_IMPERSONATION_AUDIT_DESIGN.md`
and `docs/SECURITY_KEYS.md`._

This is the source of truth for three related questions:

1. What can a **platform superadmin** access, and where are the deliberate limits?
2. How does **break-glass** into a tenant work, and is it audited?
3. If something terrible happens, **how are accounts recovered** (password / MFA / the
   last operator)?

---

## 0. Two authorities — do not conflate them

| | **Tenant owner / admin** | **Platform superadmin (operator)** |
|---|---|---|
| Identity | `SchoolMembership.is_school_owner` / `User.role = ADMIN` | `is_superuser=True` (and `User.role = SUPERADMIN`) |
| Home host | `<school>.runmycampus.com` | `manager.runmycampus.com` |
| Authorization gate | `tenant_admin_required` / `has_feature_permission` | `user_has_control_plane_access` |
| `is_staff`? | Not required (self-service owners lack it) | Yes (minted by `ensure_superuser`) |

`is_staff` is **not** an authorization signal on this platform — the platform mints
`is_staff=True` tenant admins, and self-service owners are minted `is_staff=False`.
Owners/admins are gated by `tenant_admin_required` (owner / role=ADMIN /
`settings.manage`); operators by the control-plane gate. See
`apps/accounts/decorators.py::user_is_tenant_admin`.

---

## 1. Platform superadmin god-mode

**Contract: a Django `is_superuser` account is never bounded by *authorization*.** Once
authenticated (incl. MFA — see §1.2), a superuser passes every authorization gate.

### 1.1 Where superuser already fast-allows (verified)
- Control-plane decorators — `require_control_plane_access` / `require_super_access[_with_host]`
  (via `user_has_control_plane_access`, `apps/schools/control_plane.py`).
- `permission_required` / `role_required` (`apps/accounts/decorators.py`) and every
  helper in `apps/accounts/permissions.py` (role checks, module access, student-data,
  invoice, grades).
- `User.has_feature_permission` (`apps/accounts/models.py`) — returns True for superusers.
- `has_school_permission` (`apps/schools/tenant_access.py`), ReBAC (`apps/accounts/rebac.py`).
- `ModuleAccessMiddleware` (and it fully bypasses on the manager host).
- Tenant-host access — **break-glass pass-through** (`TenantHostControlPlaneIsolationMiddleware`,
  audited; see §2.1).
- **PDP `decide()`** — added 2026-07-05 (`apps/policies/pdp.py::_subject_is_superuser`).
  The PDP defaults to `implicit_deny`; without a superuser branch, promoting it from
  advisory to hard-enforce would have denied the superadmin any resource lacking an
  explicit allow rule. The allow is still written to `PolicyDecisionLog` as a superuser
  allow.

### 1.2 Deliberate NON-bypasses (these are not authorization limits)
These are intentional and should **not** be removed to chase "no limits":

- **MFA wall** (`RequireMFAMiddleware`). A device-less superuser in strict mode is sent to
  MFA *enrollment*, not denied. Keeping MFA on the most powerful account is a security
  best practice; it gates *authentication*, not *access*. (If MFA is lost, see §3.2.)
- **RLS tenant scoping** (`apps/tenancy/middleware_rls_jwt.py`). A superuser's queries are
  row-scoped to the tenant they are *bound to*. Per-tenant browse works (break-glass);
  only a single-request **cross-tenant** query is row-filtered. This is tenant isolation,
  by design — cross-tenant reporting uses the operator surfaces, not raw tenant queries.
- **Tenant plan/entitlement gates** (`is_feature_enabled` / `billing.entitlements.can` /
  `platform_runtime.entitlement_gates.can_capability`). These answer "does *this tenant's
  plan* include the feature", not "may this *user* act". When a superadmin break-glasses
  into a tenant they see that tenant's real plan state — which is correct. To unlock a
  feature for a tenant, change the tenant's plan via the operator tools, don't special-case
  the gate.

Net: **superadmin authorization is unlimited; authentication (MFA) and tenant isolation
(RLS) remain, and plan features reflect the tenant's plan.**

---

## 2. Break-glass into a tenant

### 2.1 Raw superuser break-glass (fastest, full-write, audited)
A Django superuser may browse **any** tenant host directly — no token, no per-tenant
assignment, no consent. This is the "platform root never self-locks" path. Its control is
a throttled, PII-free audit line: `TenantHostControlPlaneIsolationMiddleware._audit_break_glass`
emits `logging.getLogger("security.break_glass").warning(...)` once per `(user, school)` per
hour (`_BREAK_GLASS_AUDIT_THROTTLE_SECONDS`). Full write access.

### 2.2 Signed impersonation "Open as school" (blessed, consented, read-only default)
For a named, consented, time-boxed session use the impersonation flow
(`apps/schools/super_views_impersonation.py::switch_to_tenant` →
`apps/accounts/views_impersonation.py::impersonate_entry`). Gates: control-plane access +
`platform.impersonate` scope → per-tenant assignment or JIT grant → optional dual-control
(four-eyes) → justification → principal consent. It mints a signed `TimestampSigner` token,
logs `ImpersonationLog.SWITCH` + `AuditLog` CRITICAL, and sets a session marker
`{school_id, actor_id, read_only, granted_at}`. Defaults **read-only**
(`ImpersonationReadOnlyGuardMiddleware` 403s writes on sensitive prefixes) and **expires**
after `IMPERSONATION_SESSION_MAX_AGE_SECONDS` (default 1h) via `_impersonation_expired`.

Use §2.2 for routine support (consented, audited, read-only); §2.1 is the emergency root path.

### 2.3 Step-up for sensitive actions (sudo)
Genuinely destructive/financial tenant-config actions (payout setup, integration
credentials, …) sit behind `@require_step_up()` (`apps/accounts/step_up.py`): a fresh
password + MFA re-confirm on the SAME session grants a short elevation window
(`STEP_UP_REAUTH_MAX_AGE_SECONDS`, default 10 min) — the `sudo` model, not a re-login.

---

## 3. Account recovery playbook

### 3.1 Forgotten password (self-service)
`/authentication/login/` → "Forgot password". `apps/accounts/password_reset.py::PortalPasswordResetForm`
accepts **username OR email** and, deliberately, also emails **never-activated owners**
(provisioned with `set_unusable_password`) — that is the recovery path when an onboarding
link expired.

### 3.2 MFA lockout (lost authenticator)
In order of preference:
1. **Backup codes** — the 10 one-time static codes issued at MFA setup. Enter one at the
   MFA prompt (`views_mfa`) or via `/authentication/mfa/...` regenerate while still signed in.
2. **Operator-assisted reset** — if backup codes are lost/exhausted, a platform operator
   (shell/deploy access) runs:

   ```
   python manage.py reset_user_mfa <username-or-email> [--yes]
   ```

   This removes the user's TOTP + backup + passkey devices
   (`apps/accounts/management/commands/reset_user_mfa.py`) and audits to
   `security.account_recovery`. On next login the user re-enrolls MFA fresh. This is the
   realistic recovery for a locked-out **owner** (who otherwise cannot reach `disable_mfa`,
   which is itself behind the login MFA gate).
3. **Last resort** — a superuser edits the user's devices directly (Django admin / shell).

### 3.3 Last operator locked out
The canonical platform admin (`CANONICAL_PLATFORM_ADMIN_USERNAME = "admin"`) is protected
from offboarding (`user_may_offboard_operator` returns False for it and for self), and a
superuser never self-locks. To recover privileged access (needs shell/deploy):

```
python manage.py ensure_superuser --username admin --password '<new>'   # create/promote + set password
python manage.py ensure_superadmin                                       # idempotent admin/admin for runbooks
python manage.py changepassword admin                                    # rotate an existing admin
```

`ensure_superuser` sets `is_staff + is_superuser + is_active + role=SUPERADMIN` and syncs the
`PlatformOperatorProfile`.

---

## 4. Honest deferrals (not yet built)
- **Self-service MFA recovery via email** (a signed "I lost my authenticator" link, like
  password reset) — today MFA-lockout recovery for an owner needs an operator (§3.2.2).
- **Signed offline break-glass bootstrap token** for a fully locked-out platform (all
  operators gone) without shell access — today recovery requires infra/shell (§3.3).
- **Reason prompt on raw superuser break-glass** (§2.1 is audit-only; §2.2 already prompts).

---

## 5. Related
- `apps/accounts/decorators.py` — `tenant_admin_required`, `user_is_tenant_admin`.
- `apps/accounts/step_up.py`, `apps/accounts/views_step_up.py` — sudo step-up.
- `apps/accounts/manager_login_next.py::use_operator_login_template` — tenant host never
  renders the operator login skin.
- `apps/policies/pdp.py` — PDP superuser god-mode.
- `docs/OPERATOR_IMPERSONATION_AUDIT_DESIGN.md`, `docs/SECURITY_KEYS.md`.
