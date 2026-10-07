#!/usr/bin/env python3

"""Quick launcher for Metroid Bread Seed Manager"""



import sys

import os



# Require Python 3.10 or newer.

if sys.version_info < (3, 10):

    print(f"ERROR: Python 3.10+ required (you have {sys.version_info.major}.{sys.version_info.minor})")

    sys.exit(1)



# Check that tkinter is installed.

try:

    import tkinter

except ImportError:

    print("ERROR: tkinter not found!")

    print("On Ubuntu/Debian: sudo apt-get install python3-tk")

    print("On Fedora: sudo dnf install python3-tkinter")

    sys.exit(1)



# Check PyYAML and install it if missing.

try:

    import yaml

except ImportError:

    print("Installing PyYAML...")

    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])

    import yaml



# Use the script folder as the working folder.

os.chdir(os.path.dirname(os.path.abspath(__file__)))



# Load and start the GUI.

from DreadSeedManager import main



if __name__ == "__main__":

    main()

