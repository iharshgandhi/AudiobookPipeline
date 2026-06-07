#!/bin/bash
# =============================================================================
#  3_strip_tags.command
#
#  Copies HindiTagged/*_tagged.txt → HindiClean/*.txt, removing all
#  character voice tags (<Alice>...</Alice>) and pause markers
#  (<pause>, <pause:800>). The result is clean Hindi prose ready for
#  single-voice narration.
#
#  Prerequisites:
#    - AI-translated tagged Hindi chapters in HindiTagged/
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

mkdir -p "$SCRIPT_DIR/HindiTagged" "$SCRIPT_DIR/HindiClean"

python "$SCRIPT_DIR/scripts/strip_tags.py"
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
