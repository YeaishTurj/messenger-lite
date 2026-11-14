#!/usr/bin/env bash
# Messenger Lite - Linux Uninstaller
set -e

echo "==> Uninstalling Messenger Lite..."

rm -f "$HOME/.local/bin/messenger-lite"
rm -f "$HOME/.local/share/applications/messenger-lite.desktop"
rm -f "$HOME/.local/share/pixmaps/messenger-lite.svg"
rm -f "$HOME/.local/share/pixmaps/messenger.svg"
rm -f "$HOME/.local/share/messenger-lite/icon.svg"

for theme in hicolor Papirus Papirus-Dark; do
    for size in scalable 16x16 22x22 24x24 32x32 48x48 64x64; do
        rm -f "$HOME/.local/share/icons/$theme/$size/apps/messenger-lite.svg"
        rm -f "$HOME/.local/share/icons/$theme/$size/apps/messenger.svg"
    done
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f "$HOME/.local/share/icons/$theme" 2>/dev/null || true
    fi
done

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications"
fi

echo "==> Messenger Lite uninstalled."
echo "Note: User profile data kept at ~/.local/share/messenger-lite"
