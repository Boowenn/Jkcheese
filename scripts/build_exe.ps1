$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (Test-Path ".\requirements.txt") {
  python -m pip install -r .\requirements.txt
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name Jkcheese `
  --paths $repoRoot `
  main.py

Write-Host "Built dist\\Jkcheese.exe"
