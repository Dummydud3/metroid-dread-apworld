#!/usr/bin/env bash
# Launch the Dread Client Hub (YAML editor + client / patcher)
set -euo pipefail
cd "$(dirname "$0")"
export SKIP_REQUIREMENTS_UPDATE=1

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js / npm not found. Install Node.js LTS from https://nodejs.org"
  exit 1
fi

ENSURE_SCRIPT="$(cd .. && pwd)/ensure_client_deps.py"
WORLD_DIR="$(cd .. && pwd)"
VENV_DIR="$WORLD_DIR/_metroid_dread_venv"
if [[ -f "$ENSURE_SCRIPT" ]]; then
  echo "Checking Python client dependencies..."
  echo "Linux: packages install into local venv: $VENV_DIR"
  runner=""
  # Prefer an existing Hub venv if present.
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    runner="$VENV_DIR/bin/python"
    echo "Using venv Python: $runner"
  else
    for py in python3.12 python3.11 python3.13 python3 python; do
      if command -v "$py" >/dev/null 2>&1; then
        runner=$py
        break
      fi
    done
  fi
  if [[ -z "$runner" ]]; then
    echo
    echo "No usable Python 3.11–3.13 found for the Hub client."
    echo "Archipelago Text Client uses its own bundled Python — Hub needs a system install."
    echo "Install Python 3.12 (Arch: pacman -S python), then re-run this launcher."
    echo "Client deps will be installed into $VENV_DIR (not systemwide)."
    exit 2
  fi
  set +e
  "$runner" "$ENSURE_SCRIPT" --world "$WORLD_DIR"
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo
    echo "Python client dependency check failed (exit $rc)."
    echo "Hub Connect will also retry — ensure python -m venv works, then re-run."
    echo "Deps are installed into $VENV_DIR only (never systemwide / pip --user)."
    exit "$rc"
  fi
  echo
fi

if [[ ! -d node_modules/electron ]]; then
  echo "Installing Electron dependencies..."
  npm install
fi

if [[ ! -d node_modules/adm-zip ]]; then
  echo "Installing missing packages..."
  npm install
fi

# Auto-repair incomplete Electron binary install.
need_repair=0
if [[ ! -f node_modules/electron/path.txt ]]; then
  need_repair=1
elif [[ ! -f node_modules/electron/dist/electron ]] && \
     [[ ! -f node_modules/electron/dist/electron.exe ]] && \
     [[ ! -f "node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" ]]; then
  need_repair=1
fi
if [[ "$need_repair" -eq 1 ]]; then
  echo "Electron binary missing or incomplete — repairing..."
  rm -rf node_modules/electron
  npm install
fi

exec npm start
