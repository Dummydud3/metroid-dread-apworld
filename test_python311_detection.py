#!/usr/bin/env python3
"""
Test Python 3.11 Detection and Subprocess Execution
Verifies the GUI's Python version detection works correctly
"""

import sys
import subprocess
from pathlib import Path

def find_python_311():
    """Same detection logic as DreadSeedManager.py"""
    candidates = []
    
    if sys.platform == "win32":
        for minor in range(13, 10, -1):
            candidates.append(["py", f"-3.{minor}"])
        candidates.append(["py", "-3"])
    
    for minor in range(13, 10, -1):
        candidates.append([f"python3.{minor}"])
    
    candidates.append(["python3"])
    candidates.append(["python"])
    
    for cmd_list in candidates:
        try:
            result = subprocess.run(
                cmd_list + ["--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version_str = result.stdout or result.stderr
                if "Python 3." in version_str:
                    version_part = version_str.split("Python 3.")[1].split()[0]
                    minor = int(version_part.split(".")[0])
                    
                    if minor >= 11:
                        return cmd_list, version_str.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
            continue
    
    return None, None

def main():
    print("=" * 60)
    print("Python 3.11+ Detection Test")
    print("=" * 60)
    print()
    
    # Show current Python
    print(f"Current Python (running this script):")
    print(f"  Version: {sys.version}")
    print(f"  Executable: {sys.executable}")
    print()
    
    # Test detection
    print("Searching for Python 3.11+...")
    cmd, version = find_python_311()
    
    if cmd:
        print(f"[OK] Found: {' '.join(cmd)}")
        print(f"  Version: {version}")
        print()
        
        # Test subprocess call
        print("Testing subprocess execution...")
        try:
            test_script = Path(__file__).parent / "test_import.py"
            
            # Create temporary test script
            test_script.write_text("""
import sys
print(f"Subprocess Python: {sys.version}")
print(f"Version info: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# Check if this is Python 3.11+
if sys.version_info >= (3, 11):
    print("[OK] Python 3.11+ confirmed!")
    sys.exit(0)
else:
    print("[FAIL] Python version too old")
    sys.exit(1)
""")
            
            result = subprocess.run(
                cmd + [str(test_script)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            print(result.stdout)
            
            if result.returncode == 0:
                print("[OK] Subprocess test passed!")
            else:
                print("[FAIL] Subprocess test failed!")
                print(result.stderr)
            
            # Clean up
            test_script.unlink()
            
        except Exception as e:
            print(f"[FAIL] Subprocess test error: {e}")
    else:
        print("[FAIL] Python 3.11+ not found!")
        print()
        print("Please install Python 3.11 or newer:")
        print("  - Windows: Download from python.org")
        print("  - Ubuntu/Debian: sudo apt install python3.11")
        print("  - Mac: brew install python@3.11")
        return 1
    
    print()
    print("=" * 60)
    print("Test Complete")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
