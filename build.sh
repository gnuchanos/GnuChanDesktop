#!/bin/sh
set -eu

if [ "$(uname -s)" != "Linux" ]; then
    echo "Build and tests must run in WSL/Linux." >&2
    exit 1
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
python3 -m py_compile gnuchan_desktop_panel.py tests/test_panel.py
python3 -m unittest discover -s tests -v
python3 gnuchan_desktop_panel.py --version
python3 gnuchan_desktop_panel.py --check-config --config examples/panel.conf
echo "Build and configuration tests passed."
