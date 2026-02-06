# Render Production Deployment - Commands to Run ✅

**Issue:** Dashboard looks the same after deployment  
**Reason:** Changes need to be pushed and static files need to be collected  
**Solution:** Run these commands on Render shell  

---

## Footer / backend dashboard not showing after Render deploy?

If you deployed from the Render dashboard but **don’t see the footer** (accordion, compact layout) or **backend dashboard fixes** (Quick Actions, RBAC sections):

1. **Push your branch to the one Render uses** (usually `main`):  
   `git push origin main` (or push the branch your Render service is set to).
2. In **Render Dashboard** → your service → **Deployments** → **Manual Deploy** → choose **“Clear build cache & deploy”** so Render rebuilds from the latest code (otherwise it may reuse an old build).
3. In **Settings** → **Build & Deploy** → **Branch**: confirm it’s **`main`** (or the branch that has the footer/dashboard commits).

Full checklist: **[docs/DEPLOYMENT_BACKEND_DASHBOARD.md](docs/DEPLOYMENT_BACKEND_DASHBOARD.md)** (section 6: Render).

---

## 🔴 CRITICAL: You're 11 Commits Ahead of Production!

Your local changes haven't been pushed to Render yet.

### Current Status:
```
Local (main):      06e05f1 ✅ (11 commits ahead)
Production (main): [Previous version] ❌ (old code still running)
```

---

## 📋 DEPLOYMENT COMMANDS FOR RENDER

### Step 1: Push Changes to Production (DO THIS FIRST!)
```bash
git push origin main
```

### Step 2: Access Render Shell
- Go to https://dashboard.render.com
- Select your service: `school-management-system`
- Click "Shell" tab
- Execute the following commands:

---

## 🚀 COMMANDS TO RUN IN RENDER SHELL

### Step 3: Collect Static Files
```bash
python manage.py collectstatic --noinput
```
This gathers all CSS, JS, and other static files for the new dashboard.

### Step 4: Run Database Migrations (if needed)
```bash
python manage.py migrate
```
This applies any new database changes.

### Step 4b: Seed Theme Packs (Theme & Experience color palettes)
If the **Theme & Experience** page is missing the themepack cards and color-combination column (Neutrals, Blues, Greens, Warm, Dark, Accessibility), run once:
```bash
python manage.py seed_admin_dashboard_palettes
```
This creates the preset ThemePacks with admin dashboard palettes. Optional: add to your **Release Command** so they exist after every deploy:  
`python manage.py migrate --noinput && python manage.py seed_admin_dashboard_palettes && python manage.py seed_render_users`

### Step 5: Clear Django Cache
```bash
python manage.py shell
```
Then inside the shell:
```python
from django.core.cache import cache
cache.clear()
exit()
```

### Step 6: Check for Syntax Errors
```bash
python manage.py check
```
Should return: `System check identified no issues (0 silenced).`

### Step 7: Verify New URL Routes
```bash
python manage.py show_urls | grep admin
```
Should show: `admin/dashboard/` route

---

## ✅ STEP-BY-STEP RENDER DEPLOYMENT

### Option A: Using Render Dashboard UI (Easiest)
1. Go to https://dashboard.render.com
2. Select `school-management-system` service
3. Click "Deployments" tab
4. Click "Deploy latest commit"
5. Wait for deployment to complete
6. Render will automatically:
   - Pull latest code from GitHub
   - Run build commands
   - Collect static files
   - Restart service

### Option B: Using Render Shell (Manual Control)
1. Go to https://dashboard.render.com
2. Select service → "Shell" tab
3. Run commands below (copy-paste each one):

```bash
# Pull latest code
git pull origin main

# Install new dependencies (if any)
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Check system health
python manage.py check

# Clear cache
python manage.py shell << EOF
from django.core.cache import cache
cache.clear()
EOF

# Restart server (optional - Render usually handles this)
pkill -f gunicorn
```

---

## 🔍 VERIFICATION STEPS

### After deployment, verify:

1. **Check if code updated:**
```bash
git log --oneline -1
# Should show: "docs: Add complete backend dashboard implementation guide"
```

2. **Check if static files collected:**
```bash
ls -la staticfiles/css/
# Should show: command-palette.css, design-system-unified.css, etc.
```

3. **Check if new URL exists:**
```bash
python manage.py show_urls | grep "admin/dashboard"
# Should show route
```

4. **Test health endpoint:**
```bash
curl https://school-management-system-2kzk.onrender.com/healthz/
# Should return: {"status": "ok"}
```

5. **Test new dashboard:**
```
Visit: https://school-management-system-2kzk.onrender.com/admin/dashboard/
(Should require login, then show backend dashboard)
```

---

## 📊 WHAT'S BEING DEPLOYED

### New Files:
```
✅ templates/admin/admin_dashboard.html (backend dashboard)
✅ Updated apps/observability/views.py (admin_dashboard view)
✅ Updated config/urls.py (/admin/dashboard/ route)
```

### Documentation:
```
✅ BACKEND_DASHBOARD_ARCHITECTURE.md
✅ BACKEND_DASHBOARD_COMPLETE.md
✅ BACKEND_DASHBOARD_FINAL_INTEGRATION.md
```

### Total Changes:
- 11 commits
- 3 new files
- 2 files modified
- ~2,000 lines added
- 0 lines removed

---

## ⚠️ TROUBLESHOOTING

### If dashboard still looks the same after deployment:

#### Problem 1: Cache not cleared
```bash
# Clear cache again
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
>>> exit()

# Or clear browser cache:
# Press Ctrl+Shift+Delete and clear browsing data
```

#### Problem 2: Static files not collected
```bash
# Recollect with verbose output
python manage.py collectstatic --noinput --verbosity 3
```

#### Problem 3: Old version still running
```bash
# Check running processes
ps aux | grep gunicorn
ps aux | grep python

# Restart service (in Render dashboard or via shell)
pkill -f gunicorn
```

#### Problem 4: Check error logs
```bash
# View logs in Render dashboard or:
journalctl -u render --since "10 minutes ago"
```

---

## 🎯 QUICK DEPLOYMENT CHECKLIST

- [ ] **Push changes to GitHub:**
  ```bash
  git push origin main
  ```

- [ ] **Option A: Click "Deploy" in Render dashboard** OR

- [ ] **Option B: Run in Render shell:**
  ```bash
  git pull origin main
  python manage.py collectstatic --noinput
  python manage.py migrate
  python manage.py check
  ```

- [ ] **Wait 2-5 minutes for service to restart**

- [ ] **Clear browser cache (Ctrl+Shift+Delete)**

- [ ] **Visit dashboard:**
  - https://school-management-system-2kzk.onrender.com/admin/dashboard/

- [ ] **Verify it looks different (utilitarian design)**

---

## 📱 COMMON COMMANDS REFERENCE

```bash
# Django management
python manage.py check              # Verify system
python manage.py migrate            # Run migrations
python manage.py collectstatic      # Gather static files
python manage.py shell              # Open Python shell

# Git
git pull origin main                # Get latest from GitHub
git log --oneline -5                # View recent commits
git status                          # Check current status

# Cache clearing
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
>>> exit()

# Process management
ps aux | grep gunicorn              # Check if running
pkill -f gunicorn                   # Kill process
systemctl restart render            # Restart service

# File checking
ls -la staticfiles/                 # Check static files
find . -name "admin_dashboard.html" # Find template
```

---

## 🚀 EXPECTED OUTCOME

After running these commands, you should see:

**At `/admin/dashboard/`:**
```
┌──────────────────────────────────────────────────┐
│ System Dashboard              [Refresh] [Back]    │
├──────────────────────────────────────────────────┤
│ Total Users | DB Status | System Health | Active │
│    145      | ✓Connected| ✓ Healthy   | 23     │
│                                                   │
│ ADMIN OPERATIONS                                 │
│ [User Mgmt] [Academic] [Finance] [Config]       │
│ [Data Export] [Audit Logs]                      │
│                                                   │
│ DATA MANAGEMENT                                  │
│ [Recent Activity] [Health Checks]               │
│                                                   │
│ QUICK ACTIONS                                    │
│ [Clear Cache] [Backup] [Notifications] [Sync]   │
│ [Reports] [Logs]                                │
│                                                   │
└──────────────────────────────────────────────────┘
```

Not the pretty/colorful frontend dashboard.

---

## 📞 SUPPORT

If still having issues:

1. **Check Render logs:** Dashboard → Logs tab
2. **Check Django errors:** `python manage.py check`
3. **Clear cache and browser:** Ctrl+Shift+Delete
4. **Wait 5 minutes:** Service needs time to restart
5. **Hard refresh page:** Ctrl+Shift+R (clears browser cache)

---

**Next Step:** Push to GitHub and deploy! 🚀
