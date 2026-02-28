param(
    [string]$ProjectRoot = "",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonPath = $venvPython
    } else {
        $PythonPath = "python"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $ProjectRoot "backups\phase0"
$dbBackupDir = Join-Path $backupRoot "db"
$configBackupDir = Join-Path $backupRoot "ui_config"

New-Item -ItemType Directory -Force -Path $dbBackupDir | Out-Null
New-Item -ItemType Directory -Force -Path $configBackupDir | Out-Null

$dbPath = Join-Path $ProjectRoot "db_working.sqlite3"
if (Test-Path $dbPath) {
    $dbTarget = Join-Path $dbBackupDir ("db_working_" + $timestamp + ".sqlite3")
    Copy-Item -Path $dbPath -Destination $dbTarget -Force
    Write-Host "DB snapshot created: $dbTarget"
} else {
    Write-Host "DB snapshot skipped: db_working.sqlite3 not found"
}

$managePy = Join-Path $ProjectRoot "manage.py"
if (-not (Test-Path $managePy)) {
    throw "manage.py not found at $managePy"
}

$configTarget = Join-Path $configBackupDir ("ui_config_" + $timestamp + ".json")
& $PythonPath $managePy export_ui_config --output $configTarget
if ($LASTEXITCODE -ne 0) {
    throw "export_ui_config failed"
}
Write-Host "UI config snapshot created: $configTarget"

$metaFile = Join-Path $backupRoot ("snapshot_meta_" + $timestamp + ".txt")
@(
    "timestamp=$timestamp"
    "project_root=$ProjectRoot"
    "python_path=$PythonPath"
    "db_path=$dbPath"
    "ui_config_path=$configTarget"
) | Set-Content -Path $metaFile -Encoding UTF8

Write-Host "Phase 0 baseline snapshot complete."
