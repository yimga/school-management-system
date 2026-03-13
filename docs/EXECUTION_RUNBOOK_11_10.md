# RunMyCampus 11/10 Execution Runbook

**Purpose:** Short phase-completion notes for the 11/10 execution plan. Single source of truth for status remains [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). **All optionals = non-negotiable.** Every deliverable in the authoritative plans (RunMyCampus_Master_Blueprint_SINGLE, Design_System_Blueprint_For_Cursor, Technical_Refactor_Map_and_Tenant_Blueprint_Integration, RUNMYCAMPUS_11_10_NORTH_STAR_COMPLETION_PLAN, ledger, execution plan) is required. See [NON_NEGOTIABLE_BACKLOG.md](NON_NEGOTIABLE_BACKLOG.md) and ledger §14.

## Phase completion

- **Phase A (Red-alert hardening):** Verified pre_deploy_gate passes for lint_secret_exposure, lint_gilead_residue, lint_no_print_in_apps, lint_csrf_exempt_usage, lint_allow_any_usage, lint_raw_sql_usage, lint_broad_except. Ledger §2.1–2.4 DONE. Artifacts: docs/security/SITESETTINGS_INVENTORY.md, docs/security/CSRF_EXEMPT_AUDIT.md, docs/security/ALLOWANY_API_AUDIT.md, docs/security/raw_sql_audit.md.
- **Phase B (siteconfig/SiteSettings dismantling):** Verified lint_tenant_settings (get_solo, school.settings/features) and lint_siteconfig_legacy_imports pass. Ledger §2.1 DONE; SITESETTINGS_INVENTORY.md and runtime resolver in place.
- **Phase C (Runtime and metadata law):** Ledger §3.1–3.3 DONE. Code: platform_runtime/helpers.py get_effective_site_settings, test_precedence.py, test_runtime_contract.py, test_metadata_catalog. Local test DB had migration conflict; CI/pre_deploy_gate runs these tests.
- **Phase D (Studio OS):** Ledger §4 DONE. apps/studio_os with shell and five modes (experience, automation, output, launch, control); urls and views present; legacy siteconfig routes retained for backward compatibility.
- **Phase E (Ecosystem productization):** Ledger §7 DONE. apps/packages (InstalledPackage, ExperiencePack, DocumentPack), package types blueprint/workflow/dashboard/policy/theme; marketplace and seeding per ledger.
- **Phase F (UX and marketing):** Ledger §8 DONE. Role-home, contextual actions, page archetypes, marketing front per ledger.
- **Phase G (Docs truth):** Ledger §9 DONE. DOCS_COMPLETION_AUDIT and DOCS_ROADMAP_AUDIT reconciled; PHASE_10_BACKLOG/WHATS_LEFT as single backlog refs.
- **Final audit rerun:** Completed. All lints passed. Scoring gate (§12) and final blunt summary checkpoints satisfied per ledger. See AUDIT_RERUN_RESULT.md.

## Advanced coding pass (2026-03-12)

- **AI gateway → persistent audit:** Every `invoke()` path now persists to `AIActionAuditLog` via `platform_runtime.helpers.log_ai_action` from `_audit_log()` (task_type, tier, outcome, request_id, user_id, tenant_id). Callers can pass `metadata={"user_id": ...}` so audit rows are user-attributable.
- **Studio OS unified preview:** Single source for embed URLs: `apps/studio_os/services.py` defines `STUDIO_MODE_EMBED_TARGETS` and `get_studio_preview_url(mode, request)`. Shell view uses it in `_resolve_embed_urls()` instead of ad-hoc `reverse(...) + "?embed=1"`.
- **Metadata lineage API:** `apps/metadata/usage_registry.get_lineage_consumers(entity_code=..., field_id=...)` is the documented entry point for "what uses this entity/field?" (downstream dashboards, workflows, policies, reports); delegates to `metadata.services.get_downstream_dependencies`.

## Named artifact locations

| Artifact | Location |
|----------|----------|
| site_settings_usage_inventory | docs/security/SITESETTINGS_INVENTORY.md |
| Public/exempt endpoint ledger | docs/security/CSRF_EXEMPT_AUDIT.md, docs/security/ALLOWANY_API_AUDIT.md |
| Raw SQL ledger | docs/security/raw_sql_audit.md |
| Gilead residue | lint_gilead_residue.py (CI); runtime-visible refs excluded by script |
