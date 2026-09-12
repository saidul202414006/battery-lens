#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Battery Lens — Local Linux/macOS Build Script
#
# Linux  → dist/BatteryLens-{version}-x86_64.AppImage
# macOS  → dist/BatteryLens-{version}-macOS.dmg
#
# Usage: bash build/build_local.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

OS="$(uname -s)"
VERSION=$(python3 -c "from version import __version__; print(__version__)" 2>/dev/null || echo "1.0.0")

echo ""
echo "═══════════════════════════════════════════"
echo " Battery Lens — Local Build"
echo " Platform : $OS"
echo " Version  : $VERSION"
echo "═══════════════════════════════════════════"

# ── 1. Ensure venv exists ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate 2>/dev/null || true

# ── 2. Install/update dependencies ───────────────────────────────────────────
echo ""
echo "[1/4] Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if [ "$OS" = "Darwin" ]; then
    pip install -r requirements-macos.txt --quiet
fi
pip install pyinstaller --quiet
echo "✓ Dependencies installed"

# ── 3. PyInstaller ────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Running PyInstaller..."
rm -rf dist/BatteryLens dist/BatteryLens.app
pyinstaller battery_lens.spec \
    --distpath dist \
    --workpath build/pyinstaller_work \
    --noconfirm \
    --log-level WARN
echo "✓ PyInstaller complete"

# ── 4. Platform packaging ─────────────────────────────────────────────────────
echo ""
if [ "$OS" = "Linux" ]; then
    echo "[3/4] Building AppImage..."

    # Check appimagetool
    if ! command -v appimagetool &>/dev/null; then
        echo "  Downloading appimagetool..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
             -O /tmp/appimagetool
        chmod +x /tmp/appimagetool
        sudo mv /tmp/appimagetool /usr/local/bin/appimagetool 2>/dev/null || \
            export PATH="/tmp:$PATH"
    fi

    bash build/build_appimage.sh "$VERSION"
    OUTPUT="dist/BatteryLens-${VERSION}-x86_64.AppImage"

elif [ "$OS" = "Darwin" ]; then
    echo "[3/4] Building DMG..."
    if ! command -v create-dmg &>/dev/null; then
        echo "  Installing create-dmg..."
        brew install create-dmg --quiet 2>/dev/null || true
    fi
    bash build/create_dmg.sh "$VERSION"
    OUTPUT="dist/BatteryLens-${VERSION}-macOS.dmg"
else
    echo "Unknown platform: $OS"
    exit 1
fi

# ── 5. Cleanup ────────────────────────────────────────────────────────────────
echo ""
echo "[4/4] Cleaning up..."
rm -rf build/pyinstaller_work build/BatteryLens.AppDir

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
if [ -f "$OUTPUT" ]; then
    echo "  ✓ Build successful!"
    echo "  Output: $OUTPUT"
    echo "  Size:   $(du -sh "$OUTPUT" | cut -f1)"
else
    echo "  ✗ Build output not found: $OUTPUT"
    exit 1
fi
echo "════════════════════════════════════════════════"
echo ""
