$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$tmpDir = Join-Path $repoRoot ".tmp"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$uiConfigPath = Join-Path $tmpDir ("ui_config_dry_run_" + $timestamp + ".json")

if (-not (Test-Path $tmpDir)) {
  New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

Write-Host "[Phase 16] Running release hardening dry-run checks..."
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan

Write-Host "[Phase 16] Exporting UI config snapshot to $uiConfigPath"
python manage.py export_ui_config $uiConfigPath

Write-Host "[Phase 16] Printing active theme pointers..."
python manage.py shell -c "from apps.siteconfig.models import SiteSettings; s=SiteSettings.get_solo(); print('theme_pack_id=', s.theme_pack_id, 'admin_theme_pack_id=', s.admin_theme_pack_id, 'preview_mode_enabled=', s.preview_mode_enabled)"

Write-Host "[Phase 16] Dry-run complete."
