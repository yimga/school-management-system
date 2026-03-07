$ErrorActionPreference = "Stop"

param(
  [string]$ConfigPath = "fixtures/ui_config.json"
)

& python manage.py check_ui_parity --input-file $ConfigPath --strict
if ($LASTEXITCODE -ne 0) {
  throw "UI parity check failed for $ConfigPath"
}

Write-Host "UI parity check passed against $ConfigPath"
