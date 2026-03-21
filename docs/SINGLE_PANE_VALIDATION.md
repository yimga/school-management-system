# Single Pane of Glass — Validation Checklist

**Purpose:** Ensure administrators have one management surface (single pane of glass) with no conflicting or multiple management sites. System config is the single config surface; control plane is the single shell on manager.

---

## 1. Entry points (manager host)

| Entry | URL / target | Purpose |
|-------|----------------|--------|
| **Sign-in** | `/super/` → redirect to login; after login → control plane dashboard | Single entry; no separate "admin" login label in nav |
| **Control plane** | `super:dashboard` (`/super/`) | Single shell: one top bar, one sidebar |
| **System config** | `siteconfig:console_domains_hub` (`/siteconfig/console/`) | Single config surface: platform config + domains + operational links |
| **Platform operator hub** | `super:platform_operator_hub` (`/super/platform-operator-hub/`) | Super-first curated links + full platform-admin changelist registry (verified `get_app_list`); primary path before raw `/admin/` |
| **Legacy path** | `/super/config/` | Redirects to System config (no separate hub page) |
| **Backoffice (raw CRUD)** | `admin:index` (`/admin/`) | Secondary/advanced; operator hub and System config link here for extremes only |

**Validated:** Nav, header, sidebar, quick actions, and dashboard action registry point "System config" → `siteconfig:console_domains_hub`. No primary link to Django admin in manager nav/header.

---

## 2. No duplicate "Configuration Engine" vs "System config"

| Location | Rule |
|----------|------|
| **Manager nav / header** | Label = "System config"; target = System config (console). |
| **Django admin (when visited directly)** | Label = "Platform Backoffice" (not "Configuration Engine") so the config brand is only System config. |
| **Breadcrumbs inside admin** | First crumb = "Platform Backoffice" (link to admin index). |
| **Tenant** | "Admin Panel" / "Backoffice" for Django admin; "System config" for console_domains_hub in portal sidebar. |

**Validated:** Naming is aligned: "System config" = bounded console; "Platform Backoffice" = Django admin (raw CRUD only).

---

## 3. Single shell

| Check | Status |
|-------|--------|
| Manager uses `control_plane_base.html` for `/super/*` | ✓ |
| Manager uses same top bar (admin_nav_bridge) when in Django admin | ✓ |
| No second "management site" URL promoted in manager UI | ✓ |
| Control plane nav built from `control_plane_nav.py`; one "System config" under Platform Settings | ✓ |

---

## 4. Backoffice only where needed

| Surface | Backoffice link |
|---------|-----------------|
| System config page | No link to admin (all config in console). |
| Site settings / Regions / Plans etc. list | Optional "Open in backoffice" for raw CRUD; primary action = System config. |
| Manager header / dropdown | No "Backoffice" or "Advanced backoffice" link (removed). |
| Tenant portal sidebar | "System config" → console; no duplicate "Configuration Engine" → admin. |

---

## 5. Run validation

- **URLs:** Visit `/super/` → dashboard. Click "System config" in sidebar → System config page. Visit `/super/config/` → redirects to System config.
- **No double config:** Search UI for "Configuration Engine" as a link target; should not appear as primary CTA on manager (only "System config").
- **Docs:** This file; RUNBOOK references `system_config_url` and System config.

---

**Code alignment (done):**
- `config/admin.py`: Platform admin site_title/site_header/index_title = "Platform Backoffice" (no "Configuration Engine").
- `templates/admin/base.html`: First breadcrumb = "Platform Backoffice" on manager, "Admin" on tenant.
- `templates/admin/index_superadmin.html`: Eyebrow and title = "Platform Backoffice".
- `templates/components/admin_nav_bridge.html`: Location when on admin = "Platform Backoffice".
- `apps/accounts/views.py`: Sidebar "admin" item: on manager → "System config" → siteconfig:console_domains_hub; on tenant → "Admin Panel" → admin:index.
- `templates/auth/admin_login.html`: Title/labels = "RunMyCampus Manager sign-in".
- Error pages 403/403_control_plane: No "Configuration Engine" brand; point to control plane / System config.

**Last validated:** Single-pane merge complete. System config = single config surface; Platform Backoffice = Django admin (secondary, no nav entry on manager).
