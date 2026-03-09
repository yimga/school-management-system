# Registries and structural config — sole source

**Goal:** Registries (country, subdivision, terminology, calendar, institution type, education levels, etc.) are complete and the **only** source for structural config. No hardcoded lists or School.settings for terms, levels, or types. Blueprint and policy are the single source of operating model.

## Registries

- **Location:** apps/registries (and platform runtime step 3 — RegistryContext). Country, subdivision, education level, terminology, calendar, institution type as applicable.
- **Seed data:** Use management commands and migrations to seed; verify coverage with verify_registry_coverage or equivalent. Document supported regions and any gaps.
- **Read path:** Tenant and control-plane code must read structure (terms, levels, types) from registries or from runtime (runtime.registry) / blueprint / policy — not from School.settings or hardcoded dicts.

## Bypasses to remove

- Replace any code that uses hardcoded term lists, level lists, or institution types with registry or runtime/blueprint lookup. Lint or test can assert key flows (admissions, grading, finance) do not read structure from school.settings; use runtime or registry APIs.

## Regional landing and blueprint

- **Regional landing:** Public pages per region; SEO (meta, sitemap) and UX (load time, mobile) documented or implemented. See marketing and docs/MARKETING_EXECUTION.md.
- **Blueprint/policy:** Operating model (grading scale, admission numbering, etc.) from TenantBlueprint and PolicyBundle only; enforced by runtime and docs/POLICY_BLUEPRINT_SINGLE_PATH.md.

## Tests

- Tests that key flows (e.g. admissions, grading) read structure only from registries and runtime (blueprint/policy). Example: assert runtime.registry or get_effective_policy is used; no direct school.settings for structural keys in tenant view path.

## References

- apps/registries/
- apps/platform_runtime/runtime_resolver.py — step 3 (registry)
- docs/PLATFORM_APPS_PUBLIC_API.md (registries section)
- docs/POLICY_BLUEPRINT_SINGLE_PATH.md
