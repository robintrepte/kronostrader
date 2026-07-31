# One-time setup + simple start scripts for local Windows/macOS/Linux.

param(
  [ValidateSet("all", "infra", "inference", "trader", "dashboard")]
  [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Ensure-Venv($AppDir) {
  $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv in $AppDir ..."
    python -m venv (Join-Path $AppDir ".venv")
  }
  return $venvPython
}

function Ensure-Pip($AppDir) {
  $py = Ensure-Venv $AppDir
  $req = Join-Path $AppDir "requirements.txt"
  Write-Host "Installing $AppDir deps (skip if already done)..."
  & $py -m pip install -q -r $req
  return $py
}

switch ($Target) {
  "infra" {
    docker compose -f infra/docker-compose.yml --env-file .env up postgres redis -d
    Write-Host "Postgres :5432  Redis :6379"
  }
  "inference" {
    $py = Ensure-Pip (Join-Path $Root "apps\inference")
    Set-Location (Join-Path $Root "apps\inference")
    & $py run.py
  }
  "trader" {
    $py = Ensure-Pip (Join-Path $Root "apps\trader")
    Set-Location (Join-Path $Root "apps\trader")
    & $py run.py
  }
  "dashboard" {
    npx pnpm@11.18.0 --filter @kronos/dashboard dev
  }
  "all" {
    Write-Host @"

Kronos local run — open THREE terminals in the repo root and run:

  .\scripts\dev.ps1 infra
  .\scripts\dev.ps1 inference
  .\scripts\dev.ps1 trader
  .\scripts\dev.ps1 dashboard

Or after infra is up, just the last three.

Dashboard: http://localhost:3033
No manual env exports needed — apps read the root .env file.

"@
    docker compose -f infra/docker-compose.yml --env-file .env up postgres redis -d
  }
}
