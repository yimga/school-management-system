# Tenant surface exception — agent handoff (Good → Best → Exception)

**SOT claim:** `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 batch **1728** (NOT DONE until waves complete)  
**Depends on:** batches **1726** (role-home E2E 5/5), **1727** (preview→live homes), **1720** (E2E harness) — all DONE  
**Visual SOT (operator):** `docs/generated/preview_app_shell_admin_v1_200x.html` (`/admin/` 200x — filter rail, changelist density, luxury chrome)  
**Phase crosswalk:** `docs/phase_checklists/phase_08_dashboards_role_homes.md`, `phase_03_navigation_command_archetypes.md`

---

## Mission

Cycle 8 proved **five role-home entry points** (Good). Batch 1727 elevated **home layouts** toward preview-live (Best). This program takes **every tenant menu + submenu destination** to **Exception**: same craft as operator `/admin/` — balanced folds, bento intelligence, filter rails on task pages, copilot/tools on all shells, zero dead nav, phased Playwright proof over **200** tenant sweep routes.

**Non-negotiables**

- Semantic tokens only (`static/css/design-tokens.css`, `.rmc-*`). No forked hex in templates.
- **4 viewport folds max** on task surfaces; `data-rmc-scroll-policy="paginate"` on tables/wizards; section anchor nav when 2+ folds.
- Copilot rail + operator tools tray on **every** tenant authenticated page (not only homes).
- Sidebar taxonomy: **ops sections before config** (`portal_sidebar_items.py` `PORTAL_CONFIG_SECTIONS`).
- Every wave: named verifier green + record in `RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md` — no narrative-only completion.
- Do **not** create parallel strategy docs; extend this file + SOT §11.4 batch 1728 only.

---

## Tier model (what “done” means)

| Tier | Meaning | Status |
|------|---------|--------|
| **Good** | Five role homes: login, MFA, HTTP 200, chrome assertions, reveal armed | **DONE** — `ROLE_HOME_VISUAL_SWEEP_E2E_PASS` |
| **Best** | Preview-live bento on homes; admin cockpit/setup zones; section nav | **PARTIAL** — batch 1727 on homes; inner pages uneven |
| **Exception** | All sidebar destinations + high-traffic inner pages match `/admin/` density; 200-route sweep phased green | **NOT DONE** — this handoff |

---

## Honest coverage today

Source: `docs/generated/portal_tenant_sweep_routes.json` (200 routes, `demo-school`).

| Status | Count | Meaning |
|--------|------:|---------|
| **proven** | 5 | Cycle 8 Playwright role-home only |
| **partial** | 72 | Same route family as a home (e.g. `/authentication/backend/*`) — not individually swept |
| **queued** | 123 | Studio, deep backend, other families — exception wave |

Interactive matrix (filterable): open **`docs/generated/preview_tenant_surface_coverage_matrix.html`** in a browser.

### Five proven P0 paths

1. `/portal/parent/`
2. `/portal/teacher/`
3. `/portal/student-portal/grades/`
4. `/authentication/backend/`
5. `/authentication/backend/performance/`

---

## Browser previews (open locally)

Start at the hub, then drill into role mockups and coverage.

| File | Purpose |
|------|---------|
| `docs/generated/preview_tenant_elevation_hub.html` | Hub — tiers, waves, links |
| `docs/generated/preview_tenant_elevation_exception_targets.html` | Tabbed **exception targets** (Parent / Teacher / Student / Admin) — admin-inspired bento, filter rails, sidebar |
| `docs/generated/preview_tenant_surface_coverage_matrix.html` | 200 routes × proven/partial/queued |
| `docs/generated/preview_app_shell_admin_v1_200x.html` | **Inspiration:** operator `/admin/` |
| `docs/generated/preview_app_shell_tenant_portal_v3_100x.html` | Current tenant 100x baseline |

Windows: open via `file:///` or drag into Chrome/Edge from repo `docs/generated/`.

---

## Implementation waves (execute in order)

### Wave A — Menu & nav integrity

**Goal:** Every sidebar and submenu link resolves; ops/config order correct; no dead hrefs on tenant chrome.

| Task | Where |
|------|--------|
| Audit `build_portal_sidebar_items` vs live `reverse()` | `apps/siteconfig/portal_sidebar_items.py` |
| Baseline floor for degraded nav | `build_portal_sidebar_baseline` in same file |
| Primary nav inline (header) | `templates/partials/tenant_primary_nav.html`, `portal_chrome.py` |
| Taxonomy reference | `docs/architecture/sidebar_navigation_taxonomy.md` |

**Gates**

```bash
python scripts/scan_operator_shell_dead_hrefs.py --strict   # 0
python scripts/verify_interaction_integrity_completion.py    # INTERACTION_INTEGRITY_PASS
```

**Deliverable:** JSON or verifier listing every sidebar `url_name` → resolved path per role (Parent, Teacher, Student, Admin). Fix broken or duplicate items.

---

### Wave B — Inner-page bento (admin changelist pattern)

**Goal:** High-traffic **task** pages (not discovery feeds) use filter rail + dense table + sticky primary action — port grammar from `/admin/` 200x preview.

**P0 inner pages (implement first)**

| Role | Path family | Pattern |
|------|-------------|---------|
| Teacher | `evals:teacher_marks_list`, attendance, timetable | Filter rail + paginated `.rmc-data-table` |
| Parent | finance, results, calendar | Bento summary + paginated history |
| Student | grades detail, workflow | Card density + section nav |
| Admin | `accounts:backend_student_list`, RBAC, `finance:dashboard` | Changelist + bulk actions strip |

**Templates / static (likely touch)**

- `templates/accounts/backend_dashboard.html` (reference implementation)
- `templates/parent/*`, `templates/teacher/*`, `templates/student/*`
- `static/css/rmc-data-table*.css`, admin changelist parity CSS if exists
- Reuse: `components/pagination.html`, `.rmc-section-nav`, `.rmc-admin-bento-*`

**Gates**

```bash
python scripts/verify_page_fold_standards.py
python scripts/audit_luxury_ui_surface.py
python scripts/scan_undefined_css_classes.py --compare   # 0
```

---

### Wave C — Chrome parity on all destinations

**Goal:** Copilot rail + tools tray + tenant header 100x on **every** swept route, not only homes.

| Surface | Contract |
|---------|----------|
| Tools tray | `#page-data-rmc-tenant-tools`, `.rmc-operator-tools__edge-tab`, tray open assertion |
| Copilot | `[data-rmc-copilot-rail]`, expand contract |
| Header | `[data-rmc-tenant-header-100x="1"]`, `[data-rmc-tenant-primary-nav-inline="1"]` |
| Preview live | `[data-rmc-preview-live-*="1"]` per role where applicable |

**Gates**

```bash
python scripts/verify_tenant_copilot_expand_contract.py
python scripts/verify_operator_tools_tray.py
python scripts/verify_preview_shell_100x_tenant_parity.py
```

---

### Wave D — Playwright depth (phased)

**Goal:** Extend proof beyond 5 homes.

**Phase D1 — P0 menus (~20 routes/role)**

Extend `scripts/run_role_home_visual_sweep.mjs` (or sibling) with a `ROLE_SWEEP_P0_MENUS=1` mode:

- One URL per **top-level sidebar section** + first child link per role
- Same harness as Cycle 8: `tests/e2e/helpers/tenant-login.js`, subdomain host map, TOTP seed

**Phase D2 — Full abrupt-end**

```bash
npm run sweep:abrupt-end:routes    # refresh docs/generated/portal_tenant_sweep_routes.json
npm run sweep:abrupt-end             # tenant tier; Django up + host map
```

**E2E env (local Windows — use gate snapshot, do not full migrate)**

```bash
export RMC_E2E_GATE_SNAPSHOT=.django_test_dbs/default.sqlite3
export DB_FILE=db_playwright_role_home_cycle8.sqlite3
export RMC_E2E_KEEP_DB=1
export VISUAL_QA_PORT=8020
export ROLE_SWEEP_TENANT_ONLY=1
export DJANGO_SQLITE_TIMEOUT=90
npm run sweep:role-home:e2e
```

**CI canonical:** `.github/workflows/role-home-visual-sweep-e2e.yml`

**Gates**

- `var/role-home-visual-sweep.json` — `failed: 0` for expanded surface set
- Console: `ROLE_HOME_VISUAL_SWEEP_E2E_PASS`
- `python scripts/verify_role_home_visual_sweep_harness.py`

---

## Menu inventory (must eventually balance)

From `apps/siteconfig/portal_sidebar_items.py` + `_BASELINE_BY_ROLE` / `_BASELINE_ADMIN`:

### Parent

- Home: Family Home  
- My Workflow  
- Children & Learning, Performance Tracking  
- Finance, Calendar  
- Portal Tools: Community, Video, Documents  

### Teacher

- Workspace: My Classes, Workflow, Gradebook, Attendance, Timetable  
- Learning Management, Human Resources, Settings  

### Student

- Home (grades), Workflow  
- Assignments / portal features per flags  

### Admin / staff

- Admin Panel: Command Center, Setup wizards  
- People & Access: Students, RBAC  
- Financial Management  
- Configuration: School config, Feature control, Site settings, Region, Django admin link  
- Analytics & Reports (when entitled)  

**Rule:** Each **bold section** needs at least one exception-grade page (Wave B), not only the landing URL.

---

## Key code map

| Area | Path |
|------|------|
| Sidebar builder | `apps/siteconfig/portal_sidebar_items.py` |
| Portal chrome | `apps/siteconfig/portal_chrome.py` |
| Tenant shell | `templates/portal_base.html` |
| Admin backend | `apps/accounts/views.py` → `backend_dashboard` |
| Role-home sweep | `scripts/run_role_home_visual_sweep.mjs`, `scripts/run_role_home_e2e.mjs` |
| Sweep route ledger | `docs/generated/portal_tenant_sweep_routes.json` |
| Demo seed | `apps/schools/demo_user_seeding.py`, `ensure_developer_sandbox_tenant` |
| E2E login | `tests/e2e/helpers/tenant-login.js` |

---

## Agent copy-paste prompt (start here)

```
You own SOT §11.4 batch 1728 — Tenant surface exception (Good → Exception).

READ FIRST (in order):
1. docs/phase_checklists/TENANT_SURFACE_EXCEPTION_HANDOFF.md
2. docs/generated/preview_tenant_elevation_hub.html (browser)
3. docs/generated/preview_tenant_elevation_exception_targets.html (browser)
4. docs/generated/preview_app_shell_admin_v1_200x.html (visual SOT for /admin/)
5. apps/siteconfig/portal_sidebar_items.py

CLAIM ONE WAVE ONLY: A (menu integrity) | B (inner bento) | C (chrome parity) | D (Playwright).

RULES:
- Smallest diff; match existing .rmc-* patterns.
- No new parallel plan markdown.
- End wave with named verifier green; update SOT §11.4 batch 1728 status + RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md.
- Tenant scope only (demo-school); operator /admin/ is inspiration not migration target.

CURRENT WAVE: <A|B|C|D1|D2>
```

---

## Definition of done (batch 1728)

| Wave | Repo-scope (today) | Closes 1728 → DONE |
|------|-------------------|---------------------|
| **A** Menu integrity | **DONE** — `TENANT_SIDEBAR_BASELINE_INTEGRITY_PASS`, dead hrefs 0 | Yes |
| **B** Inner bento | **DONE** — filter rail on gradebook; finance/results already paginated | Yes (P0 pages) |
| **C** Chrome parity | **DONE** — copilot/tools/preview-to-live verifiers green | Yes |
| **D1** P0 Playwright | **Harness DONE** — CI job `role-home-p0-menus` (22 surfaces); token `TENANT_MENU_P0_SWEEP_E2E_PASS` | **After first green CI run** (or local `var/tenant-menu-p0-sweep.json` failed=0) |
| **D2** 200-route abrupt-end | **NOT DONE** — deferred to **batch 1729** (phased by route family) | No — separate batch |

**1728 → DONE** when D1 CI is green (or operator commits `var/tenant-menu-p0-sweep.json` with `failed: 0`, `p0Menus: true`, `passed: 22`). **D2 is explicitly out of 1728 scope** — do not block 1728 on 200/200.

**1729 (next)** — Wave D2 only: `npm run sweep:abrupt-end:routes` + phased tenant abrupt-end; update `preview_tenant_surface_coverage_matrix.html` statuses.

---

## Out of scope (do not expand)

- Marketing `runmycampus.com` surfaces (separate CI job `role-home-marketing`)  
- Control plane `/super/` (use manager previews)  
- Postgres RLS production deploy  
- Rewriting Unfold `/admin/` — **adopt patterns**, do not fork operator admin  
- New strategy roadmaps or duplicate §11.4 batches

---

## Already shipped (do not redo)

| Item | Proof |
|------|--------|
| Role-home 5/5 E2E | `ROLE_HOME_VISUAL_SWEEP_E2E_PASS`, batch 1726 cycle 8 |
| `settings.manage` for `demo.admin` | `demo_user_seeding.py`, TOTP in `run_role_home_e2e.mjs` |
| E2E gate snapshot | `RMC_E2E_GATE_SNAPSHOT`, `DJANGO_SQLITE_TIMEOUT` in harness |
| Preview-live homes | batch 1727, `TENANT_PREVIEW_TO_LIVE_PASS` |
| Tools tray + admin bento on backend | batches 1724–1725 |

---

## Suggested PR sequence

1. **PR1 — Wave A:** Nav integrity + dead href fixes  
2. **PR2 — Wave B (teacher + parent):** Gradebook + finance inner pages  
3. **PR3 — Wave B (admin lists):** Student list / RBAC changelist parity  
4. **PR4 — Wave C:** Chrome gaps on non-home templates  
5. **PR5 — Wave D1:** Extended Playwright P0 menu sweep  
6. **PR6 — Wave D2:** Abrupt-end tranches (by route family from matrix)

---

*Handoff authored 2026-06-24 after Cycle 8 close. Previews live under `docs/generated/preview_tenant_elevation_*`.*
