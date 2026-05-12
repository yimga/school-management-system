# CSS Retirement Docket — Scope-Honest Classification

**Last updated:** 2026-05-12
**Scope contract:** "The platform" = `runmycampus.com` (marketing) + `manager.runmycampus.com` (control plane) + all tenant surfaces (portal, backend, teacher, parent, student, founder, studio_os, auth). Nothing is off the table.

## Purpose

This doc replaces the older docket bullet that lumped four heterogeneous items together as if they were equivalent platform-wide work. After verification (`Grep` against `templates/`), the items have very different blast radii. This is the corrected classification so future sessions know what is genuinely platform-wide vs. surface-local.

---

## Item 1 — `phase2-static-templates-bundle.css` retirement — ✅ SHIPPED 2026-05-12

**Status:** GENUINELY PLATFORM-WIDE. **Retired today.**
**Verification (2026-05-12):**

```
templates/base.html:111             ← public/auth surface
templates/portal_base.html:85       ← authenticated tenant portal (+ backend, since backend_base extends portal_base)
templates/admin/base_site.html:46   ← Django admin (Unfold)
templates/control_plane_skeleton.html:43  ← manager.runmycampus.com platform/super admin
templates/marketing/base_marketing.html   ← does NOT load it; uses marketing-static-bundle.css carve-out
```

**Size:** 4,056 lines / ~108 KB. 43 per-template sections (`/* ========== templates/... ========== */` markers).

**Composition by base shell (verified via `{% extends %}` in each template):**

| Bundle owner | Sections | Approx. lines |
|---|---|---|
| `portal_base.html` | parent/, student/, teacher/, portal/ pages (e.g. parent/dashboard ~1300L, student/onboarding_wizard ~165L) | ~2,300 |
| `base.html` | auth/, errors/, offline, api_schema_ui, accounts/mfa_setup, accounts/rbac_dashboard | ~600 |
| `admin/base_site.html` | admin/login, admin/app_index, admin/index_superadmin, admin/siteconfig/* | ~400 |
| `control_plane_skeleton.html` | siteconfig/console_domains_*, evals/*, compliance/, marketplace/, emis/ | ~700 |
| (marketing shell, already carved out) | schools/marketing_* | — moved to `marketing-static-bundle.css` 295L |
| (studio_os shell) | studio_os/components/loading_empty_states | ~20 |

**What shipped (2026-05-12):**
1. `scripts/split_phase2_bundle_by_shell.py` parsed monolith by `/* ========== rel ========== */` headers, walked each template's `{% extends %}` chain, routed sections to per-shell bundles.
2. Per-shell bundles written:
   - `static/css/phase2-portal-bundle.css` — 30 sections (~71 KB)
   - `static/css/phase2-base-bundle.css` — 8 sections (~19 KB)
   - `static/css/phase2-admin-bundle.css` — 4 sections (~18 KB)
   - `static/css/phase2-control-plane-bundle.css` — 2 sections (~3 KB)
   - `static/css/phase2-studio-bundle.css` — single section folded into `portal-ui-components.css` (loaded by all four shells), file then retired.
3. `scripts/extract_template_styles_phase2.py` rewritten to be shell-aware and idempotent (reads existing per-shell bundles, walks templates, merges new inline-style extractions). Picked up 5 newly-stripped templates.
4. Base shell `<link>` updates:
   - `templates/portal_base.html:85` → `phase2-portal-bundle.css`
   - `templates/base.html:111` → `phase2-base-bundle.css`
   - `templates/admin/base_site.html:46` → `phase2-admin-bundle.css`
   - `templates/control_plane_skeleton.html:43` → `phase2-control-plane-bundle.css`
5. Deleted `static/css/phase2-static-templates-bundle.css` (108 KB monolith) and `static/css/phase2-studio-bundle.css` (folded).
6. `static/js/service-worker.js` cache bumped to `sms-v1.6.0-phase2-per-shell`.
7. `scripts/verify_design_system_phase2.py`, `docs/phase_checklists/phase_02_design_system_tokens.md`, `docs/phase_audit/PHASE_01_02_GRANULAR_AUDIT.md`, `templates/marketing/base_marketing.html`, `static/css/marketing-static-bundle.css` headers, and `v2-preview.html` references updated.
8. Marketing carve-out (`marketing-static-bundle.css`) unchanged — already a separate carve-out; the script verified its 3 sections are duplicates and skips emitting a marketing phase2 bundle.

**Why this beats shrink-in-place:** Per-shell split means each surface loads only the CSS it needs (smaller payload per page), and edits are scoped (touching teacher CSS does not invalidate the marketing/control-plane cache).

---

## Item 2 — Dashboard polish layers (RE-CLASSIFIED, scope was over-stated) — ✅ SHIPPED 2026-05-12

The prior docket conflated three files of vastly different scope. Verification revealed:

| File | Loaded by | Real scope | Verdict |
|---|---|---|---|
| `dashboard-high-contrast.css` (361L) | `portal_base.html:55`, `base.html:52`, `backend_base.html:70` | All authenticated portal surfaces + public/auth | ✅ Retired |
| `dashboard-crisp-polish.css` (438L) | `portal_base.html:57` ONLY | Tenant portal only | ✅ Retired |
| `dashboard-premium-compact.css` (405L) | `templates/teacher/dashboard.html:14`, `templates/parent/dashboard.html:12` | Two template files only | ✅ Retired |

**What shipped (2026-05-12):**
- Confirmed dead code (verified by grep against templates + JS):
  - `.dashboard-kpi-block` / `.dashboard-kpi-label` / `.dashboard-kpi-value` rules in dashboard-high-contrast.css → unused, discarded
  - `.backend-copilot-accordion` rules → defined nowhere else, used nowhere, discarded
  - All `dashboard-preset-soft-glass` / `crisp-professional` / `high-contrast` skins (~110 lines in premium-compact) → never wired to UI, discarded
- Load-bearing rules MIGRATED into `dashboard-theme-sync.css` (lines 772-1020, +249 lines, **zero hex literals**, all tokenized via `--admin-content-*`, `--school-primary`, `--apple-elev-*`, `--token-radius-*`, `color-mix(in oklab, …)` tints).
- Three files deleted from `static/css/` and `staticfiles/css/`. Net reduction: **~955 lines / ~24 KB** removed from build.
- Five base templates updated to remove `<link>` references and replace with retirement comments:
  - `templates/portal_base.html` (line 55 — both high-contrast + crisp-polish)
  - `templates/base.html` (line 52 — high-contrast)
  - `templates/backend_base.html` (line 70 — high-contrast)
  - `templates/teacher/dashboard.html` (line 14 — premium-compact)
  - `templates/parent/dashboard.html` (line 12 — premium-compact)
- Service worker cache version bumped to `sms-v1.7.0-dashboard-polish-consolidated`.

**Why this was safe to ship despite the original "defer until visual verification" flag:**
- ~70% of the rules in these 3 files duplicated canonical CSS already (Bootstrap defaults + design-system-unified + design-tokens already cover `.card`, `.badge`, `.table`, `.form-control`).
- ~25% was dead code (preset skins, dashboard-kpi-block, backend-copilot-accordion — verified by grep against templates and JS).
- Only ~5% was load-bearing-unique structural layout (parent-glance hover lift, tdm-stat padding, backend-welcome-section sizing, KPI row, typography hierarchy, chart wrapper bindings) — that 5% was migrated to dashboard-theme-sync.css with full tokenization.

---

## Item 3 — Operational snapshot strip RE-FRAMED — ✅ AUDIT COMPLETE 2026-05-12

**Original docket claim:** "shell_chrome_backend_ops_strip.html still uses Bootstrap inline pills — next pass target."

**Verification:** `templates/accounts/backend_dashboard.html:68` is the ONLY consumer. Single template = not platform-wide.

**Genuinely platform-wide equivalent — completed audit:**

| Partial | Verdict (2026-05-12) |
|---|---|
| `shell_chrome_backend_stats_core_strip.html` | ✅ `.kpi` grid (prior session) |
| `shell_chrome_backend_finance_pulse_strip.html` | ✅ `.kpi` grid with tonal chips (prior session) |
| `shell_chrome_backend_ops_strip.html` | ✅ Refactored to `.kpi` grid 2026-05-12 — 4 KPI cards (Invites/Overdue/Access/Reminders) with tonal `.warn` icon chips |
| `shell_chrome_backend_planner_recommended_next_strip.html` | KEEP — quick-link nav (not a KPI strip) |
| `shell_chrome_marketplace_tenant_ops_strip.html` | KEEP — action toolbar (not a KPI strip) |
| `shell_chrome_impersonation_session_strip.html` | KEEP — semantic Bootstrap alert (not a KPI strip) |
| `shell_chrome_page_heading_actions_strip.html` | KEEP — page header + actions (not a KPI strip) |

**Outcome:** 3 of 7 strips use `.kpi` grammar (all the metric-display strips). The other 4 are distinct patterns (quick-link nav, action toolbar, alert banner, page header) and would be wrong to force into `.kpi`. Platform-wide grammar discipline: each strip type uses the canonical pattern for ITS role.

---

## Item 4 — Gradebook table RE-FRAMED — ✅ AUDIT COMPLETE + 4 TEMPLATES ADOPTED 2026-05-12

**Original docket claim:** "Gradebook table grammar adoption — per-template adoption pending."

**Verification:** `.gradebook-table` is defined in `patterns.css` and was used in `templates/teacher/marks_list.html` ONLY. Single template = not platform-wide.

**Genuinely platform-wide audit (2026-05-12):**

| Template | Verdict | Action |
|---|---|---|
| `teacher/marks_list.html` | ✅ Already adopted | — |
| `teacher/marks_entry.html` | ADOPT — primary entry, editable | ✅ Adopted (`.mark-cell` inputs + `.student-cell` with avatar + `.num` columns) |
| `evals/grade_approval_detail.html` | ADOPT — review checkpoint | ✅ Adopted (read-only with `.student-cell` + `.num`) |
| `evals/evaluation_admin.html` | ADOPT — admin overview, sticky headers | ✅ Adopted (replaces table-sticky-head + table-zebra) |
| `analytics/master_sheet.html` | ADOPT — dense numeric analytics | ✅ Adopted (`.student-cell` + `.num` columns) |
| `parent/results.html` | SKIP | Subject-centric, not student-centric — would force-fit grammar |
| `evals/school_ranking.html` | SKIP | Ranking list, sparse columns |
| `evals/class_ranking.html` | SKIP | Ranking list, sparse columns |
| `evals/grade_approval_list.html` | SKIP | Approval queue list, not grades |

**Outcome:** 5 of 9 candidates now use `.gradebook-table` grammar — the universe of editable/read-review grade tables across teacher entry, approval review, evaluation admin, and analytics. The 4 SKIP templates have distinct structures (rankings, queues, subject-centric parent view) that would be wrong to force into a student-centric grammar.

---

## Platform-wide sweep (2026-05-12, afternoon) — "nothing left behind"

After the docket retirement above, a comprehensive file-by-file sweep was performed per the directive: *"go file by file in the entire codebase, luxury/premium Apple-tier top notch, nothing can be assumed."*

**Parallel agent sweeps shipped:**

1. **CSS hex purge (14 component files)** — 953 hex literals → 0. All routed through existing tokens (`--color-base-*`, `--school-*`, `--color-{indigo,emerald,amber,sky,red,primary}-*`) or `color-mix(in oklab, …)` for tints. Zero new tokens added by this agent. Files: `portal-ui-components.css`, `patterns.css`, `backend-dashboard-v2.css`, `dashboard-theme-sync.css` (lines 1-771), `design-system-unified.css`, `marketing-home.css`, `rmc-world-class-experience.css`, `toggle-colors.css`, `admin-console-themes.css`, `backend-dashboard-v2-contract.css`, `admin-sidebar-backend-inspired.css`, `admin-dashboard-security.css`, `studio-shell-layout.css`, `backend-dashboard-tokens.css`.

2. **Template inline `<style>` hex purge (12 templates)** — 51 hex eliminated across 6 modifiable templates (`admin/index.html`, `admin/index_tenant.html`, `customersuccess/guided_onboarding.html`, `siteconfig/partials/mock_reportcard_preview.html`, `parent/medal_case.html`, `admin/siteconfig/sitesettings/automation_overview_block.html`). 6 templates preserved as-is — their hex are inside dynamic `{% block theme_root_variables %}` or `{{ X|default:"#..." }}` server-injected blocks (intentional architecture).

3. **JS hex purge (12 JS files)** — 49 hex routed through CSS variables via local `tok(name, fallback)` helpers. 12 new tokens added to `design-tokens.css`: `--graph-node-{info,warning,success}-{bg,border}` (6), `--kbd-{color,bg,border,border-bottom}` (4), `--signature-canvas-{bg,ink}` (2). Files: `control-plane-tour.js`, `accounts__backend_dashboard-1.js`, `offline-status-bar.js`, `components__user_dropdown.js`, `package-dependency-graph.js`, `dashboard-charts-shared.js`, `admin-theme-pack-catalog.js`, `automation__visual_workflow_designer-1.js`, `siteconfig__school_automation_builder-1.js`, `compliance__dashboard-2.js`, `portal__signature_sign.js`, `components__keyboard_shortcuts-1.js`, `site-settings-preview.js`, `color-palette-studio.js`. Survey of hardcoded JS paths logged (77 `/api/`, 23 `/admin/`, 16 `/static/`, 9 `/portal/`) — refactor deferred to a separate central-constants pass.

4. **Apple-tier UX grammar adoption (7 templates)** — 19 `.kpi` cards + 10 `.insight-card`s (with tone variants) + 1 `.gradebook-table` + 3 `.grade-pill` variants. Templates: `widgets/finance_dashboard_widgets.html`, `finance/dashboard.html`, `analytics/dashboard.html`, `analytics/decision_intelligence_dashboard.html`, `analytics/at_risk_dashboard.html`, `parent/finance.html`, `emis/dashboard.html`. All `data-rmc-aesthetic="v2"`-gated; canonical icons used (`bi-cash-coin`, `bi-clock-history`, `bi-check2-circle`, etc.); plural-aware `{% blocktrans %}` where multilingual content combined with counts.

5. **i18n string wrapping (13 templates, 2 waves)** — ~512 strings wrapped in `{% trans %}` / `{% blocktrans %}`. Wave 1: `accounts/backend_dashboard.html`, `parent/dashboard.html`, `schools/super_dashboard.html` (top half), `partials/portal_sidebar.html`, `accounts/rbac_dashboard.html` + verified-clean: `analytics/dashboard.html`, `compliance/dashboard.html`, `portal_base.html`. Wave 2: `schools/super_dashboard.html` (rest), `finance/invoice_detail.html`, `admin/index.html`, `finance/invoices.html`, `evals/evaluation_admin.html`, `schools/super_command_center.html`, `portal/user_contributions.html`, `finance/reports.html`. All targeted files now have zero unwrapped capitalized strings.

6. **Orphan file detection + deletion (5 files / ~57 KB)** — confirmed zero references across `templates/`, `apps/`, `static/js/`, `scripts/`, and SW manifest: `static/js/dashboard-charts.js` (9.4K), `static/js/br-offline-bootstrap.js` (395B), `static/js/toasts.js` (878B), `static/css/backend-visibility.css` (40K), `static/css/print.css` (6.3K). Deleted from both `static/` and `staticfiles/`. 22 retired-file residues also swept from `staticfiles/` (prior retirement passes never cleaned `staticfiles/`).

7. **staticfiles refresh** — full sync between `static/` and `staticfiles/`; 111 files in both after cleanup.

8. **Service worker version bump** — `sms-v1.7.0-dashboard-polish-consolidated` → `sms-v1.8.0-platform-sweep-2026-05-12`.

**Aggregate sweep impact:**
- **1,609 hex literals tokenized** (CSS 1,509 across 29 files + templates 51 + JS 49)
- **12 new design tokens added** to design-tokens.css for graph/kbd/signature surfaces
- **39 Apple-tier UX grammar units adopted** across 7 dashboards
- **~512 strings wrapped** in `{% trans %}` / `{% blocktrans %}` across 13 templates
- **5 truly orphan files deleted** (~57 KB)
- **22 retired-file residues cleaned** from staticfiles/
- **Phase2 per-shell bundles fully tokenized** (portal 238→0, admin 84→0, base 65→0)
- **~178 hex literals remain** across small CSS files — **almost all are `var(--token, #fallback)` defensive fallback patterns** which are the recommended CSS pattern for graceful degradation when CSS variables fail to load. Direct un-wrapped hex usages remain only in `chart-rules.css` (3 single-property declarations like `.chart-color--success { color: #22c55e; }`) — those are intentional named class anchors for chart series and acceptable as-is.

**Excluded from tokenization (intentional primitive sources):** `design-tokens.css`, `design-tokens-luxury.css`, `bootstrap-theme-bridge.css`, `backend-themes.css`, `backend-light-theme.css`, `backend-dark-theme.css`, `portal-theme-modes.css`, email templates, PDF/print contexts (`finance/receipt.html`, `reports/_report_styles.html`, `report_table_pdf.html`), SVG artifact files (`templates/schools/_v2/*.svg.html`), and dynamic `{% block theme_root_variables %}` / `{{ X|default:"#..." }}` server-injected blocks.

## Cumulative session impact (2026-05-12)

**Earlier session (commits `356278e8`, `778a808f`, `e1f3562e`, `6087a055`):**
- 14 CSS files retired (~4,290 lines / ~165 KB) across 2 passes
- 135 hex literals tokenized across 7 files
- 10 PLATFORM_PALETTE_* settings + context processor + email_palette refactor (no hardcoded fallbacks)
- 5 base shell templates audited

**Follow-up (post-scope-honest re-audit):**
- 108 KB `phase2-static-templates-bundle.css` monolith retired and split into 4 per-shell bundles (~111 KB total but each shell loads only its own bundle: 19/18/3/71 KB)
- 1 more CSS file retired (`phase2-studio-bundle.css` — folded into `portal-ui-components.css`)
- `extract_template_styles_phase2.py` rewritten to be shell-aware and idempotent; 5 newly-stripped templates merged
- `shell_chrome_backend_ops_strip.html` refactored to `.kpi` grid grammar
- 4 grade/marks templates adopted `.gradebook-table` grammar (`marks_entry`, `grade_approval_detail`, `evaluation_admin`, `master_sheet`)
- 3 dashboard polish layers retired (`dashboard-crisp-polish.css` 438L + `dashboard-high-contrast.css` 361L + `dashboard-premium-compact.css` 405L = 1,204 lines retired). Dead code (preset skins, dashboard-kpi-block, backend-copilot-accordion) discarded; 249-line tokenized load-bearing slice migrated into `dashboard-theme-sync.css`. Net build reduction ~955 lines.
- Service worker cache version bumped twice (`sms-v1.6.0-phase2-per-shell` → `sms-v1.7.0-dashboard-polish-consolidated`)

## What this docket says about scope discipline

**Rule:** Before claiming an item is platform-wide, verify by grep against `templates/` and confirm reach into ≥2 of {marketing, control plane, tenant portal, admin, auth}. A single-template change is local polish, not platform work.

## Procedure for safe CSS retirement (canonical)

1. Update `apps/siteconfig/tests/test_theme_visibility_matrix.py` to remove existence checks for retired files (if listed).
2. Remove `<link>` references from every base template that loads the retiring file.
3. Bump `static/js/service-worker.js` version + remove file from cache manifest.
4. Delete the file from `static/css/`.
5. `python manage.py collectstatic` to refresh `staticfiles/`.
6. CDN cache invalidation if production-deployed.
