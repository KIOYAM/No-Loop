# No_Loop developer environment bootstrap (Windows PowerShell).
# Sets ALL env vars from ENVIRONMENT.md section 2 - nothing on C:, ever (R-ENV-2).
# Usage:  . scripts/devenv.ps1

$env:NOLOOP_DEV = "1"

# Project root (this script lives in <root>/scripts/)
$env:NOLOOP_PROJECT_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# All caches redirected to D: (never C:\Users\...\AppData)
New-Item -ItemType Directory -Force -Path "D:\DevCache\pip" | Out-Null
New-Item -ItemType Directory -Force -Path "D:\DevCache\uv" | Out-Null
New-Item -ItemType Directory -Force -Path "D:\DevCache\ms-playwright" | Out-Null
$env:PIP_CACHE_DIR = "D:\DevCache\pip"
$env:UV_CACHE_DIR = "D:\DevCache\uv"
$env:PLAYWRIGHT_BROWSERS_PATH = "D:\DevCache\ms-playwright"

# Local AI / model caches (only relevant if the developer opts in)
New-Item -ItemType Directory -Force -Path "D:\DevCache\huggingface" | Out-Null
$env:HF_HOME = "D:\DevCache\huggingface"
New-Item -ItemType Directory -Force -Path "D:\DevCache\ollama-models" | Out-Null
$env:OLLAMA_MODELS = "D:\DevCache\ollama-models"

# App data during development stays inside the project on D:
$env:NOLOOP_DATA_DIR = Join-Path $env:NOLOOP_PROJECT_ROOT ".local-data"
New-Item -ItemType Directory -Force -Path $env:NOLOOP_DATA_DIR | Out-Null

# Use the project venv python for plain `python` in this shell
$env:PATH = (Join-Path $env:NOLOOP_PROJECT_ROOT ".venv\Scripts") + ";" + $env:PATH

Write-Host "No_Loop dev environment ready."
Write-Host "  project root : $env:NOLOOP_PROJECT_ROOT"
Write-Host "  data dir     : $env:NOLOOP_DATA_DIR"
Write-Host "  pip cache    : $env:PIP_CACHE_DIR"
Write-Host "Verify venv   : python -c \"import sys; print(sys.executable)\""
