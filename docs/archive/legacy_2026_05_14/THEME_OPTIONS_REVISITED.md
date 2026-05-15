# Theme Options Revisited

A concise recap of theme options and how to proceed. Use this to decide what to implement.

---

## 1. What’s Already in Place (No Change Needed)

| Item | Where it lives | Notes |
|------|----------------|--------|
| **Branding** | Site Settings → Branding | Logo, primary/accent/semantic colors, brand_font, theme_pack |
| **Backend console theme** | Site Settings → Theme & Experience | Dark / Light (backend_console_theme) |
| **Admin sidebar** | Site Settings → Admin Sidebar Theme | Full color set (admin_sidebar_*) + admin_theme_pack (logo/bg) |
| **Footer** | Site Settings → Footer Content | Accreditation, links, badges, support hours |
| **Portal content** | Site Settings → Portal Content | Quick actions, announcements, etc. |
| **User theme preference** | DashboardUserPreference | Light/dark/system per user on portal |

---

## 2. Theme Options Not Yet Implemented

### Phase A – Quick wins (no new models; small scope)

| # | Item | What it does | Effort | Impact |
|---|------|----------------|--------|--------|
| **A1** | **Login from SITE** | Login hero uses SITE logo, primary_color, accent_color, background (or theme pack). Optional fields: login_hero_heading, login_hero_subtext (or reuse site_name/tagline). | Low | High – first screen matches school brand |
| **A2** | **Header toggles** | Booleans: show_header_search, show_header_notifications, show_header_profile_menu (optional: show_header_theme_toggle). Portal/backend header shows or hides these. | Low | Medium – admins control header clutter |
| **A3** | **Favicon** | SiteSettings.favicon (ImageField). Output in base.html, portal_base, backend_base, admin base. | Low | Medium – browser tab shows school icon |
| **A4** | **Layout style** | layout_style: “boxed” or “fluid”. Wrapper class in portal_base/backend_base; CSS max-width when boxed. | Low | Low–medium – optional contained width |
| **A5** | **Default sidebar collapsed** | default_sidebar_collapsed (bool). When creating/defaulting DashboardUserPreference, set sidebar_collapsed from it. | Low | Low – new users get collapsed sidebar if desired |

### Phase B – Email and communication

| # | Item | What it does | Effort | Impact |
|---|------|----------------|--------|--------|
| **B1** | **Email branding** | Base email template (or snippet) with SITE logo URL, primary_color, site_name. Report_ready_* and other system emails use it so all emails share school branding. | Medium | High – every email looks on-brand |
| **B2** | **Branded domain (display)** | Optional portal_domain or branded_domain. Shown on login (“You’re logging in to …”) and in email footer; no DNS logic. | Low | Low – cosmetic only |

### Phase C – Navigation and sidebar

| # | Item | What it does | Effort | Impact |
|---|------|----------------|--------|--------|
| **C1** | **Sidebar menu order** | Fixed set of portal sidebar item IDs. Optional JSON (e.g. portal_sidebar_order or per-role) on SiteSettings; portal_sidebar.html renders in that order when set. | Medium | Medium – admins reorder nav without code |
| **C2** | **Collapsed sidebar icon** | Optional sidebar_icon (ImageField) on SiteSettings or ThemePack. When nav sidebar is collapsed, show this icon (e.g. small logo). | Low | Low – polish when sidebar is collapsed |

### Phase D – Optional advanced

| # | Item | What it does | Effort | Impact |
|---|------|----------------|--------|--------|
| **D1** | **Chart type per widget** | Config (e.g. on DashboardWidget or widget_meta) for bar/pie/line per chart widget; dashboard JS uses it. | Medium | Low–medium – admins choose chart type |
| **D2** | **Secondary font** | secondary_font + “use for headings” (bool). Expose as CSS variable; use in base/portal for headings. | Low | Low – typography variety |
| **D3** | **Base font size** | base_font_size (e.g. 14, 16). Expose as --base-font-size; use in rem-based typography. | Low | Low – accessibility / consistency |
| **D4** | **Default widgets per role** | Optional JSON: role → list of widget IDs. Use when initializing DashboardUserPreference or resolving default visible_widgets. | Medium | Medium – “instructor vs student” defaults without code |
| **D5** | **Admin “use site primary”** | Boolean: when True, admin sidebar accent/active border uses SiteSettings.primary_color. | Low | Low – admin matches portal accent |

---

## 3. How to Proceed – Decision Options

Pick one path (or mix and match specific items).

| Option | What to do | Best when |
|--------|------------|-----------|
| **Do nothing** | Leave theme as-is. Only branding, backend theme, and admin sidebar are configurable. | Current look is enough; no time for theme work. |
| **Phase A only** | Implement A1–A5: login from SITE, header toggles, favicon, layout_style, default_sidebar_collapsed. | You want a branded login and a few global knobs quickly. |
| **Phase A + B1** | Phase A plus email base template with SITE logo/primary. | You care about first impression (login) and every email looking on-brand. |
| **Phase A + B** | Phase A plus B1 and B2 (email branding + branded domain display). | Same as above plus “You’re logging in to …” and email footer domain. |
| **Phase A + C** | Phase A plus sidebar order (C1) and collapsed icon (C2). | You want full control over nav and sidebar presentation. |
| **Full plan (A+B+C)** | All of Phase A, B, and C. | You want the full “theme and site control” set without Phase D. |
| **Pick specific items** | Choose only certain items (e.g. A1, A3, B1). | You have a short list of must-haves. |

---

## 4. Recommendation (Short)

- **Minimum:** **Phase A** – login from SITE (A1), favicon (A3), and optionally header toggles (A2). Gives branded first impression and basic admin control with low effort.
- **If you care about emails:** Add **B1** (email branding) so report_ready and other system emails use SITE logo and colors.
- **Phase C and D** can wait until you need sidebar reorder, collapsed icon, or chart/widget defaults.

---

## 5. Next Step

Reply with one of:

1. **“Phase A”** – implement all of Phase A (A1–A5).  
2. **“Phase A + B1”** (or “Phase A + B”) – Phase A plus email branding (and optionally B2).  
3. **“Phase A + C”** or **“Full A+B+C”** – broader theme control.  
4. **“Only A1, A3”** (or similar) – specific items from the tables above.  
5. **“Do nothing”** – keep current theme behaviour and revisit later.

Once you choose, we can implement that set and leave the rest for later.
