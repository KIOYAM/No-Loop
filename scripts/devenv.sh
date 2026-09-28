#!/usr/bin/env bash
# No_Loop developer environment bootstrap (bash / Git Bash on Windows).
# Sets ALL env vars from ENVIRONMENT.md section 2 - nothing on C:, ever (R-ENV-2).
# Usage:  source scripts/devenv.sh

export NOLOOP_DEV=1

# Project root (this script lives in <root>/scripts/)
export NOLOOP_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# All caches redirected to D: (never C:\Users\...\AppData)
mkdir -p /d/DevCache/pip /d/DevCache/uv /d/DevCache/ms-playwright
export PIP_CACHE_DIR="D:/DevCache/pip"
export UV_CACHE_DIR="D:/DevCache/uv"
export PLAYWRIGHT_BROWSERS_PATH="D:/DevCache/ms-playwright"

# Local AI / model caches (only relevant if the developer opts in)
mkdir -p /d/DevCache/huggingface /d/DevCache/ollama-models
export HF_HOME="D:/DevCache/huggingface"
export OLLAMA_MODELS="D:/DevCache/ollama-models"

# App data during development stays inside the project on D:
export NOLOOP_DATA_DIR="$NOLOOP_PROJECT_ROOT/.local-data"
mkdir -p "$NOLOOP_DATA_DIR"

# Use the project venv python for plain `python` in this shell
export PATH="$NOLOOP_PROJECT_ROOT/.venv/Scripts:$PATH"

echo "No_Loop dev environment ready."
echo "  project root : $NOLOOP_PROJECT_ROOT"
echo "  data dir     : $NOLOOP_DATA_DIR"
echo "  pip cache    : $PIP_CACHE_DIR"
echo 'Verify venv   : python -c "import sys; print(sys.executable)"'
