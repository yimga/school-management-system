# Silent Ollama install for operator workstation (RunMyCampus recovery wave).
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    ollama --version
    exit 0
}
$out = Join-Path $env:TEMP "OllamaSetup.exe"
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $out -UseBasicParsing
Start-Process -FilePath $out -ArgumentList "/S" -Wait
$ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
$env:Path = "$ollamaDir;$env:Path"
& "$ollamaDir\ollama.exe" --version
