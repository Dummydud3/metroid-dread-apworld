"""
Metroid Bread icon registration

Registers the launcher icon under the key used by launcher.py (icon="metroid_bread").
Uses the ap: path form so the icon resolves from the world package / apworld.
"""

from worlds.LauncherComponents import icon_paths

# Packaged with the world at data/icon.png (rounded cover art).
icon_paths["metroid_bread"] = f"ap:{__package__}/data/icon.png"
