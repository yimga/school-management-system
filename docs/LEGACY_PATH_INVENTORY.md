# Legacy Path Inventory

**Purpose:** §3.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) and [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §2d. Single inventory of legacy URLs, views, and re-exports so each can be deprecated and deleted **per migration** after (1) a replacement exists and is used, (2) no callers reference the old path.

**Rule:** Each deletion is a separate change (remove route → remove view → remove re-exports). Doing it in bulk without migration would break callers. Document every removal in [SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md](SUBTRACTIVE_CLEANUP_RELEASE_NOTES.md).

---

## 1. Status key

| Status | Meaning |
|--------|--------|
| **REMOVED** | Path or code deleted; documented in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| **REDIRECT** | Legacy URL kept but redirects to replacement; safe for bookmarks. |
| **CANDIDATE** | Replacement exists; deletion/redirect pending product confirmation. |
| **KEEP** | Legacy path retained by design (e.g. alternate entry). |

---

## 2. URL / route inventory

| Path | Type | Status | Replacement | Notes |
|------|------|--------|-------------|--------|
| `ensure_gilead_admin` (management command) | Command | **REMOVED** | `ensure_default_tenant_admin` | Same args. Documented in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| `ensure_superadmin` (management command) | Command | **CANDIDATE** | `ensure_superuser` | Deprecation warning in command; use ensure_superuser (ADMIN_PASSWORD, --username, --password). Removal after deprecation period per management_commands_inventory.md §5a. |
| `/admin/siteconfig/customizer/` | URL | **REDIRECT** | `studio_os:experience` (`/studio/experience/`) | config/urls.py `admin_siteconfig_customizer_redirect`. Optional: remove URL when product confirms bookmarks migrated. |
| `/siteconfig/customizer/` | URL | **REDIRECT** | `studio_os:experience` (`/studio/experience/`) | Phase B: redirect added in config/urls.py, config/tenant_urls.py, config/manager_urls.py. |
| `siteconfig.webhook_delivery` (code) | Module ref | **REMOVED** | `apps.events.webhooks` | Callers use events.webhooks. |
| `/siteconfig/workflow-hub/` | URL | **REDIRECT** | `studio_os:automation` | config/urls.py `legacy_workflow_hub_redirect`. Step 6 / Optional 12 done. If product confirms a different legacy path, add that path to same redirect or document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| `/siteconfig/report-library/` | URL | **REDIRECT** | `studio_os:output` | config/urls.py `legacy_report_library_redirect`. Step 6 / Optional 12 done. If product confirms a different legacy path, add that path to same redirect or document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |

---

## 3. Product sign-off (Step 6 unblocked) and optional next steps

**Product sign-off (2026-03-12):** Remove old legacy paths; new config / Studio OS is canonical. System and code aligned to current platform direction; keep only current tenant and reconfigure to match current config. Legacy siteconfig views `workflow_hub` and `report_library` are now redirect-only to Studio OS (query string preserved).

1. **admin/siteconfig/customizer/** — Redirect in place; keep redirect for bookmarks.
2. **siteconfig/customizer/** — View is redirect-only to `studio_os:experience`.
3. **Workflow hub / report library:** **DONE.** Config redirects + siteconfig views redirect-only to `studio_os:automation` and `studio_os:output`. Legacy render logic removed.

---

## 4. Policy (nothing left behind)

- Before deleting a legacy path: grep for references (URLs, imports, redirects); ensure replacement is live and linked.
- After each deletion: update this inventory, add a row to SUBTRACTIVE_CLEANUP_RELEASE_NOTES, and run CI (lint_tenant_settings, manage.py check).
- New legacy paths (e.g. from future migrations) must be added here with status CANDIDATE until removed or redirected.

---

*Source: RUNMYCAMPUS §1.7 (delete as aggressively as you add); BACKLOG §2d.*
