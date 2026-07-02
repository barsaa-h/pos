#!/bin/bash
# Launch the GTK app directly for local visual testing
set -euo pipefail

cd "$(dirname "$0")"

echo "=== POS GTK Desktop ==="
echo "Launching GTK app... (make sure you're on a graphical session)"
echo ""

# Use system Python (not venv) — GTK app needs system gi (PyGObject)
/usr/bin/python3 -m posgtk.main "$@"
