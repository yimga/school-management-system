# Admin Sidebar Improvement Plan

## 1. Drag and Drop on /admin – Recommendation

**Should we add it?** **No** – keep the admin dashboard as a fixed layout for now.

| Reason | Details |
|--------|---------|
| Different purpose | /admin is the configuration engine; /backend is the daily workflow dashboard. Admins need predictable layout for configuration tasks. |
| Lower value | Admins visit /admin for structured tasks (CRUD, settings). Reordering widgets adds little benefit. |
| Consistency | Docs already state drag-and-drop is for backend/teacher/parent dashboards only. Admin uses a fixed, curated layout. |
| Complexity | Adding Sortable.js and layout API to admin would duplicate logic and increase maintenance. |

**Recommendation:** Leave /admin as fixed layout. If admins later request customization, revisit.

---

## 2. Issues from Images – Analysis & Fix Plan

### Issue A: Logo/Graphic Sticking Out / Another Color on Sidepanel

**What you’re seeing:** Jagged blue/teal and dark green shapes peeking from behind menu items on the right side of the sidebar.

**Likely cause:** A background image or decorative element is still rendered, or an overlay/watermark is bleeding through.

**Where to fix:**
- Expand `static/css/no-watermark.css` to cover more elements and pseudo-elements inside the admin sidebar.
- Check for `background-image` on `#nav-sidebar-inner`, `.navigation_header`, or parent containers.
- Check Unfold’s default styles and any `::before` / `::after` pseudo-elements that might add overlays.
- Add selectors such as: `#nav-sidebar *`, `#nav-sidebar-inner *`, `.navigation_header`, and any Unfold-specific wrappers.

**Fix steps:**
1. Add stronger `no-watermark.css` overrides for admin sidebar elements.
2. Ensure `background-image: none !important` on all sidebar-related selectors.
3. Ensure `::before` and `::after` on sidebar elements use `display: none` or `background: none`.

---

### Issue B: Header Logo Not Visible (Image 1)

**What you’re seeing:** On the “updated” sidebar (Image 1), the logo and “Gilead School Management” are missing. Only the avatar block and “Configuration” appear.

**Likely cause:** The **navigation_header** (Unfold) and our **admin-sidebar-header** (custom) are two different blocks:

| Block | Location | Content |
|-------|----------|---------|
| **navigation_header** | Top of sidebar | Logo (site_logo/site_icon) + branding text |
| **admin-sidebar-header** | Inside our app_list | Avatar + “admin” + “Configuration” |

If `branding` is empty or complex, or if `site_logo`/`site_icon` fails to render, the navigation_header can appear empty. Our admin-sidebar-header has no logo; it’s user-only.

**Fix steps:**
1. **Show logo + brand in header:** Always render logo and “Gilead School Management” in the top area, either by:
   - Making navigation_header robust when `branding` is heavy (e.g. only show `site_header` text, not full branding block), or
   - Adding an explicit logo + brand block above our admin-sidebar-header in `admin/app_list.html`.
2. **Use SITE_ADMIN_LOGO_URL:** Use the configured admin logo from context instead of relying only on Unfold’s SITE_ICON.
3. **Simplify branding in sidebar:** Pass `site_header` and `site_subheader` to the sidebar instead of the full branding block (weather, nav bridge, etc.).

---

### Issue C: Old vs New Sidebar Inconsistency (Image 1 vs Image 2)

**What you’re seeing:**  
- **Image 1:** “Updated” sidebar – no logo, avatar + Quick Access + app groups.  
- **Image 2:** “Old” sidebar – logo, “Gilead School Management”, “Gilead Tech High School”, standard Unfold layout.

**Likely cause:** Two different app_list paths:

| Condition | Template | Layout |
|-----------|----------|--------|
| `sidebar_navigation` has items | Unfold `unfold/helpers/app_list.html` | Group-based, Unfold default header |
| `sidebar_navigation` empty | Our `admin/app_list.html` | Custom header (avatar, Quick Access), no logo block |

UNFOLD `SIDEBAR.navigation` is `[]`, so we normally use our custom app_list. If some routes or states cause `sidebar_navigation` to be populated, Unfold’s app_list is used instead, which keeps the default header with logo and branding.

**Fix steps:**
1. **Single header source:** Add a clear logo + brand block to our `admin/app_list.html` that always appears at the top, regardless of which app_list is used.
2. **Unify header logic:** Ensure navigation_header and our custom header never conflict – either:
   - Always show logo in navigation_header and treat our admin-sidebar-header as a secondary “user” block, or
   - Move logo + brand into our app_list header so it’s always present.
3. **Check routing:** Confirm whether index vs app detail pages use different contexts so that `sidebar_navigation` differs.

---

## 3. Text Color Derivation on the Platform

Text colors come from:

| Source | Purpose |
|--------|---------|
| **Design tokens** (`design-tokens.css`) | Base variables such as `--admin-sidebar-text`, `--portal-text`, `--overlay-text`. |
| **Theme packs** | ThemePack model and SiteSettings supply values that override tokens. |
| **Backend themes** | `backend-dark-theme.css`, `backend-themes.css` define `--backend-text`, `--header-brand-fg`, etc. |
| **Unfold** | `--color-base-*`, `--font-subtle-*`, `text-important`, `text-subtle` Tailwind-like variables. |
| **Inline overrides** | Templates use `style="color: var(--admin-sidebar-text)"` when needed. |

**Flow:**
1. `:root` and theme blocks set CSS variables from SiteSettings/ThemePack.
2. Component CSS uses `var(--variable-name, fallback)`.
3. Dark/light mode overrides come from `html[data-bs-theme="dark"]` and `body.portal-backend-*`.

---

## 4. Fix Implementation Checklist

| # | Task | File(s) |
|---|------|---------|
| 1 | Broaden no-watermark coverage for admin sidebar | `static/css/no-watermark.css` |
| 2 | Add logo + “Gilead School Management” to sidebar top | `templates/admin/app_list.html`, `templates/unfold/helpers/navigation_header.html` |
| 3 | Use SITE_ADMIN_LOGO_URL in admin sidebar when available | Context + navigation_header or app_list |
| 4 | Ensure branding in sidebar uses simple text, not full branding block | `site_icon.html` or new sidebar branding partial |
| 5 | Unify header so logo appears consistently on index and app pages | navigation_header + app_list coordination |
| 6 | Remove any remaining background/watermark sources in admin | Audit Unfold + custom CSS |

---

## 5. Quick Wins (Recommended First)

1. Add logo + site name block at the top of `admin/app_list.html`, above the existing admin-sidebar-header.
2. Expand `no-watermark.css` with admin-specific selectors.
3. Ensure navigation_header always shows logo when `site_icon` or `SITE_ADMIN_LOGO_URL` is present.
