$ErrorActionPreference = "Stop"
# Some manage.py commands emit DEBUG lines to stderr; treat exit code as source of truth.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

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

Write-Host "[powerhouse_wave0] Django check"
Invoke-StrictCommand -CommandParts @("python", "manage.py", "check")

Write-Host "[powerhouse_wave0] Migrations check"
Invoke-StrictCommand -CommandParts @("python", "manage.py", "makemigrations", "--check", "--dry-run")

Write-Host "[powerhouse_wave0] Tenant model audit"
Invoke-StrictCommand -CommandParts @("python", "manage.py", "audit_tenant_models", "--strict")

Write-Host "[powerhouse_wave0] RBAC and smoke targeted suite"
$testModules = @(
  "apps.accounts.tests.test_smoke_urls",
  "apps.siteconfig.tests.test_admin_ui_smoke",
  "apps.api.tests.test_dashboard_api_rbac",
  "apps.requests.tests.test_views_security",
  "apps.accounts.tests.test_mfa_redirect_safety"
)
Invoke-StrictCommand -CommandParts (@("python", "manage.py", "test") + $testModules + @("-v", "1"))

$wave0DbFileUserSet = $false
if ($env:POWERHOUSE_WAVE0_DB_FILE) {
  $wave0DbFile = $env:POWERHOUSE_WAVE0_DB_FILE
  $wave0DbFileUserSet = $true
} else {
  $baseDir = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "GileadTechHigh"
  } else {
    [System.IO.Path]::GetTempPath()
  }
  $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $wave0DbFile = Join-Path $baseDir ("wave0_gate_{0}_{1}.sqlite3" -f $PID, $timestamp)
}
$wave0DbDir = Split-Path -Parent $wave0DbFile
if (-not (Test-Path $wave0DbDir)) {
  New-Item -ItemType Directory -Path $wave0DbDir -Force | Out-Null
}
if (Test-Path $wave0DbFile) {
  Remove-Item $wave0DbFile -Force
}

$originalDbFile = $env:DB_FILE
$env:DB_FILE = $wave0DbFile

try {
  Write-Host "[powerhouse_wave0] Bootstrap isolated DB for compliance checks"
  Invoke-StrictCommand -CommandParts @("python", "manage.py", "migrate", "--noinput")

  Write-Host "[powerhouse_wave0] Seed compliance baseline"
  Invoke-StrictCommand -CommandParts @("python", "manage.py", "seed_compliance_baseline")

  Write-Host "[powerhouse_wave0] Compliance auditor strict pass"
  Invoke-StrictCommand -CommandParts @("python", "manage.py", "compliance_auditor", "--strict", "--min-score", "70")

  Write-Host "[powerhouse_wave0] Access-control consistency scan"
  $acOutput = & python manage.py verify_access_control
  if ($LASTEXITCODE -ne 0) {
    throw "verify_access_control returned non-zero exit status: ${LASTEXITCODE}"
  }
  Write-Output $acOutput
  if ($acOutput -match "Issues found: [1-9][0-9]*") {
    throw "verify_access_control reported unresolved issues"
  }
} finally {
  $env:DB_FILE = $originalDbFile
  if (-not $wave0DbFileUserSet -and (Test-Path $wave0DbFile)) {
    Remove-Item $wave0DbFile -Force -ErrorAction SilentlyContinue
  }
}

Write-Host "[powerhouse_wave0] Render startup command sanity"
if (-not (Select-String -Path "render.yaml" -Pattern "render_start_web.sh" -Quiet)) {
  throw "render.yaml must reference scripts/release/render_start_web.sh"
}
if (-not (Select-String -Path "Procfile" -Pattern "render_start_web.sh" -Quiet)) {
  throw "Procfile must reference scripts/release/render_start_web.sh"
}

Write-Host "[powerhouse_wave0] PASSED"
