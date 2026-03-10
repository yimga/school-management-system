# High-end changes on main (this file proves they’re on GitHub)

If you see **this file** on the **main** branch at  
**https://github.com/yimga/school-management-system**,  
then you’re on the right branch and the high-end work is there.

---

## What’s included

1. **Configuration Engine (admin) login**
   - **File:** `templates/auth/admin_login.html`
   - Dark/gold layout, “Configuration Engine sign-in”, “superuser account”, “Back to public site”.
   - **File:** `config/admin.py` — `login_template = "auth/admin_login.html"`, `public_site_url` in context.

2. **Platform-wide premium styling**
   - **File:** `static/css/platform-high-end.css` — premium tokens, sidebars, cards, charts.
   - Loaded in: `templates/base.html`, `templates/portal_base.html`, `templates/control_plane_skeleton.html`, `templates/admin/base_site.html`.

3. **Manager login**
   - **File:** `static/css/manager-login.css` — shared dark/gold login styles.
   - **File:** `templates/auth/manager_login.html` — uses `public_site_url`.

4. **Admin index & links**
   - **File:** `templates/admin/index.html` — manager vs tenant header actions (Control plane / Master Sheet, etc.).
   - **File:** `templates/admin/extra_user_links.html` — Control plane, Back to public site (when manager host).

5. **Tenant/superadmin alignment**
   - **File:** `templates/siteconfig/feature_control_panel.html` — “Schools” link only on manager host.
   - **Docs:** `docs/architecture/phase10_superadmin_vs_tenant_ui.md` (§ 8.6), `docs/RUNMYCAMPUS_UI_IMPROVEMENTS.md`, `docs/RESPONSIVE_AND_LINKS_AUDIT.md`.

6. **Pre-commit tests**
   - **File:** `scripts/run_tests_pre_commit.ps1`
   - **Tests:** `apps/siteconfig/tests/test_admin_high_end.py`

---

## How to confirm on GitHub

1. Open: **https://github.com/yimga/school-management-system**
2. Use the branch dropdown and select **main**.
3. In the file list, open **HIGHEND_CHANGES_ON_MAIN.md** (this file).
4. Then open **config/admin.py** and search for `auth/admin_login.html` and `public_site_url`.
5. Open **templates/auth/admin_login.html** and search for “Configuration Engine sign-in”.
6. Open **static/css/platform-high-end.css** and check the first lines (premium tokens).

If those match, the high-end code is on GitHub main.
