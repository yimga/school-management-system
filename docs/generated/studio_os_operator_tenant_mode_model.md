# Studio OS — Operator / Tenant Mode Model (v3.54.0)

**Wave:** Studio OS next-realm command-cockpit · **Generated:** 2026-05-21

## Host resolution

| Attribute | Operator (manager) | Tenant |
|---|---|---|
| Host | `manager.runmycampus.com` | per-tenant subdomain |
| Detection | `request.public_host_kind == 'manager'` | `request.public_host_kind != 'manager'` |
| Tenant context | resolved via `studio_os:set_operator_school` | `request.school` (NEVER POST body) |
| Cross-tenant marker | `# tenant-isolation-allow: <3+-part-reason>` | n/a |

## Role taxonomy

| Role | Host | Auth signals | Key capabilities |
|---|---|---|---|
| Operator (manager / super) | manager | `is_staff` / `is_superuser` / `@staff_member_required` / `# rbac-allow: super-staff-*` | Platform-wide RBAC, cross-tenant audit, platform templates, infra apply, approval queue |
| Operator (implementation/support) | manager | `is_staff` + tenant-scoped perms | Read-only audit for assigned tenants, tenant-scoped impact preview |
| Tenant school admin | tenant | `@login_required` + `request.school` membership | Own theme/experience/workflows/reports/launch tasks/feature toggles |
| Tenant implementor | tenant | `has_perm` + tenant scope | Draft mode + request approval + view simulations |

## Per-section capability matrix

### Overview (cockpit home)

| Capability | Operator | Tenant |
|---|---|---|
| 8 mission-signal tiles | All (incl. cross-tenant counts) | 6 of 8 (no platform-only signals) |
| Mode card grid (5 cards) | ✓ | ✓ |
| Studio guidance panel | ✓ | ✓ |
| RBAC hub chip | ✓ (`--operator` variant) | ✗ |
| Feature control hub chip | ✓ | ✗ |
| Approval / Workflow / Import / Document / Report library chips | ✓ | ✓ (own tenant) |
| Right-rail launch readiness | Cross-tenant summary | Own tenant only |

**Enforcement:** Template-level `{% if request.public_host_kind == 'manager' %}` gate in `overview_command_cockpit.html` lines 179-190.

### Experience

| Capability | Operator | Tenant |
|---|---|---|
| Theme & colors | Platform templates | Own school |
| Customizer / school-website blocks | Cross-tenant view + edit | Own school |
| Theme tokens panel | ✓ (read + edit) | ✓ (read + edit own) |
| Compare themes | Cross-tenant | Own scope |
| Publish | ✓ | ✓ (own; writes to studio_audit) |
| Rollback to prior version | ✓ | ✓ (own) |

**Destructive reversible:** rollback (preserves version history).
**Enforcement:** `apps/siteconfig/views.py::theme_colors` + `studio_experience_compare` scope by tenant.

### Automation

| Capability | Operator | Tenant |
|---|---|---|
| Workflow templates | Platform-level | Own school workflows |
| Approval queue | Cross-tenant | Own |
| Simulation preview | Any workflow | Own workflows only |
| Activate / Deactivate | Operator approval | Request approval |
| Replay delivery | ✓ (audit-logged) | ✓ (own) |
| Rollback workflow | ✓ (audit-logged) | ✓ (own) |

**Destructive reversible:** replay (creates new delivery row), rollback to prior workflow state.
**Approval required:** activate workflows with destructive triggers, replay.
**Enforcement:** `data-rmc-confirm` on destructive buttons → shared JS handler. View-level tenant scoping.

### Output

| Capability | Operator | Tenant |
|---|---|---|
| Document templates | Platform-level | Own school documents |
| Report card builder | Admin (operator) | Tenant builder for own |
| Cross-tenant readiness counts | ✓ | Own only |
| Branding inheritance chain | Cross-tenant view | Own |
| Publish report / Export | ✓ | ✓ (own) |

**Money format rule:** Decimal helpers (`apps.finance.json_decimal.amount_str`) — NEVER `float()` per `scan_money_float` baseline 0.
**Enforcement:** Template-level tenant-scoped iframe sources.

### Launch

| Capability | Operator | Tenant |
|---|---|---|
| Infrastructure preview | Cross-tenant | Own school |
| Infrastructure validate (dry-run) | ✓ | ✓ (own) |
| Infrastructure apply | ✓ (`data-rmc-confirm` + perm gate) | "Request platform apply" (no direct mutation) |
| Plan selection | Manage all plans | Read-only / request |
| Role previews (Admin/Teacher/Parent/Student) | Cross-tenant | Own school |
| Go-live state | All tenants | Own school |

**Approval required:** infrastructure apply (operator `data-rmc-confirm` gated; tenant request triggers operator workflow). Current state: `school_infrastructure_apply_api` returns 501 (intentional — counsel docket; per [companion siblings memory](../../memory/feedback_companion_siblings_no_programmatic_sis_login.md)).

### Control

| Capability | Operator | Tenant |
|---|---|---|
| Audit entries | Cross-tenant (staff) | Own school only |
| Rollback | ✓ (perm-gated, `data-rmc-confirm`) | ✓ (own, perm-gated) |
| AI cleanup | ✓ (`data-rmc-confirm` + perm gate) | ✗ (destructive irreversible) |
| System config console | ✓ | ✗ |
| Feature flag toggles (writes) | Cross-tenant | ✗ (READ only own) |
| Impact analysis | Cross-tenant | Own school |
| Dependency graph | Cross-tenant | Own scope |

**PII safety:** Audit entries render `actor_display` (hashed prefix OR `displayed_name`) — **NEVER** raw `actor_email` / `_username` / `_slug`. Same pattern as Migration Cloud audit log per CLAUDE.md.
**Enforcement:** `studio_audit_api` / `studio_rollback` / `studio_ai_cleanup` scope by user + tenant. Template-level `data-rmc-confirm` + `{% if perms.X %}` on destructive buttons.

## Tenant safety invariants

1. **No cross-tenant data leak.** Preview routes scope to `request.school` via tenant middleware. Verified by `test_studio_os_operator_tenant_boundaries.py` (v3.54.0 new).
2. **No tenant-side platform mutations.** Gated by `request.public_host_kind == 'manager'` OR `@staff_member_required`.
3. **No PII in audit lists.** `actor_display` field — never `actor_email`/`_username`/`_slug`.
4. **Destructive actions require two gates.** `data-rmc-confirm` AND permission check — both must pass.
5. **Role names from registry.** `apps.platform_runtime.role_registry` / `User.Role` TextChoices — never hardcoded string literals (`scan_role_strings` baseline 268 holds).
6. **AI guidance doesn't leak operator internals.** School slug → `sha256[:8]` in all logs/payloads (per batch 1372 R2).
7. **Operator cannot accidentally bleed cross-tenant audit data into tenant views.** Audit list filters by `request.school` for tenant users.

## Enforcement layers

| Layer | Mechanisms |
|---|---|
| Template | `{% if request.public_host_kind == 'manager' %}` · `{% if perms.X %}` · `data-rmc-confirm` · `{% trans %}` |
| View | `@login_required` · `@staff_member_required` (operator-only) · `request.school` queryset scoping · `# tenant-isolation-allow:` markers |
| Service | Lazy-import + try/except · `log_exception_with_context` with `request_context_for_log` (PII-hashed) |
| JavaScript | Capture-phase `data-rmc-confirm` handler in `studio_os__shell.js` — runs BEFORE native handlers |
| Scanner | `scan_tenant_queryset_safety` 0 · `scan_pii_logging_smell` 0 · `scan_role_strings` 268 (pinned) · `scan_drf_schema_coverage` 0 |

## Tests proving boundaries

- `test_control_governance_cockpit.py::test_non_staff_user_blocked_from_control_canvas`
- `test_control_governance_cockpit.py::test_audit_list_renders_actor_display_not_email`
- `test_control_governance_cockpit.py::test_role_names_come_from_registry_not_literal`
- `test_control_governance_cockpit.py::test_rollback_button_has_confirm_pattern_and_perm_gate`
- `test_launch_readiness_cockpit.py::test_operator_only_apply_button_hidden_for_tenants`
- `test_studio_os_operator_tenant_boundaries.py` (cross-cutting; v3.54.0 new module — see Phase 11 deliverables)
- `test_overview_next_realm.py::test_operator_only_hub_chips_hidden_when_not_manager_host`

## Honest deferrals

- `studio_os:set_operator_school` UI exists but coordinator did not audit this wave.
- Tenant role-preview routes per audience (Admin/Teacher/Parent/Student) use existing `studio_role_preview_entries` shape — real per-audience preview routes are a v3.55+ wave.
- Automation tenant-scoped approval workflow real implementation deferred — cockpit shows honest empty state.
