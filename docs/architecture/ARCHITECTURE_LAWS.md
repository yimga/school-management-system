# RunMyCampus Architecture Laws

These laws are **non-negotiable**. All code and code-review must comply. CI and lint scripts enforce them where possible.

## Law 1 — No new hardcoding

No new tenant behavior may be hardcoded in views, forms, templates, or services.

- Use `request.tenant_runtime`, policy, registries, and blueprints.
- Do not add `country == "XX"`, `region == "YY"`, or tenant-specific branches in module logic.
- **Enforcement:** `scripts/check_no_hardcoding.py`, `scripts/lint_tenant_settings.py`.

## Law 2 — Runtime is the source of truth

All variable behavior must flow through:

**Registry → Blueprint → Policy → Tenant Override → Runtime**

- Resolve behavior from `request.tenant_runtime` (or `build_tenant_runtime_for_tenant(tenant)` in jobs).
- Do not read `School.settings` or `School.features` directly in tenant-facing code; use `get_effective_policy(school)` or runtime.
- Prefer `apps.platform_runtime.helpers` and `request.tenant_runtime.policy` over `SiteSettings.get_solo()` for tenant behavior.
- **Enforcement:** `scripts/lint_tenant_settings.py`; code review.

## Law 3 — Schema-per-tenant is primary

Do not re-expand mixed tenancy philosophy. Schema-per-tenant is the primary tenancy model.

## Law 4 — No module forks per country or tenant

One governed core. Many controlled expressions.

- Do not fork modules per country or tenant (e.g. no `views_cm.py` vs `views_us.py`).
- Use policy, blueprint, and registry to vary behavior.

## Law 5 — Control plane, admin backoffice, marketing plane, and tenant plane are separate surfaces

Do not blur them.

- **Marketing:** `runmycampus.com` — conversion, SEO, trust.
- **Control plane:** `manager.runmycampus.com/super/` — governance, tenants, marketplace, migration, observability.
- **Admin backoffice:** `manager.runmycampus.com/admin` — internal ops, config, data.
- **Tenant plane:** tenant domains — school operations, role shells.

Each has its own shell, density, and navigation.

## Law 6 — Packs, providers, policies, apps, and workflows are versioned, previewable, auditable

No mystery blobs. All platform artifacts (blueprint packs, policy bundles, workflow packs, dashboard packs, marketplace apps) are versioned and auditable.

## Law 7 — Sidebars and navigation are governed systems, not template leftovers

Navigation must be runtime-aware and role-aware.

- Control plane: `apps.schools.control_plane_nav.build_control_plane_nav(request)`.
- Tenant: from runtime, entitlements, and installed apps — not hardcoded menu lists in templates.
- **Enforcement:** Code review; no new hardcoded nav in templates.

## Law 8 — Every major layer must be observable

Providers, workflows, migration, apps, runtime, dashboards, modules — all must be inspectable and monitorable (health, metrics, audit).

## Law 9 — Security, permissions, impersonation, exports, provider secrets, and app scopes are centralized and audited

No improvisation. Use centralized identity, permission checks, export restrictions, and scope handling.

## Law 10 — The product must feel premium everywhere

Not just in screenshots. Every surface (marketing, control plane, admin, tenant) must meet the same quality bar: design tokens, shell consistency, page families, and no visual debt.

---

## Override precedence (platform-wide)

When merging policy/blueprint/tenant values:

1. Platform defaults  
2. Region / country defaults  
3. Blueprint defaults  
4. Policy bundle defaults  
5. Plan / entitlement constraints  
6. Tenant overrides  
7. Scheduled / temporary overrides  
8. Request-mode overlays (preview, sandbox, impersonation-safe masking)

## References

- **Runtime compilation order:** [RUNTIME_COMPILATION_ORDER.md](RUNTIME_COMPILATION_ORDER.md)
- **SiteSettings audit:** [SITESETTINGS_AUDIT.md](SITESETTINGS_AUDIT.md)
- **No-hardcoding checklist:** [no_hardcoding_checklist.md](no_hardcoding_checklist.md) and `scripts/check_no_hardcoding.py`
- **Experience shells:** [experience_shells.md](experience_shells.md)
- **Sidebar taxonomy:** [sidebar_navigation_taxonomy.md](sidebar_navigation_taxonomy.md)
- **Shell implementation (template/surface mapping):** [SHELL_IMPLEMENTATION.md](SHELL_IMPLEMENTATION.md)
