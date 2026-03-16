# Changes Not Visible After Deploy — Quick Fix

If after a commit and deployment you still see old content (no Studio OS, empty marketplace/catalog, old UI), follow these in order.

---

## 1. Use the correct URL (manager vs public)

**Studio OS and the control plane (`/super/`, marketplace, catalogs) are only on the manager host.**

| You want to see | Use this URL (example) |
|-----------------|------------------------|
| **Studio OS**, control plane, marketplace, Create school | **https://manager.runmycampus.com** (or `https://manager.<your-base-domain>`) |
| Marketing, login, public pages | `https://runmycampus.com` or the default Render URL |

The default Render URL (e.g. `school-management-system-2kzk.onrender.com`) is the **public** host. It does **not** serve `/super/` or `/studio/`. You must:

1. In Render: add a **custom domain** **manager.runmycampus.com** (or `manager.<your-base-domain>`) for your web service.
2. In Render **Environment**, add **manager.runmycampus.com** to **ALLOWED_HOSTS** (e.g. append `,manager.runmycampus.com` to the existing value).
3. Log in as superuser and open **https://manager.runmycampus.com/super/** and **https://manager.runmycampus.com/studio/**.

See [RENDER_SHELL_AFTER_DEPLOY.md §0b](RENDER_SHELL_AFTER_DEPLOY.md#0b-where-you-see-studio-os-marketplace-and-control-plane) for the full table.

---

## 2. Seed catalog and clear cache (run once after this deploy)

Open **Render Dashboard → your Web service → Shell** and run:

```bash
python manage.py check && python manage.py bootstrap_platform_catalog --all && python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

This populates marketplace, blueprints, workflows, dashboards, registries, and clears cache so the UI shows new data. Without it, App catalog / Blueprint marketplace / Studio can stay empty or show old state.

---

## 3. Make future deploys seed automatically

In **Render Dashboard → Web service → Environment** add:

- **RUN_BOOTSTRAP_PLATFORM_CATALOG** = `1`

Then run **Manual Deploy → Deploy latest commit**. Pre-deploy will run `bootstrap_platform_catalog --all` on every deploy so you don’t need to run it in Shell again.

---

## 4. Confirm the latest commit is deployed

1. **Render Dashboard → Web service → Deployments** — open the latest deploy; ensure **Build** and **Pre-Deploy** finished successfully.
2. If the deploy used an old commit: **Manual Deploy → Deploy latest commit** (or **Clear build cache & deploy** if needed).
3. In **Shell**: `git log --oneline -3` — you should see your latest commit (e.g. the one with “NEXT_50 step 6 DONE”, “pre-deploy gate fix”, etc.).

---

## 5. If static/CSS looks old

Pre-deploy runs `collectstatic`. If you still see old styles:

1. In Render, run **Manual Deploy → Clear build cache & deploy**.
2. In Shell after deploy: `python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"`.
3. Hard-refresh the browser (Ctrl+Shift+R or Cmd+Shift+R) or try an incognito window.

---

## Summary one-liner (Shell, after deploy)

```bash
python manage.py check && python manage.py bootstrap_platform_catalog --all && python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('Cache cleared')"
```

Then open **https://manager.runmycampus.com/super/** and **https://manager.runmycampus.com/studio/** (with your actual manager domain and after adding RUN_BOOTSTRAP_PLATFORM_CATALOG=1 for next time).

See also: [RENDER_SHELL_AFTER_DEPLOY.md §0](RENDER_SHELL_AFTER_DEPLOY.md#0-i-dont-see-most-changes-after-deploy--run-these), [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
