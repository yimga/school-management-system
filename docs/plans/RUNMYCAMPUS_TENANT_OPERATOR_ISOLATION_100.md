# RunMyCampus — Tenant ⟂ Operator Isolation to Certified 100% (Implementation Prompt)

> **Companion audit (read first):** `docs/generated/tenant_operator_isolation_forensic_audit_2026_07_04.md`.
> This plan closes the 7 confirmed gaps (H1–H7) that audit found, and turns the "no mingling, ever" guarantee from *structurally true today* into *CI-certified and regression-proof*.

## The one-paragraph brief you can paste to Claude Code

```text
Implement docs/plans/RUNMYCAMPUS_TENANT_OPERATOR_ISOLATION_100.md wave by wave, in order,
audit-first. The goal: a tenant identity or session can NEVER cross into operator authority,
and this is proven by wired CI gates, not convention. Do NOT rip out the sound isolation spine
(Part A of the companion audit) — user_has_control_plane_access, the host-split urlconfs, the
signed impersonation flow, the websocket room scoping. PRESERVE and CERTIFY them. Every fix must
be tenant/platform-WIDE (fix the class, not one site) and land with its own regression test and,
where the wave says so, a wired CI gate. Never grant is_staff/is_superuser to owners, never add a
Django /admin/ path for owners, and keep the owner gate (SchoolMembership.is_active_owner) disjoint
from the operator gate (user_has_control_plane_access). Path-scoped git only; FF-only; bump the
service-worker CACHE_VERSION on any CSS/JS wave. Do not claim a wave done until its acceptance gate
runs green and you paste the evidence.
```

---

## Prime directives (non-negotiable — do not relitigate)

1. **The disjointness invariant is sacred.** `user_has_control_plane_access` (`apps/schools/control_plane.py:77`) must keep returning **False for any user with a `SchoolMembership`** before consulting roles. No new code path may bridge the owner gate (`SchoolMembership.is_active_owner`) to the operator gate. If a change would let a tenant identity satisfy any operator check, it is wrong by definition.
2. **`is_staff` is NOT an operator signal.** The platform deliberately mints `is_staff=True` tenant admins (`ensure_default_tenant_admin.py:131`, `create_teacher_parent_accounts.py:127`). Therefore `@staff_member_required` / bare `user.is_staff` must never be the sole gate on anything operator-flavored, and never on any view reachable from `config/tenant_urls.py`.
3. **Preserve, don't replace.** Do not rewrite tenant middleware, the urlconf split, the impersonation flow, the AI gateway, or the websocket consumers. Extend the existing `.rmc-*`/gate/scanner grammar; add gates alongside the reference-integrity family, don't fork a parallel system.
4. **Fix the class, gate the class.** Every finding is representative of a class. Enumerate the whole class, fix all of it, then add a CI gate so the class can never regrow. A one-site patch without a gate is a rejected fix.
5. **Audit-first per wave.** Before editing, enumerate the real sites (grep/AST) and write them into the wave's PR description. No blind sweeps.
6. **Evidence or it didn't happen.** A wave is done only when its acceptance command runs green and the output is pasted. Never trust `$?` after a pipe; never tail-pipe test evidence.

---

## Wave 1 — Seal the `is_staff`-as-operator-gate class (closes **H1**) — **P0**

**Objective:** no view reachable from the tenant host may be gated only by `is_staff`/`is_superuser`; operator-flavored views get the control-plane gate; tenant-admin tools get a proper non-`is_staff` tenant permission.

**Repo-controlled tasks:**
1. **Enumerate the class.** Build the set of URLconf modules `include()`d (transitively) from `config/tenant_urls.py` (start: `apps/assist_dock/urls.py:561`, `apps/migration_cloud/urls_connectors`, and every other `include(...)` in that file). For each view they route, record its auth decorator/mixin. Flag every view whose only gate is `@staff_member_required`, `staff_member_required`, `user_passes_test(lambda u: u.is_staff)`, or a bare `request.user.is_staff`/`is_superuser` body check.
2. **Re-gate each flagged view by intent:**
   - *Operator-flavored* (introspection, impersonation, platform config, cross-tenant data): replace with `require_control_plane_access` / `require_platform_scope(<scope>)` from `apps/schools/control_plane.py` / `apps/platform_runtime/operator_identity.py`. Confirmed sites: `apps/assist_dock/power_views.py:113 inspect_landing` and `:138 impersonate_landing` — an `is_staff` tenant admin can currently open `/assist/inspect/` and read routing/auth internals + `site_settings` key names. Re-gate both to control-plane access (or drop them from the tenant mount).
   - *Genuine tenant-admin tools* that happen to use `is_staff`: re-gate to a tenant permission that is NOT `is_staff` (e.g. `SchoolMembership.is_active_owner` / an admin-role check / `has_school_permission`), so a real tenant admin keeps access without leaning on the overloaded flag.
3. **Do NOT remove the `# rbac-allow:` markers blindly** — update each to reflect the new, correct gate.
4. **Verify the migration_cloud connector mount** (`urls_connectors` on the tenant host): confirm every view there is tenant-scoped (reads only `request.school`) and carries no cross-tenant operator capability. If any operator-only view leaked into `urls_connectors`, move it to the operator urlconf.

**New CI gate (the class-seal):** `scripts/scan_staff_gate_on_tenant_surface.py` — stdlib AST, deps-free (runs in the `architectural-boundaries.yml` boundary job). It resolves the transitive `include()` tree from `config/tenant_urls.py`, then fails if any view in that tree is gated only by `staff_member_required`/`is_staff`/`is_superuser` without a recognized control-plane signal (`require_platform_scope`, `require_control_plane_access`, `user_has_control_plane_access`) OR an explicit `# tenant-surface-staff-allow: <reason>` marker. Baseline 0 after Wave 1 burndown. Wire it into `architectural-boundaries.yml` **and** add it to `verify_ci_gate_wiring.py`'s `REQUIRED_GATES`.

**Tests:** a `TransactionTestCase` proving (a) a `role=ADMIN, is_staff=True` tenant user on a tenant host gets 403 on each re-gated operator view, and (b) a legitimate control-plane operator gets 200. Add a unit test locking `inspect_landing`/`impersonate_landing` deny an `is_staff` tenant admin.

**Acceptance gate:** `python scripts/scan_staff_gate_on_tenant_surface.py --strict` → 0; the new tests green; `verify_ci_gate_wiring.py` green.

**Claims not allowed until evidence:** "no is_staff operator surface on the tenant host" until the scanner is green AND wired.

---

## Wave 2 — Revive the dead operator→tenant isolation middleware (closes **H2**) — **P1**

**Objective:** the operator→tenant confinement + read-only guard that the code *intends* actually runs.

**Repo-controlled tasks:**
1. Fix the dead discriminator in `apps/accounts/middleware.py` at `:447` (`TenantHostControlPlaneIsolationMiddleware`) and `:557` (`ImpersonationReadOnlyGuardMiddleware`): `public_host_kind` never equals `"tenant"`. Replace `!= "tenant"` with the real tenant-host condition. Preferred: have `UrlConfSwitcherMiddleware` (`apps/schools/middleware.py:637-661`) set a positive `request.is_tenant_host = True` on the tenant fall-through branch, and key both middlewares off that. Fallback: `public_host_kind is None and getattr(request, "school", None) is not None`.
2. Re-confirm the ALLOWED path/prefix lists still make sense once the body executes (impersonate/end/logout/static/health).
3. Confirm the middleware order still places these *after* `TenantMiddleware` (so `request.school` is set) — it does today.

**Tests:** prove that on a real tenant host (a) a `SUPERADMIN`-role operator *without* a matching `session["impersonation"]` is redirected to `/super/`, (b) *with* a matching impersonation session is allowed, (c) a superuser is exempt (break-glass), (d) a normal tenant user is untouched. Add a guard test asserting the discriminator is not the literal `"tenant"` (regression seal for the dead-code class).

**Acceptance gate:** the four-case middleware test green; `python manage.py check` clean.

---

## Wave 3 — Host-header hardening at ingress (closes **H3**) — **P1**

**Objective:** host classification (which selects tenant vs operator urlconf) is not attacker-controllable via `X-Forwarded-Host`.

**Repo-controlled tasks:**
1. In `apps/schools/middleware.py:319-333 _request_host_raw` (and the twin in `apps/schools/channels_tenant_middleware.py:20-29`): stop trusting the *first* `X-Forwarded-Host` token blindly. Take the **last** hop, or validate the resolved host against the canonical base-domain set / `ALLOWED_HOSTS` before allowing `manager`/operator classification. Keep tenant-subdomain resolution working (custom domains, `*.runmycampus.com`).
2. Add a settings-driven trusted-proxy toggle if needed (`TRUSTED_HOST_HEADER_PROXY`), defaulting to the safe behavior. No hardcoding.
3. Document the Render edge assumption in `docs/` — whether the platform edge strips client `X-Forwarded-Host`. This is the external-owner half: confirm the proxy config actually strips/normalizes the header (record as external evidence, do not claim done from code alone).

**Tests:** a request with a forged `X-Forwarded-Host: manager.<base>` from a tenant subdomain must NOT be classified `manager` (must not select `config.manager_urls`). A legitimate manager-host request still classifies `manager`.

**Acceptance gate:** the spoofing test green; existing tenant-resolution tests (`apps/tenancy/`, `apps/schools/`) still green.

---

## Wave 4 — Wire the unwired gates + build the two missing gates (closes **H4**) — **P0 for certification**

**Objective:** every boundary axis has a wired CI gate; a regression on any axis fails a PR.

**Repo-controlled tasks:**
1. **Wire the four dormant verifiers** into `architectural-boundaries.yml` (or the appropriate workflow), each as its own job/step, and add each to `verify_ci_gate_wiring.py`'s `REQUIRED_GATES`:
   - `verify_super_platform_scope_coverage.py`
   - `verify_tenant_offboarding_operator_only.py`
   - `scan_access_resolver_fragmentation.py` (also **fix the CLAUDE.md doc drift** — it currently claims this is wired when it is not).
   - `verify_super_tenant_shell_aggressive.py`
2. **De-hardcode `verify_super_platform_scope_coverage.py`.** Replace the hardcoded 33-view allowlist with an AST enumeration of every view routed by `config/manager_urls.py` + the `super:` namespace, asserting each carries `@require_platform_scope`/`require_control_plane_access` (or a reviewed `# super-scope-allow: <reason>`). A 34th operator view must fail the gate automatically.
3. **Build the end-to-end negative gate** `scripts/verify_tenant_cannot_reach_operator_routes.py` (runtime, in `ci.yml::django-tests`): enumerate **every** URL pattern in `config/manager_urls.py` + every `super:`-namespaced route, and assert that a synthetic authenticated **tenant** user (`role=ADMIN`, `is_staff=True`, with a `SchoolMembership`) receives 403/redirect (never 200 / never operator data) on each — both on the tenant host and on the manager host. This is the single "a tenant session cannot reach ANY operator route" proof the audit found missing. Baseline: all-denied.
4. **Build the template-link gate** `scripts/scan_tenant_template_operator_links.py` (stdlib, deps-free): flag any `{% url 'super:…' %}` / `{% url 'manager_…' %}` / hardcoded `/super/` in a non-operator template subtree unless it sits inside a `public_host_kind == 'manager'` guard (or carries `<!-- operator-link-allow: <reason> -->`). Baseline 0 (the ~10 current shared-shell sites are all correctly guarded — verify and let them pass).
5. Add all new gates to `verify_ci_gate_wiring.py::REQUIRED_GATES` and document each in the CLAUDE.md scanner table.

**Tests:** each new scanner ships with `scripts/tests/test_<gate>.py` (stdlib) proving it flags a planted violation and excuses a marked one.

**Acceptance gate:** all six gates run green in CI; `verify_ci_gate_wiring.py` green; a deliberately-planted un-gated operator view / tenant `super:` link fails the relevant gate (demonstrate, then revert).

---

## Wave 5 — Defense-in-depth on operator data helpers (closes **H5**) — **P2**

**Objective:** operator cross-tenant reads/writes are authorized in the data layer, not only at the socket connect gate; CI can see them.

**Repo-controlled tasks:**
1. In `apps/api/consumers.py:560-667` (`persist_support_agent_reply` / `load_support_ticket_for_agent` / `set_support_ticket_status`): after loading the ticket by `pk`, assert the operator is authorized for that ticket's tenant (control-plane + the relevant scope; honor `OperatorTenantAssignment` if that is the intended trust model). Fail closed.
2. Add explicit `# tenant-isolation-allow: <reason>` markers on the deliberate cross-tenant operator queries so they are *visible* to reviewers (the scanner can't see chained `.filter(pk=)` — the marker is the human seal).
3. Consider extending `scan_tenant_queryset_safety.py` to chase one level of `.select_related(...).filter(pk=...)` on a tenant-scoped model receiver, OR document explicitly why operator ticket helpers are exempt.

**Tests:** removing/reordering the connect gate is caught — a test that calls the helper with a foreign-tenant `ticket_id` as a non-authorized operator raises/denies.

**Acceptance gate:** the helper-authorization tests green; support live-chat suite (`apps/api/tests/test_support_agent_console.py`) still green.

---

## Wave 6 — Audit the break-glass + bound impersonation (closes **H6**, **H7**) — **P2**

**Repo-controlled tasks:**
1. **H6:** emit an audit record when a superuser browses a tenant host un-impersonated (the exemption at `apps/accounts/middleware.py:457-462`). It stays allowed (break-glass), but it must be observable — write an `AuditLog`/`ImpersonationLog` entry.
2. **H7:** give `session["impersonation"]` a dedicated TTL (settings-driven, default e.g. 60 min), independent of the role session timeout; expire → force re-mint. No hardcoding.

**Tests:** superuser tenant-host visit produces an audit row; an impersonation session past its TTL is treated as ended.

**Acceptance gate:** both tests green.

---

## Wave 7 — Certify 100% (regenerate proof in CI)

**Objective:** the "100%" is a living, CI-refreshed artifact, not a stale doc.

**Repo-controlled tasks:**
1. Wire `generate_tenant_isolation_certification.py` and `generate_tenant_isolation_penetration_report.py` into CI in **--check/--verify mode** (regenerate → assert no drift vs the committed artifact, same pattern as `verify_sbom_current.py`). Add a `--check` mode if they only have generate mode today. Do NOT let them silently rewrite baselines on a plain run.
2. Extend the penetration scenario matrix with the newly-closed cases: the `is_staff`-tenant-admin-on-tenant-host scenario (H1), the dead-middleware scenario (H2), the XFH-spoof scenario (H3), and the exhaustive route-enumeration result (Wave 4.3).
3. Update `docs/generated/tenant_operator_isolation_forensic_audit_2026_07_04.md` Part C matrix to show every axis now ✅, and record the live command evidence.
4. **External-owner evidence (separate, not claimable from repo):** Postgres RLS proof on real Render Postgres (the `tenants-rls.yml` real-DB path), the edge/proxy `X-Forwarded-Host` stripping config (Wave 3), and a third-party penetration engagement. List these as `EXTERNAL_BLOCKED` — the repo work is done when the gates are green; the external proof is owner-controlled.

**Acceptance gate (definition of 100%):**
- Every gate in the Part C matrix is wired and green.
- `verify_tenant_cannot_reach_operator_routes.py` proves *every* operator route denies a tenant session (0 reachable).
- `scan_staff_gate_on_tenant_surface.py` == 0.
- `scan_tenant_template_operator_links.py` == 0.
- `verify_super_platform_scope_coverage.py` (de-hardcoded) covers 100% of operator views.
- `verify_ci_gate_wiring.py` green (no gate can silently vanish).
- The certification + penetration artifacts regenerate with no drift in CI.
- `python manage.py check` + `makemigrations --check --dry-run` clean.

---

## Guardrails checklist (apply on every wave)

- Path-scoped git staging only; never `git add -A`; never stage peer WIP; FF-only push; never `--no-checkout`; gate push on tree count ≥ 13000.
- Bump `static/js/service-worker.js` `CACHE_VERSION` monotonically on any wave that ships CSS/JS.
- Update `docs/CSS_RETIREMENT_DOCKET.md` + `MEMORY.md` per the deploy checklist.
- Tests via `DJANGO_SETTINGS_MODULE=config.settings_test python manage.py test <dotted.path>` (Django unittest, NOT pytest). Run the long :memory: build in the background; read the log; never tail-pipe the exit code.
- Never log tokens/credentials; store secrets encrypted at rest.
- Owners never get `is_staff`/`is_superuser`; no Django `/admin/` for owners; owner authority = `SchoolMembership.is_school_owner`/`is_active_owner()`; operators use `require_platform_scope`/`user_has_control_plane_access` on `/super/` only.
- Do not claim production readiness from local SQLite; RLS/edge/pen-test are external evidence.

## Wave sequencing summary

| Wave | Closes | Priority | Deliverable |
|---|---|---|---|
| 1 | H1 | P0 | Re-gate `is_staff` operator surfaces on tenant host + `scan_staff_gate_on_tenant_surface.py` |
| 2 | H2 | P1 | Revive dead isolation middleware + regression seal |
| 3 | H3 | P1 | X-Forwarded-Host classification hardening |
| 4 | H4 | P0 (cert) | Wire 4 dormant gates + de-hardcode scope coverage + 2 new gates (route-enum + template-link) |
| 5 | H5 | P2 | Operator helper data-layer authorization |
| 6 | H6, H7 | P2 | Break-glass audit + impersonation TTL |
| 7 | — | P0 (cert) | CI-refreshed certification + penetration proof; define & prove 100% |
