#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <comma-separated-library-ids>" >&2
  echo "Example: $0 abc123,def456" >&2
  exit 1
fi

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
IDS="$1"

mkdir -p "$HOME_DIR"
export HOME="$HOME_DIR"

echo "Installing MuseSounds libraries: $IDS"
exec /opt/muse-sounds-manager/muse-sounds-manager --headless --install-musesounds="$IDS"
