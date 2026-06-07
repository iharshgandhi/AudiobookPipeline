#!/bin/bash
# =============================================================================
#  2_generate_images.command
#
#  Renders Prompts/<chapter>/ImageN.txt → Images/<chapter>/ImageN.png
#  via Pollinations.ai (free, Flux model).
#
#  Safe to interrupt and re-run:
#    - Skips any prompt whose .png already exists
#    - If you don't like an image, delete that one PNG and re-run
#
#  Uses settings from config.json (pollinations_token, poll_model, etc.)
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Double-click setup.command first."
  read -r -p "Press Enter to close..." _
  exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/.venv/bin/activate"

python "$SCRIPT_DIR/scripts/pollinations_generate.py"
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
