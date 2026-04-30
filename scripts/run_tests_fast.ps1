# Fast repeat: reuse file-backed SQLite test DB (--keepdb). Serial runner.
param(
    [string[]] $TestArgs = @()
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:RMC_RELIABLE_TEST_RUNNER = if ($env:RMC_RELIABLE_TEST_RUNNER) { $env:RMC_RELIABLE_TEST_RUNNER } else { "1" }
if (-not $env:DJANGO_TEST_DB_FILE) {
    $env:DJANGO_TEST_DB_FILE = "$Root\.django_test_dbs\fast_reuse.sqlite3"
}
New-Item -ItemType Directory -Path (Split-Path $env:DJANGO_TEST_DB_FILE) -Force | Out-Null
Write-Host "run_tests_fast: DJANGO_TEST_DB_FILE=$($env:DJANGO_TEST_DB_FILE) (--keepdb)"
& python manage.py test --noinput --keepdb @TestArgs
exit $LASTEXITCODE
