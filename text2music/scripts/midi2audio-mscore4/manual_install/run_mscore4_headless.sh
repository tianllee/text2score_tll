#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
MSCORE_BIN="${MSCORE_BIN:-/workspace/data/sungkyun/amt/musescore_synth/.muse4/musescore4/squashfs-root/bin/mscore4portable}"
export HOME="$HOME_DIR"
export QT_QPA_PLATFORM=offscreen
export MU_QT_QPA_PLATFORM=offscreen
if [[ -n "${QT_LOGGING_RULES:-}" ]]; then
  export QT_LOGGING_RULES="${QT_LOGGING_RULES};qt.qml.typeregistration=false"
else
  export QT_LOGGING_RULES="qt.qml.typeregistration=false"
fi
exec "$MSCORE_BIN" "$@"
