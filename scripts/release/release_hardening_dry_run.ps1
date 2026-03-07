$ErrorActionPreference = "Stop"

function Invoke-StrictCommand {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$CommandParts
  )

  & $CommandParts[0] $CommandParts[1..($CommandParts.Length - 1)]
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $($CommandParts -join ' ')"
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$tmpDir = Join-Path $repoRoot ".tmp"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$uiConfigPath = Join-Path $tmpDir ("ui_config_dry_run_" + $timestamp + ".json")

if (-not (Test-Path $tmpDir)) {
  New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

Write-Host "[Phase 16] Running release hardening dry-run checks..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "check")
Invoke-StrictCommand -CommandParts @("python", "manage.py", "makemigrations", "--check", "--dry-run")
Invoke-StrictCommand -CommandParts @("python", "manage.py", "migrate", "--plan")

Write-Host "[Phase 16] Exporting UI config snapshot to $uiConfigPath"
Invoke-StrictCommand -CommandParts @("python", "manage.py", "export_ui_config", "--output", $uiConfigPath)

Write-Host "[Phase 16] Printing active theme pointers..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "shell", "-c", "from apps.siteconfig.models import SiteSettings; s=SiteSettings.get_solo(); print('theme_pack_id=', s.theme_pack_id, 'admin_theme_pack_id=', s.admin_theme_pack_id, 'preview_mode_enabled=', s.preview_mode_enabled)")

Write-Host "[Phase 16] Dry-run complete."
