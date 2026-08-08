#!/bin/bash
# Metroid Dread Seed Manager Launcher (Linux/Mac)

echo "===================================="
echo "Metroid Dread Seed Manager"
echo "===================================="
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found!"
    echo "Please install Python 3.10 or newer."
    exit 1
fi

# Check for PyYAML
python3 -c "import yaml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing required dependency: PyYAML..."
    python3 -m pip install pyyaml
fi

# Launch GUI
echo "Launching Seed Manager GUI..."
echo ""

cd "$(dirname "$0")"
python3 DreadSeedManager.py

if [ $? -ne 0 ]; then
    echo ""
    echo "GUI closed with error"
    read -p "Press Enter to continue..."
fi
