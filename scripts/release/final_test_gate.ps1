$ErrorActionPreference = "Stop"

Write-Host "[Phase 15] Running Django system checks..."
python manage.py check

Write-Host "[Phase 15] Verifying migrations are in sync..."
python manage.py makemigrations --check --dry-run

$testModules = @(
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
python manage.py test $testModules --verbosity 1

Write-Host "[Phase 15] Final gate passed."
