param(
    [ValidateSet("export", "import", "normalize", "roundtrip")]
    [string]$Mode = "roundtrip",
    [string]$ProjectRoot = "",
    [string]$PythonPath = "",
    [string]$ConfigPath = "",
    [switch]$SkipNormalize
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

$managePy = Join-Path $ProjectRoot "manage.py"
if (-not (Test-Path $managePy)) {
    throw "manage.py not found at $managePy"
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $ProjectRoot "fixtures\ui_config.json"
}

function Run-Manage([string[]]$CommandArgs) {
    & $PythonPath $managePy @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py command failed: $($CommandArgs -join ' ')"
    }
}

switch ($Mode) {
    "export" {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConfigPath) | Out-Null
        Run-Manage ("export_ui_config", "--output", $ConfigPath)
        Write-Host "Exported UI config to $ConfigPath"
    }
    "import" {
        if (-not (Test-Path $ConfigPath)) {
            throw "Config file not found: $ConfigPath"
        }
        Run-Manage ("import_ui_config", $ConfigPath)
        if (-not $SkipNormalize) {
            Run-Manage ("normalize_ui_config")
        }
        Write-Host "Imported UI config from $ConfigPath"
    }
    "normalize" {
        Run-Manage ("normalize_ui_config")
        Write-Host "Normalized UI config."
    }
    "roundtrip" {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConfigPath) | Out-Null
        Run-Manage ("export_ui_config", "--output", $ConfigPath)
        Run-Manage ("import_ui_config", $ConfigPath)
        if (-not $SkipNormalize) {
            Run-Manage ("normalize_ui_config")
        }
        Write-Host "Roundtrip export/import complete: $ConfigPath"
    }
}
