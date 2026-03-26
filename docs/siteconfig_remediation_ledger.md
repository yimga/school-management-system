# Siteconfig Remediation Ledger (§6.1)

**Purpose:** §6.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Track siteconfig app remediation; nothing deferred.

**Status:** **MET (repo §2.1 / §12 behavioral gate)** — freeze, inventory, domain ownership, runtime-first tenant behavior, bounded Configuration Control Center, and Phase B SiteSettings dismantling per SOT. **§11.4:** subtractive legacy URLs + further bounded-console replacement.

---

## 1. Actions status

| Action | Status | Evidence |
|--------|--------|----------|
| Freeze expansion | DONE | SITECONFIG_FREEZE_POLICY.md; no new tenant-facing logic; CI lint_tenant_settings, lint_siteconfig_legacy_imports |
| Inventory settings usage | DONE | site_settings_usage_inventory.md; domain_ownership.py; generate_platform_inventory.py |
| Migrate ownership | DONE (behavioral) | Bounded contexts (bounded_context_ownership.md); field ownership in domain_ownership; tenant truth via `get_effective_site_settings` / resolver — SOT §2.1 completion gates [x]. |
| Delete legacy behavior paths | §11.4 | Subtractive cleanup per SITECONFIG_OWNERSHIP_MIGRATION.md + LEGACY_PATH_INVENTORY; not an open **PARTIAL** §12 item. |
| Reduce raw SQL | DONE (audit) | raw_sql_audit.md; siteconfig: cache_utils, recover_database allowlisted |
| Reduce broad exceptions | DONE (audit) | broad_exception_audit.md; allowlist + CI |
| Remove Gilead residue | DONE | migration 0155_normalize_gilead_residue_runmycampus; gilead_residue_inventory.md; lint_gilead_residue |
| Replace giant admin pages with bounded consoles | IN PROGRESS | Phase B: Bounded console at siteconfig:console_domains_hub (/siteconfig/console/); linked from control plane nav "Configuration Control Center"; manager uses control_plane_base shell; domains link to Studio OS (Experience, Automation, Output) and feature control; further replacement incremental. |

---

## 2. Current score

**5.0/10** per plan. Target 11/10 via ownership migration, bounded consoles, and runtime-only tenant behavior.

---

## 3. Completion gate (§6.1)

- [x] Freeze and inventory complete.
- [x] Ownership migrated into bounded contexts (behavioral §2.1); legacy path subtraction tracked under §1.7 / LEGACY_PATH_INVENTORY.
- [x] Bounded consoles ship (CCC + Studio OS integration); further giant-admin replacement = §11.4 cadence.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §6.1.*
