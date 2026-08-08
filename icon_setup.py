"""
Metroid Dread icon registration
"""

from worlds.LauncherComponents import icon_paths
from Utils import local_path
import os

# Try to register Metroid Dread icon if it exists
# Expected location: data/metroid_dread_icon.png
icon_file = local_path('data', 'metroid_dread_icon.png')
if os.path.exists(icon_file):
    icon_paths['metroid_dread'] = icon_file
else:
    # Fallback to default icon
    icon_paths['metroid_dread'] = local_path('data', 'icon.png')
