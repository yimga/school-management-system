# §2.1 Resolver → Migrate → Delete ordering (nothing left behind)

**Purpose:** Single checklist for the dependency chain: **(1) Resolver first** — ensure a resolver or bounded-context service provides the value; **(2) Migrate** — switch every tenant-facing call site to the resolver; **(3) Delete** — remove legacy paths only after replacement is live and verified. No step skipped; no endpoint or field left without a status.

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1; [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §2b.

---

## 1. Ordering rule (mandatory)

| Phase | Action | Condition to proceed |
|-------|--------|----------------------|
| **1. Resolver first** | Implement or confirm resolver (or bounded-context service) that provides the same value as the legacy singleton read. | Resolver exists, tested, and documented in resolver_registry or domain_ownership. |
| **2. Migrate** | Replace every tenant-facing call site: `SiteSettings.get_solo()` / `.load()` → `get_effective_site_settings(request=..., school=...)` or `get_cached_site_settings(school=...)` or domain-specific resolver. | No tenant app code uses get_solo/load for that value; CI (`lint_tenant_settings --check-get-solo-only`) passes. |
| **3. Delete** | Remove legacy URL, accessor, or column only after (1) and (2) are done and verified in staging. | Replacement is live; no remaining references (grep, URLconf, redirects); documented in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |

**Rule:** Never delete before migrate; never migrate before resolver exists.

---

## 2. Resolver inventory (phase 1 status)

| Resolver / source | Location | Provides | Status |
|-------------------|----------|----------|--------|
| get_effective_site_settings | apps.platform_runtime.helpers | Full site settings for request/school; runtime-first then SiteSettings fallback | **DONE** — used by tenant views |
| get_cached_site_settings | apps.evals.caching (and automation helpers) | Cached site settings for school (no request) | **DONE** — evals/caching migrated from SiteSettings.load() |
| build_tenant_runtime | apps.platform_runtime.runtime_resolver | Blueprint, branding, policy, entitlements, integrations, localization | **DONE** — RESOLVER_ENTRY_POINTS |
| get_effective_policy | apps.policies.resolver | Policy flags and rules | **DONE** |
| workflow_resolver / dashboard_resolver | apps.siteconfig | Workflow and dashboard for action/role | **DONE** |
| RuntimeDefaults + SiteSettings fallback | platform_runtime.helpers | Platform defaults when no tenant | **DONE** |
| PlatformPhaseBDomainSnapshot (batches 4–13) | platform_runtime.phase_b_domain_snapshots + helpers._build_platform_site_settings_base | Per-domain JSON mirrors of `SiteSettings.owned_payload` (excl. brand_experience → PGB; marketplace snapshot strips `sms_api_key`) | **DONE** |

All tenant-facing reads must go through one of the above. No new singleton surface.

---

## 3. Migrate inventory (phase 2 status)

| Call site type | Status | Notes |
|----------------|--------|--------|
| Tenant app code (views, services, tasks) | **DONE** | lint_tenant_settings --check-get-solo-only pass; no get_solo/load in tenant apps. |
| Tests | **Allowlisted** | get_solo only in siteconfig/*/tests, api/tests, finance/tests, accounts/tests, portal/tests, requests/tests — acceptable in test code. |
| siteconfig (definition) | **Definition only** | SiteSettings.get_solo() defined in siteconfig/models.py; callers are platform (backfill_runtime_defaults, sync_from_site_settings) or tests. |
| Management commands (platform) | **Allowlisted** | platform_runtime/management, siteconfig/management (e.g. backfill_runtime_defaults) documented as intentional. |

**Conclusion:** Phase 2 (migrate) is complete for all tenant-facing code. Remaining get_solo/load usages are in tests or allowlisted platform commands.

---

## 4. Delete candidates (phase 3 — after product confirmation)

| Legacy path | Replacement | Condition to delete | Status |
|-------------|--------------|----------------------|--------|
| admin/siteconfig/customizer/ URL | Studio OS Experience (studio_os:experience) | Redirect in place (config/urls.py). Product confirms bookmarks migrated; then optional remove URL or keep redirect. | **BLOCKED** — per BACKLOG Step 6 |
| Other admin/portal URLs with Studio OS equivalent | Per URL | Replacement live; no callers; document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. | NOT DONE (per migration) |
| SiteSettings.get_solo() definition | N/A | Cannot remove while platform backfill and sync use it. Ownership move (model/table to bounded context) is separate, incremental. | NOT DONE |
| **SiteSettings** columns: theme/report FKs + branding media (Batch 3) | **PlatformGlobalBranding** (`brand_experience`) + `apply_theme_experience_state` / resolvers | Physical columns dropped in `siteconfig.0163`; CI: `lint_phase_b_batch3_sitesettings_fk_writes.py` | **DONE** (schema + lint) |

---

## 5. Schema/behavior changes

- **Schema:** Moving a field to another model (e.g. RuntimeDefaults, policy table) requires a Django migration (add column/FK, backfill, then deprecate old column). Each such move is one migration; order by dependency (e.g. policy before entitlements).
- **Behavior:** Resolver must return the same semantics as the legacy read (or a documented, backward-compatible change). Test with contract tests (e.g. test_runtime_contract, get_effective_site_settings coverage).

---

## 6. Checklist summary (nothing left behind)

- [x] **Phase 1 (Resolver):** All required resolvers exist (get_effective_site_settings, get_cached_site_settings, build_tenant_runtime, get_effective_policy, workflow/dashboard resolvers).
- [x] **Phase 2 (Migrate):** All tenant-facing call sites use resolver or get_effective_site_settings; lint_tenant_settings passes; get_solo/load only in siteconfig definition, tests, allowlisted commands.
- [ ] **Phase 3 (Delete):** Legacy path deletion is per-migration and BLOCKED for customizer URL on product confirmation; other deletions as replacement goes live.
- [x] **Ordering documented:** This doc is the single checklist; BACKLOG §2b and SITECONFIG_OWNERSHIP_MIGRATION reference it.

---

*Source: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1; [domain_ownership.md](domain_ownership.md); [site_settings_usage_inventory.md](site_settings_usage_inventory.md).*
