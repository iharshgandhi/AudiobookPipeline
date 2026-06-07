#!/bin/bash
# =============================================================================
#  4b_convert_multi.command
#
#  MULTI-VOICE narration. Converts every TAGGED chapter in
#  HindiTagged/*_tagged.txt to AudioMulti/<chapter>.mp3 using Microsoft
#  Edge TTS (free).
#
#  Each character's dialogue must be wrapped in tags, e.g.:
#       घना जंगल था। <Alice>कौन है वहाँ?</Alice> उसने पूछा।
#
#  Every character is read in the voice assigned in character_voices.txt;
#  ALL text outside tags is read by the NARRATOR voice.
#  Tags are stripped before speaking — they only route the voice.
#
#  Pauses are inserted between spans (longer when speaker changes), after
#  chapter headings, at paragraph breaks, and at <pause> / <pause:800> tags.
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

mkdir -p "$SCRIPT_DIR/HindiTagged" "$SCRIPT_DIR/AudioMulti"

python "$SCRIPT_DIR/scripts/convert_multi.py"
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
