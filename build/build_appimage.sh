#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Battery Lens — Linux AppImage Build Script
#
# Creates a self-contained AppImage from the PyInstaller output.
# The AppImage runs on Ubuntu 20.04+, Fedora 35+, Arch, openSUSE, etc.
#
# Prerequisites (on the build machine, NOT bundled):
#   sudo apt install fuse libfuse2    # Ubuntu/Debian
#   wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
#   chmod +x appimagetool-x86_64.AppImage
#   sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool
#
# Usage:
#   bash build/build_appimage.sh [version]
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION="${1:-$(python3 -c 'from version import __version__; print(__version__)' 2>/dev/null || echo '1.0.0')}"

PYINSTALLER_OUT="$ROOT_DIR/dist/BatteryLens"
APPDIR="$SCRIPT_DIR/BatteryLens.AppDir"
OUTPUT_DIR="$ROOT_DIR/dist"

echo "═══════════════════════════════════════════"
echo " Battery Lens — AppImage Builder v${VERSION}"
echo "═══════════════════════════════════════════"

# ── 1. Verify PyInstaller output exists ──────────────────────────────────────
if [ ! -f "$PYINSTALLER_OUT/BatteryLens" ]; then
    echo ""
    echo "ERROR: PyInstaller output not found at: $PYINSTALLER_OUT/BatteryLens"
    echo "Run first: pyinstaller battery_lens.spec"
    exit 1
fi

# ── 2. Build AppDir structure ─────────────────────────────────────────────────
echo ""
echo "[1/4] Setting up AppDir structure..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# Copy PyInstaller output
cp -r "$PYINSTALLER_OUT/." "$APPDIR/usr/bin/"

# ── 3. Copy icon ──────────────────────────────────────────────────────────────
ICON_SRC="$ROOT_DIR/assets/icon_256.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APPDIR/BatteryLens.png"
    cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/BatteryLens.png"
else
    # Fallback: generate a minimal PNG icon
    python3 -c "
from PIL import Image
img = Image.new('RGBA', (256, 256), (10, 25, 60, 255))
img.save('$APPDIR/BatteryLens.png')
img.save('$APPDIR/usr/share/icons/hicolor/256x256/apps/BatteryLens.png')
"
fi

# ── 4. AppRun launcher ────────────────────────────────────────────────────────
echo "[2/4] Creating AppRun launcher..."
cat > "$APPDIR/AppRun" << 'APPRUN_EOF'
#!/bin/bash
# Battery Lens AppImage launcher
# Checks for required system tray library before launching.

SELF="$(readlink -f "$0")"
HERE="$(dirname "$SELF")"

# ── System tray dependency check ─────────────────────────────────────────────
_HAS_INDICATOR=false
python3 -c "
import gi
try:
    gi.require_version('AppIndicator3','0.1')
    from gi.repository import AppIndicator3
    exit(0)
except Exception:
    pass
try:
    gi.require_version('AyatanaAppIndicator3','0.1')
    from gi.repository import AyatanaAppIndicator3
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null && _HAS_INDICATOR=true

if [ "$_HAS_INDICATOR" = false ]; then
    MSG="Battery Lens needs a system tray library to show its icon.\n\nInstall it with your package manager:\n\n  Ubuntu/Debian:\n  sudo apt install gir1.2-appindicator3-0.1\n\n  Fedora:\n  sudo dnf install libappindicator-gtk3\n\n  Arch/Manjaro:\n  sudo pacman -S libappindicator-gtk3\n\nAfter installing, re-launch Battery Lens."

    # Try graphical error dialog first
    if command -v zenity &>/dev/null; then
        zenity --warning --title="Battery Lens — Setup Required" --width=420 \
               --text="$MSG" 2>/dev/null && exit 1
    elif command -v kdialog &>/dev/null; then
        kdialog --sorry "$MSG" --title "Battery Lens — Setup Required" && exit 1
    fi

    # Fallback: terminal message
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Battery Lens: System tray library missing"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Ubuntu/Debian:"
    echo "    sudo apt install gir1.2-appindicator3-0.1"
    echo "  Fedora:"
    echo "    sudo dnf install libappindicator-gtk3"
    echo "  Arch/Manjaro:"
    echo "    sudo pacman -S libappindicator-gtk3"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

# ── Launch ────────────────────────────────────────────────────────────────────
exec "$HERE/usr/bin/BatteryLens" "$@"
APPRUN_EOF
chmod +x "$APPDIR/AppRun"

# ── 5. Desktop file ───────────────────────────────────────────────────────────
cat > "$APPDIR/BatteryLens.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Battery Lens
GenericName=Battery Monitor
Comment=Monitor and diagnose battery behaviour
Exec=BatteryLens
Icon=BatteryLens
Categories=Utility;System;Monitor;
Keywords=battery;power;monitor;health;anomaly;
StartupNotify=false
X-AppImage-Version=VERSION_PLACEHOLDER
DESKTOP_EOF

# Substitute version
sed -i "s/VERSION_PLACEHOLDER/${VERSION}/" "$APPDIR/BatteryLens.desktop"

cp "$APPDIR/BatteryLens.desktop" "$APPDIR/usr/share/applications/"

# ── 6. Build AppImage ─────────────────────────────────────────────────────────
echo "[3/4] Building AppImage..."
mkdir -p "$OUTPUT_DIR"

OUTPUT_FILE="$OUTPUT_DIR/BatteryLens-${VERSION}-x86_64.AppImage"

if command -v appimagetool &>/dev/null; then
    ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "$OUTPUT_FILE"
else
    echo "ERROR: appimagetool not found."
    echo "Download from: https://github.com/AppImage/AppImageKit/releases"
    echo "  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O /usr/local/bin/appimagetool"
    echo "  chmod +x /usr/local/bin/appimagetool"
    exit 1
fi

echo "[4/4] Cleaning up build directory..."
rm -rf "$APPDIR"

echo ""
echo "✓ AppImage created: $OUTPUT_FILE"
echo "  Size: $(du -sh "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "To use:"
echo "  chmod +x $OUTPUT_FILE"
echo "  ./$OUTPUT_FILE"
