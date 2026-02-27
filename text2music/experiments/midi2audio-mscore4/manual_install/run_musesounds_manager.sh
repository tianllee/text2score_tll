#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOME_DIR="${HOME_DIR:-$ROOT_DIR/.home}"
export HOME="$HOME_DIR"
exec /opt/muse-sounds-manager/muse-sounds-manager "$@"
