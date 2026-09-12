#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Battery Lens — macOS DMG Creator
#
# Wraps the PyInstaller .app bundle in a user-friendly drag-to-install DMG.
#
# Prerequisites:
#   brew install create-dmg
#   (hdiutil fallback works without any install)
#
# Usage:
#   bash build/create_dmg.sh [version]
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION="${1:-$(python3 -c 'from version import __version__; print(__version__)' 2>/dev/null || echo '1.0.0')}"

APP_BUNDLE="$ROOT_DIR/dist/BatteryLens.app"
OUTPUT_DIR="$ROOT_DIR/dist"
OUTPUT_DMG="$OUTPUT_DIR/BatteryLens-${VERSION}-macOS.dmg"
ICON_PNG="$ROOT_DIR/assets/icon.png"

echo "═══════════════════════════════════════════"
echo " Battery Lens — DMG Creator v${VERSION}"
echo "═══════════════════════════════════════════"

# ── 1. Verify .app bundle exists ─────────────────────────────────────────────
if [ ! -d "$APP_BUNDLE" ]; then
    echo ""
    echo "ERROR: .app bundle not found at: $APP_BUNDLE"
    echo "Run first: pyinstaller battery_lens.spec"
    exit 1
fi

echo "[1/3] Converting icon PNG → ICNS..."
# Convert PNG to ICNS for macOS app icon
ICONSET_DIR="$OUTPUT_DIR/BatteryLens.iconset"
mkdir -p "$ICONSET_DIR"
if [ -f "$ICON_PNG" ]; then
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null 2>&1 || true
        double=$((size * 2))
        sips -z $double $double "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET_DIR" -o "$ROOT_DIR/assets/icon.icns" 2>/dev/null || true
    rm -rf "$ICONSET_DIR"
    echo "  ✓ icon.icns created"
else
    echo "  ⚠ icon.png not found — DMG will use default icon"
fi

echo "[2/3] Building DMG..."
mkdir -p "$OUTPUT_DIR"

# Remove old DMG if exists
rm -f "$OUTPUT_DMG"

if command -v create-dmg &>/dev/null; then
    # Professional DMG with custom window, background, and arrow
    create-dmg \
        --volname "Battery Lens ${VERSION}" \
        --window-pos 200 120 \
        --window-size 560 380 \
        --icon-size 100 \
        --icon "BatteryLens.app" 140 185 \
        --hide-extension "BatteryLens.app" \
        --app-drop-link 420 185 \
        --no-internet-enable \
        "$OUTPUT_DMG" \
        "$APP_BUNDLE" \
    || {
        # create-dmg can exit non-zero if code signing is skipped — check output exists
        if [ -f "$OUTPUT_DMG" ]; then
            echo "  ✓ DMG created (unsigned)"
        else
            echo "  create-dmg failed — falling back to hdiutil"
            USE_HDIUTIL=1
        fi
    }
else
    USE_HDIUTIL=1
fi

# ── Fallback: simple hdiutil DMG ─────────────────────────────────────────────
if [ "${USE_HDIUTIL:-0}" = "1" ]; then
    TMPDIR_DMG=$(mktemp -d)
    cp -r "$APP_BUNDLE" "$TMPDIR_DMG/"
    ln -s /Applications "$TMPDIR_DMG/Applications"

    hdiutil create \
        -volname "Battery Lens ${VERSION}" \
        -srcfolder "$TMPDIR_DMG" \
        -ov \
        -format UDZO \
        "$OUTPUT_DMG"

    rm -rf "$TMPDIR_DMG"
fi

echo "[3/3] Verifying DMG..."
if [ -f "$OUTPUT_DMG" ]; then
    echo ""
    echo "✓ DMG created: $OUTPUT_DMG"
    echo "  Size: $(du -sh "$OUTPUT_DMG" | cut -f1)"
    echo ""
    echo "Installation (end user):"
    echo "  1. Open BatteryLens-${VERSION}-macOS.dmg"
    echo "  2. Drag Battery Lens → Applications"
    echo "  3. Launch from Launchpad or Applications folder"
    echo "  4. It appears in the menu bar (top right)"
else
    echo "ERROR: DMG was not created."
    exit 1
fi
