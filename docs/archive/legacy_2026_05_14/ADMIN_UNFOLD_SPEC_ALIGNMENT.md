# Admin Sidebar & Dashboard vs Unfold-Inspired Spec

This document maps the **Unfold-inspired design spec** (integrated search, collapsible sections, badges, dual-state icons, quick actions, child menus, tooltips, recents, sticky footer, soft theme transitions) to the current implementation and planned enhancements.

---

## Reference Spec (Summary)

- **Integrated Search Bar** – Permanent, stylized search at top of sidebar; search models/data.
- **Segmented Sections** – Collapsible groups (e.g. User Management, Product Catalog).
- **Notification Badges** – Small, high-contrast count badges next to items (e.g. red "5" next to Orders).
- **Dual-State Icons** – Icons that change from outlined to filled when active.
- **Quick Action Handlers** – Small "+" next to parent items (e.g. Invoices) to trigger "Create New" from sidebar.
- **Indented Trees with Connectors** – Vertical lines connecting child items to parent.
- **Contextual Tooltips** – In collapsed (icon-only) view: hover shows parent name + top 3 child links.
- **"Recent Items" Sub-list** – Dynamic "Recents" parent with user's most visited/edited (future).
- **Nested Tab Systems** – If child menu too deep, move 3rd level to content tabs (UX guideline).
- **Soft Dark/Light Transitions** – Smooth CSS transitions for sidebar when toggling theme.
- **Sticky Footer Profiles** – User profile at bottom of sidebar with account/org switcher (multi-tenancy).

---

## Current Implementation vs Spec

| Spec Item | Status | Notes |
|-----------|--------|------|
| Integrated Search Bar | ✅ Done | `nav-search` at top of sidebar; filters model links (`base_site.html`). |
| Segmented Sections | ✅ Done | Collapsible app groups (`.admin-app-group__toggle`), accordion for default modules; state in `localStorage`. |
| Notification Badges | ✅ Done + enhanced | Count badges on model links (`.admin-sidebar-badge`); optional **attention** variant for high-contrast (e.g. when count > 0). |
| Dual-State Icons | ⚪ Partial | No Material Icons; Django admin uses text. Active state uses border/background (`.active`, `aria-current`). Optional: add icon font later. |
| Quick Action "+" | ✅ Done | "+" link next to each model when `add_url` exists; "Add [Model]" from sidebar. |
| Indented Trees with Connectors | ✅ Done | Vertical connector line for child list (`.admin-app-models` / child block) in CSS. |
| Contextual Tooltips (collapsed) | ✅ Done | When sidebar collapsed, app group headers get `title` with app name + first 3 child links; native tooltip on hover. |
| Recent Items Sub-list | 📋 Future | Requires backend (session/history) + template; documented for later. |
| Nested Tab Systems | 📋 Guideline | Documented; move 3rd-level nav to content tabs when needed. |
| Soft Dark/Light Transitions | ✅ Done | Sidebar and key elements use `transition` on `background`, `border-color`, `color`. |
| Sticky Footer Profiles | ✅ Done | Sidebar footer block at bottom with current user link and placeholder for account/org switcher. |

---

## Files Touched

- **Sidebar JS:** `templates/admin/base_site.html` – search, badges, collapsible, tooltips (collapsed), quick-add injection, sticky footer injection.
- **Sidebar CSS:** `static/css/admin_sidebar_enhanced.css` – connectors, badge variants, quick-add link, footer, transitions.
- **App list template:** `templates/admin/app_list.html` – optional quick "+" link when `model.add_url` is available (or add via JS).
- **Docs:** `docs/ADMIN_UNFOLD_SPEC_ALIGNMENT.md` (this file).

---

## Optional / Future

- **Dual-State Icons:** Introduce an icon font (e.g. Material Icons) and apply outlined/filled per active state.
- **Recent Items:** Backend endpoint or middleware to record last N visited admin URLs; sidebar "Recents" section that lists them.
- **Multi-tenancy switcher:** When supported, wire sticky footer dropdown to switch organization/account.
