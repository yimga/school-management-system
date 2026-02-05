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

# 2. Create superuser (admin)
python manage.py ensure_superuser --no-input --password Sch00l_1234

# 3. Create teacher and parent (same password as you like)
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password Sch00l_1234
```

**Result:**

| Username | Password | Role |
|----------|----------|------|
| **admin** | Sch00l_1234 | Superuser |
| **teacher1** | Sch00l_1234 | Teacher |
| **Parent1** | Sch00l_1234 | Parent |

- Log in at **/authentication/login/** or **/admin/**.
- Exact usernames: `admin`, `teacher1`, `Parent1` (case-sensitive).

To use a different password (e.g. from env):

```bash
ADMIN_PASSWORD=YourSecret python manage.py ensure_superuser --no-input
python manage.py create_teacher_parent_accounts --teacher-username teacher1 --parent-username Parent1 --password YourSecret
```

---

### Option B – Production (Render)

On Render, test users are created by the **preDeployCommand** (or Release Command), not by you manually.

1. In **Render Dashboard** → your service → **Environment**, set **ADMIN_PASSWORD** (e.g. a strong secret). This is required for seed.
2. Set **Release Command** (or preDeployCommand in Blueprint) to:
   ```bash
   python manage.py migrate --noinput && python manage.py seed_render_users
   ```
3. Deploy. After each deploy, **seed_render_users** runs and creates or updates:
   - **admin** (superuser) – password = `ADMIN_PASSWORD`
   - **teacher1** (teacher) – password = `ADMIN_PASSWORD`
   - **Parent1** (parent) – password = `ADMIN_PASSWORD`

If credentials disappear (e.g. ephemeral DB or new DB), set `ADMIN_PASSWORD` and redeploy so `seed_render_users` runs again. See **docs/CREDENTIALS_AND_RESTORE.md** and **docs/CONFIG_AND_USERNAMES_REFERENCE.md**.

---

### Option C – Full local test data (Buea synthetic seed)

For testing with many students, parents, teachers, invoices, evals, etc.:

```bash
python manage.py migrate --noinput
python manage.py ensure_superuser --no-input --username admin --password Sch00l_1234
python manage.py seed_buea_synthetic --scale small
```

- **admin** / Sch00l_1234 – superuser (from ensure_superuser).
- All Buea seed users (teachers, parents, admins, bursar) use password **Test124**.
- Usernames: e.g. teacher_buea_01 … teacher_buea_10, parent_buea_001 … parent_buea_150, admin_buea_01 … admin_buea_05, bursar_buea. See **docs/CONFIG_AND_USERNAMES_REFERENCE.md**.

---

## 3. Quick verification checklist

After creating users and starting the server:

- [ ] **Login:** Open `/authentication/login/`, log in as **admin** (or teacher1 / Parent1). You should be redirected to the correct dashboard by role.
- [ ] **Backend:** As admin, open `/authentication/backend/` (or `/backend/`). Backend dashboard loads; sidebar on the **left**; no 500.
- [ ] **Django Admin:** As admin, open `/admin/`. Sidebar on the **left**; app list and models load.
- [ ] **Parent:** Log in as **Parent1**, open `/portal/parent/`. Parent dashboard loads.
- [ ] **Teacher:** Log in as **teacher1**, open `/portal/teacher/`. Teacher dashboard loads.

---

## 4. Where test-user logic lives

| What | Where |
|------|--------|
| Superuser (admin) | `apps/accounts/management/commands/ensure_superuser.py` |
| Teacher + parent (teacher1, Parent1) | `apps/accounts/management/commands/create_teacher_parent_accounts.py` |
| Render seed (admin + teacher1 + Parent1) | `apps/accounts/management/commands/seed_render_users.py` (calls ensure_superuser + create_teacher_parent_accounts) |
| Full Buea synthetic data | `apps/academics/management/commands/seed_buea_synthetic.py` |

---

## 5. More detail

- **Credentials and restore:** **docs/CREDENTIALS_AND_RESTORE.md**
- **Usernames and config (Render + Buea):** **docs/CONFIG_AND_USERNAMES_REFERENCE.md**
- **Deployment (Render, static, backend):** **docs/DEPLOYMENT_BACKEND_DASHBOARD.md**
