# apps/accounts

> The `User` model, authentication (password / SSO / passkey / MFA), the RBAC
> role catalog, the ReBAC tuple store, and the operator/owner consoles.

**Tenancy:** SHARED (public schema; identity must resolve *before* a tenant schema is selected)
**Scale:** 18 models · 50 migrations · 121 test modules · ~53k LOC

## What this app owns

Accounts answers two questions for the whole platform: *who is this* and *may
they do this*. It owns `User` (the `AUTH_USER_MODEL`), every login path — email
backend, legacy-hash intake, OIDC, SAML, WebAuthn passkeys, MFA, step-up — and
both authorization models the platform runs: the RBAC catalog (`AccessRole` →
`Permission`) and a lightweight ReBAC tuple store (`RelationshipTuple`) that
runs alongside it.

It is **SHARED on purpose**. Identity has to resolve before django-tenants can
pick a schema, and one human can hold roles at several schools, so users cannot
live inside a tenant schema. The consequence is that tenant scoping here is
explicit and manual: rows that belong to a school carry a `school` FK
(`AccessRole`, `RelationshipTuple`, `SecurityAuditLog`, `UserTenantBinding`,
`DeviceRegistration`, …) and every query must filter on it. There is no schema
boundary catching your mistake.

The authorization story is deliberately consolidated. `effective_access.py` is
the **single** consumer entry point for access decisions — each function
delegates verbatim to the helper that owns the rule, so behavior is bit-identical
to the pre-facade call sites, but new enforcement layers wire in once instead of
across every view. `scripts/scan_access_resolver_fragmentation.py` is a CI
ratchet that counts direct calls to the underlying helpers and only lets that
number go down. RBAC and ReBAC dual-run: ReBAC `check()` is evaluated next to
RBAC and mismatches are logged rather than enforced, gated by
`RMC_REBAC_ENABLED` / `RMC_REBAC_DUAL_RUN_LOG_MISMATCH`.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `User` | `accounts_user` | The platform's `AUTH_USER_MODEL` (`models.py:182`, subclasses `AbstractUser`). Carries `role`, the Django authority flags (`is_staff` / `is_superuser` / `is_active`), and the Fernet-encrypted `legacy_*` columns used by the migration-cloud password-preservation path. |
| `Permission` | `accounts_permission` | Flat permission catalog keyed by `code`. |
| `AccessRole` | `accounts_accessrole` | RBAC role catalog. `school=NULL` = platform-wide template; `school` set = one tenant's catalog. |
| `RoleGroup` | `accounts_rolegroup` | Reusable bundle of roles an owner applies to people at once. |
| `TemporaryRoleGrant` | `accounts_temporaryrolegrant` | Time-limited grant; effective only while `valid_from <= now < expires_at`. |
| `RelationshipTuple` | `accounts_relationship_tuple` | `(school, subject, relation, object)` ReBAC edge in Postgres. |
| `Delegation` | `accounts_delegation` | Out-of-Office / Acting: delegator hands authority to a delegate for a date range. |
| `DelegationActionLog` | `accounts_delegationactionlog` | Every action a delegate performed as proxy. |
| `UserTenantBinding` | `accounts_usertenantbinding` | Binds a user to a school, tagged with its source (OIDC / SAML / manual). |
| `UserPasskey` | `accounts_userpasskey` | WebAuthn public key for biometric login. |
| `KnownLoginContext` | `accounts_known_login_context` | Device/network fingerprint previously seen for this user. |
| `SecurityAuditLog` | `accounts_securityauditlog` | Tenant-scoped security events: LOGIN, MFA_CHANGE, PWD_RESET, DATA_EXPORT, LOCKDOWN_TRIGGERED. |
| `DeviceRegistration` | `accounts_device_registration` | Registered client device; unique per `(school, user, device_id)`. |
| `OfflineCapabilityToken` | `accounts_offline_capability_token` | Short-lived offline authorization blob — **minted online only**. |
| `OfflineAccessIntent` | `accounts_offline_access_intent` | Low-risk IAM intent queued offline; applied only after a server `check()`. |
| `TenantStaffInvite` | `accounts_tenantstaffinvite` | School-scoped staff invite. |
| `FederationSsoHealth` | `accounts_federationssohealth` | Per-IdP last successful login vs failures. |
| `UserPreference` | `accounts_userpreference` | UI/UX preferences. **Not** theme — see the gotcha below. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `effective_access` | Canonical access facade — call this, never the helpers behind it |
| Module | `rebac` / `models_rebac` / `rebac_signals` | Tuple store, `check()`, RBAC dual-run, sync signals |
| Module | `superadmin_service` | Single source of truth for promoting/demoting a platform super-admin |
| Module | `decorators` | `role_required`, `require_permission`, `tenant_admin_required` — dual-role "hat" aware |
| Module | `middleware_impersonation_readonly` | Blocks writes during read-only impersonation; **flag-gated, default OFF** |
| Module | `iam_snapshot` | Signed read-only IAM snapshots pushed to devices |
| Module | `step_up` / `mfa_setup_flow` / `views_passkey` | Re-auth and second-factor flows |
| Module | `views_owner_console*` | Owner-facing people / roles / workflows / support consoles |
| Celery | `expire_past_delegations` | Revokes delegations past their end date |
| Celery | `prepare_rollover_proposal`, `apply_rollover_proposal` | Year-rollover proposal pipeline |
| Celery | `run_migration_async` | Async legacy-data migration runner |
| Celery | `sunset_stale_legacy_hashes_task`, `audit_encryption_key_orphans_task` | Legacy-hash / key hygiene |
| Celery | `watch_django_cryptography_upstream` | Upstream watch for the encrypted-field dependency |
| Command | `promote_superadmin`, `ensure_superadmin`, `ensure_superuser` | Operator bootstrap |
| Command | `sync_rebac_tuples`, `check_rebac_enforcement_readiness` | ReBAC backfill + pre-flight |
| Command | `backfill_user_roles`, `check_roles`, `list_expired_temporary_grants` | RBAC maintenance |
| Command | `rotate_encryption_keys`, `security_log_retention`, `reset_user_mfa` | Security ops |
| Command | `refresh_saml_idp_metadata`, `ensure_default_tenant_admin` | SSO / tenant setup |

## Before you change this

- **`role=SUPERADMIN` alone is not god-mode.** Django's operator surfaces gate on
  `is_superuser` / `is_staff`, and the RBAC role does not set them — assigning
  the role by itself produces a user who looks like a super-admin and is locked
  out. `superadmin_service` writes all four signals together (`is_staff`,
  `is_superuser`, `is_active`, `role`) precisely so nobody is half-provisioned.
  Go through it (or `manage.py promote_superadmin`); do not hand-set flags.
  Demotion deliberately clears **only** `is_superuser`/`is_staff` — never
  `is_active`, never a guessed replacement role.
- **Never call the access helpers directly.** Go through `effective_access`. The
  fragmentation scanner is a one-way ratchet: adding a direct call fails CI.
- **This app is SHARED — there is no schema boundary.** Any model with a `school`
  FK must be filtered by it in every query. A deliberate exception carries a
  `# tenant-isolation-allow: <reason>` marker (e.g. the parent multi-school
  membership switch, which is user-scoped by design).
- **`AccessRole.school=NULL` means platform template, not "no school".** Filtering
  a tenant's role catalog with a bare `.filter(school=school)` silently drops the
  legacy global templates; forms scope via a roles-queryset-for-school helper.
- **Devices never write ReBAC tuples offline.** They receive *signed, read-only*
  snapshots (`iam_snapshot`), and `OfflineAccessIntent` rows are only applied
  after a server-side `check()`. `OfflineCapabilityToken` is minted online only.
  Keep that direction of trust.
- **`middleware_impersonation_readonly` is a no-op unless
  `IMPERSONATION_READ_ONLY_ENFORCED` is truthy.** That default is intentional: a
  misjudged allowlist would block legitimate operator support actions, so it is
  wired into MIDDLEWARE but switched on only after request-path verification. The
  allowlist must always retain the URL names an operator needs to *exit* the
  session.
- **Theme preference does not live on `UserPreference`.** It lives on
  `DashboardUserPreference`, which is what the context processor reads. Adding a
  theme field here creates a second, silently-ignored source of truth.
- **`role_required` resolves dual-role "hats".** A user whose primary role is not
  `PARENT`/`TEACHER` can still pass those checks via `has_parent_hat` /
  `has_teacher_hat`. Teacher-and-parent is a real, supported person; do not
  "simplify" this to a primary-role equality check.
- **`ready()` imports three signal modules** (`signals`, `rebac_signals`,
  `signals_access`) for their side effects. `signals_access` is what makes
  role/permission changes propagate to open sessions in real time — dropping an
  import silently staleness-freezes access.
- Legacy `User.legacy_*` columns are **Fernet-encrypted field descriptors**,
  imported eagerly (not lazily) so `makemigrations` deconstructs them correctly.
  Moving that import breaks schema generation.
