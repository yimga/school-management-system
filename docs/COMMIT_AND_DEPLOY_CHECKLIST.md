# Commit and deploy checklist

Use this before pushing to ensure the app can deploy (e.g. on Render).

## 1. Deploy-critical files (must be committed)

These are **required** for `bootstrap_platform_catalog` and predeploy to work. If any are missing, deploy or post-migrate bootstrap can fail.

| File | Status | Action |
|------|--------|--------|
| `apps/siteconfig/management/commands/bootstrap_platform_catalog.py` | Untracked | `git add` |
| `apps/marketplace/management/commands/seed_marketplace_apps.py` | Untracked | `git add` |
| `scripts/release/render_predeploy.sh` | Modified | `git add` |
| `docs/DEPLOY_RENDER.md` | Modified | `git add` |
| `docs/BOOTSTRAP_PLATFORM_CATALOG.md` | Untracked | `git add` (recommended) |
| `apps/portal/management/commands/seed_kb_articles.py` | Modified | `git add` (Tag fix) |

Optional: if you use migration `0141_globalsupportticket_assigned_to`, add  
`apps/siteconfig/migrations/0141_globalsupportticket_assigned_to.py`.

## 2. One-time: add and stage deploy-critical files

```bash
git add apps/siteconfig/management/commands/bootstrap_platform_catalog.py
git add apps/marketplace/management/commands/seed_marketplace_apps.py
git add scripts/release/render_predeploy.sh
git add docs/DEPLOY_RENDER.md
git add docs/BOOTSTRAP_PLATFORM_CATALOG.md
git add apps/portal/management/commands/seed_kb_articles.py
```

## 3. Verify before commit

- **Django check:** `python manage.py check`
- **Bootstrap loads:** `python manage.py bootstrap_platform_catalog --help`
- **Optional:** run your test suite (e.g. `pytest` or `python manage.py test` on critical apps).

## 4. Commit and push

```bash
git status   # confirm deploy-critical files are staged
git commit -m "Bootstrap platform catalog, seed KB fix, deploy docs and predeploy wiring"
git push
```

## 5. Deploy (Render)

- Set `RUN_BOOTSTRAP_PLATFORM_CATALOG=1` if you want blueprint + marketplace seeded on each deploy.
- Set `RUN_FULL_BOOTSTRAP=1` as well to run full seed (global data, registries, portal, etc.) when desired.
- Ensure `DATABASE_URL` is set (PostgreSQL recommended).
- Pre-deploy command should be: `./scripts/release/render_predeploy.sh`.

## Other modified files

You have many other modified (and untracked) files. Either:

- **Option A:** Stage and commit all changes you want in this release (including the deploy-critical set above), then push.
- **Option B:** Commit only the deploy-critical set above first, push, deploy; then commit the rest in a follow-up.

Do **not** leave the six deploy-critical files uncommitted when you push if you rely on bootstrap or the updated predeploy script.
