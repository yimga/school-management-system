# /admin Dashboard and Sidebar — Master Plan (Updated)

This document is the single source for fixing and upgrading the `/admin` experience. It incorporates: (1) your requirements (dual-sidebar, zero-cost MFA for every user with encouragement, UNFOLD-style navigation, command-center dashboard, redundancy removal), (2) existing issues from the codebase audit, and (3) gaps and improvements noted during the update.

**Guiding principles:** Make /admin the "engine" of the platform; reduce redundancy at all costs; MFA for every user account with clear encouragement to set it up.

---

## 1. Current Architecture (Summary)

### 1.1 Entry points

| URL | Purpose | Access |
|-----|---------|--------|
| `/admin/` | Configuration Engine — custom index + Django admin CRUD | Superuser only |
| `/admin/dashboard/` | Observability dashboard | Staff |
| `/authentication/backend/` | Backend Console — operations, workflows | Staff |

### 1.2 Sidebar today

- **Templates:** `admin/base.html` → `admin/nav_sidebar.html` → `admin/sidebar_inner.html` → `admin/app_list.html`.
- **Data:** `config.admin.GileadAdminSite.get_app_list()` with custom sections (people, academic, financial, operations, system). Quick access (Dashboard, Site settings, Backend Console) is hardcoded in `app_list.html`.
- **Unfold:** `UNFOLD["SIDEBAR"]` has `show_search=True`, `show_all_applications=True`, `navigation=[]` (empty). So the sidebar is fully custom; Unfold’s built-in navigation is unused.

### 1.3 MFA today

- **Stack:** `django_otp`, `django_otp.plugins.otp_totp`, `RequireMFAMiddleware`, `OTPMiddleware`.
- **Logic:** `SiteSettings.require_mfa_roles` (JSON list). When a user’s role is in that list, middleware redirects to MFA setup if they have no TOTP device. Bypass paths include `/admin/login`, `/admin/logout`; `/admin/` itself is **not** bypassed, so role-required users are redirected from admin to MFA setup.
- **Gap:** MFA is **role-based** only. There is no “require MFA for all staff” or “encourage MFA for everyone.” No persistent “Set up MFA” prompt in admin for users who don’t have it.

### 1.4 Configuration Control Center / Site Settings

- **Model:** Single-object `SiteSettings` (get_solo()). No changelist of multiple “settings”; it’s a single change form.
- **Secondary nav:** `admin/siteconfig/sitesettings/settings_sidebar.html` already provides a **secondary sidebar** on the Site Settings form (search + grouped sections with anchors). There is no separate “Config center” changelist with `?group=general|grading|mfa`; the form is one page with in-page sections.
- **Gap:** No dedicated “Security & MFA” tab in the UI with an MFA compliance widget (e.g. “MFA enabled: X%”) and no explicit “Security & MFA” section in the settings sidebar that links to MFA enforcement and status.

---

## 2. Requirements (From Your Spec) — In Scope

- **Global navigation:** Group all modules into 4–5 collapsible domains (e.g. Operational Core, Academic Processing, Financial Engine, System & Infrastructure). Use a single, consistent structure (Unfold-style or current get_app_list, but not both duplicated).
- **Dual-sidebar:** Primary = module navigation (left). Secondary = when in Configuration Control Center / Site Settings: contextual nav (General, Grading, Finance, Security & MFA) with optional MFA health widget.
- **Zero-cost MFA (TOTP):** Keep current stack. **Every user account** should have MFA; **encourage** setup for all (banner/prompt in admin and profile). Option to **require** MFA for all staff (not just by role).
- **Command-center dashboard:** KPI cards (MFA compliance %, Unpaid fees, Attendance, Active sessions, Pending approvals), Action Queue (pending items from apps.requests / approvals), System Health. No “Welcome, Admin” empty space.
- **CMD+K:** Global command palette for instant navigation (Unfold: `show_search` / `command_search`).
- **Sidebar:** Vertically scrollable, no layout gaps; thin, consistent scrollbar.
- **Professional polish:** Breadcrumbs always visible; bulk actions (select-all) on tables; empty states with “Create New”; dirty-state alert (“You have unsaved changes”) on config forms.
- **Redundancy:** Remove duplicate assets and duplicate branding; one source of truth for navigation and styles.

### 2.1 UNFOLD sidebar config (reference)

Your spec suggested a structure like this in `settings.py`. Use it as the target shape; adapt `link` to actual admin changelist URLs (e.g. `admin:people_student_changelist` — our model names may differ).

```python
UNFOLD["SIDEBAR"] = {
    "show_search": True,
    "show_all_applications": False,
    "navigation": [
        {"title": _("Operational Core"), "collapsible": True, "items": [
            {"title": _("Accounts"), "link": reverse_lazy("admin:accounts_user_changelist"), "icon": "manage_accounts"},
            {"title": _("People"), "link": reverse_lazy("admin:people_student_changelist"), "icon": "groups"},
            {"title": _("Academics"), "link": reverse_lazy("admin:academics_classroom_changelist"), "icon": "auto_stories"},
        ]},
        {"title": _("Academic Processing"), "collapsible": True, "items": [
            {"title": _("Evaluations"), "link": reverse_lazy("admin:evals_evaluation_changelist"), "icon": "grading"},
            {"title": _("Reports"), "link": reverse_lazy("admin:reports_reportcard_changelist"), "icon": "summarize"},
        ]},
        {"title": _("Financial Engine"), "collapsible": True, "items": [
            {"title": _("Finance"), "link": reverse_lazy("admin:finance_invoice_changelist"), "icon": "payments"},
            {"title": _("Payroll"), "link": reverse_lazy("admin:payroll_payslip_changelist"), "icon": "account_balance_wallet"},
        ]},
        {"title": _("System & Infrastructure"), "collapsible": True, "items": [
            {"title": _("Config center"), "link": reverse_lazy("admin:siteconfig_sitesettings_changelist"), "icon": "settings"},
            {"title": _("Compliance"), "link": reverse_lazy("admin:compliance_complianceauditlog_changelist"), "icon": "verified_user"},
            {"title": _("Automation"), "link": reverse_lazy("admin:automation_automationexecutionlog_changelist"), "icon": "robot"},
        ]},
    ],
}
```

If we keep a custom app list instead, the **same domain names and order** should be used so there is no duplication of structure.

### 2.2 Admin UX checklist (from your spec)

| Feature | Standard | Benefit |
|---------|----------|---------|
| Breadcrumbs | Always visible at top | Admin never gets lost in deep modules |
| Bulk actions | Select-all checkboxes on every table | Time-saver for people, finance, etc. |
| Empty states | “No X found” + “Create New” button | Directs user on what to do next |
| Dirty state alerts | “You have unsaved changes” popup | Prevents data loss in siteconfig |

---

## 3. Issues and Gaps (Consolidated)

### 3.1 Bugs / Quick fixes

| # | Issue | Where | Fix |
|---|--------|--------|-----|
| 1 | Duplicate `admin-dashboard.css` | `admin/base_site.html` | Remove second `<link>`. |
| 2 | EMIS not in admin | `emis/admin.py` uses default `admin.site` | Register with `config.admin_site`; add `emis` to `get_app_list` `app_order`. |
| 3 | Incomplete `app_order` | `config/admin.py` | Add `automation`, `requests`, `communication`, `emis` with section and order. |
| 4 | Simplebar dead attribute | `app_list.html`: `data-simplebar` | Remove or add Simplebar JS; document choice. Prefer native scroll to reduce dependency. |

### 3.2 MFA gaps

| # | Gap | Fix |
|---|-----|-----|
| 5 | MFA only role-based | Add `SiteSettings.require_mfa_all_staff` (bool). When True, middleware redirects **any** staff without TOTP to MFA setup (except bypass paths). Default False for backward compatibility. |
| 6 | No “encourage” for all users | Show a **dismissible** “Set up MFA for stronger security” banner (or link in user dropdown) in admin when `not user_has_device(user)`. Same on profile page (already has “Set up” link; ensure it’s prominent). Optionally show on first login. |
| 7 | No MFA compliance on dashboard | Add **MFA compliance %** to admin index: e.g. “Staff with MFA: X / Y (Z%)”. Add to KPI row. |
| 8 | No Security & MFA in Config center / Site Settings | In Site Settings secondary sidebar, add a **Security & MFA** group (or section) linking to in-page anchor for `require_mfa_roles` / `require_mfa_all_staff` and help text. Optionally add a small “MFA status” widget in that sidebar (e.g. “Compliance: Secure” when enforcement is on and count shown). |

### 3.3 Sidebar and navigation gaps

| # | Gap | Fix |
|---|-----|-----|
| 9 | UNFOLD `navigation` empty | **Option A:** Populate `UNFOLD["SIDEBAR"]["navigation"]` with collapsible groups (Operational Core, Academic Processing, Financial Engine, System & Infrastructure) and links to admin changelists; set `show_all_applications=False` and use one source. **Option B:** Keep current `get_app_list()` but ensure the template renders **collapsible** groups with the same domain names and that the sidebar is the only place that defines nav (no duplicate list elsewhere). Prefer one source to avoid redundancy. |
| 10 | No CMD+K command palette | Enable Unfold’s command search if available: `UNFOLD["SIDEBAR"]["command_search"] = True` (or equivalent). Ensure Ctrl+K focuses sidebar search or global command palette. |
| 11 | Vertical scroll / gaps | Ensure primary sidebar has `h-screen sticky top-0 overflow-y-auto` and thin scrollbar (existing `admin-sidebar-scroll.css`). Remove any `gap` or margin that creates a visual break between sidebar and content. |

### 3.4 Dashboard (index) gaps

| # | Gap | Fix |
|---|-----|-----|
| 12 | No MFA KPI | Add `mfa_enabled_count`, `mfa_staff_total`, `mfa_compliance_percent` to index context; add one KPI card “MFA Compliance” (e.g. “85%” with link to Site Settings or MFA setup). |
| 13 | No Action Queue / Pending approvals | Add “Pending approvals” (or “Action queue”) from `apps.requests` (e.g. `AccessRequest` pending count and top 5 items) to index context and a small widget on the dashboard. If observability or other “pending” sources exist, unify under one “To-Do” / “Action queue” list. |
| 14 | Unpaid fees / Collection ratio | Add KPI for total unpaid (or collection ratio) from finance if not already present; ensure it’s permission-aware. |
| 15 | DASHBOARD_CALLBACK | Unfold may support a dashboard callback to inject context; if so, use it for KPIs and action queue so the index stays the single “engine” view. Otherwise keep logic in `GileadAdminSite.index`. |

### 3.5 Configuration Control Center — Site Settings (secondary sidebar) gaps

| # | Gap | Fix |
|---|-----|-----|
| 16 | Security & MFA section | Add a “Security & MFA” group (or section) in `settings_nav_groups` (or equivalent) for Site Settings, with anchor to MFA-related fields. Ensure `require_mfa_roles` and (new) `require_mfa_all_staff` are in that section with clear help text. |
| 17 | MFA widget in sidebar | In `settings_sidebar.html` (or change_form), add a small “MFA status” block (e.g. “Compliance: Secure” when enforcement on; “X% staff with MFA”) at bottom of secondary sidebar, only when viewing Site Settings. |

### 3.6 Redundancy and polish

| # | Issue | Fix |
|---|--------|-----|
| 18 | Heavy header | Reduce redundancy: sidebar already has brand. Consider replacing large nav bridge + weather + site name with **one compact top bar**: “Admin | Backend” switcher + user tools. Make weather optional or collapsible. |
| 19 | Theme/tokens | Audit admin/sidebar CSS variables; define in one place (e.g. design-tokens or one admin-sidebar file); remove duplicate or unused stylesheet links. |
| 20 | Breadcrumbs | Ensure breadcrumbs are always visible at top of content (Unfold or custom). |
| 21 | Dirty state | On Site Settings (and other critical forms), add “You have unsaved changes” on beforeunload or when navigating away with dirty form. |
| 22 | Empty states / Bulk actions | Audit key list views (people, finance, requests): ensure empty state copy + “Create New” and select-all where appropriate. |

### 3.7 Mobile and accessibility

| # | Issue | Fix |
|---|--------|-----|
| 23 | Mobile sidebar toggle | Ensure a visible “Menu” (hamburger) in the header on small viewports that opens the sidebar; clear close button and focus management. |
| 24 | A11y | Collapsible groups: keyboard (Enter/Space) and `aria-expanded`; sidebar collapse control has accessible name; skip link and focus order verified. |

---

## 4. Recommended Implementation Plan (Prioritized)

### Phase 1 — Fixes and single source (no UX break)

1. Remove duplicate `admin-dashboard.css` in `admin/base_site.html`.
2. Register EMIS with `config.admin_site`; add `emis` (and missing apps) to `get_app_list` `app_order`.
3. Remove `data-simplebar` from `#nav-sidebar-apps` and rely on native scroll (or add Simplebar and document). Ensure sidebar is vertically scrollable and scrollbar styled.

### Phase 2 — MFA: every user + encourage

4. Add `SiteSettings.require_mfa_all_staff` (BooleanField, default False). In `RequireMFAMiddleware`: if True, redirect **any** staff without TOTP to MFA setup (same bypass paths). Keep `require_mfa_roles`; when `require_mfa_all_staff` is True it applies to all staff regardless of role.
5. Add **encouragement** in admin: if user is staff and `not user_has_device(user)`, show a dismissible banner (e.g. “Set up MFA for stronger security — [Set up now]”) on admin index and/or in header. Store “dismissed” in session or user preference so it doesn’t spam every page.
6. Add **MFA compliance** to admin index: compute `mfa_enabled_count` (staff with TOTP), `mfa_staff_total`, `mfa_compliance_percent`; add one KPI card “MFA Compliance” and pass to template.
7. In profile and MFA setup page: keep “Set up MFA” / “Manage” prominent; optionally add one-line copy: “We recommend MFA for all staff.”

### Phase 3 — Sidebar: hierarchical and one source

8. **Single source for navigation:** Either (A) populate `UNFOLD["SIDEBAR"]["navigation"]` with collapsible groups (Core Management, Academic Processing, Financial Engine, System & Infrastructure) with `reverse_lazy` links to actual changelists (accounts, people, academics, evals, reports, finance, payroll, siteconfig, compliance, automation, etc.), set `show_all_applications=False`, and use Unfold’s sidebar rendering for those groups; or (B) keep `get_app_list()` and current template but ensure the sidebar template renders **collapsible** sections with the same domain names and that no other nav duplicates this. Choose one and remove the other to avoid redundancy.
9. Enable **CMD+K** (or equivalent): set `command_search=True` if Unfold supports it; ensure Ctrl+K focuses global search or command palette.
10. Ensure **vertical scroll** and no layout gaps (sticky sidebar, overflow-y-auto, thin scrollbar).

### Phase 4 — Dashboard as command center

11. Add **Action queue / Pending approvals:** in `GileadAdminSite.index`, query pending `AccessRequest` (or equivalent) and optionally other “pending” items; add to context and a small “To-Do” or “Pending approvals” widget on the dashboard.
12. Add **Unpaid fees / Collection** KPI if not present (permission-aware).
13. Keep or add **System health** widget (e.g. “System Status: Online”, “Last backup” if applicable) on dashboard.

### Phase 5 — Configuration Control Center and Security & MFA

14. Add **Security & MFA** section to Site Settings secondary sidebar (in `settings_nav_groups` or equivalent) with anchor to MFA-related fields; add help text for “Require MFA for all staff” and “Require MFA for roles.”
15. Add small **MFA status widget** in Site Settings secondary sidebar (e.g. “Staff with MFA: X/Y” or “Compliance: Secure” when enforcement on).

### Phase 6 — Redundancy and polish

16. **Header:** Replace or shrink nav bridge + weather + site name with one compact top bar (switcher + user tools); make weather optional/collapsible.
17. **Design tokens:** Consolidate admin/sidebar CSS variables; remove duplicate stylesheet links.
18. **Breadcrumbs:** Ensure always visible.
19. **Dirty state:** “You have unsaved changes” for Site Settings (and other critical forms).
20. **Empty states / Bulk actions:** Audit and add where missing.

### Phase 7 — Mobile and a11y

21. Visible **Menu** toggle on small screens; sidebar close and focus management.
22. **Accessibility:** Collapsible keyboard + aria; sidebar collapse label; skip link and focus order.

---

## 5. MFA Behavior Summary (Target)

- **Zero-cost:** TOTP only (current); no SMS/email cost.
- **Require:** Option “Require MFA for all staff” (new) + existing “Require MFA for roles.” When either applies, middleware redirects to MFA setup until device is configured.
- **Encourage:** For every user without MFA: persistent (dismissible) prompt in admin and clear “Set up MFA” in profile/dropdown. Dashboard shows MFA compliance % so admins see progress.
- **Config center / Site Settings:** Security & MFA section in Site Settings with enforcement toggles and optional MFA status widget in secondary sidebar.

---

## 6. File Reference

| Area | Files |
|------|--------|
| Sidebar | `templates/admin/base.html`, `nav_sidebar.html`, `sidebar_inner.html`, `app_list.html` |
| App list / nav | `config/admin.py` (`get_app_list`, `app_order`), `config/settings.py` (`UNFOLD`) |
| MFA | `apps/accounts/middleware.py` (RequireMFAMiddleware), `views_mfa.py`, `templates/accounts/mfa_setup.html`, `apps/siteconfig/models.py` (require_mfa_roles) |
| Dashboard | `config/admin.py` (index), `templates/admin/admin_dashboard.html` |
| Config center (Site Settings) | `templates/admin/siteconfig/sitesettings/settings_sidebar.html`, `change_form.html`, siteconfig admin (settings_nav_groups) |
| Header | `templates/unfold/helpers/header.html`, `templates/components/admin_nav_bridge.html` |
| Styles | `static/css/admin-sidebar-*.css`, `admin-dashboard.css`, `templates/admin/base_site.html` |
| EMIS | `emis/admin.py` |

---

## 8. Pre-build checklist (verify before implementation)

**Admin URL names (use in UNFOLD or links):** `admin:accounts_user_changelist`, `admin:people_studentprofile_changelist`, `admin:academics_classroom_changelist`, `admin:evals_evaluation_changelist`, `admin:reports_reportcard_changelist`, `admin:finance_invoice_changelist`, `admin:payroll_payslip_changelist`, `admin:siteconfig_sitesettings_changelist`, `admin:compliance_complianceauditlog_changelist`, `admin:requests_accessrequest_changelist`, `admin:automation_automationexecutionlog_changelist`. (Plan 2.1 used shortened names; use these exact names.)

**Sidebar:** We override Unfold’s sidebar (admin/base.html → nav_sidebar → app_list). So `UNFOLD["SIDEBAR"]["navigation"]` is not used. Decide before Phase 3: either (A) use Unfold’s nav (remove override, set navigation, add Quick access items) or (B) keep our sidebar and make app_list collapsible with same domain names—do not implement both.

**Action queue:** `AccessRequest` with `status=PENDING`; respect request-manager permissions in index context.

**MFA:** Add `require_mfa_all_staff` on SiteSettings (same fieldset as require_mfa_roles or new “Security & MFA”); migration; middleware checks it.

**EMIS:** Register with config.admin_site; add emis to get_app_list app_order.

**Dependencies:** django-unfold 0.76, django-otp, qrcode—already in requirements.

---

## 7. Summary

- **Fix first:** Duplicate CSS, EMIS registration, app_order, Simplebar.
- **MFA:** Add “require for all staff” option and **encourage** setup for every user (banner + dashboard KPI + Security & MFA in Config center / Site Settings).
- **Sidebar:** One source of truth (Unfold navigation or get_app_list); collapsible domains; CMD+K; vertically scrollable, no gaps.
- **Dashboard:** Command center with MFA compliance, Action queue (pending approvals), unpaid/collection KPI, system health.
- **Config center / Site Settings:** Secondary sidebar with Security & MFA section and MFA widget.
- **Redundancy:** Single nav source, compact header, consolidated tokens/styles, breadcrumbs, dirty state, empty states and bulk actions where needed.

This plan should be treated as the single roadmap for making /admin the “engine” of the platform and fixing all identified gaps and redundancies.

**Pre-build checklist:** Use exact admin URL names (e.g. `admin:people_studentprofile_changelist`). We override Unfold sidebar so `UNFOLD["SIDEBAR"]["navigation"]` is unused—choose Unfold nav OR our app_list in Phase 3. Action queue = `AccessRequest` with `status=PENDING`. Add `require_mfa_all_staff` on SiteSettings + migration. EMIS: register with admin_site and app_order. Dependencies: django-unfold 0.76, django-otp, qrcode already present.
