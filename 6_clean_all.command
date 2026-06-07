#!/bin/bash
# =============================================================================
#  6_clean_all.command
#
#  Deletes ALL generated content so you can start a fresh pipeline run.
#
#  DELETES:
#    Prompts/       Images/       HindiClean/
#    AudioSingle/   AudioMulti/   Videos/
#    HaikuOutput/   HindiTagged/
#
#  PRESERVES (NEVER deleted):
#    EnglishSource/              — your English chapters
#    scripts/                    — Python implementation
#    .venv/                      — Python dependencies
#    config.json                 — tracked settings (no secrets)
#    config.local.json           — YOUR API key (gitignored)
#    config.example.json         — reference for new setups
#    character_voices.txt        — character → voice mapping
#    sample_character_voices.txt — reference voice assignments
#    tag_chapters.py             — tagging utility (if present)
#    BookToPrompts_HaikuPrompt.md
#    translation_mega_prompt.md
#    README.md, .gitignore
#    All .command files
#
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=============================================="
echo "  CLEAN ALL — Reset Pipeline to Fresh State"
echo "=============================================="
echo ""
echo "This will PERMANENTLY DELETE these folders and ALL their contents:"
echo ""
echo "  • Prompts/        (generated image prompt files)"
echo "  • Images/         (generated PNG images)"
echo "  • HindiClean/     (tag-stripped Hindi text)"
echo "  • AudioSingle/    (single-voice MP3s)"
echo "  • AudioMulti/     (multi-voice MP3s)"
echo "  • Videos/         (final MP4 videos)"
echo "  • HaikuOutput/    (AI prompt reply files)"
echo "  • HindiTagged/    (AI-translated tagged chapters)"
echo ""
echo "These will be KEPT:"
echo ""
echo "  • EnglishSource/  (your English chapters)"
echo "  • config.local.json (your API key)"
echo "  • config.json + config.example.json"
echo "  • character_voices.txt + sample_character_voices.txt"
echo "  • tag_chapters.py (if present)"
echo "  • All .command files, scripts/, .venv/"
echo "  • Mega-prompts, README.md, .gitignore"
echo ""

printf "Type 'DELETE' to confirm: "
read -r CONFIRM

if [ "$CONFIRM" != "DELETE" ]; then
  echo ""
  echo "Cancelled — nothing was deleted."
  read -r -p "Press Enter to close..." _
  exit 0
fi

echo ""
echo "Deleting..."

FOLDERS=(
  "Prompts"
  "Images"
  "HindiClean"
  "AudioSingle"
  "AudioMulti"
  "Videos"
  "HaikuOutput"
  "HindiTagged"
)

for folder in "${FOLDERS[@]}"; do
  if [ -d "$SCRIPT_DIR/$folder" ]; then
    rm -rf "$SCRIPT_DIR/$folder"
    echo "  ✓ $folder/ deleted"
  else
    echo "  - $folder/ (already empty)"
  fi
done

# Recreate the empty folders the user needs to drop files into
mkdir -p "$SCRIPT_DIR/HaikuOutput"
mkdir -p "$SCRIPT_DIR/HindiTagged"

echo ""
echo "All generated content deleted."
echo "You are back to a fresh start. EnglishSource/ is untouched."
echo ""
read -r -p "Press Enter to close this window..." _
