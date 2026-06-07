"""Strip character voice tags from tagged Hindi chapter files.

Reads:   HindiTagged/chapter_NN_tagged.txt
Writes:  HindiClean/chapter_NN.txt  (clean, no XML-style tags)

Strips:
  - <CharacterName> ... </CharacterName>  (any character tag)
  - <pause> or <pause:NNN>               (pause markers)
  - Any stray/orphan tag markup

The resulting file is identical prose, just without voice-routing markup.
Ready for single-voice TTS or plain reading.

Re-run safety: skips if the clean file already exists (unless --force).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import HINDI_TAGGED_DIR, HINDI_CLEAN_DIR, chapter_stem, list_tagged_chapters

# Matches: <CharacterName>...</CharacterName>  OR  <pause> / <pause:800>
TAG_RE = re.compile(
    r"<pause(?::\d+)?\s*/?>|<([A-Za-z][A-Za-z0-9_]*)>.*?</\2>",
    re.DOTALL,
)
# Stray/unclosed tags
STRAY_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_]*(?::\d+)?\s*/?>")


def strip_tags(text: str) -> str:
    """Remove all character voice tags and pause markers from text."""
    # First remove complete tag pairs
    text = TAG_RE.sub("", text)
    # Then remove any stray tags
    text = STRAY_RE.sub("", text)
    # Clean up extra whitespace from tag removal
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Strip character voice tags from tagged Hindi chapters."
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing clean files.",
    )
    args = ap.parse_args()

    tagged = list_tagged_chapters()
    if not tagged:
        sys.exit(
            "ERROR: no *_tagged.txt files found in HindiTagged/.\n"
            "  After translating chapters with the AI mega-prompt,\n"
            "  save the tagged output files to HindiTagged/."
        )

    HINDI_CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    done = 0
    skipped = 0
    for tag_path in tagged:
        stem = chapter_stem(tag_path)
        clean_path = HINDI_CLEAN_DIR / f"{stem}.txt"

        if clean_path.exists() and not args.force:
            print(f"  skip: {clean_path.name} already exists")
            skipped += 1
            continue

        text = tag_path.read_text(encoding="utf-8")
        clean_text = strip_tags(text)
        clean_path.write_text(clean_text, encoding="utf-8")
        print(f"  {tag_path.name}  →  {clean_path.name}")
        done += 1

    print(
        f"\nStripped tags from {done} file(s). "
        f"{skipped} already existed (skipped)."
    )


if __name__ == "__main__":
    main()
