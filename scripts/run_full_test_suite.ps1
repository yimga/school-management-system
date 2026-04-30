# Full test suite: reset, unique DB path, serial runner, stall guard (Windows).
param(
    [string[]] $TestArgs = @()
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ($env:SKIP_RESET -ne "1") {
    if ($env:RESET_KILL_MANAGE_PY -eq "1") {
        & "$Root\scripts\reset_test_environment.ps1" -KillManagePy
    } else {
        & "$Root\scripts\reset_test_environment.ps1"
    }
}

$env:RMC_RELIABLE_TEST_RUNNER = if ($env:RMC_RELIABLE_TEST_RUNNER) { $env:RMC_RELIABLE_TEST_RUNNER } else { "1" }
$dbPath = & python "$Root\scripts\generate_test_db_path.py"
$env:DJANGO_TEST_DB_FILE = $dbPath
if (-not $env:PYTHONUNBUFFERED) { $env:PYTHONUNBUFFERED = "1" }

Write-Host "run_full_test_suite: DJANGO_TEST_DB_FILE=$dbPath"

$stall = if ($env:RMC_TEST_STALL_SECONDS) { $env:RMC_TEST_STALL_SECONDS } else { "300" }
$max = if ($env:RMC_TEST_MAX_SECONDS) { $env:RMC_TEST_MAX_SECONDS } else { "0" }

$guardArgs = @(
    "$Root\scripts\run_tests_with_guard.py",
    "--stall-seconds", $stall,
    "--max-seconds", $max,
    "--",
    "python", "manage.py", "test", "--noinput"
) + $TestArgs

& python @guardArgs
exit $LASTEXITCODE
