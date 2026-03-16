# Siteconfig Remediation Ledger (§6.1)

**Purpose:** §6.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Track siteconfig app remediation; nothing deferred.

**Status:** PARTIAL — freeze and inventory done; ownership migration and legacy deletion in progress.

---

## 1. Actions status

| Action | Status | Evidence |
|--------|--------|----------|
| Freeze expansion | DONE | SITECONFIG_FREEZE_POLICY.md; no new tenant-facing logic; CI lint_tenant_settings, lint_siteconfig_legacy_imports |
| Inventory settings usage | DONE | site_settings_usage_inventory.md; domain_ownership.py; generate_platform_inventory.py |
| Migrate ownership | IN PROGRESS | Bounded contexts defined (bounded_context_ownership.md); ownership per field in domain_ownership + docs/domain_ownership.md; evals/caching SiteSettings.load()→get_cached_site_settings(school=); move to brand_experience, runtime_blueprints, policies, etc. |
| Delete legacy behavior paths | NOT DONE | After migration; track in SITECONFIG_OWNERSHIP_MIGRATION.md / migration plan |
| Reduce raw SQL | DONE (audit) | raw_sql_audit.md; siteconfig: cache_utils, recover_database allowlisted |
| Reduce broad exceptions | DONE (audit) | broad_exception_audit.md; allowlist + CI |
| Remove Gilead residue | DONE | migration 0155_normalize_gilead_residue_runmycampus; gilead_residue_inventory.md; lint_gilead_residue |
| Replace giant admin pages with bounded consoles | IN PROGRESS | Phase B: Bounded console at siteconfig:console_domains_hub (/siteconfig/console/); linked from control plane nav "System config"; manager uses control_plane_base shell; domains link to Studio OS (Experience, Automation, Output) and feature control; further replacement incremental. |

---

## 2. Current score

**5.0/10** per plan. Target 11/10 via ownership migration, bounded consoles, and runtime-only tenant behavior.

---

## 3. Completion gate (§6.1)

- [x] Freeze and inventory complete.
- [ ] Ownership migrated into bounded contexts; legacy paths deleted.
- [ ] Giant admin pages replaced by bounded consoles (Studio OS).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §6.1.*
