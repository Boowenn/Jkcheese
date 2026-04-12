$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name Jkcheese `
  --paths $repoRoot `
  main.py

Write-Host "Built dist\\Jkcheese.exe"
