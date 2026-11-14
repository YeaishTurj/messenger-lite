#!/usr/bin/env bash
# Messenger Lite - Linux Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
DATA_DIR="$HOME/.local/share/messenger-lite"
PIXMAPS_DIR="$HOME/.local/share/pixmaps"

echo "==> Installing Messenger Lite..."

mkdir -p "$BIN_DIR" "$APP_DIR" "$DATA_DIR" "$PIXMAPS_DIR"

# Install script
chmod +x "$SCRIPT_DIR/src/messenger-lite.py"
ln -sf "$SCRIPT_DIR/src/messenger-lite.py" "$BIN_DIR/messenger-lite"
cp -f "$SCRIPT_DIR/src/messenger-lite.py" "$DATA_DIR/messenger-lite.py"

# Install official icon in dedicated app dir and pixmaps
cp -f "$SCRIPT_DIR/assets/icon.svg" "$DATA_DIR/icon.svg"
cp -f "$SCRIPT_DIR/assets/icon.svg" "$PIXMAPS_DIR/messenger-lite.svg"
cp -f "$SCRIPT_DIR/assets/icon.svg" "$PIXMAPS_DIR/messenger.svg"

# Install official icon across all common desktop icon themes
for theme in hicolor Papirus Papirus-Dark; do
    for size in scalable 16x16 22x22 24x24 32x32 48x48 64x64; do
        target_dir="$HOME/.local/share/icons/$theme/$size/apps"
        mkdir -p "$target_dir"
        cp -f "$SCRIPT_DIR/assets/icon.svg" "$target_dir/messenger-lite.svg"
        cp -f "$SCRIPT_DIR/assets/icon.svg" "$target_dir/messenger.svg"
    done
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f "$HOME/.local/share/icons/$theme" 2>/dev/null || true
    fi
done

# Install desktop entry
sed "s|Exec=messenger-lite|Exec=$BIN_DIR/messenger-lite|g" \
    "$SCRIPT_DIR/assets/messenger-lite.desktop" > "$APP_DIR/messenger-lite.desktop"
chmod +x "$APP_DIR/messenger-lite.desktop"

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR"
fi

echo "==> Installation complete!"
echo "Official Messenger logo installed across system themes and application launcher."
echo "You can launch it by running: messenger-lite"
