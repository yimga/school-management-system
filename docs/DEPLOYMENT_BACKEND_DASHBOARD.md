# Backend Dashboard: Why Fixes Don’t Show After Deployment

If you deployed but don’t see the backend dashboard fixes (RBAC-gated sections, theme, cards, Quick Actions, etc.) on `/backend/`, use this checklist.

**Recommended deploy process:** Deploy from **`main`** (or the branch that has your latest code). On **Render**, use **Manual Deploy → “Clear build cache & deploy”** so templates and static files (sidebar, footer, Document Library Manager, etc.) are fresh. Then run **collectstatic** and **restart** the app if your pipeline doesn’t do it.

---

## 1. Deploy from the right branch

The backend dashboard fixes live on **`improvements`** and are merged into **`main`**. The script `deploy.sh` used to default to **`production-phase8`**, which may not include those commits.

**Do one of the following:**

- **Option A – Deploy from `main` (recommended)**  
  On the server (or in CI), deploy from `main` so you get the latest dashboard and RBAC fixes:
  ```bash
  export DEPLOY_BRANCH=main
  ./deploy.sh production   # or staging
  ```
  If your deploy doesn’t use `deploy.sh`, ensure the branch you deploy (e.g. in GitHub Actions or your CI) is **`main`** (or a branch that has merged `improvements`).

- **Option B – Update your long-lived deploy branch**  
  If you must keep using a branch like `production-phase8`, merge `main` into it and push, then deploy as usual:
  ```bash
  git checkout production-phase8
  git pull origin production-phase8
  git merge origin/main -m "Merge main: backend dashboard and RBAC fixes"
  git push origin production-phase8
  ```
  Then run your normal deployment (e.g. `./deploy.sh production` if it’s set to use `production-phase8`).

---

## 2. Static files and restart

After code deploy, static files and the app must be updated:

- Run **collectstatic** (e.g. `python manage.py collectstatic --noinput --clear`).
- **Restart** the app (e.g. Gunicorn/uWSGI, or `supervisorctl restart all` in `deploy.sh`).

If you don’t, old CSS/JS can be served and the dashboard can look or behave like the old version.

---

## 3. Caching

- **Browser**: Hard refresh (e.g. Ctrl+Shift+R / Cmd+Shift+R) or open `/backend/` in a private window.
- **CDN / reverse proxy**: Purge cache for the site (or at least for `/backend/` and static paths) after deploy.

---

## 4. RBAC: Some sections only for certain roles

Part of the “fixes” is **RBAC**: some dashboard sections are hidden unless the user has the right permissions:

| Section / link              | Required permission / role |
|----------------------------|----------------------------|
| Add Student, Add Teacher, Onboard wizards | `action_perms.people` (e.g. ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN) |
| Create Invoice, Finance Console | `action_perms.finance` (e.g. ADMIN, LEADERSHIP, IT_ADMIN, BURSAR, SUPERADMIN) |
| Site Settings / Customizer | `action_perms.site_settings` (settings.manage + admin-like role) |

If you log in as a user **without** those roles, those buttons/sections will not appear. That’s intentional. To see them:

- Log in as a user with the right role (e.g. Admin/Superadmin), or  
- Grant the user the corresponding feature permissions (e.g. `settings.manage`, finance access).

---

## 5. Quick verification

After deploying and clearing cache:

1. Open **`/backend/`** (or your backend dashboard URL).
2. Log in with an **admin/superuser** (or a user with people + finance + site_settings).
3. You should see:
   - Quick Actions (Add Student, Add Teacher, Onboard, Create Invoice, Site Settings, Finance Console, etc.)
   - RBAC-gated sections only when your user has the right permissions.
   - Correct theme (light/dark from Site Settings → Backend theme).

If you use `deploy.sh`, set **`DEPLOY_BRANCH=main`** (or merge `main` into your deploy branch) and ensure **collectstatic** and **restart** run; then use this verification. If something still doesn’t show, check role/permissions (section 4) and caching (section 3).

---

## 6. Deploying via Render dashboard (footer / backend not updating)

If you deploy from **Render** (dashboard “Deploy” button) and don’t see the **footer** (accordion, compact layout, Support & Help, Quick Links, etc.) or the **backend dashboard** fixes:

1. **Render builds from the branch connected to the service**  
   In Render Dashboard → your service → **Settings** → **Build & Deploy** → **Branch**: set it to **`main`** (or the branch that has the footer and dashboard commits). Save.

2. **Your latest code must be on that branch on GitHub**  
   The footer and dashboard work live on `improvements` and are merged into `main`. Push so **origin/main** has them:
   ```bash
   git checkout main
   git pull origin main
   # If your work is on improvements, merge it in:
   git merge improvements -m "Merge improvements: footer and backend dashboard"
   git push origin main
   ```
   If you only ever work on `improvements`, either connect Render to **`improvements`** in the dashboard, or merge `improvements` into `main` and push `main` (then connect Render to `main`).

3. **Clear build cache and redeploy**  
   In Render Dashboard → your service → **Deployments** → **Manual Deploy** → choose **“Clear build cache & deploy”**. That forces a fresh build from the current branch; otherwise Render may reuse an old build and you won’t see template/CSS changes (including the footer).

4. **Where the footer appears**  
   The dashboard footer is included in **portal_base.html**, so it appears on all portal and backend pages (parent dashboard, backend `/backend/`, etc.). If you still don’t see it after (1)–(3), confirm you’re on a page that uses the portal (e.g. `/backend/` or parent dashboard), and do a hard refresh (Ctrl+Shift+R) or try an incognito window.
