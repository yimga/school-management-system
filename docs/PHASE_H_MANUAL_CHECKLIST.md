# Phase H — Manual Checklist (Full Codebase and Live UX Verification)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11 Phase H. This doc is the **manual** pass checklist. Automated checks: `apps.accounts.tests.test_phase_h_ux_verification`, `scripts/phase_h_audit.py`, `scripts/run_phase_h_verification.sh`. See [PHASE_H_UX_VERIFICATION.md](PHASE_H_UX_VERIFICATION.md).

**Goal:** Before considering the plan complete, ensure the entire codebase and live experience are production-ready and **visibly correct after deployment**. No broken links, no erroring pages, responsive everywhere, everything in frame and well labeled.

---

## 1. How to use this checklist

- Run **after** automated Phase H tests and `phase_h_audit.py` (static + `--live`).
- **Automated URL check:** Run `python scripts/phase_h_url_check.py` (resolve); with server run `python scripts/phase_h_url_check.py --hit http://localhost:8000` to GET and report status.
- Perform on a **deployed** or **staging** environment so “visibly correct” can be verified.
- For each section, tick when done; note any failures and fix or log.
- **Execution log:** Record run metadata and results in [PHASE_H_EXECUTION_LOG.md](PHASE_H_EXECUTION_LOG.md) for audit trail.

---

## 2. Links, buttons, shortcuts

- [ ] **Control plane:** Every link in `partials/control_plane_sidebar.html` resolves and opens the correct page (no 404/500).
- [ ] **Control plane:** Navbar links (Configuration Engine, Profile, Preferences, Logout) work.
- [ ] **Control plane:** Ctrl+K (search) opens and shows intents; shortcuts help (?) works.
- [ ] **Tenant backend:** Sidebar and top nav links resolve (Dashboard, People, Finance, Site config, etc.).
- [ ] **Tenant portal:** Role-specific nav (parent, teacher, student, etc.) — all links work.
- [ ] **Marketing:** Header/footer and in-page links (Product, Pricing, Book demo, Login, etc.) work.
- [ ] **Studio OS:** All rail entries (Experience, Automation, Output, Launch, Control) open correct embed or page.
- [ ] **Auth:** Login, logout, signup, password reset, find school — no broken links.

---

## 3. Pages and dashboards (no 404/500)

- [ ] **Control plane:** `/super/`, `/super/dashboard/`, Studio OS entry, marketplace, billing, registries, runtime inspector, workflow packs, etc. — all return 200 and render.
- [ ] **Tenant backend:** Backend dashboard, people (students, guardians, teachers), siteconfig (theme, blueprints, workflow hub, sync center), accounts (workflow center, migration), finance, marketplace tenant, API Center — all return 200 and render.
- [ ] **Tenant portal:** Parent dashboard, teacher dashboard, finance, analytics, document library, signature requests, requests — all return 200 and render.
- [ ] **Marketing:** `/`, `/product/`, `/pricing/`, `/book-demo/`, `/products/*`, topic pages — all return 200 and render.
- [ ] **Error pages:** 403, 404, 500 (control plane and tenant) render with correct shell and messaging (no raw stack trace).

---

## 4. UI/UX — responsive and high-end

- [ ] **§8.0.6:** Every page is **fluid** (no fixed-width page wrapper causing horizontal scroll on mobile).
- [ ] **§8.0.6:** Layout uses Flexbox or Grid; typography uses `clamp()` or media queries; no fixed pixel width/height for layout.
- [ ] **Mobile:** Test key pages on a narrow viewport (e.g. 375px): no horizontal scroll; sidebar collapses to drawer or top nav where applicable.
- [ ] **Tablet/desktop:** Key pages at 768px and 1280px — layout and readability correct.
- [ ] **Design system:** Same tokens and visual language on control plane and tenant; no “white on one page, dark on another” inconsistency in the same surface.

---

## 5. Framing and structure

- [ ] All pages are **in frame** (nothing spewing outside viewport or overflowing).
- [ ] Main content has a clear landmark (e.g. `main` or `#cp-main-content` / `#main-content`).
- [ ] Skip link (“Skip to main content”) present and works on control plane, tenant, and marketing where required.
- [ ] Page titles and headings are present and meaningful (no blank or generic “Page” titles in primary flows).

---

## 6. After deployment

- [ ] **Deploy** to staging/production and verify **changes are visibly seen** (e.g. new product page, responsive behavior, tokens).
- [ ] **Cache:** Hard refresh or incognito so updated CSS/JS are loaded; confirm no stale shell or broken assets.
- [ ] **Manager URL:** If applicable, confirm control plane and Studio OS are reachable at the documented manager URL (e.g. manage.runmycampus.com). See [CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md](CHANGES_NOT_VISIBLE_AFTER_DEPLOY.md).

---

## 7. Full test suite

- [ ] Run full test suite: `python manage.py test` (or project-specific command); fix any regressions.
- [ ] Run Phase H automated: `python manage.py test apps.accounts.tests.test_phase_h_ux_verification`; `python scripts/phase_h_audit.py` and `python scripts/phase_h_audit.py --live`.
- [ ] Optional: run E2E or smoke if available; document result.

---

## 8. Sign-off

- [ ] All sections above completed; any failures documented and either fixed or logged as known issues with owner.
- [ ] Phase H completion gate in RUNMYCAMPUS §11 satisfied: no broken links/shortcuts; no erroring pages; consistent high-end UI/UX; correct framing; proper seeding and integration; successful deploy with no critical issues.

**Date completed:** _______________  
**Completed by:** _______________

---

*Source: RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11 Phase H; PATH_TO_100_PERCENT_EXECUTION_PLAN.md.*
