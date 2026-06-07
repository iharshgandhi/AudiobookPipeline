#!/bin/bash
# =============================================================================
#  4a_convert_single.command
#
#  Converts every HindiClean/*.txt to AudioSingle/<chapter>.mp3 using
#  Microsoft Edge TTS (free, cloud) with a SINGLE voice.
#
#  Hardcoded for Hindi — uses the voice from config.json
#  (default: hi-IN-MadhurNeural, a male native Hindi voice).
#
#  Safe to interrupt and re-run: chapters whose .mp3 already exists are
#  skipped.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Double-click setup.command first."
  read -r -p "Press Enter to close..." _
  exit 1
fi

# Make Homebrew's ffmpeg visible
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found. Re-run setup.command."
  read -r -p "Press Enter to close..." _
  exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/.venv/bin/activate"

mkdir -p "$SCRIPT_DIR/HindiClean" "$SCRIPT_DIR/AudioSingle"

python "$SCRIPT_DIR/scripts/convert_single.py"
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
