#!/bin/bash
# =============================================================================
#  1_split_prompts.command
#
#  Reads the AI's mega-prompt reply from HaikuOutput/*.txt and writes
#  per-image prompt files into Prompts/<chapter>/ImageN.txt.
#
#  Prerequisites:
#    - Ran setup.command once
#    - At least one .txt in EnglishSource/
#    - At least one .txt in HaikuOutput/ with ===PROMPTS=== ... ===END=== block
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

mkdir -p "$SCRIPT_DIR/EnglishSource" "$SCRIPT_DIR/HaikuOutput" "$SCRIPT_DIR/Prompts"

# Check for existing prompts — ask before overwriting
EXISTING=$(find "$SCRIPT_DIR/Prompts" -type f -name "Image*.txt" 2>/dev/null | wc -l | tr -d ' ')

FORCE_FLAG=""
if [ "${EXISTING:-0}" -gt 0 ]; then
  echo ""
  echo "Found $EXISTING existing prompt file(s) in Prompts/."
  printf "Overwrite with what the AI produced this time? [y/N]: "
  read -r ANS
  case "$ANS" in
    y|Y|yes|Yes|YES) FORCE_FLAG="--force" ;;
    *) echo "  keeping existing prompt files — nothing to do."; read -r -p "Press Enter to close..." _; exit 0 ;;
  esac
fi

python "$SCRIPT_DIR/scripts/split_prompts.py" $FORCE_FLAG
RC=$?

echo ""
read -r -p "Press Enter to close this window..." _
exit $RC
