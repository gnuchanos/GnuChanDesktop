#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX=${PREFIX:-/usr/local}
DESTDIR=${DESTDIR:-}
BIN_DIR="$DESTDIR$PREFIX/bin"
APP_DIR="$DESTDIR${APP_DIR:-/usr/share/applications}"
mkdir -p "$BIN_DIR" "$APP_DIR"
install -m 755 "$ROOT/gnuchan_desktop_panel.py" "$BIN_DIR/gnuchan-desktop-panel"
install -m 644 "$ROOT/gnuchan-desktop-panel.desktop" "$APP_DIR/gnuchan-desktop-panel.desktop"
ln -sf gnuchan-desktop-panel "$BIN_DIR/GnuChanDesktop"
sed -i 's/\r$//' "$BIN_DIR/gnuchan-desktop-panel" \
    "$APP_DIR/gnuchan-desktop-panel.desktop"
echo "Installed GnuChan Desktop panel to $BIN_DIR"
echo "Runtime requirements: Python 3 with Tk, xrandr, and feh (for wallpaper)."
