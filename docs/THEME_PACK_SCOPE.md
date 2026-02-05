# How ThemePacks Apply Across the Site

ThemePacks **do not** apply to the entire site by default. The site has **two separate theme choices** that control different areas.

---

## 1. **Portal theme pack**

| Setting | Field | Where it applies |
|--------|--------|-------------------|
| **Theme pack** | `SiteSettings.theme_pack` | Portal (student/parent/teacher dashboards), login page, and any view that uses `SITE.active_theme` or `SITE_THEME`. |

- **Context:** `SITE_THEME` = `site.active_theme` (i.e. `theme_pack` or the default ThemePack).
- **Used by:** Portal base templates, login, reports that use site theme.
- **Changed in:** Site Settings → **Branding** → **Theme pack** dropdown.

So: **Theme pack** = theme for the portal (families, students, teachers as portal users). It does **not** change `/admin` or `/backend`.

---

## 2. **Staff theme pack (Admin + Backend)**

| Setting | Field | Where it applies |
|--------|--------|-------------------|
| **Admin theme pack** | `SiteSettings.admin_theme_pack` | **Both** `/admin/` (Django admin) **and** `/backend/` (Workflow Center, backend dashboards). |

- **Context:** `SITE_ADMIN_THEME` = `site.get_admin_theme()` (i.e. `admin_theme_pack` or fallback).
- **Used by:** `/admin` (admin index, model list/changelist, change forms, admin dashboard) and `/backend` (backend_base.html, Workflow Center).
- **Changed in:** Site Settings → **Theme & Experience** → **Admin theme pack** (or the "Staff theme (Admin + Backend)" palette selector).

So: **Admin theme pack** = shared theme for staff dashboards. Changing it updates both `/admin` and `/backend`.

---

## 3. **Summary**

| Area | Controlled by | Field |
|------|----------------|-------|
| Portal (e.g. /portal/, /parent/, /teacher/) | Theme pack | `theme_pack` |
| Login page | Theme pack | `theme_pack` |
| **Django /admin/** (including admin dashboard) | **Staff theme pack** | `admin_theme_pack` |
| **Backend** (/backend/, Workflow Center) | **Staff theme pack** | `admin_theme_pack` |

- Changing **Theme pack** updates portal and login; `/admin` and `/backend` stay unchanged.
- Changing **Admin theme pack** (staff theme) updates both `/admin` and `/backend`; portal and login stay unchanged.

---

## 4. **How other "profiles" or pages get their theme**

- **Portal / role dashboards (parent, teacher, student):** Use `SITE.active_theme` → **Theme pack**.
- **Login:** Uses site theme (Theme pack).
- **Backend (/backend/):** Uses `SITE_ADMIN_THEME` → **Admin theme pack** (shared with /admin). Also uses `backend_console_theme` (Dark/Light) for light/dark mode.
- **Django admin (/admin/):** Uses **Admin theme pack** (same as backend).

There is no per-user or per-role ThemePack in the model; user preferences (e.g. dark/light) can override **presentation** (e.g. `data-bs-theme`) but the **palette** (colors) still comes from the Theme pack or Admin theme pack above.

---

## 5. **Deep Space / Midnight Blue**

The **Deep Space / Midnight Blue** ThemePack has been added as a **staff** theme (slug: `admin-deep-space-midnight`). It applies to both `/admin` and `/backend` when you set **Admin theme pack** (staff theme) to "Deep Space / Midnight Blue" in Site Settings. It does **not** change the portal; use **Theme pack** for that.

To seed it (with other staff palettes):

```bash
python manage.py seed_admin_dashboard_palettes
```

If you already ran the command before, run it again (no `--reset`): it will **update or create** the new palette so "Deep Space / Midnight Blue" appears in the Staff theme pack list.

---

## 6. **Black theme (sidebar + forms)**

For a professional black theme on `/admin`, use **Deep Space / Midnight Blue** and see [docs/ADMIN_BLACK_THEME.md](ADMIN_BLACK_THEME.md) for token reference and customization.
