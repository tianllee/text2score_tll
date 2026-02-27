#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"

SAMPLER_LIB_DIR="$HOME_DIR/.local/share/MuseSampler/lib"
SOUNDS_DIR="$HOME_DIR/Muse Sounds"
INSTRUMENTS_MARKER="$SOUNDS_DIR/.instruments"

echo "Checking MuseSounds installation state..."
echo "HOME_DIR=$HOME_DIR"

if [[ ! -d "$SAMPLER_LIB_DIR" ]]; then
  echo "NOT READY: MuseSampler library directory missing: $SAMPLER_LIB_DIR" >&2
  exit 2
fi

if ! find "$SAMPLER_LIB_DIR" -maxdepth 1 -type f | grep -q .; then
  echo "NOT READY: MuseSampler library directory is empty: $SAMPLER_LIB_DIR" >&2
  exit 3
fi

if [[ ! -d "$SOUNDS_DIR" ]]; then
  echo "NOT READY: Muse Sounds directory missing: $SOUNDS_DIR" >&2
  exit 4
fi

if [[ ! -f "$INSTRUMENTS_MARKER" ]]; then
  echo "NOT READY: Missing instruments marker file: $INSTRUMENTS_MARKER" >&2
  exit 5
fi

sound_count="$(find "$SOUNDS_DIR" -type f | wc -l | awk '{print $1}')"
if [[ "$sound_count" -lt 5 ]]; then
  echo "NOT READY: Muse Sounds appears incomplete (file count=$sound_count)." >&2
  exit 6
fi

echo "READY: MuseSounds installation detected."
echo "MuseSampler files:"
find "$SAMPLER_LIB_DIR" -maxdepth 1 -type f -printf "  %f\n"
echo "Muse Sounds file count: $sound_count"
