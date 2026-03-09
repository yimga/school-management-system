# Admin UI improvement ideas

The `/admin/` UI is in good shape (Unfold, custom sidebar, tenant vs manager dashboards). This doc lists **prioritized improvements** you can tackle next. Use it to pick what to implement.

**Recently done:** Platform admin index (`index_superadmin.html`) has a tips line (sidebar + Control plane link). Super: breadcrumbs added on dashboard, command center, and support dashboard for consistent “you are here” and back navigation.

---

## High impact, lower effort

| Idea | What | Where |
|------|------|--------|
| **Breadcrumbs everywhere** | Ensure changelist and change-form pages show a clear breadcrumb (e.g. Home › Siteconfig › Site settings). | Unfold / `base_site.html`; list/change templates. |
| **Empty states** | When a changelist has zero items, show a friendly message + primary “Add first X” CTA instead of a bare table. | Admin list templates or Unfold overrides. |
| **Page title in content** | Every admin page has an `<h1>` (or prominent title) in the main content area so screen readers and quick scanning work. | Changelist, change_form, custom views. |
| **Quick “Add” in header** | On changelist pages, add a visible “Add [model]” button in the content header (in addition to sidebar). | Changelist template or admin class. |
| **Filter sidebar discoverability** | Make the right-hand filter panel more visible (e.g. “Filters” label, or open-by-default on first visit). | Unfold / changelist CSS or template. |

---

## Navigation and structure

| Idea | What | Where |
|------|------|--------|
| **“All apps” link** | Add a dedicated “All applications” view or link (classic Django app list) for power users who want to see every app in one place. | New view or `index_tenant.html`. |
| **Sidebar: Pin hint** | Make “Pin this page” more discoverable (e.g. icon, or short tooltip on first visit). | `app_list.html` + optional JS. |
| **Section default state** | Remember which sidebar sections (Overview, Configuration, Content) are open/closed per user or globally. | Already partially done via localStorage; ensure consistent. |
| **Recent / frequent** | “Recently visited” or “Frequently used” links in sidebar (from session or simple analytics). | Sidebar template + optional view/context. |

---

## Visual and consistency

| Idea | What | Where |
|------|------|--------|
| **Card and spacing tokens** | Use design tokens for card radius, padding, and gap so all admin cards feel consistent. | `index_tenant.html`, `admin-console-themes.css`, design-tokens. |
| **Button hierarchy** | Primary vs secondary actions are obvious (e.g. one solid “Save”, others outline). | Change forms, custom admin views. |
| **Table density** | Optional “compact” table mode for changelists with many columns. | Unfold or custom list CSS. |
| **Success feedback** | After save/delete, a short success message (toast or inline) that’s easy to notice. | Unfold messages; ensure not buried. |

---

## Accessibility and mobile

| Idea | What | Where |
|------|------|--------|
| **Skip link** | Already present; ensure it’s the first focusable element and works on all admin pages. | `base_site.html`. |
| **Focus order** | Tab order: skip link → sidebar toggle → main content → sidebar. | Layout and tabindex. |
| **Sidebar on mobile** | Collapsible sidebar with overlay or slide-in; main content remains usable. | Sidebar CSS/JS. |
| **Touch targets** | Buttons and links at least 44px for touch. | Global admin CSS. |

---

## Data and trust

| Idea | What | Where |
|------|------|--------|
| **Real KPIs** | Replace any placeholder stats (e.g. “28 tables”, “~450 MB”) with real data or remove. | `admin_context.py`, dashboard templates. |
| **Loading states** | For slow changelists or custom views, show a loading indicator. | Optional; list view or JS. |

---

## References

- **Dashboard content:** `docs/ADMIN_DASHBOARD_CHANGE_PLAN.md`
- **Sidebar structure:** `docs/ADMIN_SIDEBAR_RESTRUCTURE_PLAN.md`
- **Templates:** `templates/admin/` (index_tenant.html, app_list.html, base_site.html)
- **Context:** `apps/dashboard/admin_context.py`, `config/admin.py`
