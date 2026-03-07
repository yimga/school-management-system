# Pre-commit test gate: Django check + full test suite.
# Requires: virtualenv with project dependencies installed (pip install -r requirements.txt).
# Run with venv activated:  .\scripts\run_tests_pre_commit.ps1
# From repo root:          & .\scripts\run_tests_pre_commit.ps1
$ErrorActionPreference = "Stop"
$root = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }
if (-not (Test-Path (Join-Path $root "manage.py"))) {
    $root = (Get-Location).Path
}
Set-Location $root

# Use py -3 if python is not available (e.g. Windows Store stub only)
$python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py -3" }

Write-Host "[run_tests_pre_commit] Django check" -ForegroundColor Cyan
& $python manage.py check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[run_tests_pre_commit] Full test suite (parallel 4)..." -ForegroundColor Cyan
& $python manage.py test --verbosity=1 --parallel 4
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[run_tests_pre_commit] PASSED" -ForegroundColor Green
exit 0
