$ErrorActionPreference = "Stop"

param(
  [string]$Formats = "odt,docx"
)

& python manage.py verify_kb_exports --formats $Formats --strict
if ($LASTEXITCODE -ne 0) {
  throw "KB export verification failed for formats: $Formats"
}

Write-Host "KB export verification passed for formats: $Formats"
