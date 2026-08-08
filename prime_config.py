# Complete Prime 1 configuration extracted from working multiworld
# This is the FULL configuration from a real Randovania Prime 1 multiworld preset
import json
import os


def load_complete_prime_config():
    """Load the complete Prime 1 configuration from the extracted file."""
    path = os.path.join(os.path.dirname(__file__), "prime_config_complete.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# For embedding directly in preset_generator.py without external file dependency
COMPLETE_PRIME_CONFIG = None  # Will be loaded on first use

def get_embedded_prime_config():
    """Get the complete Prime config, loading it once and caching."""
    global COMPLETE_PRIME_CONFIG
    if COMPLETE_PRIME_CONFIG is None:
        try:
            COMPLETE_PRIME_CONFIG = load_complete_prime_config()
        except:
            # Fallback if file not found - use minimal config
            COMPLETE_PRIME_CONFIG = {}
    return COMPLETE_PRIME_CONFIG
