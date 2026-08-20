#!/usr/bin/env python3
"""
Quick launcher for Metroid Bread Seed Manager
Cross-platform Python 3 launcher
"""

import sys
import os

# Ensure Python 3.10+
if sys.version_info < (3, 10):
    print(f"ERROR: Python 3.10+ required (you have {sys.version_info.major}.{sys.version_info.minor})")
    sys.exit(1)

# Check for tkinter
try:
    import tkinter
except ImportError:
    print("ERROR: tkinter not found!")
    print("On Ubuntu/Debian: sudo apt-get install python3-tk")
    print("On Fedora: sudo dnf install python3-tkinter")
    sys.exit(1)

# Check/install PyYAML
try:
    import yaml
except ImportError:
    print("Installing PyYAML...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml

# Change to script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import and run
from DreadSeedManager import main

if __name__ == "__main__":
    main()
