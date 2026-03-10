# Metadata Governance Roles (§15)

**Minimum roles for metadata governance (Codex §9):**

| Role | Scope |
|------|--------|
| Platform Config Admin | SiteSettings, platform defaults, regional config |
| Runtime Steward | Blueprints, workflow/dashboard packs, resolver overrides |
| Policy Steward | Policy bundles, approval rules, feature toggles |
| Registry Steward | RegionConfig, grading scales, terminology, global registries |
| Marketplace Governor | Marketplace listings, publisher verification, pack certification |
| Migration Operator | Migration playbooks, quarantine, data migration |
| Implementation Specialist | Tenant setup, Setup Studio, onboarding |
| District Operator | District/multi-school control (when enabled) |
| Tenant Admin | Tenant-scoped config (branding, dashboards, workflows) |
| Support Read-Only | View runtime and config for support; no mutate |
| Break-Glass | Emergency override with audit; time-bound |

**CI fails on (§15):** Direct singleton in tenant code (`lint_tenant_settings --check-get-solo-only`); optional strict: mega-files (`lint_mega_files`), broad except (`lint_broad_except --strict`). Run `scripts/pre_deploy_gate.sh`; set `CODEX_STRICT=1` to fail on mega-files and broad except in addition to get_solo.
