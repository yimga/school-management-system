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
| `ensure_superadmin` (management command) | Command | **KEEP (thin alias)** | `ensure_superuser` | **Not removed:** `apps/accounts/management/commands/ensure_superadmin.py` delegates to `ensure_superuser` with fixed `admin`/`admin` for deploy scripts. Prefer `ensure_superuser` when you need custom credentials. Tests: `apps/accounts/tests/test_ensure_superadmin_command.py`. |
| `/admin/siteconfig/customizer/` | URL | **REDIRECT** | `studio_os:experience` (`/studio/experience/`) | config/urls.py `admin_siteconfig_customizer_redirect`. Optional: remove URL when product confirms bookmarks migrated. |
| `/siteconfig/customizer/` | URL | **REDIRECT** | `studio_os:experience` (`/studio/experience/`) | Phase B: redirect added in config/urls.py, config/tenant_urls.py, config/manager_urls.py. |
| `siteconfig.webhook_delivery` (code) | Module ref | **REMOVED** | `apps.events.webhooks` | Callers use events.webhooks. |
| `/siteconfig/workflow-hub/` | URL | **REDIRECT** | `studio_os:automation` | config/urls.py `legacy_workflow_hub_redirect`. Step 6 / Optional 12 done. If product confirms a different legacy path, add that path to same redirect or document in SUBTRACTIVE_CLEANUP_RELEASE_NOTES. |
| `/siteconfig/report-library/` | URL | **REDIRECT** | `studio_os:output?pane=reports` (default; merges existing query) | `legacy_report_library_redirect` in config/urls.py + tenant_urls.py (+ manager reuse). §4.4 / §6.1 hub pane. |
| `/siteconfig/reports/` | URL | **REDIRECT** | `studio_os:output?pane=reports` | Same as above. |
| `/siteconfig/theme-colors/` | URL | **KEEP + redirect** | `studio_os:experience` (staff) or `?standalone=1` (non-staff with `settings.manage`) | `theme_colors_page`: GET without `embed=1`/`standalone=1` sends staff to Experience Studio; others to full-page form. POST targets unchanged; success redirect mirrors same rule. Deep link `theme_colors` → `studio_os:experience`. |
| `/siteconfig/feature-control/` | URL | **REDIRECT** (GET) | `studio_os:control` | `embed=1` keeps embeddable form for Studio iframes. |
| Document library manage (portal) | URL | **REDIRECT** (GET) | `studio_os:output?pane=documents` | `document_library_manage`; `embed=1` preserved. |
| `siteconfig.views.customizer` | View | **REMOVED** | — | All callers use `studio_os:experience`; config-level redirect for `/siteconfig/customizer/` only. LEGACY_PATH_INVENTORY §2. |
| `siteconfig.views.report_library` | View | **REMOVED** | — | All callers use `studio_os:output`; config-level redirect for `/siteconfig/reports/` and `/siteconfig/report-library/`. |
| `siteconfig.views_dashboard_config.workflow_hub` | View | **REMOVED** | — | All callers use `studio_os:automation`; config-level redirect for `/siteconfig/workflow-hub/`. |
| `super:admin_bridge_integrations` (and 7 sibling URL **names**) | URL name | **REMOVED** | `super:admin_bridge` + `kwargs={"bridge_key": "…"}` | Legacy **paths** (e.g. `/super/admin-bridge/integrations-marketplace/`) **301** to canonical slug; `reverse("super:admin_bridge_*")` raises `NoReverseMatch`. Tests: `test_legacy_admin_bridge_paths_redirect_to_canonical_slug`, `test_legacy_admin_bridge_named_urls_removed`. |

---

## 3. Product sign-off (Step 6 unblocked) and further removals

**Product sign-off (2026-03-12):** Remove old legacy paths; new config / Studio OS is canonical. System and code aligned to current platform direction; keep only current tenant and reconfigure to match current config. Legacy siteconfig views `workflow_hub` and `report_library` are now redirect-only to Studio OS (query string preserved).

**Further legacy path removals (product sign-off):** Siteconfig views `customizer`, `report_library`, and `workflow_hub` have been **removed**. All in-app links and reverse() callers now use `studio_os:experience`, `studio_os:output`, and `studio_os:automation`. Config-level redirects remain for `/siteconfig/customizer/`, `/siteconfig/workflow-hub/`, `/siteconfig/report-library/`, and `/siteconfig/reports/` so bookmarks and external links still work.

1. **admin/siteconfig/customizer/** — Redirect in place; keep redirect for bookmarks.
2. **siteconfig/customizer/** — Config-level redirect only (no siteconfig view).
3. **Workflow hub / report library / customizer:** **DONE.** Config redirects only; siteconfig views removed. All callers use Studio OS URLs.

---

## 4. Automated validation (replacement + purge discipline)

Run after changes that touch redirects, admin bridges, or outcome-center links:

```bash
python -m pytest apps/studio_os/tests/test_phase_05_legacy_redirects.py \
  apps/schools/tests/test_super_config_migration_urls.py \
  apps/siteconfig/tests/test_control_outcome_center.py \
  apps/schools/tests/test_platform_admin_bridge_completeness.py -q
```

Or use the bundled script (same tests):

```bash
python scripts/validate_legacy_replacements.py
```

**In-app reverse():** Only `super:admin_bridge` with `kwargs={"bridge_key": "…"}` — legacy URL names were removed (2026-03-25). Bookmark **paths** under `/super/admin-bridge/…` still work via **301** to the slug route.

## 5. Policy (nothing left behind; non-negotiable)

- Before deleting a legacy path: grep for references (URLs, imports, redirects); ensure replacement is live and linked. **CANDIDATE** rows are **not** permanent deferrals—each must become REMOVED, REDIRECT, or KEEP with justification, per SOT §11.4 queue discipline.
- After each deletion: update this inventory, add a row to SUBTRACTIVE_CLEANUP_RELEASE_NOTES, and run CI (lint_tenant_settings, manage.py check).
- New legacy paths (e.g. from future migrations) must be added here with status CANDIDATE until removed or redirected.

**Single pane completion (Phase I.5 world-class):** High-use admin lives in super_* / Control Studio (RUNBOOK_ADMIN_TO_SUPER_MIGRATION). "Open in backoffice" is only for rare/legacy flows; document any such link here or in the runbook.

---

## 6. Structural split (BR-12)

| Module | Status | Notes |
|--------|--------|-------|
| `apps/schools/super_views_helpers.py` | **KEEP** | Shared geo/registry helpers |
| `apps/schools/super_views_provisioning.py` | **KEEP** | `api_create_school` |
| `apps/schools/super_views.py` | **REDUCED** | Imports provisioning + helpers |

---

*Source: RUNMYCAMPUS §1.7 (delete as aggressively as you add); BACKLOG §2d.*
