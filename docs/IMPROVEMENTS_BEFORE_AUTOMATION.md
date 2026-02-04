# Improvements Before Phase 3 (Automation)

**Purpose:** Quick wins and Phase 1.3 polish so the codebase and UX are in good shape before starting the automation workflow (Phase 3).

---

## 1. Phase 1.3 – UX polish (recommended)

### 1.1 Unsaved changes indicator
- **Current:** Site Settings form already has dirty tracking and `beforeunload` (browser prompt on leave when dirty).
- **Improvement:** Show a visible **“Unsaved changes”** indicator (e.g. a small badge or text near the Save bar or in the header) when the form is dirty, and hide it after save. Improves clarity without changing behavior.
- **Effort:** Low (use existing `dirty` flag in JS; add a small DOM element and toggle its visibility).

### 1.2 Replace at least one raw JSON with a structured widget
- **Current:** `backend_feature_flags` is already partially structured in Site Settings (explicit checkboxes and multi-selects for entity console, import, API schema, roles, etc.) with a readonly summary. `portal_features` is still a raw JSON field in the main form (there is a separate Feature Control audit UI that edits it).
- **Improvement:** Either:
  - **Option A:** In Site Settings, add a structured widget for **portal_features** (e.g. checkboxes for known keys: syllabus, documents, forums, video, messaging) and sync to/from the JSON field, like `backend_feature_flags`. Keeps everything in one place.
  - **Option B:** Add a short help line under the `portal_features` field: “Or use **Feature Control** to toggle features with audit trail” with a link to the Feature Control page. No new widget, but better discoverability.
- **Effort:** Option A medium (form fields + clean/init); Option B low.

---

## 2. Phase 1.1 – Verify / close out

### 2.1 Breadcrumb
- **Current:** `SiteSettings` model has `verbose_name_plural = "Site Settings"` (no double “s”). If the admin UI still shows “Site Settingss” anywhere, it may be from Unfold’s tab label or another template.
- **Improvement:** Confirm in the browser that the Site Settings page shows “Site Settings” (not “Site Settingss”). If it still shows the typo, track down the source (e.g. Unfold’s change_form title or app list) and fix.
- **Effort:** Low (inspect + one string fix if needed).

### 2.2 Finance Automation as one section
- **Current:** With the vertical sidebar (Phase 1.2), “Finance Automation” is already a single sidebar section containing all finance automation fields. The old “merge into one tab” is effectively done.
- **Improvement:** None required; optionally add in-tab subheadings inside the Finance Automation section (e.g. readonly “Fee invoice generation”, “Payment reminders”) for scanability. Already partially done via fieldset description.
- **Effort:** Optional, low.

---

## 3. Small cleanup (optional)

- **Console logs:** Remove or guard `console.log('[Site Settings] ...')` in `change_form.html` so production doesn’t clutter the console.
- **MASTER_PLAN checklist:** Mark Phase 1.1 and 1.2 items as done where applicable so the doc reflects current state.
- **Docs:** Ensure `SITE_SETTINGS_UX_AND_THEME_FINDINGS.md` and this file are linked from `MASTER_PLAN.md` “Related docs” if useful.

---

## 4. Phase 2 – Confirm complete (before automation)

- **2.1 Reports – publish and approved grades:** Implemented (flags, publish guard, report context filter, publish page UX, audit).
- **2.2 Evals – single grading deadline:** Confirm whether a single canonical source (e.g. `SubjectAssignment.grading_deadline_at` or one evals deadline model) is used everywhere; remove or redirect old `GradingDeadline` references. If not yet done, do this before or early in Phase 3 so automation can rely on one source.
- **2.3 Publish audit:** Implemented.

---

## 5. Suggested order before Phase 3

| Priority | Item | Effort | Notes |
|----------|------|--------|------|
| 1 | Unsaved changes indicator (1.1) | Low | High clarity gain |
| 2 | Breadcrumb check/fix (2.1) | Low | Quick close-out |
| 3 | Portal features: Option B help link (1.2) or Option A structured widget | Low / Medium | Option B is enough for “one improvement” |
| 4 | Phase 2.2: Single grading deadline source | Medium | Needed for automation consistency |
| 5 | Console.log cleanup + MASTER_PLAN checkboxes | Low | Housekeeping |

After these, proceed with **Phase 3 (Automation):** ExecutionLog for all automations, config in Site Settings, approval queue where configured, redundancy removal.

---

## 6. Applied (pre-automation pass)

- **Unsaved changes indicator:** Added in Site Settings change form: `#site-settings-unsaved-indicator` (hidden by default); JS shows it when form is dirty and hides on submit. Uses existing dirty tracking and beforeunload.
- **Feature Control help:** In Feature Toggles (Modules): new readonly field `portal_features_help` with link to Feature Control; fieldset description explains portal_features JSON and Feature Control. Excluded from form submission in `get_form`.
- **Console.log:** Removed or simplified Site Settings change form console.log calls (back button retries no longer log).
- **MASTER_PLAN:** Phase 1.1 (breadcrumb, Finance merge, Verify) and 1.3 (sticky save + unsaved indicator, portal_features/Feature Control link) marked done.
- **Breadcrumb:** Model already has `verbose_name_plural = "Site Settings"`; no typo found in code. Left as-is.
