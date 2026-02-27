#!/usr/bin/env bash
set -euo pipefail

# Reproducible setup for MuseScore 4 headless rendering + Muse Sounds Manager.
#
# What this script automates:
# - System dependencies
# - MuseScore Studio AppImage download + extraction
# - Muse Sounds Manager (.deb) download + install
# - Headless manager initialization and local workspace layout

ROOT_DIR="${ROOT_DIR:-$PWD}"
WORK_DIR="${WORK_DIR:-$ROOT_DIR/.muse4}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
MANUAL_INSTALL_DIR="$ROOT_DIR/manual_install"

MUSESCORE_VERSION="${MUSESCORE_VERSION:-4.6.5}"
MUSESCORE_BUILD="${MUSESCORE_BUILD:-253511702}"
MUSESCORE_URL="${MUSESCORE_URL:-https://cdn.jsdelivr.net/musescore/v${MUSESCORE_VERSION}/MuseScore-Studio-${MUSESCORE_VERSION}.${MUSESCORE_BUILD}-x86_64.AppImage}"
MUSESOUNDS_MANAGER_URL="${MUSESOUNDS_MANAGER_URL:-https://muse-cdn.com/Muse_Sounds_Manager_x64.deb}"
# Default set includes the libraries requested in this project.
DEFAULT_MUSESOUNDS_IDS="6a0d49c3-df4b-4f86-ad8f-61c131b7428c,e4a60bd8-4a44-4c5a-ad3a-3bccf48a5f64,d2e779d2-3ec9-4337-82c4-f689f7dd9581,4fe4c30d-53d8-4980-891c-b5c1af2d29f2,b75ca51c-8a44-455a-b378-269049aaf506,90c55796-5d20-47de-ac4c-62a641b4dbed,0013e17f-55dd-42fb-bba3-110337a64849,d6353666-c534-4c48-833e-c86f0926656f,f2fbf84c-06da-45c9-be57-f2722d9fd363,fbd15858-9185-41ed-918b-8e360a698dbe,3a82bdc5-b4aa-4c02-aca1-1b3d4914154a,10a350b6-7c03-43b1-8d3e-6edca0225bc4"
MUSESOUNDS_IDS="${MUSESOUNDS_IDS:-$DEFAULT_MUSESOUNDS_IDS}"
INSTALL_MUSESOUNDS="${INSTALL_MUSESOUNDS:-1}"

APPIMAGE_PATH="$WORK_DIR/MuseScore-Studio.AppImage"
EXTRACT_DIR="$WORK_DIR/musescore4"
MSCORE_BIN="$EXTRACT_DIR/squashfs-root/bin/mscore4portable"
MANAGER_DEB="$WORK_DIR/Muse_Sounds_Manager_x64.deb"

if [[ $EUID -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

mkdir -p "$WORK_DIR" "$HOME_DIR" "$MANUAL_INSTALL_DIR"

echo "[1/8] Installing system dependencies..."
$SUDO apt-get update
$SUDO apt-get install -y \
  ca-certificates wget unzip ffmpeg \
  libasound2 libegl1 libopengl0 libnss3 libpipewire-0.3-0 \
  libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 \
  xdg-utils

echo "[2/8] Downloading MuseScore Studio AppImage..."
if [[ ! -f "$APPIMAGE_PATH" ]]; then
  wget -O "$APPIMAGE_PATH" "$MUSESCORE_URL"
else
  echo "  Reusing existing: $APPIMAGE_PATH"
fi
chmod +x "$APPIMAGE_PATH"

echo "[3/8] Extracting MuseScore AppImage..."
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
(
  cd "$EXTRACT_DIR"
  "$APPIMAGE_PATH" --appimage-extract >/dev/null
)
if [[ ! -x "$MSCORE_BIN" ]]; then
  echo "MuseScore binary not found after extraction: $MSCORE_BIN" >&2
  exit 1
fi

echo "[4/8] Downloading Muse Sounds Manager (.deb)..."
if [[ ! -f "$MANAGER_DEB" ]]; then
  wget -O "$MANAGER_DEB" "$MUSESOUNDS_MANAGER_URL"
else
  echo "  Reusing existing: $MANAGER_DEB"
fi

echo "[5/8] Installing Muse Sounds Manager..."
$SUDO dpkg -i "$MANAGER_DEB" || $SUDO apt-get -f install -y

echo "[6/8] Initializing Muse Sounds Manager headlessly..."
HOME="$HOME_DIR" /opt/muse-sounds-manager/muse-sounds-manager --headless || true

echo "[7/8] Writing helper launcher scripts..."
cat > "$MANUAL_INSTALL_DIR/run_mscore4_headless.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="\${ROOT_DIR:-\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="\${HOME_DIR:-\$ROOT_DIR/.home}"
MSCORE_BIN="\${MSCORE_BIN:-$MSCORE_BIN}"
export HOME="\$HOME_DIR"
export QT_QPA_PLATFORM=offscreen
export MU_QT_QPA_PLATFORM=offscreen
if [[ -n "\${QT_LOGGING_RULES:-}" ]]; then
  export QT_LOGGING_RULES="\${QT_LOGGING_RULES};qt.qml.typeregistration=false"
else
  export QT_LOGGING_RULES="qt.qml.typeregistration=false"
fi
exec "\$MSCORE_BIN" "\$@"
EOF
chmod +x "$MANUAL_INSTALL_DIR/run_mscore4_headless.sh"

cat > "$MANUAL_INSTALL_DIR/run_musesounds_manager.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
export HOME="$HOME_DIR"
exec /opt/muse-sounds-manager/muse-sounds-manager "$@"
EOF
chmod +x "$MANUAL_INSTALL_DIR/run_musesounds_manager.sh"

cat > "$MANUAL_INSTALL_DIR/install_musesounds_headless.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <comma-separated-library-ids>" >&2
  echo "Example: $0 abc123,def456" >&2
  exit 1
fi
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
export HOME="$HOME_DIR"
exec /opt/muse-sounds-manager/muse-sounds-manager --headless --install-musesounds="$1"
EOF
chmod +x "$MANUAL_INSTALL_DIR/install_musesounds_headless.sh"

echo "[8/8] Installing MuseSounds libraries (headless)..."
if [[ "$INSTALL_MUSESOUNDS" == "1" && -n "$MUSESOUNDS_IDS" ]]; then
  HOME="$HOME_DIR" /opt/muse-sounds-manager/muse-sounds-manager --headless --install-musesounds="$MUSESOUNDS_IDS"
else
  echo "  Skipped (INSTALL_MUSESOUNDS=$INSTALL_MUSESOUNDS, MUSESOUNDS_IDS length=${#MUSESOUNDS_IDS})"
fi

echo
echo "Setup complete."
echo "MuseScore binary: $MSCORE_BIN"
echo
echo "Then verify with:"
echo "  ./manual_install/verify_musesounds_ready.sh"
echo "If needed, install additional IDs:"
echo "  ./manual_install/install_musesounds_headless.sh <id1,id2,...>"
echo "Render with:"
echo "  ./manual_install/run_mscore4_headless.sh --sound-profile \"MuseSounds\" -o out.wav in.mid"
