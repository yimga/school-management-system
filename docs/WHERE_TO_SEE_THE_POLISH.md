# Where to See the Polish (High-End Admin & Platform Styling)

All of this is in the codebase on **branch `main`** (merge commit: "Merge origin/main: keep high-end admin, platform styling...").

---

## 1. On GitHub

- **Repo:** https://github.com/yimga/school-management-system  
- **Branch:** `main` (use the branch dropdown).  
- **Commit:** Latest should be the merge; before that, "Initial commit: school management system with high-end admin...".

**Files to open on GitHub to confirm:**

| What | File path |
|------|-----------|
| Admin high-end login template | `templates/auth/admin_login.html` |
| Admin config (Configuration Engine, public_site_url) | `config/admin.py` |
| Platform premium CSS | `static/css/platform-high-end.css` |
| Manager login CSS (shared dark/gold) | `static/css/manager-login.css` |
| Admin index (manager vs tenant header actions) | `templates/admin/index.html` |
| Phase 10 doc § 8.6 | `docs/architecture/phase10_superadmin_vs_tenant_ui.md` |
| UI improvements status | `docs/RUNMYCAMPUS_UI_IMPROVEMENTS.md` |
| Pre-commit test script | `scripts/run_tests_pre_commit.ps1` |

If you see "Configuration Engine sign-in", "superuser account", `login_template = "auth/admin_login.html"`, and `platform-high-end.css` in those files, the polish is on GitHub.

---

## 2. In the Running App

You have to **run the Django server** to see the visual polish.

1. **Admin (Configuration Engine) login**
   - Go to: `http://manager.localhost:8000/admin/login/` (or your manager host + `/admin/login/`).
   - You should see: dark background, gold accent, "Configuration Engine sign-in", "Sign in with your superuser account", "Back to public site".

2. **Manager login**
   - Same host: `.../authentication/login/` (when `public_host_kind` is manager).
   - Same dark/gold style, "Back to public site" link.

3. **Platform-wide premium styling**
   - Any page that extends `portal_base`, `control_plane_skeleton`, `admin/base_site`, or `base.html` loads `platform-high-end.css` (rounded cards, sidebar polish, shadows). Open any dashboard or sidebar page to see it.

4. **Control plane**
   - On manager host: `/super/` — header "Configuration Engine", sidebar links, same premium look.

---

## 3. If You Don’t See It

- **Another folder / another machine:** Run `git pull origin main` there so you have the latest `main`.
- **GitHub:** Make sure you’re on branch **main** and refresh the page; open the files in the table above.
- **In the app:** Start the server (`python manage.py runserver` or your usual command) and open the URLs in section 2.
