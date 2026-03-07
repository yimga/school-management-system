# UI Parity Runbook (Dev -> Render)

This keeps `/admin`, dashboard, sidebar, child menus, and theme behavior consistent between local dev and Render.

## 1) Export current dev UI config

Run locally:

```bash
python manage.py export_ui_config --output fixtures/ui_config.json
```

This exports:
- `siteconfig.themepack`
- `siteconfig.sitesettings`

## 2) Commit and deploy

```bash
git add fixtures/ui_config.json
git commit -m "Update UI parity fixture from dev"
git push origin main
```

## 3) Import on Render

Run in Render shell after deploy:

```bash
python manage.py import_ui_config fixtures/ui_config.json
python manage.py collectstatic --noinput --clear
```

`import_ui_config` automatically runs `normalize_ui_config` unless `--skip-normalize` is used.

## 4) Verify

```bash
echo $RENDER_GIT_COMMIT
python manage.py shell -c "from apps.siteconfig.models import SiteSettings; s=SiteSettings.objects.first(); print(s.theme_pack_id, s.admin_theme_pack_id, s.primary_color, s.accent_color, s.backend_console_theme)"
```

## 5) Permanent deployment guardrails

`render.yaml` includes:
- `preDeployCommand`: migrate + seed admin theme packs + import `fixtures/ui_config.json` (when `APPLY_UI_FIXTURE_ON_DEPLOY=1`) + normalize UI config
- `buildCommand`: collectstatic

This prevents drift from missing ThemePacks, duplicate defaults, stale theme pointers, and dev/live UI config mismatches.

## 6) Important manual parity item: media files

Theme logos/backgrounds are in `media/`. Keep persistent storage mounted on Render (for example `/opt/render/project/src/media`) or re-upload branding assets after deploy.  
Without media parity, UI can still look different even when code + DB config match.
