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
| `/admin/siteconfig/customizer/` | URL | **REDIRECT** | `studio_os:experience` (`/studio/experience/`) | config/urls.py `admin_siteconfig_customizer_redirect`. Optional: remove URL when product confirms bookmarks migrated. |
| `/siteconfig/customizer/` | URL | **CANDIDATE** | Studio OS Experience | Same behavior as Studio OS Experience hub. When product confirms, can redirect to `studio_os:experience` or keep as alternate entry. |
| `siteconfig.webhook_delivery` (code) | Module ref | **REMOVED** | `apps.events.webhooks` | Callers use events.webhooks. |
| `/siteconfig/workflow-hub/` | URL | **REDIRECT** | `studio_os:automation` | config/urls.py `legacy_workflow_hub_redirect`. Step 6 / Optional 12 done. If product confirms a different legacy path, add that path to same redirect or document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| `/siteconfig/report-library/` | URL | **REDIRECT** | `studio_os:output` | config/urls.py `legacy_report_library_redirect`. Step 6 / Optional 12 done. If product confirms a different legacy path, add that path to same redirect or document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |

---

## 3. Optional next steps (when product confirms)

1. **admin/siteconfig/customizer/** — Change from redirect to 410 Gone, or keep redirect indefinitely for bookmarks.
2. **siteconfig/customizer/** — Redirect to `studio_os:experience` or deprecate view and keep redirect only.
3. **Workflow hub / report library:** **DONE.** §2 paths `/siteconfig/workflow-hub/` and `/siteconfig/report-library/` redirect to `studio_os:automation` and `studio_os:output`. If product identifies different legacy URLs, add those paths to the same redirect views in config/urls.py and document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES.

---

## 4. Policy (nothing left behind)

- Before deleting a legacy path: grep for references (URLs, imports, redirects); ensure replacement is live and linked.
- After each deletion: update this inventory, add a row to SUBTRACTIVE_CLEANUP_RELEASE_NOTES, and run CI (lint_tenant_settings, manage.py check).
- New legacy paths (e.g. from future migrations) must be added here with status CANDIDATE until removed or redirected.

---

*Source: RUNMYCAMPUS §1.7 (delete as aggressively as you add); BACKLOG §2d.*
