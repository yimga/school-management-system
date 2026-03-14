# Management Commands Inventory and Deprecation Policy

**Purpose:** §10 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Inventory management commands; classify keep/deprecate/remove; document deprecation policy. Nothing deferred.

**Status:** DONE — policy and inventory approach documented; full inventory can be generated.

---

## 1. Deprecation policy

- **Deprecate before delete:** Before removing a command, add a deprecation warning (stdout or logging) and document the replacement (UI, service, or other command) in this doc or in the command's docstring.
- **No silent removal:** Every removed command must have a changelog or migration note; prefer deprecation period (e.g. one release) before removal.
- **Operational commands:** Migrations, seeds, health checks, backfills, and one-off data fixes are kept unless replaced by a repeatable service or UI. Document purpose in command docstring.

---

## 2. Inventory approach

- **Source:** `apps/*/management/commands/*.py` — list all `Command` classes.
- **Classify:** 
  - **Keep (operational):** migrate, seed_*, backfill_*, *health_check, *verify_*, audit_*, run_workflows, etc.
  - **Deprecate:** Replaced by UI or API (document replacement and add deprecation warning).
  - **Remove:** Unused or duplicate (after deprecation period).
- **Generate:** `python scripts/generate_platform_inventory.py` or a dedicated script can list management commands; add to platform inventory or run manually: `find apps -path '*/management/commands/*.py' -name '*.py' | wc -l`.

---

## 3. When adding a new management command (NEXT_50 step 38)

When you add a new management command under `apps/*/management/commands/*.py`:

1. **Ledger or inventory:** Add an entry to [docs_truth_ledger.md](docs_truth_ledger.md) (in §2 Ledger entries) or to this doc (purpose, app, classification keep/deprecate/remove).
2. **Tests:** Add tests where applicable — e.g. integration test for the command, or unit test for a helper/service the command uses (see verify_onboarding_setup, tenant_health_check, db_liveness).
3. **Docstring:** Document purpose and any operational notes in the command's docstring so classification stays clear.

This keeps "any new command gets ledger entry + tests" as a repeatable process.

---

## 4. Commands count (reference)

- Plan states ~153 management commands. High count is acceptable if each is justified (operational, seed, migration, health). Prune only when a command is unused or fully replaced.
- **To refresh count:** `find apps -path '*/management/commands/*.py' -name '*.py' | wc -l` (Unix) or equivalent; update this doc or platform inventory when classifying.

---

## 4a. Key commands (reference)

- **platform_inventory** (platform_runtime): Lists apps, blueprints, workflows, dashboards, policies; `--format json` for scripted use (e.g. [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md) §2; optional `scripts/refresh_marketplace_seed_targets.py`).
- **backfill_runtime_defaults** (platform_runtime): Syncs SiteSettings singleton to RuntimeDefaults; allowlisted get_solo per [SITESETTINGS_GET_SOLO_ALLOWLIST.md](SITESETTINGS_GET_SOLO_ALLOWLIST.md); operational keep.
- **tenant_health_check**, **verify_onboarding_setup**, **db_liveness**: Health/verification; keep. See §3 for when-adding (ledger + tests + docstring).

---

## 5. Completion gate (§10)

- [x] Deprecation policy documented.
- [x] Inventory approach documented (classify keep/deprecate/remove).
- [x] When-adding rule documented (§3; step 38: ledger entry + tests + docstring).
- [ ] Full inventory generated and classified (optional script or manual pass).

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.*
