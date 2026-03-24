# Site Settings Redesign Plan

**Goal**: Redesign the Site Settings page so it can fit as many settings as possible and remain easy to use, with focus on the area where the different site-setting links (tabs) are shown.

---

## 1. What the current screen shows

From the current Site Settings page:

- **Breadcrumb**: "Configuration Control Center > Site Settings**s**" — there is a small typo (double "s").
- **Settings navigation**: A long **horizontal row of tab links**. Included are:
  - Company Details, Login/Header & Layout, Theme & Experience, Portal & content, Footer Content, Feature Toggles, Backend Orchestration & Limits, Notifications & Analytics, Compliance & Payroll
  - Then **seven** Finance Automation tabs in a row: Fee Invoice Generation, Fee Plan Copying, Payment Reminders, Invoice Status Updates, Receipt Verification, Bank Deposit Verification, Payment Instructions (and in code there are more: Real-world scenarios, Analytics Defaults, Metadata).
- **Problems**:
  - The row is **crowded** and will get worse as more modules (evals, reports, payroll, etc.) add settings.
  - **No grouping**: Finance Automation is flattened into many equal-weight tabs.
  - **Horizontal layout doesn’t scale**: New categories mean more tabs, wrapping or overflow.
  - **Content area**: Some settings appear as **raw JSON** in large text areas, which is hard for non-technical admins and error-prone.
- **Already good**: Sticky save bar, Back button, theme toggles styling.

So the main focus is: **redesign the “different site setting links” area** so it scales and stays easy to use.

---

## 2. Redesign direction: navigation that scales

### 2.1 Option A – Vertical sidebar (recommended for “fit as many as possible”)

Replace the single horizontal tab row with a **left sidebar** used only on the Site Settings change form:

- **Left sidebar** (fixed or collapsible on small screens):
  - **Groups** (e.g. General, Branding & theme, Portal & content, Backend & limits, **Finance automation**, Analytics & deadlines, Metadata).
  - Under **Finance automation**: sub-items (Fee invoice generation, Fee plan copying, Payment reminders, Invoice status, Receipt verification, Bank verification, Payment instructions, Real-world scenarios).
  - Under **General** (or similar): At a glance, Company details, Login/header, Theme & experience, Footer.
  - Other groups can also have sub-items as the number of settings grows (e.g. Evals, Reports, Payroll, Compliance).
- **Main area**: Only the **selected section’s** fields are shown (one “panel” at a time).
- **Benefits**: Unlimited sections and groups; same pattern as many “Settings” UIs; easy to add Evals, Reports, etc. under their own groups later.

**Implementation outline**:

- Use a **custom change_form template** for `SiteSettings` that does **not** render Unfold’s default `tab_list` for this page.
- In the template (or a fragment):
  - Output a **sidebar** of groups and links; each link sets which “section” is active (e.g. via `#section-slug` or a hidden input + JS).
  - Output **one panel per fieldset** (or per logical group), and show only the panel for the active section (e.g. with `data-section="..."` and JS or Alpine).
- Form stays a single Django form; all fields remain in the DOM; only visibility is toggled so save still submits everything. Optional: persist last-visited section in `sessionStorage`.

### 2.2 Option B – Fewer top-level tabs + in-tab subsections (quicker win)

Keep Unfold’s tab bar but **reduce the number of tabs** by grouping:

- **One “Finance Automation” tab** instead of seven separate tabs.
- Inside that tab, use **in-tab structure**:
  - **Subsections** implemented as:
    - Collapsible blocks (Django fieldset `classes: ("collapse",)`), each with a clear heading (e.g. “Fee invoice generation”, “Payment reminders”), or
    - Visible subheadings + one big fieldset that contains all finance automation fields ordered by subsection.
- **Other groupings** (optional): e.g. “Portal & content” and “Footer” could stay as now or be merged into “General” with subsections.

**Implementation outline**:

- In `SiteSettingsAdmin.fieldsets`, **merge** all “Finance Automation - …” fieldsets into **one** fieldset named **“Finance Automation”**.
- Put all those fields in one tuple, ordered by subsection; add a **readonly “description”** or custom **readonly block** before each logical subsection that renders a subheading (e.g. “Fee invoice generation”, “Payment reminders”, …). That way you keep one tab but with clear in-tab structure.
- Result: fewer tabs in the horizontal row, so the “different site setting links” area is less crowded and easier to scan. You can later add more subsections (Evals, Reports) inside the same or new tabs without adding many more top-level tabs.

### 2.3 Hybrid (recommended path)

- **Phase 1 (short term)**: Implement **Option B** — one “Finance Automation” tab with in-tab subsections (and fix breadcrumb typo). Quick, no new templates, fewer tabs.
- **Phase 2 (medium term)**: Implement **Option A** for Site Settings only — custom change_form with **vertical sidebar** and groups, so the “different site setting links” become a scalable sidebar. Migrate existing tabs/groups into sidebar sections and sub-items; add Evals, Reports, Compliance, etc. under their own groups as needed.

---

## 3. Other improvements to include in the plan

| Area | Current | Improvement |
|------|--------|-------------|
| **Breadcrumb** | “Site Settingss” | Fix typo to “Site Settings” (wherever the breadcrumb is set). |
| **Raw JSON** | Some settings (e.g. portal config, backend flags) shown as big JSON text areas | Where possible, replace with **structured form widgets** (e.g. key/value pairs, checkboxes, multi-select) and keep JSON only for “Advanced” or export. |
| **Sticky save** | Already present | Keep; consider “Unsaved changes” indicator when form is dirty. |
| **Mobile** | Horizontal tabs wrap or overflow | With Option A, sidebar becomes a drawer or dropdown on small screens. With Option B, fewer tabs help. |
| **Discoverability** | Many tabs look the same | With sidebar: use icons + short labels per group; optional “Recently edited” or “Most used” section at top. |
| **New modules** | Adding Evals/Reports/Payroll settings would add more tabs | With Option A, add “Evals & grading”, “Reports & report cards”, “Payroll” as new sidebar groups with sub-items, so the “different site setting links” area stays one sidebar, not an ever-longer tab bar. |

---

## 4. Where to fix the breadcrumb typo

- Search for “Site Settingss” or “Site settingss” in templates and admin (e.g. `breadcrumbs` or title for Site Settings).
- Likely in: `config/admin.py` (admin site title/breadcrumb), or a template that builds breadcrumbs for `siteconfig.sitesettings` change form.

---

## 5. Summary

- **Focus**: Redesign the **site setting links** area so it can fit many more settings and stay easy to use.
- **Observation**: The current horizontal tab row is already crowded and will not scale as more modules add settings.
- **Proposal**:
  - **Short term**: Reduce tabs by grouping (e.g. one “Finance Automation” tab with in-tab subsections) and fix “Settingss” → “Site Settings”.
  - **Medium term**: Move to a **vertical sidebar** for Site Settings only, with groups and sub-items (e.g. Finance automation with 7+ sub-items), so all current and future setting categories live in one scalable navigation.
- **Extra**: Replace raw JSON with form widgets where possible; keep sticky save; improve mobile and discoverability as above.

This plan can be used as the “Site Settings” part of the broader improvement plan (evals, reports, guardrails, etc.) so that when we touch Site Settings, we do it in a structured, scalable way.
