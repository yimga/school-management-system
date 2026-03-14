# SiteConfig Freeze Policy

**Purpose:** §2.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Freeze new tenant-facing business logic in `siteconfig`; make runtime the only legal tenant-behavior engine.

**Status:** In force. Nothing deferred.

---

## 1. Policy

- **No new tenant-facing business logic in siteconfig.** New behavior that affects tenant experience (branding, features, workflows, reports, policies, registries, plans, marketplace) must be implemented in the owning bounded context (brand_experience, runtime_blueprints, policies, global_registries, plans_entitlements, marketplace, etc.), not in siteconfig.
- **No new direct `SiteSettings.get_solo()` in tenant-facing apps.** All tenant-facing code must resolve settings via `get_effective_site_settings(request=..., school=...)` from `apps.platform_runtime.helpers`. CI enforces: `scripts/lint_tenant_settings.py --check-get-solo-only` and `--check-school-settings-features`.
- **No new legacy domain sprawl in siteconfig.** New “system” or “admin” config that belongs to a bounded context must live in that app; siteconfig is limited to platform-default SiteSettings and migration shims that are being removed.

---

## 2. CI enforcement

| Check | Script | Gate |
|-------|--------|------|
| No get_solo() in tenant apps | lint_tenant_settings.py --check-get-solo-only | pre_deploy_gate.sh |
| No direct school.settings/features in tenant paths | lint_tenant_settings.py --check-school-settings-features | pre_deploy_gate.sh |
| No new legacy siteconfig domain imports | lint_siteconfig_legacy_imports.py | pre_deploy_gate.sh |
| Bounded context boundaries | lint_bounded_context_imports.py --strict | pre_deploy_gate.sh |

---

## 3. Where new work goes

| Concern | Owner app / layer |
|---------|-------------------|
| Branding, theme, experience | brand_experience, platform_runtime (resolver) |
| Feature flags, policies | policies, platform_runtime (get_effective_flags) |
| Blueprints, dashboards, workflows | runtime_blueprints, packages, automation |
| Plans, entitlements | plans_entitlements |
| Registries, localization | global_registries |
| Integrations, SMS, email, API | marketplace / integrations |
| Report/document defaults | reports, documents |

---

## 4. Completion

- [x] Policy documented.
- [x] CI rule forbidding new tenant-facing SiteSettings.get_solo() in place (lint_tenant_settings).
- [x] Pre-deploy gate runs all checks above.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1.*
