# Owner Identity & Console — design doc

Status: **active build** · Owner-approved (Option A, full program) · 2026-07-03
Proposal + HTML samples: `_RMC_FIX_REVIEW_2026-07-03/OWNER_CONSOLE_PROPOSAL.html`

## 1. What we're building and why

The school **creator** should be able to do *everything* in their tenant on day one,
then delegate downward (assign superadmins, co-owners, granular roles) or transfer the
school outright. Today that power is real but scattered across a dozen backend pages,
and there is no first-login moment that tells a new owner "you own this — here's how to
run it or hand it off".

We build a **tenant-scoped Owner Console**: a first-class command center that matches the
operator control-plane in polish, but is **tenant-skinned (light + indigo)** so it can
never be mistaken for — or route into — the operator's dark `/super/` plane. The owner is
a true tenant-superuser inside it; delegation and transfer live in one place.

### Locked decisions (owner, 2026-07-02 / 07-03)
- **Full tenant-superuser by default + granular delegation.** Creator can do everything,
  then reassign.
- **One designed program** (design doc + first slice, then iterate) — not piecemeal.
- **No `is_staff` / `is_superuser` grant. No Django `/admin/` for owners.** The owner is a
  tenant-superuser via the access-role graph only. This is the isolation guarantee.

## 2. Audit first — what ALREADY exists (do not rebuild)

This is a **surface-and-fill** program, not a from-scratch build. The ownership spine is
already in the codebase and CI-gated:

| Capability | Where it lives today | Status |
|---|---|---|
| Per-school owner flag (transferable, multi-owner, last-owner guard) | `apps/schools/models.py::SchoolMembership.is_school_owner` + `owner_memberships()` / `is_owner()` | **Built** |
| Grant co-owner / revoke / **transfer** ownership / suspend / reactivate / offboard | `apps/accounts/views_tenant_identity.py` (owner-gated via `_is_school_owner`) | **Built** |
| Staff roster + per-user detail + invite (emailed) + regulator grant | `views_tenant_identity.py::tenant_identity_roster` / `_detail` / `_invite` | **Built** |
| Ownership-change audit trail (PII-free) | `SecurityAuditLog.EventType.OWNERSHIP_CHANGED` + `_audit_ownership` | **Built** |
| First-run owner onboarding wizard (account → school → launchpad) | `apps/accounts/views_owner_onboarding.py` (post-signup-verify, token-authed) | **Built** |
| Per-role first-run welcome card / guided tour infra | `apps/dashboard/first_run_zero_state.py` + `context_processors.py` | **Built** (reused) |
| Tenant⟂operator isolation | `verify_backend_base_shell_routing.py` (CI gate) | **Built** |

### What is genuinely NEW (the gaps this program closes)
1. **First-login role confirmation** — a one-time "you're the owner" moment: confirm /
   assign a superadmin / decide later. (Slice 1.)
2. **The Owner Console shell + Overview** — a coherent tenant-skinned home that unifies the
   existing surfaces above instead of scattering them. (Slice 2.)
3. **Bulk multi-role assignment + Role groups** — today role assignment is one-user /
   one-role; owners want to select many people and apply a bundle of roles at once. (Slice 3.)
4. **Console sections** — Modules / Billing / Data & Export / Branding / Audit surfaced in
   the shell, each gated on real tenant-superuser powers with a safe hard-floor. (Slice 4.)

## 3. Isolation guarantees (non-negotiable, unchanged)

- **No `is_staff` / `is_superuser`.** Owner authority comes from `SchoolMembership.is_school_owner`
  + the access-role graph (`has_feature_permission`), never Django staff status.
- **Tenant-host only.** The console lives under the tenant urlconf
  (`<school>.runmycampus.com/portal/owner/…`) — no route into `/super/`. Enforced by
  `verify_backend_base_shell_routing.py`.
- **Scoped by construction.** Every query is tenant-scoped; an owner sees only their own
  school's people, data and billing.
- **Light ≠ dark.** The console is tenant-skinned (indigo/light) vs the operator plane's
  dark chrome — a human can tell them apart at a glance.

## 4. Phasing

| Slice | Deliverable | New surface | Migration |
|---|---|---|---|
| **S1** | First-login owner confirmation card (confirm / assign superadmin / defer) | `partials/owner_first_login_card.html` + `owner_first_login.py` + `owner_confirm_role` view | none (state in `DashboardUserPreference`) |
| **S2** | Owner Console shell + Overview | `/portal/owner/` landing, tenant-skinned | none |
| **S3** | People & Roles (surfaces existing hub) + bulk multi-role + `RoleGroup` | `BulkUserRolesForm` role→roles, `RoleGroup` model unioned in `effective_access.py` | 1 (RoleGroup) |
| **S4** | Modules / Billing / Data / Branding / Audit sections | console sub-pages | as needed |

### Slice 1 — first-login owner confirmation (this commit)

- **Gate** (`owner_first_login.build_owner_first_login_card`): authenticated · on the
  `accounts:backend_dashboard` landing · `SchoolMembership.is_owner(user, school)` ·
  not yet acknowledged. Fail-soft — any error yields `None`.
- **State**: `DashboardUserPreference.dashboard_layout["owner_role_ack_<school_id>"]` =
  `"confirmed"` | `"deferred"` (no migration; mirrors the tour-completion pattern).
- **Actions**:
  - *Yes, I'll run it* → POST `accounts:owner_confirm_role` (`decision=confirm`) → stays owner.
  - *Assign a superadmin* → existing `accounts:tenant_identity_invite`.
  - *Decide later* → POST `accounts:owner_confirm_role` (`decision=defer`) → dismiss;
    delegation is always reachable from the identity hub / console afterward.
- **Render**: `partials/owner_first_login_card.html` (fixed-position, tenant-skinned modal),
  included in the peer-clean `templates/accounts/backend_dashboard.html`; styling in
  `static/css/owner-first-login.css` (theme-aware tokens only — dark/light readable).
- No `is_staff` is ever granted — the card only *reflects* the owner's existing authority.
