#!/bin/bash
# Metroid Bread Seed Manager Launcher (Linux/Mac)
# Python deps go into a local venv (never systemwide / pip --user).

set -euo pipefail

echo "===================================="
echo "Metroid Bread Seed Manager"
echo "===================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/_metroid_bread_venv"
VENV_PY="$VENV_DIR/bin/python"

pick_base_python() {
  for py in python3.12 python3.11 python3.13 python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

if [[ -x "$VENV_PY" ]]; then
  PYTHON="$VENV_PY"
  echo "Using venv Python: $PYTHON"
else
  if ! BASE="$(pick_base_python)"; then
    echo "ERROR: Python 3 not found!"
    echo "Please install Python 3.11–3.13 (Arch: pacman -S python)."
    exit 1
  fi
  echo "Creating local venv at $VENV_DIR (deps will not be installed systemwide)..."
  "$BASE" -m venv --system-site-packages "$VENV_DIR"
  PYTHON="$VENV_PY"
  echo "Using venv Python: $PYTHON"
fi

if ! "$PYTHON" -c "import yaml" 2>/dev/null; then
  echo "Installing required dependency into venv: PyYAML..."
  "$PYTHON" -m pip install pyyaml
fi

echo "Launching Seed Manager GUI..."
echo ""

set +e
"$PYTHON" DreadSeedManager.py
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  echo ""
  echo "GUI closed with error"
  read -r -p "Press Enter to continue..."
fi
