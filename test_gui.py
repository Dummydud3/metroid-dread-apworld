"""
Quick test script for DreadSeedManager GUI

Tests that the GUI can:
1. Launch without errors
2. Load default configuration
3. Save YAML files
4. Get current configuration
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_gui_basic():
    """Test basic GUI functionality without showing window"""
    print("Testing DreadSeedManager...")
    
    # Import after path setup
    from worlds.metroid_bread.DreadSeedManager import DreadSeedManager
    import tkinter as tk
    
    # Create app (but don't run mainloop)
    print("✓ Creating GUI window...")
    app = DreadSeedManager()
    
    # Test loading defaults
    print("✓ Loading default configuration...")
    config = app.load_default_config()
    assert config["game"] == "Metroid Bread"
    assert "Metroid Bread" in config
    
    # Test getting current config
    print("✓ Getting current configuration...")
    current = app.get_current_config()
    assert current["name"] == app.player_name_var.get()
    assert current["game"] == "Metroid Bread"
    
    # Test that all vars are initialized
    print("✓ Checking all variables initialized...")
    assert hasattr(app, 'player_name_var')
    assert hasattr(app, 'goal_var')
    assert hasattr(app, 'progressive_vars')
    assert hasattr(app, 'trick_vars')
    assert hasattr(app, 'item_vars')
    
    # Test YAML save
    print("✓ Testing YAML generation...")
    import tempfile
    import yaml
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        temp_file = f.name
    
    try:
        app.save_yaml_to_file(temp_file)
        print(f"✓ YAML saved to: {temp_file}")
        
        # Verify it can be loaded
        with open(temp_file, 'r') as f:
            loaded = yaml.safe_load(f)
        
        assert loaded["game"] == "Metroid Bread"
        assert "Metroid Bread" in loaded
        print("✓ YAML is valid and loadable")
        
        # Clean up
        Path(temp_file).unlink()
        
    except Exception as e:
        print(f"✗ Error: {e}")
        Path(temp_file).unlink(missing_ok=True)
        raise
    
    # Close window
    app.destroy()
    
    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    try:
        test_gui_basic()
        print("\nGUI is working correctly!")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
