#!/bin/bash
# =============================================================================
#  5b_merge_multi.command
#
#  Merges Images/<chapter>/*.png with AudioMulti/<chapter>.mp3 into
#  Videos/<chapter>_multi.mp4 — using the MULTI-VOICE (character) audio track.
#
#  REQUIRES Apple Silicon + h264_videotoolbox (hardware GPU encode).
#  No CPU fallback.
#
#  Run this after 4b_convert_multi.command.
#
#  Behavior:
#    - Total audio duration is split evenly across all images
#    - Adjacent images crossfade with a RANDOM "diffusion/merge"-style
#      transition (fade, dissolve, pixelize, hblur, radial, ...)
#    - Output size is controlled by `video_bitrate_mbps` in config.json
#      (default 2.5 Mbps — plenty for slideshows at 720p)
#    - Always overwrites existing .mp4
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

mkdir -p "$SCRIPT_DIR/Videos"

python "$SCRIPT_DIR/scripts/merge_to_video.py" --mode multi
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
