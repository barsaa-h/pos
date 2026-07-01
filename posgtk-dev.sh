#!/bin/bash
# Launch the GTK app directly for local visual testing
set -euo pipefail

cd "$(dirname "$0")"

echo "=== POS GTK Desktop ==="
echo "Launching GTK app... (make sure you're on a graphical session)"
echo ""

# Use system Python (not venv) — GTK app needs system gi (PyGObject)
POS_SKIP_MODULE_INIT=1 /usr/bin/python3 -m posgtk.main "$@"
