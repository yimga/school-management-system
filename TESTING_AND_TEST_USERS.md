# Testing and Test Users

Single reference for testers: **portals, URLs, and how to create test users** (local and production).

---

## 1. Portals and URLs

| Portal | URL | Who | Notes |
|--------|-----|-----|--------|
| **Login** | `/authentication/login/` | Everyone | Same login for all portals; redirect after login depends on role. |
| **Home (redirect)** | `/` | Anonymous → login; Logged-in → role-based redirect | |
| **Backend dashboard** | `/authentication/backend/` or `/backend/` | Admin / staff | Main workflow dashboard (Quick Actions, RBAC sections, KPIs). |
| **Django Admin** | `/admin/` | Superuser / staff | Unfold admin (models, Site Settings, users). Sidebar should stay on the **left** (critical layout fallback if static CSS fails). |
| **Parent portal** | `/portal/` or `/portal/parent/` | Parent | Parent dashboard, finance, results, link child, contact school. |
| **Teacher portal** | `/portal/teacher/` | Teacher | Teacher dashboard, marks, attendance, timetable, workflow. |
| **Help / KB** | `/kb/` | Authenticated | Knowledge base. |
| **Site config / Customizer** | `/siteconfig/customizer/` | Staff | Theme and site settings (also linked from admin). |

**Canonical entry points after login (by role):**

- **Admin / staff:** `/authentication/backend/` (backend dashboard).
- **Teacher:** `/portal/teacher/` (teacher dashboard).
- **Parent:** `/portal/parent/` (parent dashboard).

---

## 2. Creating Test Users

### Option A – Local (minimal: admin + teacher + parent)

Use this for quick local testing with three accounts.

```bash
# 1. Migrate (if not already done)
python manage.py migrate --noinput

# 2. Ensure platform admin (admin/admin) and optionally tenant demo users
python manage.py seed_render_users
```

If you want tenant demo users with a specific password, set it when running the command:

```bash
ADMIN_PASSWORD=Sch00l_1234 python manage.py seed_render_users
```

Or run the commands separately (platform admin vs tenant users use different passwords):

```bash
python manage.py ensure_superuser --no-input --username admin --password admin
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --principal-username principal1 --password Sch00l_1234
```

**Result:**

| Username | Password | Role |
|----------|----------|------|
| **admin** | admin (platform super-admin) | Superuser |
| **teacher1** | From ADMIN_PASSWORD or --password above | Teacher |
| **Parent1** | From ADMIN_PASSWORD or --password above | Parent |
| **principal1** | From ADMIN_PASSWORD or --password above | Principal |

- Log in at **/authentication/login/** or **/admin/**.
- Exact usernames: `admin`, `teacher1`, `Parent1`, `principal1` (case-sensitive).
- Platform admin is always **admin** / **admin**; tenant users have a separate password (ADMIN_PASSWORD or the one you pass to create_teacher_parent_accounts).

---

### Option B – Production (Render)

On Render, test users are created by the **preDeployCommand** (or Release Command), not by you manually.

1. **Release Command** (or preDeployCommand in Blueprint) should run `seed_render_users` (e.g. via `./scripts/release/render_predeploy.sh`).
2. Deploy. After each deploy, **seed_render_users** runs and:
   - Always ensures **admin** (superuser) with password **admin** (platform super-admin). No env var required for platform login.
   - If **ADMIN_PASSWORD** is set in Render Dashboard → Environment, also creates/updates **teacher1**, **Parent1**, **principal1** with that password (tenant demo users only).
3. Log in at `/authentication/login/` or `/super/` with **admin** / **admin**. For tenant demo users, use teacher1, Parent1, or principal1 with the value of `ADMIN_PASSWORD`.

If credentials disappear (e.g. ephemeral DB or new DB), redeploy; `seed_render_users` will ensure admin/admin again. Set `ADMIN_PASSWORD` only if you want tenant demo users. See **docs/CREDENTIALS_AND_RESTORE.md** and **docs/CONFIG_AND_USERNAMES_REFERENCE.md**.

---

### Option C – Full local test data (Buea synthetic seed)

For testing with many students, parents, teachers, invoices, evals, etc.:

```bash
python manage.py migrate --noinput
python manage.py ensure_superuser --no-input --username admin --password Sch00l_1234
python manage.py seed_buea_synthetic --scale small
```

- **admin** / Sch00l_1234 – superuser (from ensure_superuser).
- All Buea seed users (teachers, parents, admins, bursar) use password **Test1234**.
- Usernames: e.g. teacher_buea_01 … teacher_buea_10, parent_buea_001 … parent_buea_150, admin_buea_01 … admin_buea_05, bursar_buea. See **docs/CONFIG_AND_USERNAMES_REFERENCE.md**.

---

## 3. Quick verification checklist

After creating users and starting the server:

- [ ] **Login:** Open `/authentication/login/`, log in as **admin** (or teacher1 / Parent1). You should be redirected to the correct dashboard by role.
- [ ] **Backend:** As admin, open `/authentication/backend/` (or `/backend/`). Backend dashboard loads; sidebar on the **left**; no 500.
- [ ] **Django Admin:** As admin, open `/admin/`. Sidebar on the **left**; app list and models load.
- [ ] **Parent:** Log in as **Parent1**, open `/portal/parent/`. Parent dashboard loads.
- [ ] **Teacher:** Log in as **teacher1**, open `/portal/teacher/`. Teacher dashboard loads.
- [ ] **Principal:** Log in as **principal1**. Can access backend; role is Principal.

---

## 4. Comprehensive Buea test plan (evals, report cards, rollover)

For **real-world testing** of the dual-curriculum (General + Technical), report cards, evals, finance, and rollover, see **docs/COMPREHENSIVE_TEST_PLAN_BUEA.md**. Log all bugs, gaps, and improvements in **test_finding.md** (project root).

---

## 5. Where test-user logic lives

| What | Where |
|------|--------|
| Superuser (admin) | `apps/accounts/management/commands/ensure_superuser.py` |
| Teacher + parent + principal (teacher1, Parent1, principal1) | `apps/accounts/management/commands/create_teacher_parent_accounts.py` |
| Render seed (admin/admin + optional tenant users) | `apps/accounts/management/commands/seed_render_users.py` (ensures admin/admin; creates teacher1, Parent1, principal1 when ADMIN_PASSWORD set) |
| Full Buea synthetic data | `apps/academics/management/commands/seed_buea_synthetic.py` |

---

## 6. More detail

- **Credentials and restore:** **docs/CREDENTIALS_AND_RESTORE.md**
- **Usernames and config (Render + Buea):** **docs/CONFIG_AND_USERNAMES_REFERENCE.md**
- **Deployment (Render, static, backend):** **docs/DEPLOYMENT_BACKEND_DASHBOARD.md**
