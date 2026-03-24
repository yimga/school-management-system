# Single Pane of Glass — Validation Checklist

**Purpose:** Ensure administrators have one management surface (single pane of glass) with no conflicting or multiple management sites. Configuration Control Center is the single config surface; control plane is the single shell on manager.

---

## 1. Entry points (manager host)

| Entry | URL / target | Purpose |
|-------|----------------|--------|
| **Sign-in** | `/super/` → redirect to login; after login → control plane dashboard | Single entry; no separate "admin" login label in nav |
| **Control plane** | `super:dashboard` (`/super/`) | Single shell: one top bar, one sidebar |
| **Configuration Control Center** | `siteconfig:console_domains_hub` (`/siteconfig/console/`) | Single config surface: platform config + domains + operational links |
| **Platform operator hub** | `super:platform_operator_hub` (`/super/platform-operator-hub/`) | Super-first curated links + full platform-admin changelist registry (verified `get_app_list`); primary path before raw `/admin/` |
| **Legacy path** | `/super/config/` | Redirects to Configuration Control Center (no separate hub page) |
| **Backoffice (raw CRUD)** | `admin:index` (`/admin/`) | Secondary/advanced; operator hub and Configuration Control Center link here for extremes only |

**Validated:** Nav, header, sidebar, quick actions, and dashboard action registry point **Config center** (short label) → `siteconfig:console_domains_hub` (full product name: **Configuration Control Center**). No primary link to Django admin in manager nav/header.

---

## 2. No duplicate "Configuration Engine" vs "Configuration Control Center"

| Location | Rule |
|----------|------|
| **Manager nav / header** | Short label = **Config center**; target = Configuration Control Center (`/siteconfig/console/`). |
| **Django admin (when visited directly)** | Label = "Platform Backoffice" (not "Configuration Engine") so the bounded console brand is **Configuration Control Center** / **Config center**. |
| **Breadcrumbs inside admin** | First crumb = "Platform Backoffice" (link to admin index). |
| **Tenant** | "Admin Panel" / "Backoffice" for Django admin; **Config center** for `console_domains_hub` in portal sidebar. |

**Validated:** Naming is aligned: **Configuration Control Center** = bounded console (short label **Config center**); "Platform Backoffice" = Django admin (raw CRUD only).

---

## 3. Single shell

| Check | Status |
|-------|--------|
| Manager uses `control_plane_base.html` for `/super/*` | ✓ |
| Manager uses same top bar (admin_nav_bridge) when in Django admin | ✓ |
| No second "management site" URL promoted in manager UI | ✓ |
| Control plane nav built from `control_plane_nav.py`; one **Config center** under Platform Settings | ✓ |

---

## 4. Backoffice only where needed

| Surface | Backoffice link |
|---------|-----------------|
| Configuration Control Center page | No link to admin (all config in console). |
| Site settings / Regions / Plans etc. list | Optional "Open in backoffice" for raw CRUD; primary return path = **Config center** / Configuration Control Center. |
| Manager header / dropdown | No "Backoffice" or "Advanced backoffice" link (removed). |
| Tenant portal sidebar | **Config center** → console; no duplicate "Configuration Engine" → admin. |

---

## 5. Run validation

- **URLs:** Visit `/super/` → dashboard. Click **Config center** in sidebar → Configuration Control Center page. Visit `/super/config/` → redirects to same console.
- **No double config:** Search UI for "Configuration Engine" as a link target; should not appear as primary CTA on manager (primary CTA = **Config center**).
- **Docs:** This file; RUNBOOK references `system_config_url` and Configuration Control Center.

---

**Code alignment (done):**
- `config/admin.py`: Platform admin site_title/site_header/index_title = "Platform Backoffice" (no "Configuration Engine").
- `templates/admin/base.html`: First breadcrumb = "Platform Backoffice" on manager, "Admin" on tenant.
- `templates/admin/index_superadmin.html`: Eyebrow and title = "Platform Backoffice".
- `templates/components/admin_nav_bridge.html`: Location when on admin = "Platform Backoffice".
- `apps/accounts/views.py`: Sidebar "admin" item: on manager → **Config center** → siteconfig:console_domains_hub; on tenant → "Admin Panel" → admin:index.
- `templates/auth/admin_login.html`: Title/labels = "RunMyCampus Manager sign-in".
- Error pages 403/403_control_plane: No "Configuration Engine" brand; point to control plane / Configuration Control Center.

**Last validated:** Single-pane merge complete. Configuration Control Center = single config surface; Platform Backoffice = Django admin (secondary, no nav entry on manager).
