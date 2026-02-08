# Dev/Live Parity Runbook

## Goal
Keep local development UI and Render production UI consistent for theme, layout, and feature toggles.

## Source of truth
- Code and templates: Git branch deployed on Render.
- Runtime UI configuration: `SiteSettings` + `ThemePack` data exported via `export_ui_config`.

## Standard local workflow
1. Ensure code is on latest branch:
   - `git pull origin main`
2. Run migrations:
   - `python manage.py migrate`
3. Sync UI config fixture roundtrip:
   - `bash scripts/release/sync_ui_config.sh roundtrip`
   - PowerShell fallback: `powershell -ExecutionPolicy Bypass -File scripts/release/sync_ui_config.ps1 -Mode roundtrip`
4. Seed curated admin packs:
   - `python manage.py seed_admin_dashboard_palettes`
5. Start local server:
   - `python manage.py runserver`

## Standard Render predeploy workflow
Render predeploy command should include:
- `python manage.py migrate --noinput`
- `python manage.py seed_admin_dashboard_palettes`
- `python manage.py import_ui_config fixtures/ui_config.json` (when enabled)
- `python manage.py normalize_ui_config`

## Production-to-local pull (manual)
1. On Render shell export current config:
   - `python manage.py export_ui_config /tmp/ui_config_prod.json`
2. Download or copy JSON into local repo as `fixtures/ui_config.prod.json`.
3. Import locally:
   - `CONFIG_PATH=fixtures/ui_config.prod.json bash scripts/release/sync_ui_config.sh import`
   - PowerShell fallback: `powershell -ExecutionPolicy Bypass -File scripts/release/sync_ui_config.ps1 -Mode import -ConfigPath fixtures/ui_config.prod.json`

## Local-to-production push (Git-driven)
1. Export local desired config:
   - `CONFIG_PATH=fixtures/ui_config.json bash scripts/release/sync_ui_config.sh export`
   - PowerShell fallback: `powershell -ExecutionPolicy Bypass -File scripts/release/sync_ui_config.ps1 -Mode export -ConfigPath fixtures/ui_config.json`
2. Commit `fixtures/ui_config.json`.
3. Push and deploy; predeploy imports the fixture.

## Parity checks after deploy
- Compare commit hash on Render:
  - `echo $RENDER_GIT_COMMIT`
- Check active theme IDs and key colors:
  - `python manage.py shell -c "from apps.siteconfig.models import SiteSettings; s=SiteSettings.get_solo(); print(s.theme_pack_id, s.admin_theme_pack_id, s.primary_color, s.accent_color)"`
- Verify Theme studio renders expected catalog and active badge states.

## Common mismatch causes
- Local has unapplied migrations.
- Render imported stale `fixtures/ui_config.json`.
- Browser cache serving old CSS/JS.
- Different branch commit than expected.

## Permanent controls
- Always run `sync_ui_config.sh` before local UI verification.
- Keep predeploy import/normalize enabled.
- Commit fixture changes explicitly when UI config should change in production.
