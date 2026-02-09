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

Write-Host "[Phase 15] Running Django system checks..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "check")

Write-Host "[Phase 15] Verifying migrations are in sync..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "makemigrations", "--check", "--dry-run")

Write-Host "[Phase 15] Verifying UI parity fixture matches DB..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "check_ui_parity", "--input-file", "fixtures/ui_config.json", "--strict")

Write-Host "[Phase 15] Verifying KB exports (ODT + DOCX) are present..."
Invoke-StrictCommand -CommandParts @("python", "manage.py", "verify_kb_exports", "--formats", "odt,docx", "--strict")

$testModules = @(
  "apps.portal.tests.test_verify_kb_exports_command",
  "apps.portal.tests.test_generate_kb_odt_command",
  "apps.siteconfig.tests.test_theme_studio",
  "apps.siteconfig.tests.test_preview",
  "apps.siteconfig.tests.test_reportcard_builder",
  "apps.siteconfig.tests.test_redirect_safety",
  "apps.siteconfig.tests.test_admin_ui_smoke",
  "apps.requests.tests.test_views_security",
  "apps.accounts.tests.test_mfa_redirect_safety",
  "apps.reports.tests.test_publish_term"
)

Write-Host "[Phase 15] Running targeted regression suite..."
Invoke-StrictCommand -CommandParts (@("python", "manage.py", "test") + $testModules + @("--verbosity", "1"))

Write-Host "[Phase 15] Final gate passed."
