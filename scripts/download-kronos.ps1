# Download Kronos weights with PowerShell (more reliable than Python HF client on some Windows networks).
param(
  [ValidateSet("base", "small")]
  [string]$Model = "base"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Root "apps\inference\models"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Get-HfFile($Repo, $File, $Dest) {
  $url = "https://huggingface.co/$Repo/resolve/main/$File"
  Write-Host "Downloading $Repo/$File ..."
  Invoke-WebRequest -Uri $url -OutFile $Dest -UseBasicParsing
  Write-Host "  -> $Dest"
}

$tokDir = Join-Path $Out "Kronos-Tokenizer-base"
$modelDir = Join-Path $Out "Kronos-$Model"
New-Item -ItemType Directory -Force -Path $tokDir, $modelDir | Out-Null

# Configs (also vendored under apps/inference/configs)
Copy-Item (Join-Path $Root "apps\inference\configs\NeoQuasar_Kronos-Tokenizer-base.json") (Join-Path $tokDir "config.json") -Force
Copy-Item (Join-Path $Root "apps\inference\configs\NeoQuasar_Kronos-$Model.json") (Join-Path $modelDir "config.json") -Force

Get-HfFile "NeoQuasar/Kronos-Tokenizer-base" "model.safetensors" (Join-Path $tokDir "model.safetensors")
Get-HfFile "NeoQuasar/Kronos-$Model" "model.safetensors" (Join-Path $modelDir "model.safetensors")

Write-Host ""
Write-Host "Done. Models are in $Out"
Write-Host "Restart inference: .\scripts\dev.ps1 inference"
