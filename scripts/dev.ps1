# One-time setup + simple start scripts for local Windows.

param(
  [ValidateSet("all", "infra", "inference", "trader", "dashboard")]
  [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-PythonLauncher {
  foreach ($ver in @("3.12", "3.11", "3.13", "3.10")) {
    try {
      $p = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $p) {
        if ($p -is [array]) { return [string]$p[-1] }
        return [string]$p.Trim()
      }
    } catch {}
  }
  return [string](Get-Command python).Source
}

function Ensure-Venv([string]$AppDir) {
  $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    $launcher = Get-PythonLauncher
    Write-Host "Creating venv in $AppDir with $launcher ..."
    $p = Start-Process -FilePath $launcher -ArgumentList @("-m", "venv", (Join-Path $AppDir ".venv")) -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -ne 0) { throw "Failed to create venv" }
  }
  if (-not (Test-Path $venvPython)) { throw "venv python missing: $venvPython" }
  return $venvPython
}

function Invoke-VenvPip([string]$PyPath, [string[]]$PipArgs, [string]$LogPath) {
  $allArgs = @("-m", "pip") + $PipArgs
  $p = Start-Process -FilePath $PyPath -ArgumentList $allArgs -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput $LogPath -RedirectStandardError "$LogPath.err"
  Get-Content $LogPath, "$LogPath.err" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
  if ($p.ExitCode -ne 0) {
    throw "pip failed (exit $($p.ExitCode)). See $LogPath"
  }
}

function Ensure-Pip([string]$AppDir) {
  # Capture only the path (Start-Process avoids pipeline pollution from pip stdout)
  $pyPath = Ensure-Venv $AppDir
  $req = Join-Path $AppDir "requirements.txt"
  $marker = Join-Path $AppDir ".venv\.deps-ok"
  $reqHash = (Get-FileHash $req -Algorithm SHA256).Hash
  $needInstall = $true
  if (Test-Path $marker) {
    $prev = Get-Content $marker -Raw -ErrorAction SilentlyContinue
    if ($prev.Trim() -eq $reqHash) { $needInstall = $false }
  }
  if ($needInstall) {
    Write-Host "Installing $AppDir deps (this can take several minutes) ..."
    $log = Join-Path $AppDir ".venv\pip-install.log"
    # ensurepip via Start-Process too
    $ep = Start-Process -FilePath $pyPath -ArgumentList @("-m", "ensurepip", "--upgrade") -Wait -PassThru -NoNewWindow
    Invoke-VenvPip $pyPath @("install", "--upgrade", "pip", "setuptools", "wheel") $log
    Invoke-VenvPip $pyPath @("install", "-r", $req) $log
    Set-Content -Path $marker -Value $reqHash -NoNewline
    Write-Host "Deps installed for $AppDir"
  } else {
    Write-Host "Deps already installed for $AppDir"
  }
  return $pyPath
}

switch ($Target) {
  "infra" {
    docker compose -f infra/docker-compose.yml --env-file .env up postgres redis -d
    Write-Host "Postgres :5433  Redis :6379"
  }
  "inference" {
    $py = Ensure-Pip (Join-Path $Root "apps\inference")
    Set-Location (Join-Path $Root "apps\inference")
    Write-Host "Starting inference with $py"
    & $py run.py
  }
  "trader" {
    $py = Ensure-Pip (Join-Path $Root "apps\trader")
    Set-Location (Join-Path $Root "apps\trader")
    Write-Host "Starting trader with $py"
    & $py run.py
  }
  "dashboard" {
    npx pnpm@11.18.0 --filter @kronos/dashboard dev
  }
  "all" {
    Write-Host "Kronos local run - open THREE terminals:"
    Write-Host "  .\scripts\dev.ps1 infra"
    Write-Host "  .\scripts\dev.ps1 inference"
    Write-Host "  .\scripts\dev.ps1 trader"
    Write-Host "  .\scripts\dev.ps1 dashboard"
    Write-Host "Dashboard: http://localhost:3033"
    docker compose -f infra/docker-compose.yml --env-file .env up postgres redis -d
  }
}
