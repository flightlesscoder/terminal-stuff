#!/usr/bin/env bash
# Launcher for the setup TUI (Python 3.8+, stdlib only). See setup/tui/ and README.md.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 exec "$py" -m tui "$@"
  fi
done
echo "setup.sh: Python 3.8+ is required (try: brew install python  /  sudo apt install python3)" >&2
exit 1
