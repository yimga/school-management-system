# Operator Identity 10× Plan — Platform Team Hub

**Status:** **DONE (Lane 1, repo-scope)** — batches **1493–1497** complete; **OPERATOR_IDENTITY_HUB_PASS**
**Plan owner:** RunMyCampus platform security / control plane
**Created:** 2026-05-24
**Target SW:** `sms-v3.90.35-operator-identity-10x-hub-2026-05-24`
**Batch IDs:** **1493** (foundation) → **1494** (gates) → **1495** (lifecycle) → **1496** (governance) → **1497** (break-glass + docs)

**Cross-links:**

- [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4 batches **1493–1497**
- [`docs/PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md`](../PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md)
- [`docs/CONTROL_PLANE_AND_PLATFORM_ADMIN.md`](../CONTROL_PLANE_AND_PLATFORM_ADMIN.md)
- Mechanical gate: `scripts/verify_operator_identity_hub.py`

---

## 0 — Executive summary

Platform operators (manager host / `/super/`) now have a first-class **Team & identity** hub at `/super/team/` with tiered `platform.*` scopes, invite/accept/offboard lifecycle, dual-control promotion, MFA gate on manager, break-glass User admin scoped to operators only, and impersonation peer picker wired to the operator roster.

| Layer | Before | After |
|-------|--------|-------|
| Roster | CLI `ensure_superuser` + break-glass Django admin | `/super/team/` paginated roster + detail |
| Scopes | Implicit superuser / SUPERADMIN role | `PlatformOperatorProfile.tier` → `platform.*` scopes |
| Lifecycle | Manual | Invite link → accept → MFA → promote (peer) → offboard |
| MFA | Generic staff MFA | `OperatorMfaRequiredMiddleware` on manager `/super/` + `/admin/` |
| Impersonation peer | Free-text email | Roster-backed `<select>` + `platform.impersonate` check |
| Feedback `is_operator` | Any `is_staff` | `user_is_platform_operator()` only |

**Program verdict:** **OPERATOR IDENTITY 10× — REPO SCOPE** (Lane 2: live manager-host MFA enrollment smoke optional).

---

## 1 — Architecture (do not relitigate)

1. **`User` stays global** — operator plane = `PlatformOperatorProfile` + `platform.*` scopes (separate from tenant RBAC).
2. **Outer gate:** `user_has_control_plane_access()` — superuser, env `CONTROL_PLANE_OPERATOR_ROLES`, or active/invited profile.
3. **Inner gates:** `@require_platform_scope(...)` on `/super/team/*` views.
4. **Tiers:** observer, support, fleet, billing, security, principal, break_glass — mapped in `apps/platform_runtime/operator_identity.py`.
5. **Dual control:** `PlatformOperatorPromotionRequest` requires peer with `platform.team.promote`; impersonation peer requires `platform.impersonate`.

---

## 2 — Deliverables (1493–1497)

### Batch 1493 — Foundation

- `PlatformOperatorProfile`, `PlatformOperatorInvite`, `PlatformOperatorPromotionRequest`
- Migration `0074_platform_operator_identity.py` + superuser backfill
- `apps/platform_runtime/operator_identity.py` scope helpers

### Batch 1494 — Gates + MFA

- `OperatorMfaRequiredMiddleware` + `OPERATOR_MFA_REQUIRED_ON_MANAGER` setting
- `@require_platform_scope` on team views
- `user_has_control_plane_access()` extended for profile holders

### Batch 1495 — Lifecycle UI

- `/super/team/` roster, detail, invite, offboard, revoke sessions
- `/authentication/operator-invite/<token>/` accept flow
- Templates under `templates/schools/super_operator_team_*.html`

### Batch 1496 — Governance

- `/super/team/promote/` + peer decide
- Impersonation peer picker on super dashboard + scope validation
- Nav: `control_plane_nav.py` + platform operator hub tile

### Batch 1497 — Break-glass + verification

- `PlatformUserAdmin` — platform admin User changelist filtered to operators
- `is_operator()` in feedback uses `user_is_platform_operator`
- Platform admin registration for identity models
- `scripts/verify_operator_identity_hub.py` + `test_operator_identity.py`

---

## 3 — Verification gates

```bash
python manage.py migrate platform_runtime
python scripts/verify_operator_identity_hub.py
python scripts/scan_operator_shell_dead_hrefs.py --strict
python manage.py check
```

**Expected:** `OPERATOR_IDENTITY_HUB_PASS`, dead hrefs **0**, migrations applied.

---

## 4 — Honest deferrals

- Env-level `CONTROL_PLANE_OPERATOR_ROLES` promotion still requires operator runbook (UI records tier, not env flip).
- Lane 2 Playwright: manager-host MFA redirect + invite accept E2E.
- Per-operator session listing at scale (current detail view scans up to 200 sessions).

---

## 5 — Deploy

1. Run migration `0074_platform_operator_identity`.
2. Bump SW (included in this wave).
3. Confirm `OPERATOR_MFA_REQUIRED_ON_MANAGER=1` on manager production (default on).
4. Seed break-glass superusers receive `break_glass` tier via backfill.
