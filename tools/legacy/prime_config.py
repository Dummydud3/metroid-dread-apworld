# Prime 1 settings taken from a working multiworld.
import json
import os


def load_complete_prime_config():
    """Load the complete Prime 1 configuration from the extracted file."""
    path = os.path.join(os.path.dirname(__file__), "prime_config_complete.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Keep settings here so the preset helper needs no extra file.
COMPLETE_PRIME_CONFIG = None  # Read the settings on first use.

def get_embedded_prime_config():
    """Get the complete Prime config, loading it once and caching."""
    global COMPLETE_PRIME_CONFIG
    if COMPLETE_PRIME_CONFIG is None:
        try:
            COMPLETE_PRIME_CONFIG = load_complete_prime_config()
        except:
            # Use basic settings if the full file is missing.
            COMPLETE_PRIME_CONFIG = {}
    return COMPLETE_PRIME_CONFIG
