"""Split the AI mega-prompt reply into per-image prompt files.

Input:   HaikuOutput/*.txt  (one or more .txt files from AI)
         EnglishSource/*.txt (chapter files — used to map [ChapterN] blocks)

Output:  Prompts/<chapter_stem>/Image1.txt ... ImageN.txt

The AI output is parsed for the ===PROMPTS=== ... ===END=== block.
[ChapterN] headers map to the Nth chapter file alphabetically from EnglishSource/.

Re-run safety: refuses to overwrite existing prompt files unless --force.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from common import (
    ENGLISH_SOURCE_DIR,
    HAIKU_OUTPUT_DIR,
    PROMPTS_DIR,
    chapter_stem,
    list_english_chapters,
    prompts_folder_for,
)

ALL_MARKERS = (
    "===STYLE_BIBLE===",
    "===CHARACTER_BIBLE===",
    "===LOCATION_BIBLE===",
    "===PROMPTS===",
    "===END===",
)
REQUIRED_MARKERS = ("===PROMPTS===", "===END===")

CHAPTER_HEADER_RE = re.compile(r"^\s*\[Chapter(\d+)[^\]]*\]\s*$")
IMAGE_HEADER_RE = re.compile(r"^\s*#(\d+)\s*$")


def parse_sections(text: str) -> dict[str, str]:
    for marker in REQUIRED_MARKERS:
        if text.find(marker) == -1:
            raise ValueError(f"Missing required section marker: {marker}")

    positions: list[tuple[int, str]] = []
    for marker in ALL_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            positions.append((idx, marker))

    positions.sort()
    present_order = [m for _, m in positions]
    expected_order = [m for m in ALL_MARKERS if m in present_order]
    if present_order != expected_order:
        raise ValueError(
            "Section markers are out of order. Expected order (of the ones present):\n  "
            + "\n  ".join(expected_order)
            + "\nGot:\n  "
            + "\n  ".join(present_order)
        )

    sections: dict[str, str] = {}
    for i, (idx, marker) in enumerate(positions):
        body_start = idx + len(marker)
        body_end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        sections[marker] = text[body_start:body_end].strip()
    return sections


def parse_prompts(prompts_block: str) -> dict[int, list[tuple[int, str]]]:
    """Returns {chapter_num: [(image_num, prompt_text), ...]}."""
    chapters: dict[int, list[tuple[int, str]]] = {}
    current_chapter: int = 0
    current_image_num: int | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_image_num, current_lines
        if current_image_num is None:
            return
        prompt_text = "\n".join(current_lines).strip()
        if not prompt_text:
            print(
                f"  warn: empty prompt body for Chapter{current_chapter} #{current_image_num}",
                file=sys.stderr,
            )
        chapters.setdefault(current_chapter, []).append(
            (current_image_num, prompt_text)
        )
        current_image_num = None
        current_lines = []

    for raw_line in prompts_block.splitlines():
        line = raw_line.rstrip()

        chap_m = CHAPTER_HEADER_RE.match(line)
        if chap_m:
            flush()
            current_chapter = int(chap_m.group(1))
            continue

        img_m = IMAGE_HEADER_RE.match(line)
        if img_m:
            flush()
            current_image_num = int(img_m.group(1))
            continue

        if current_image_num is not None:
            current_lines.append(line)

    flush()
    return chapters


def collect_input_files() -> list[Path]:
    if not HAIKU_OUTPUT_DIR.exists():
        sys.exit(
            "ERROR: HaikuOutput/ does not exist.\n"
            "  Create the folder and drop the AI's mega-prompt reply inside as a .txt file."
        )

    files = sorted(
        p for p in HAIKU_OUTPUT_DIR.glob("*.txt")
        if p.is_file() and not p.name.lower().startswith("read_me")
    )
    if not files:
        sys.exit(
            "ERROR: no .txt files found in HaikuOutput/.\n"
            "  Save the AI's reply (the block from ===PROMPTS=== to ===END===)\n"
            "  as a .txt file inside HaikuOutput/, then re-run."
        )
    return files


def merge_inputs(files: list[Path]) -> dict[int, list[tuple[int, str]]]:
    merged: dict[int, list[tuple[int, str]]] = {}
    origin: dict[int, str] = {}

    for path in files:
        print(f"  reading: {path.name}")
        text = path.read_text(encoding="utf-8")
        try:
            sections = parse_sections(text)
            chapters = parse_prompts(sections["===PROMPTS==="])
        except ValueError as e:
            sys.exit(
                f"\nERROR parsing {path.name}: {e}\n\n"
                f"  Check that the file contains ===PROMPTS=== ... ===END===,\n"
                f"  and that every image is prefixed with #N."
            )

        for chap_num, image_list in chapters.items():
            if chap_num in merged and origin.get(chap_num) != path.name:
                print(
                    f"    note: Chapter{chap_num} also appeared in "
                    f"{origin[chap_num]} — replacing with version from {path.name}"
                )
            merged[chap_num] = image_list
            origin[chap_num] = path.name

    return merged


def write_prompts(
    books: list[Path],
    parsed: dict[int, list[tuple[int, str]]],
    force: bool,
) -> None:
    """Map [ChapterN] sections to the Nth book (1-indexed, alphabetical order)."""
    chapter_nums = sorted(n for n in parsed if n > 0)
    if not chapter_nums:
        raise SystemExit(
            "ERROR: no [ChapterN] blocks found in the Haiku output.\n"
            "  The AI output must include [Chapter1], [Chapter2], etc.\n"
            "  before each group of image prompts."
        )

    use_numeric = len(chapter_nums) != len(books)
    if use_numeric:
        print(
            f"  warn: {len(books)} chapter file(s) in EnglishSource/ but "
            f"{len(chapter_nums)} [ChapterN] block(s) in HaikuOutput/. "
            f"Writing all as chapter_NN folders."
        )
        pairs: list[tuple[str, int]] = [
            (f"chapter_{n:02d}", n) for n in chapter_nums
        ]
    else:
        pairs = [(chapter_stem(b), n) for b, n in zip(books, chapter_nums)]

    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    for stem, chap_num in pairs:
        prompts_dir = prompts_folder_for(stem)

        # Check for existing prompts
        if not force and prompts_dir.exists() and any(prompts_dir.iterdir()):
            print(
                f"  skip: {prompts_dir.relative_to(prompts_dir.parent.parent)} "
                f"already has prompt files (use --force to overwrite)"
            )
            continue

        if force and prompts_dir.exists():
            shutil.rmtree(prompts_dir)
        prompts_dir.mkdir(parents=True, exist_ok=True)

        images = sorted(parsed.get(chap_num, []))
        for i, (_img_num, prompt_text) in enumerate(images, start=1):
            out = prompts_dir / f"Image{i}.txt"
            out.write_text(prompt_text + "\n", encoding="utf-8")
        total += len(images)
        print(
            f"  Chapter{chap_num}: {len(images)} prompt(s)  →  Prompts/{stem}/"
        )

    print(f"\nWrote {total} prompt(s) across {len(pairs)} chapter folder(s).")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert AI structured output into Prompts/<chapter>/ImageN.txt files.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing prompt files.",
    )
    args = ap.parse_args()

    books = list_english_chapters()

    files = collect_input_files()
    print(f"Processing {len(files)} Haiku output file(s):")
    parsed = merge_inputs(files)

    if not parsed:
        sys.exit(
            "ERROR: no prompts were parsed. Check the format of your input file(s)."
        )

    write_prompts(books, parsed, force=args.force)


if __name__ == "__main__":
    main()
