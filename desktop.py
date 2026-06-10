"""
desktop.py — OS-detecting dispatcher for the POS desktop application.

Automatically picks the correct platform launcher:
  - Windows → windows/desktop.py
  - Linux   → ubuntu/desktop.py

Usage:
    python3 desktop.py          # Auto-detect OS and start
    python3 desktop.py --tray   # Start minimized (future)
"""

import sys
import os
import platform

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

system = platform.system()
if system == "Windows":
    entry = os.path.join(PROJECT_DIR, "windows", "desktop.py")
elif system == "Linux":
    entry = os.path.join(PROJECT_DIR, "ubuntu", "desktop.py")
else:
    print(f"Unsupported platform: {system}", file=sys.stderr)
    sys.exit(1)

if not os.path.exists(entry):
    print(f"Platform launcher not found: {entry}", file=sys.stderr)
    sys.exit(1)

# Delegate to platform-specific launcher, passing all CLI args
import runpy
sys.path.insert(0, PROJECT_DIR)
runpy.run_path(entry, run_name="__main__")
