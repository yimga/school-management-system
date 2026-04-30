# Hard reset local Django test DB dir and Python caches for this repo.
# Optional: stop Python processes whose command line includes this repo + manage.py
param(
    [switch] $KillManagePy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ($KillManagePy -or $env:RESET_KILL_MANAGE_PY -eq "1") {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($Root) -and $_.CommandLine -match "manage\.py" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Get-CimInstance Win32_Process -Filter "Name = 'python3.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($Root) -and $_.CommandLine -match "manage\.py" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

$Dbs = Join-Path $Root ".django_test_dbs"
if (Test-Path $Dbs) {
    Get-ChildItem -Path $Dbs -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $attempt = 0
        while ($attempt -lt 5) {
            try {
                Remove-Item $_.FullName -Recurse -Force -ErrorAction Stop
                break
            } catch {
                $attempt++
                Start-Sleep -Milliseconds (200 * $attempt)
            }
        }
    }
}
New-Item -ItemType Directory -Path $Dbs -Force | Out-Null

Get-ChildItem -Path $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $Root -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "reset_test_environment: OK ($Root)"
