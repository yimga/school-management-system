# Wave 9 Agent P (v3.58.x) — Windows test runner that sidesteps the
# documented v3.54.0+ file-backed SQLite test-DB lock by pivoting to
# in-memory SQLite via config/settings_test.py. Operators run this
# instead of `manage.py test` directly on Windows.
#
# Usage:
#   .\scripts\run_tests_windows.ps1                    # full pytest suite
#   .\scripts\run_tests_windows.ps1 apps/schoolops/    # one app
#   .\scripts\run_tests_windows.ps1 -ExtraArgs '-x -v' apps/siteconfig/tests/test_cockpit_platform_pulse_service.py
#
# The script:
#   1. Resolves the repo root from its own location (works regardless of cwd).
#   2. Sets DJANGO_SETTINGS_MODULE to the in-memory test settings.
#   3. Sets the in-memory SQLite flags read by config/settings.py.
#   4. Best-effort cleans stale journal files from .django_test_dbs/
#      (they trip the conftest.py journal-probe and force a fresh build).
#   5. Invokes pytest with the rest of the arguments.
#
# No interactive prompts (Read-Host is intentionally avoided so this
# script is safe inside non-interactive tool runners).

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $TestPaths = @(),

    [string] $ExtraArgs = ""
)

$ErrorActionPreference = "Stop"

# Resolve repo root (this script lives in <root>/scripts/).
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "[run_tests_windows] repo root: $RepoRoot"

# --- Env flags: route to in-memory SQLite test settings -----------------
$env:DJANGO_SETTINGS_MODULE = "config.settings_test"
$env:RMC_SQLITE_TEST_MEMORY = "1"
$env:RMC_SQLITE_TEST_USE_MEMORY_NAME = "1"
$env:RMC_RUNNING_TESTS = "1"
$env:PYTHONUNBUFFERED = "1"
# Silence verbose Django logging during the test run.
$env:DJANGO_LOG_LEVEL = "CRITICAL"

Write-Host "[run_tests_windows] DJANGO_SETTINGS_MODULE=$($env:DJANGO_SETTINGS_MODULE)"
Write-Host "[run_tests_windows] in-memory SQLite: RMC_SQLITE_TEST_USE_MEMORY_NAME=$($env:RMC_SQLITE_TEST_USE_MEMORY_NAME)"

# --- Best-effort: clean stale SQLite journal/wal/shm files --------------
# Stale journal files next to .django_test_dbs/default.sqlite3 trip
# conftest.py's _sqlite_keepdb_needs_fresh_start() and force every run
# to be a fresh 845-migration build. With in-memory settings this is
# moot, but cleaning them up keeps file-backed runs healthy too.
$TestDbDir = Join-Path $RepoRoot ".django_test_dbs"
if (Test-Path $TestDbDir) {
    $stale = Get-ChildItem -Path $TestDbDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '\.(sqlite3-journal|sqlite3-wal|sqlite3-shm)$' }
    foreach ($f in $stale) {
        try {
            Remove-Item -Path $f.FullName -Force -ErrorAction Stop
            Write-Host "[run_tests_windows] removed stale: $($f.Name)"
        } catch {
            Write-Host "[run_tests_windows] skip locked: $($f.Name)"
        }
    }
}

# --- Build pytest argv --------------------------------------------------
$argv = @()
if ($TestPaths -and $TestPaths.Count -gt 0) {
    $argv += $TestPaths
}
if ($ExtraArgs -and $ExtraArgs.Trim() -ne "") {
    # Split on whitespace; for complex quoted args pass via TestPaths.
    $argv += ($ExtraArgs -split '\s+')
}

Write-Host "[run_tests_windows] invoking: python -m pytest $($argv -join ' ')"

# Use call operator to avoid issues with -m arg.
& python -m pytest @argv
$exit = $LASTEXITCODE

Write-Host "[run_tests_windows] pytest exit code: $exit"
exit $exit
