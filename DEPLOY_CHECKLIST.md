# Pre-Deploy Checklist: Admin & Backend

Run through this before testing and deploying.

## Quick start

```bash
python manage.py runserver
```

## Render predeploy (required)

- [ ] `preDeployCommand` points to `./scripts/release/render_predeploy.sh`.
- [ ] `RUN_INTEGRATION_PREFLIGHT=1` in Render env.
- [ ] `ADMIN_PASSWORD` configured (for `seed_render_users`).
- [ ] `DATABASE_URL` points to Postgres (not SQLite ephemeral disk).

---

## 1. Admin (`/admin/`)

### Access
- [ ] Open `/admin/` (or `/backend/` then "Switch to Admin").
- [ ] Log in as staff/superuser.

### Theme visibility (all must be readable)
- [ ] **Light**: Header theme → "Light". Sidebar, content, tables, and Log out are visible.
- [ ] **Dark**: Header theme → "Dark". Same elements visible; no white-on-white or black-on-black.
- [ ] **System**: Header theme → "System". Page follows OS preference and stays readable.

### Navigation & flow
- [ ] **Sidebar**: "← Dashboard" at top; "Jump to model…" search; accordion sections (e.g. People, Academics) with child links.
- [ ] **Subpages**: On any model list/add/edit, "← Back to dashboard" and "← Back" appear at top of content.
- [ ] **Log out**: Visible (header, top-right). Click works.

### Content
- [ ] Dashboard index: cards, stats, app grid load.
- [ ] Changelist: table readable; filters on the right (if any).
- [ ] Change form: labels and inputs readable; Save/Cancel visible.

---

## 2. Backend (`/backend/`)

### Access
- [ ] Open `/backend/` (redirects to backend dashboard).
- [ ] Or open `/authentication/backend/` directly.

### Theme
- [ ] Backend keeps a **light** look even when portal theme is dark (sidebar/topbar can be dark; main content area stays light and readable).

### Navigation
- [ ] Sidebar: Backend sections (Dashboard, Workflow, etc.) visible and clickable.
- [ ] "Switch to Dashboard" / "Switch to Admin" in header works.

### Workflow Center (`/authentication/workflow/`)
- [ ] Page loads; steps and links visible.
- [ ] At least one link per step works (e.g. "Academic years", "Add student", "Workflow Center").
- [ ] Breadcrumb: Backend → Workflow Center.

### Backend dashboard
- [ ] Main content and right-hand panel (e.g. Recent Activity) both visible; no overlapping.
- [ ] Quick links/cards work (e.g. RBAC, Entity Console, Workflow Center).

---

## 3. Redirects & URLs

- [ ] `/backend/` → redirects to backend dashboard (no 404).
- [ ] Admin "← Back to dashboard" → `/admin/`.
- [ ] Backend "Backend dashboard" from Workflow Center → backend dashboard.

### Canonical URLs (all environments)

| Label            | Path                      |
|------------------|---------------------------|
| Login            | `/authentication/login/`  |
| Parent dashboard | `/portal/parent/`         |
| Teacher dashboard| `/evals/teacher/`         |
| Frontend admin   | `/backend/` → `/authentication/backend/` |
| Backend admin    | `/admin/`                 |

Run `python validate_urls.py` to verify critical routes resolve.

---

## 4. After deployment: backend dashboard not updated?

If you deployed but don’t see the backend dashboard fixes (Quick Actions, RBAC-gated sections, theme) on `/backend/`, see **[docs/DEPLOYMENT_BACKEND_DASHBOARD.md](docs/DEPLOYMENT_BACKEND_DASHBOARD.md)**. Common causes: deploying from a branch that doesn’t include `main`/`improvements`, static files not collected, or RBAC hiding sections for your role.

---

## 5. Sign-off

- [ ] All items above checked.
- [ ] No console errors on admin index, one changelist, one change form, backend dashboard, Workflow Center.
- [ ] Ready for deployment.

**Date:** _______________  
**Checked by:** _______________
