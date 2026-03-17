# Subtractive cleanup — release notes template

**Purpose:** NEXT_50 step 50. Every release that removes legacy paths, deprecates endpoints, or applies migrations that delete/replace behavior must document them in a "Subtractive cleanup" section of release notes. Single place for template and running log.

**Rule:** When editing release notes (CHANGELOG or deploy announcement), add or update a subsection **Subtractive cleanup** with the items below (and any new removals in this release).

---

## Template for release notes

```markdown
## Subtractive cleanup

- **Removed paths / code:** (list files or URL paths removed or replaced)
- **Deprecated (still present, do not use):** (list if any)
- **Migrations:** (list migrations that drop columns, remove tables, or rename; note run order)
```

---

## Completed subtractive cleanups (for reference when drafting release notes)

| Release / date | Removed / replaced | Notes |
|----------------|--------------------|--------|
| (pre-tagged) | Raw SQL in `apps/schools/middleware.py` | Replaced with `rls_context.set_rls_school_id` / `reset_rls_school_id`; allowlist entry for middleware removed; see raw_sql_replacement_targets.md. |
| (pre-tagged) | siteconfig.webhook_delivery | Removed; callers use apps.events.webhooks (BACKLOG legacy path). |
| (this release) | `ensure_gilead_admin` management command | Removed (NEXT_50 step 6 subtractive cleanup). Replacement: `ensure_default_tenant_admin` with same args (e.g. `--use-admin-user`, `--slug`). PLATFORM_ACCESS_AND_CREDENTIALS.md, GILEAD_RESIDUE.md, MANAGEMENT_COMMANDS_INDEX.md updated. |
| (this release) | `admin/siteconfig/customizer/` legacy URL | Replaced: path now redirects to Studio OS Experience (`studio_os:experience`). config/urls.py `admin_siteconfig_customizer_redirect`; BACKLOG §2d candidate. Optional: remove URL later when product confirms bookmarks migrated. |
| (this release) | `/siteconfig/workflow-hub/` and `/siteconfig/report-library/` legacy URLs | Redirect: paths now redirect to Studio OS Automation and Output (`studio_os:automation`, `studio_os:output`). config/urls.py `legacy_workflow_hub_redirect`, `legacy_report_library_redirect`. LEGACY_PATH_INVENTORY §2 REDIRECT. Step 6 / Optional 12. |
| (this release) | `/siteconfig/customizer/` legacy URL (Phase B) | Redirect: path now redirects to Studio OS Experience (`studio_os:experience`). config/urls.py, config/tenant_urls.py, config/manager_urls.py `legacy_siteconfig_customizer_redirect`. LEGACY_PATH_INVENTORY §2 REDIRECT. RUNMYCAMPUS Phase B "Delete old behavior paths". |
| (this release) | siteconfig `workflow_hub` and `report_library` legacy render | Product sign-off 2026-03-12. Views now redirect-only to `studio_os:automation` and `studio_os:output` (query string preserved). Legacy render logic removed. Step 6 DONE. LEGACY_PATH_INVENTORY §3. |
| (this release) | `ensure_superadmin` management command | **REMOVED** 2026-03-12. Replacement: `python manage.py ensure_superuser` (supports ADMIN_PASSWORD, --username, --password; creates or promotes superuser). TENANT_AND_SUPERADMIN.md, PLATFORM_ACCESS_AND_CREDENTIALS.md, MANAGEMENT_COMMANDS_INDEX.md, management_commands_inventory.md updated. LEGACY_PATH_INVENTORY §2. |
| 2026-03-17 | Full release sign-off | All subtractive cleanups above included in release notes; migrations as listed. Pre-release, Build, Deploy, Post-release and optional items approved. |
| (this release) | **Further legacy path removals (product sign-off)** | Removed siteconfig views `customizer`, `report_library`, and `workflow_hub`. All in-app links and code now use `studio_os:experience`, `studio_os:output`, and `studio_os:automation`. Config-level redirects kept for `/siteconfig/customizer/`, `/siteconfig/workflow-hub/`, `/siteconfig/report-library/`, `/siteconfig/reports/`. LEGACY_PATH_INVENTORY §2 updated. |

**Migrations to mention when applicable:** `0155_normalize_gilead_residue_runmycampus` (theme/report defaults); `0156_alter_educationsystemprofile_subject_seed_and_more` (EducationSystemProfile subject_seed/term_labels serializable defaults); `platform_runtime.0004_runtimedefaults_cache_rankings_interval` (Step 4 first-class ownership); any migration that drops or renames legacy siteconfig/schools paths after replacement.

**Legacy path inventory:** For a single list of all legacy paths (REMOVED / REDIRECT / CANDIDATE) and optional next steps when product confirms, see [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md).

---

*Source: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §1.7; [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) step 50.*
