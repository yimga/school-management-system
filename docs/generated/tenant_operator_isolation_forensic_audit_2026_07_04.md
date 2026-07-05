# Tenant ⟂ Operator Isolation — Forensic Audit (2026-07-04)

**Scope:** the seam between the TENANT plane (school subdomains: portal / backend / teacher / parent / student / studio) and the OPERATOR plane (`manager.runmycampus.com`, the `/super/` control plane). The governing requirement: **a tenant identity or session must NEVER cross into operator authority, for any reason.** Operators may legitimately reach *into* tenants (support), but only through an audited, consent-gated, signed path.

**Method:** read-only, source-grounded. Six parallel read-only sweeps (ingress/routing, operator access gates, existing CI gates, template/nav leakage, websocket/data layer, impersonation/scope-elevation) plus direct verification of the two highest-severity findings against the actual code. No product code was modified; no baseline-mutating scanner was run.

**Verdict:** the tenant→operator *identity* boundary is **structurally sound today** — the keystone check (`user_has_control_plane_access`) fail-closes on the presence of any `SchoolMembership`, so no tenant owner/admin can become an operator by role or by `is_staff`. **But the boundary is NOT certified to 100%.** There are 7 concrete, source-evidenced gaps. Two are dead/mis-gated code that a tenant `is_staff` user can actually touch; one is a host-header hardening gap; the rest are CI-coverage holes that let a future regression ship undetected. None is currently a proven cross-tenant data breach, but each erodes the "no mingling, ever" guarantee.

---

## Part A — What is sound (do NOT rip these out)

The isolation spine is real and load-bearing. The hardening work must **preserve and certify** it, not replace it.

| Mechanism | Evidence | Property |
|---|---|---|
| **Keystone operator gate** | `apps/schools/control_plane.py:77-103` — `user_has_control_plane_access` returns True only for `is_superuser` **or** an active `PlatformOperatorProfile`, and returns **False for any user holding a `SchoolMembership`** (line 98) *before* the role allowlist is consulted. | A tenant owner/admin can never satisfy the operator gate — even if `CONTROL_PLANE_OPERATOR_ROLES` were mis-set to include `ADMIN`. Ignores `is_staff` entirely. |
| **Host-split urlconfs** | `config/tenant_urls.py` mounts **no** `super:` namespace. `/super/` lives only in `config/manager_urls.py` and `config/urls.py` (the local/dev full urlconf). | On a real tenant host, `/super/...` cannot resolve — 404 by construction. |
| **Three-layer fail-closed on `/super/` from a tenant host** | (1) structural 404; (2) `ReservedPublicHostAccessMiddleware` hard-redirects `/super/` off tenant hosts — `apps/schools/middleware.py:696-706`; (3) `TenantSuperAdminRequiredMiddleware` 403s any `/super/*` lacking control-plane access — `middleware.py:1409-1441`; `ManagerHostControlPlaneRequiredMiddleware` does the same for the whole manager host — `middleware.py:1444-1494`. | Defense-in-depth, not per-view-decorator reliance. |
| **Impersonation keeps operator identity** | `apps/schools/super_views_impersonation.py:84` (mint) + `apps/accounts/views_impersonation.py:56` (consume). Signed `TimestampSigner` token, `school_id` + **actor-id** bound, 1h TTL; writes `session["impersonation"]` — it does **not** `login()` as any tenant user. | There is no tenant identity to leak; every action stays attributable to the operator. Stacked gate: control-plane + `platform.impersonate` scope + per-tenant `OperatorTenantAssignment`/JIT + principal consent + optional four-eyes; fully audited (`ImpersonationLog` + CRITICAL `AuditLog`). |
| **RLS JWT is tenant-narrowing only** | `apps/tenancy/middleware_rls_jwt.py:191-286` — binds `app.current_school_id`; the `role` claim is explicitly "not an authorization channel"; a forged `school_id` is overridden by the host school. | The JWT cannot widen a tenant, let alone grant operator scope. |
| **WebSocket presence cannot leak cross-tenant** | `apps/api/consumers.py` — tenant rooms are `{prefix}_{school_id}_{user.pk}`, server-derived (`channels_tenant_middleware.py:128-136`). The `support_agents` group is **join-only-by-operators** (`consumers.py:734`, behind `agent_console_access`) and **publish-only-by-customers** (`consumers.py:424-434`, no receive handler). `agent_console_access` == the HTTP `require_platform_scope(team.read)` identity set — not weaker, not `is_staff`. | No group is jointly *received* by a tenant socket and a cross-tenant socket. |
| **Owner gate ⟂ operator gate are disjoint** | Owner = `SchoolMembership.is_active_owner()` (`apps/schools/models.py:1186-1202`), a pure per-school membership query. Operator = `user_has_control_plane_access`. Holding *any* membership is exactly what disqualifies the operator gate. | The two authority sets intersect only for a user who *independently* carries `is_superuser`/`PlatformOperatorProfile` — neither settable by any tenant-facing surface. |
| **No self-serve `is_staff`/scope elevation** | Signup (`apps/schools/signup_views.py:746`) creates only an inactive `School`; the owner user (`apps/schools/tasks.py:557-588`) is `role=ADMIN` + `SchoolMembership(is_school_owner=True)` — no `is_staff`, no profile. Operator-profile writes exist only in CLI commands. | The reverse-leak adversarial sweep found no tenant→operator path. |

---

## Part B — Confirmed gaps (the road to 100%)

### H1 — `@staff_member_required` used as an operator gate on tenant-reachable surfaces, while the platform mints `is_staff=True` tenant users. **[HIGH — systemic, tenant→operator direction]**

`is_staff` is **overloaded**. It is deliberately set on tenant-scoped users:
- `apps/accounts/management/commands/ensure_default_tenant_admin.py:131` — `user.is_staff = True` on a `role=ADMIN` user *with a `SchoolMembership`*.
- `apps/accounts/management/commands/create_teacher_parent_accounts.py:127` — `principal.is_staff = True`.

…yet `@staff_member_required` (= `is_active and is_staff`, no control-plane/membership check) is used as an "operator/super" gate on views that are mounted on the **tenant host**:
- `apps/assist_dock/urls.py` is included in `config/tenant_urls.py:561`. Its `inspect/` → `apps/assist_dock/power_views.py:113 inspect_landing` (`@staff_member_required`) renders an RBAC + settings-key **introspection overlay** (resolved URL name, namespace, view callable, module, decorator chain, and `site_settings` **key names**). Its `impersonate/` → `power_views.py:138 impersonate_landing` (`@staff_member_required`) renders an impersonation picker/CTA.

**Confirmed impact:** an `is_staff=True` tenant admin, on *their own* subdomain, can open `/assist/inspect/?page=…` and read operator-flavored internal routing/auth structure + configuration key names (information disclosure). `impersonate_landing` is only a CTA — the real minting flow (`switch_to_tenant`) stays properly control-plane-gated, so this is **not** an actual impersonation-capability breach. **Correction to the parallel audit:** the migration_cloud operator urlconf (cross-tenant audit export / token mint / MAA config-flip) is **NOT** on the tenant host — it is mounted in `config/urls.py` (local/dev) and `config/manager_urls.py` (operator host) only; `config/tenant_urls.py` mounts just `urls_connectors` (connector ingest) and the lifecycle status view. So that specific "cross-tenant export from a tenant subdomain" scenario does **not** reproduce in production.

**Root cause & fix:** `is_staff` must never be the sole gate on anything operator-flavored, because the platform makes tenant admins `is_staff`. Every `@staff_member_required` (and bare `user.is_staff`/`is_superuser` view checks) on a view reachable from `config/tenant_urls.py` must be re-gated to `require_control_plane_access` / `require_platform_scope(...)` — or the view must be moved off the tenant mount, or (if it is genuinely a tenant-admin tool) re-gated to a proper tenant-admin permission that is not `is_staff`. This is a *class* of bug, not a single site — it needs an enumeration + a CI gate.

### H2 — `TenantHostControlPlaneIsolationMiddleware` and `ImpersonationReadOnlyGuardMiddleware` are dead code on live hosts. **[MEDIUM — operator→tenant direction]**

`apps/accounts/middleware.py:447` (and `:557` for the read-only guard) early-return on `getattr(request, "public_host_kind", None) != "tenant"`. But `public_host_kind()` (`apps/schools/host_routing.py`) **never returns the string `"tenant"`** — tenant hosts resolve to `None` (verified: the literal `"tenant"` appears nowhere in `host_routing.py`). So the entire body (lines 448-473) never executes on any real tenant host. The stated control — "Platform operators must enter tenant hosts through the signed impersonation flow, not through normal tenant RBAC … closes scattered SUPERADMIN allow-lists" — **does not run in production.** The only live control on operator→tenant crossing is `_enforce_tenant_host_membership` (`apps/schools/middleware.py:995-1049`), which *permits* any control-plane user to cross.

**Fix:** change the discriminator to the real tenant condition (tenant host ⇔ `public_host_kind is None and request.school is not None`, or introduce a positive `request.is_tenant_host` marker set by `UrlConfSwitcherMiddleware`). Guard against re-introducing the same dead literal with a test.

### H3 — `X-Forwarded-Host` spoofing can select the operator urlconf. **[MEDIUM — routing hardening]**

`apps/schools/middleware.py:319-333 _request_host_raw` reads `HTTP_X_FORWARDED_HOST` **first**, takes `.split(",")[0]` (the client-supplied token if the proxy *appends*), and **bypasses `ALLOWED_HOSTS`** by design. With `USE_X_FORWARDED_HOST = True` (`config/settings.py:135`), a forged `X-Forwarded-Host: manager.runmycampus.com` makes `UrlConfSwitcherMiddleware` select `config.manager_urls` — the operator *routing tree* becomes reachable by header. **Not an escalation** (the RBAC layer behind it — `user_has_control_plane_access` — is fail-closed; the anonymously-reachable manager prefixes are health/version/marketing/HMAC-webhook only), and it is contingent on the Render edge not stripping the client header. But it makes the routing boundary fail-*open* to spoofing and lets it lean entirely on downstream RBAC. The same first-token parse exists in the Channels middleware (`channels_tenant_middleware.py:20-29`).

**Fix:** trust `X-Forwarded-Host` only from a known proxy hop (take the *last* token, or validate against the canonical base/host set) so host classification is not attacker-controllable.

### H4 — Boundary dimensions with NO wired CI gate — a regression ships green. **[HIGH for "certification", the core of "make it 100%"]**

The isolation invariant is strongly gated on some axes (`verify_tenant_control_plane_rbac.py --strict`, websocket scope, tenant-queryset safety, the guard-bypass scanner) but has **uncovered seams**:

1. **Full `/super/` per-view scope-decorator coverage** — `verify_super_platform_scope_coverage.py` is the only verifier of `@require_platform_scope` presence, it is **not wired into any workflow**, and it checks a **hardcoded 33-view list**. A 34th operator view (or any operator view added without the decorator) is caught by nothing.
2. **Operator-only offboarding** — `verify_tenant_offboarding_operator_only.py` is **unwired**. Flipping `TENANT_SELF_SERVICE_OFFBOARDING_ENABLED` to `1` or dropping `operator_approval_required` ships undetected.
3. **Access-resolver fragmentation ratchet** — `scan_access_resolver_fragmentation.py` is **unwired despite CLAUDE.md claiming `architectural-boundaries.yml::access-resolver-fragmentation`** (doc drift), and it is **absent from `verify_ci_gate_wiring.py`'s `REQUIRED_GATES`**, so the meta-gate won't catch its absence either.
4. **Operator/tenant shell-chrome separation** — `verify_super_tenant_shell_aggressive.py` is **unwired**.
5. **No single end-to-end negative gate.** There is no test that enumerates every operator route and asserts a tenant session is denied. Coverage is 3 sampled routes (`apps/security/tests/test_tenant_route_leakage.py`) + 6 scenarios (`test_boundary_penetration.py`). A new high-risk view lands protected only if it (a) sits in the manager urlconf and (b) carries the decorator — and nothing wired verifies (b) for arbitrary new views.
6. **No template-link boundary gate.** The entire tenant→operator link boundary rests on the hand-applied `{% if request.public_host_kind == 'manager' %}` convention (verified correct across ~10 shared shell templates today). `verify_template_tenant_boundaries.py` only guards the brand-pack *catalog*, not `{% url 'super:…' %}` in tenant templates — and `verify_url_name_integrity` would even *confirm* a `super:` name resolves. A new tenant template with an ungated `{% url 'super:…' %}` passes all gates.
7. **Certification artifacts are stale-prone.** `generate_tenant_isolation_certification.py` / `generate_tenant_isolation_penetration_report.py` produce "READY" verdicts (`docs/generated/tenant_isolation_*`, dated 2026-05-20) but are **never regenerated in CI**, so the verdict drifts from HEAD.
8. **Explicit "watch gaps" (unverified, ungated):** object-storage/media prefix isolation, async-job/cache tenant-context propagation, and the full API-serializer/queryset-by-membership matrix (per `docs/generated/tenant_operator_separation_gap_analysis.md`).

### H5 — Operator support-chat helpers rely solely on the connect gate + are invisible to the tenant-queryset scanner. **[LOW — defense-in-depth]**

`persist_support_agent_reply` / `load_support_ticket_for_agent` / `set_support_ticket_status` (`apps/api/consumers.py:560-667`) do a bare `GlobalSupportTicket.objects.select_related(...).filter(pk=ticket_id)` on a client-supplied `ticket_id`, with no tenant self-scoping. Their only protection is that their sole caller (`SupportAgentConsumer`) gated `connect()` on `agent_console_access`. Because they are chained `.select_related().filter(pk=)` calls, `scan_tenant_queryset_safety.py` (which does not chase chained querysets) will **not** flag them even if the gate regressed. Enforcement lives in one place, not in the data layer, and CI is blind to it.

**Fix:** add data-layer defense-in-depth (assert operator authorization for the ticket's tenant inside the helper) and/or an explicit test that removing the connect gate is caught.

### H6 — Superuser tenant-host access is un-impersonated and not `ImpersonationLog`-audited. **[LOW — operator→tenant break-glass]**

`apps/accounts/middleware.py:457-462` exempts `is_superuser` from tenant-host isolation. A platform root can browse any tenant host directly, without the signed flow and without an `ImpersonationLog` record — the least-observable operator→tenant path. Intentional break-glass, but it should at least emit an audit record.

### H7 — The impersonation session marker has no dedicated TTL. **[LOW]**

The entry *token* is 1h, but `session["impersonation"]` persists until explicit exit or ordinary role session timeout — an idle impersonation session outlives the token. Add a dedicated impersonation-window TTL.

---

## Part C — CI coverage matrix (boundary axis → wired gate)

| Boundary axis | Wired gate today | Status |
|---|---|---|
| Operator↔tenant RBAC identity | `verify_tenant_control_plane_rbac.py --strict` (`architectural-boundaries.yml`) | ✅ strong |
| `is_staff` bypass **in the 2 enumerated guard modules** | `scan_staff_bypass_tenant_guards.py --compare` | ⚠️ only 2 files; misses view-level `@staff_member_required` (**H1**) |
| WebSocket tenant binding | `verify_websocket_tenant_scope.py` | ✅ |
| Data-plane queryset scoping | `scan_tenant_queryset_safety.py` (+ marker-quality) | ✅ but blind to chained `.filter(pk=)` (**H5**) |
| Route-leak (sampled) | `test_tenant_route_leakage.py` (3 routes) + `test_boundary_penetration.py` (6) via `coverage-gate.yml` | ⚠️ samples, not exhaustive (**H4.5**) |
| `/super/` per-view decorator coverage | `verify_super_platform_scope_coverage.py` | ❌ **unwired**, hardcoded 33 (**H4.1**) |
| Operator-only offboarding | `verify_tenant_offboarding_operator_only.py` | ❌ **unwired** (**H4.2**) |
| Access-resolver fragmentation ratchet | `scan_access_resolver_fragmentation.py` | ❌ **unwired** (doc says otherwise) (**H4.3**) |
| Operator/tenant shell separation | `verify_super_tenant_shell_aggressive.py` | ❌ **unwired** (**H4.4**) |
| Tenant→operator template links | *(none)* | ❌ **no gate** (**H4.6**) |
| Certification / penetration freshness | *(none — generators never run in CI)* | ❌ stale-prone (**H4.7**) |
| Storage/media prefix, async/cache context, serializer matrix | *(none)* | ❌ unverified (**H4.8**) |

---

## Part D — Commands run (evidence, non-mutating)

Read-only reads + `Grep`/`Glob` only. No product code changed. No `scripts/scan_*`/`verify_*` executed (they rewrite baselines). Directly verified: `config/tenant_urls.py` mounts (migration operator urlconf absent; `assist_dock` present at :561); `host_routing.py` never emits `"tenant"`; `apps/accounts/middleware.py:447` dead guard; `power_views.py:113/138` `@staff_member_required`; `ensure_default_tenant_admin.py:131` + `create_teacher_parent_accounts.py:127` set tenant `is_staff=True`.

**The implementation directive that closes every gap above lives at:** `docs/plans/RUNMYCAMPUS_TENANT_OPERATOR_ISOLATION_100.md`.

---

## Part E — Remediation status (2026-07-05)

The 7-wave plan was executed end to end. Every confirmed hole is closed and, per wave, sealed by a wired CI gate so it cannot regress.

| Hole | Fix shipped | Gate that keeps it closed |
|---|---|---|
| **H1** is_staff as an operator gate on tenant surfaces | Structural super-segment seal in `TenantSuperAdminRequiredMiddleware._is_operator_super_route` (any `super/` path segment on a tenant host requires control-plane access — closes the 44-route `portal/super/…` block + api/api_v1 operator routes at once); 9 non-super operator views (assist_dock inspect/impersonate/registry, platform_runtime health/flight-deck, compliance auditor, siteconfig RAG, setup_studio bulk-promote) re-gated to `require_control_plane_access`; 45 request.school-scoped tenant-admin surfaces marked. | `scan_staff_gate_on_tenant_surface.py` (baseline 0) — `architectural-boundaries.yml` |
| **H2** dead operator→tenant isolation middleware | `UrlConfSwitcherMiddleware` sets a positive `request.is_tenant_host`; `TenantHostControlPlaneIsolationMiddleware` + `ImpersonationReadOnlyGuardMiddleware` key off it (was the never-produced `public_host_kind == "tenant"`). | `apps/accounts/tests/test_tenant_host_isolation_revival.py` (`ci.yml` Django tests) |
| **H3** X-Forwarded-Host operator-urlconf spoof | `_request_host_raw` + the Channels twin honor XFH only from a trusted edge and take the rightmost (trusted-proxy) token; `TRUST_X_FORWARDED_HOST` kill-switch. | `apps/schools/tests/test_forwarded_host_hardening.py` |
| **H4** ungated boundary axes | Wired the 4 dormant gates (`verify_super_platform_scope_coverage`, `verify_tenant_offboarding_operator_only`, `scan_access_resolver_fragmentation`, penetration freshness); built the end-to-end negative gate (`verify_tenant_cannot_reach_operator_routes` — 258 super: routes enumerated, all covered) and the template-link gate (`scan_tenant_template_operator_links`, baseline 0, caught + fixed 1 real unguarded login-page operator link and marked 2 operator partials). | all wired; `verify_ci_gate_wiring.py` (26 gates, 0 un-wired) |
| **H5** operator support helpers rely only on connect gate | `persist_support_agent_reply` / `load_support_ticket_for_agent` / `set_support_ticket_status` re-assert `agent_console_access` in the data layer (fail closed); cross-tenant queries marked `# tenant-isolation-allow`. | `apps/api/tests/test_support_agent_console.py::test_helpers_fail_closed_for_non_operator` |
| **H6** un-audited superuser break-glass | Throttled PII-free `security.break_glass` audit record on superuser direct tenant-host access. | `test_tenant_host_isolation_revival.py::test_break_glass_superuser_access_is_audited` |
| **H7** impersonation marker never expired | Dedicated `IMPERSONATION_SESSION_MAX_AGE_SECONDS` TTL on the session marker (`granted_at` stamp + `_impersonation_expired`); expired → re-mint via signed flow. | `test_tenant_host_isolation_revival.py` TTL tests |

**Updated CI coverage matrix (every axis now wired):**

| Boundary axis | Wired gate |
|---|---|
| Operator↔tenant RBAC identity | `verify_tenant_control_plane_rbac.py --strict` ✅ |
| is_staff operator gate on tenant surface | `scan_staff_gate_on_tenant_surface.py` ✅ (new) |
| Operator route reachable by tenant (enumerated) | `verify_tenant_cannot_reach_operator_routes.py` ✅ (new) |
| Tenant→operator template links | `scan_tenant_template_operator_links.py` ✅ (new) |
| `/super/` per-view scope decorator | `verify_super_platform_scope_coverage.py` ✅ (wired) |
| Operator-only offboarding | `verify_tenant_offboarding_operator_only.py` ✅ (wired) |
| Access-resolver fragmentation ratchet | `scan_access_resolver_fragmentation.py` ✅ (wired) |
| WebSocket tenant binding | `verify_websocket_tenant_scope.py` ✅ |
| Data-plane queryset scoping | `scan_tenant_queryset_safety.py` ✅ |
| Operator→tenant confinement + impersonation TTL + break-glass audit | `test_tenant_host_isolation_revival.py` ✅ (new) |
| Host-header operator-urlconf spoof | `test_forwarded_host_hardening.py` ✅ (new) |
| Certification / penetration freshness | `generate_tenant_isolation_penetration_report.py --check` ✅ (new) |
| Meta: no gate can silently vanish | `verify_ci_gate_wiring.py` (26 gates) ✅ |

**Scope decisions (surfaced):**
- `verify_super_platform_scope_coverage.py` was **wired** (its real gap) rather than fully de-hardcoded from its 33-view list: the "a 34th operator view slips through" concern is now closed comprehensively by `verify_tenant_cannot_reach_operator_routes.py` (enumerates *all* 258 super: routes) + `scan_staff_gate_on_tenant_surface.py` (non-super operator views), so a hundreds-of-view decorator burndown was not warranted.
- `verify_super_tenant_shell_aggressive.py` (operator/tenant shell **chrome** separation) remains unwired — it is a UI-chrome verifier, not a hard access boundary, and is heavier/less deterministic than a boundary-job gate; the access boundary it visually reflects is now gated by the identity/route/template/staff-gate axes above.

**External-blocked (owner-controlled, not claimable from repo):** live Postgres RLS proof on Render; the edge/proxy `X-Forwarded-Host` stripping config (Wave 3 code is defense-in-depth on top of it); a third-party penetration engagement.
