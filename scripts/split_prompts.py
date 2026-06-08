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
    safe_truncate,
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

# ---- Bible parsing & enrichment ----

BIBLE_LINE_RE = re.compile(r"^([A-Z][A-Z_0-9]+)\s*[—–-]\s*(.+)$")
STYLE_ANCHOR_RE = re.compile(r"^STYLE_ANCHOR:\s*(.+)$", re.MULTILINE)
MAX_PROMPT_CHARS = 900
MAX_CHARS_PER_CHARACTER = 2  # max characters to give compact descriptions
CORE_SCENE_CHARS = 300       # always preserve at least this much of the scene

# ---- Compact description extraction ----

# Words that indicate a phrase describes visual appearance (keep these).
_VISUAL_KW = {
    # body / build
    "barrel", "chested", "stocky", "slender", "muscular", "heavyset",
    "athletic", "thin", "build", "frame", "figure", "limb", "limp",
    # hair / facial hair
    "hair", "beard", "mustache", "bald", "ponytail", "braid", "slicked",
    "shaggy", "receding", "neat", "bangs", "curls", "wavy",
    # skin / face
    "skin", "tanned", "pale", "ruddy", "freckled", "weathered",
    "complexion", "eyes", "jaw", "face", "expression", "smile",
    "smirk", "stare", "gaze", "glasses", "spectacles", "eyebrows",
    # clothing items
    "suit", "blazer", "jacket", "coat", "shirt", "tie", "dress", "skirt",
    "shorts", "jeans", "pants", "boots", "shoes", "cap", "hat", "helmet",
    "uniform", "lab coat", "safari", "khaki", "denim", "tank top", "polo",
    "hawaiian", "armani", "slicker", "rain", "sweater", "vest", "gloves",
    "stethoscope", "briefcase", "backpack", "cowboy", "baseball",
    # colors (only keep when paired with clothing/body)
    "blond", "dark", "white", "black", "brown", "blue", "green",
    "red", "yellow", "gray", "grey", "beige", "crimson", "silver",
    # distinctive
    "handkerchief", "cigarette", "cigar", "candy", "tattoo", "scar",
    "chain", "watch", "ring", "earring", "necklace",
}

# Words that signal non-visual metadata (drop phrases containing ONLY these).
_NONVISUAL_KW = {
    "paleontologist", "botanist", "mathematician", "lawyer", "programmer",
    "warden", "geneticist", "physician", "paramedic", "biologist",
    "investigator", "engineer", "veterinarian", "entrepreneur",
    "executive", "scientist", "academic", "professor", "doctor",
    "nurse", "midwife", "technician", "pr", "public relations",
    "american", "costa rican", "irish", "english", "japanese",
    "asian", "african", "british", "visiting", "chief", "head of",
    "corporate", "field", "chaos theory", "epa",
    # personality / non-visual
    "gruff", "impatient", "practical", "sharp-minded", "attractive",
    "charismatic", "stubborn", "sardonic", "intense", "ambitious",
    "nervous", "greedy", "untrustworthy", "no-nonsense", "precise",
    "earnest", "shy", "brave", "feisty", "talkative", "tomboyish",
    "eager-to-please", "observant", "capable", "superstitious",
    "predatory", "morally", "reckless", "knowledgeable", "calm",
    "curious", "adventurous", "protective", "distracted", "skeptical",
    "traditional", "intelligent", "intellectual", "sharp",
    "confident", "brooding", "wise", "kind", "gentle", "fierce",
    "professional", "competent", "seasoned", "experienced",
    "father", "mother", "daughter", "son", "brother", "sister",
    "husband", "wife", "friend", "partner", "mentor", "student",
    "teacher", "boss", "assistant",
    # age indicators (standalone numbers)
    "early 20s", "mid 20s", "late 20s", "early 30s", "mid 30s",
    "late 30s", "early 40s", "mid 40s", "late 40s", "mid-30s",
    "late-30s", "mid-40s", "late-40s", "mid-50s", "mid-60s",
    "mid-70s", "early", "middle-aged", "elderly",
    "years old", "year old", "boy", "girl",
    # roles
    "keeping animal list", "for school project", "computer prodigy",
    "in over his head", "out of his depth",
}


def _compact_character_desc(full_desc: str) -> str:
    """Extract only key visual traits from a full bible description.

    Drops profession, nationality, age, personality — keeps body type,
    hair, facial hair, skin, clothing, distinguishing features.
    Target: 60-100 chars (vs 200-250 for full descriptions).
    """
    if not full_desc:
        return full_desc

    # Split on commas (with optional surrounding whitespace)
    phrases = [p.strip() for p in full_desc.split(",") if p.strip()]
    if not phrases:
        return full_desc

    kept: list[str] = []
    for phrase in phrases:
        phrase_lower = phrase.lower()
        # Keep if it contains visual keywords
        if any(kw in phrase_lower for kw in _VISUAL_KW):
            # But skip if it's PURELY non-visual metadata
            nonvis_count = sum(
                1 for kw in _NONVISUAL_KW if kw in phrase_lower
            )
            vis_count = sum(
                1 for kw in _VISUAL_KW if kw in phrase_lower
            )
            if vis_count >= nonvis_count or vis_count >= 2:
                kept.append(phrase)

    # If filtering removed everything, keep first 3 phrases as fallback
    if not kept:
        kept = phrases[:3]

    # Limit to ~6 traits to avoid bloat
    if len(kept) > 6:
        kept = kept[:6]

    return ", ".join(kept)


def _compact_location_desc(full_desc: str, max_chars: int = 80) -> str:
    """Keep the first ~max_chars of a location description."""
    if len(full_desc) <= max_chars:
        return full_desc
    # Break at last comma/space before limit
    for sep in (", ", " — ", "  ", " "):
        pos = full_desc.rfind(sep, 0, max_chars)
        if pos > max_chars // 2:
            return full_desc[:pos].rstrip(", —")
    return full_desc[:max_chars]


def parse_style_anchor(style_bible_text: str) -> str:
    """Extract the STYLE_ANCHOR line from the style bible.

    E.g. 'STYLE_ANCHOR: cinematic oil painting, painterly brushwork, ...'
    Returns empty string if not found.
    """
    if not style_bible_text:
        return ""
    m = STYLE_ANCHOR_RE.search(style_bible_text)
    return m.group(1).strip() if m else ""


def parse_bible_lines(bible_text: str) -> dict[str, str]:
    """Parse a bible section into {CANONICAL_NAME: description}."""
    entries: dict[str, str] = {}
    if not bible_text:
        return entries
    for line in bible_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = BIBLE_LINE_RE.match(line)
        if m:
            entries[m.group(1)] = m.group(2).strip()
    return entries


def _generate_aliases(canonical: str) -> list[str]:
    """Generate search aliases for a CANONICAL_NAME like TIM_MURPHY or DR_HENRY_WU.

    Returns lowercase forms: 'tim murphy', 'tim', 'murphy', 'henry wu', 'wu', etc.
    """
    # Strip DR_ prefix for alias generation
    clean = canonical
    if clean.startswith("DR_"):
        clean = clean[3:]

    parts = [p.lower() for p in clean.split("_") if p]
    aliases: list[str] = []

    # Full name with spaces: "tim murphy"
    if len(parts) >= 2:
        aliases.append(" ".join(parts))

    # Individual parts as standalone: "tim", "murphy"
    for p in parts:
        if len(p) > 2 and p not in ("the", "and", "for"):
            aliases.append(p)

    # Also add the canonical itself (lowered)
    aliases.append(canonical.lower())

    return aliases


def build_reference_index(
    characters: dict[str, str],
    locations: dict[str, str],
) -> list[tuple[str, str, str, str]]:
    """Build a flat index for scanning prompts.

    Returns list of (search_pattern, ref_type, canonical_name, description)
    sorted longest-pattern-first to avoid partial matches.
    ref_type is 'character' or 'location'.
    """
    index: list[tuple[str, str, str, str]] = []

    for name, desc in characters.items():
        for alias in _generate_aliases(name):
            # Escape for regex, wrap in word boundaries
            pattern = r"\b" + re.escape(alias) + r"\b"
            index.append((pattern, "character", name, desc))

    for name, desc in locations.items():
        # Location aliases: canonical lowered + space-form
        loc_aliases = _generate_aliases(name)
        for alias in loc_aliases:
            pattern = r"\b" + re.escape(alias) + r"\b"
            index.append((pattern, "location", name, desc))

    # Sort by pattern length descending (longest match first)
    index.sort(key=lambda x: -len(x[0]))
    return index


def _already_described(prompt: str, canonical: str, alias: str) -> bool:
    """Check if a character reference already has an inline description.

    E.g. 'DONALD_GENNARO — stocky lawyer...' means skip enrichment.
    """
    # Look for the name followed by an em-dash or similar within ~80 chars
    escaped = re.escape(alias)
    # Match: NAME — description (already enriched or originally described)
    already = re.search(
        escaped + r"\s*[—–-]\s*.{10,80}",
        prompt,
        re.IGNORECASE,
    )
    return already is not None


def detect_and_enrich(
    prompt: str,
    index: list[tuple[str, str, str, str]],
    style_anchor: str = "",
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Detect character/location references and enrich the prompt inline.

    Uses *compact* character descriptions (visual traits only) to keep
    prompts within Pollinations' budget.  When space is tight, only the
    first 2 characters get descriptions; the rest are name-only.
    Locations are appended if budget allows, otherwise dropped.
    A final ``_safe_truncate`` pass guarantees no broken parentheticals.
    """
    found_chars: dict[str, str] = {}   # canonical → compact desc
    found_locs: dict[str, str] = {}    # canonical → compact loc desc
    matched_positions: list[tuple[int, int, str, str, str]] = []
    # (start, end, ref_type, canonical, matched_alias)

    # Scan for all references in the index
    for pattern, ref_type, canonical, desc in index:
        for m in re.finditer(pattern, prompt, re.IGNORECASE):
            start, end = m.start(), m.end()
            matched_alias = m.group(0)
            # Check this position isn't already claimed by a longer match
            if any(
                prev_start <= start < prev_end or prev_start < end <= prev_end
                for prev_start, prev_end, _, _, _ in matched_positions
            ):
                continue
            # Skip if already described inline
            if _already_described(prompt, canonical, matched_alias):
                continue
            matched_positions.append(
                (start, end, ref_type, canonical, matched_alias)
            )
            if ref_type == "character":
                found_chars[canonical] = _compact_character_desc(desc)
            else:
                found_locs[canonical] = _compact_location_desc(desc)

    if not found_chars and not found_locs:
        # No references detected — just fix up style and return
        return _apply_style_anchor(prompt, style_anchor)

    # ---- Enrich characters inline (compact descriptions) ----
    enriched = prompt
    enrichments: list[tuple[int, int, str, str]] = []
    seen_chars: set[str] = set()
    char_matches = [
        (s, e, c, a)
        for s, e, t, c, a in matched_positions
        if t == "character"
    ]
    # Sort leftmost-first — pick the first occurrence per character
    char_matches.sort(key=lambda x: x[0])

    # Build enrichments for the first MAX_CHARS_PER_CHARACTER characters
    # (the rest stay name-only — the AI already named them in the scene).
    char_count = 0
    for start, end, canonical, alias in char_matches:
        if canonical in seen_chars:
            continue
        seen_chars.add(canonical)
        enrichments.append((start, end, canonical, alias))
        char_count += 1
        if char_count >= MAX_CHARS_PER_CHARACTER:
            break

    # Apply right-to-left for position safety
    enrichments.sort(key=lambda x: -x[0])
    for start, end, canonical, alias in enrichments:
        desc = found_chars.get(canonical, "")
        if desc:
            replacement = f"{alias} ({desc})"
        else:
            replacement = alias  # name-only fallback
        enriched = enriched[:start] + replacement + enriched[end:]

    # ---- Style anchor ----
    enriched = _apply_style_anchor(enriched, style_anchor)

    # ---- Append locations (if budget allows) ----
    loc_budget = max_chars - len(enriched) - 30  # reserve 30 for safety
    if found_locs and loc_budget > 40:
        loc_descs = list(found_locs.values())
        if len(loc_descs) > 2:
            loc_descs = loc_descs[:2]
        loc_text = " | ".join(loc_descs)
        loc_suffix = f" — SETTING: {loc_text}"
        if len(enriched) + len(loc_suffix) <= max_chars:
            enriched = enriched.rstrip() + loc_suffix

    # ---- Final safe truncation ----
    if len(enriched) > max_chars:
        before = len(enriched)
        enriched = safe_truncate(enriched, max_chars)
        print(
            f"  warn: enriched prompt truncated {before} → "
            f"{len(enriched)} chars (limit {max_chars}).",
            file=sys.stderr,
        )

    return enriched


def _apply_style_anchor(prompt: str, style_anchor: str) -> str:
    """Prepend the style anchor, stripping any trailing duplicate
    and removing the ``[style]`` shorthand marker."""
    if not style_anchor:
        return prompt
    result = prompt
    # Remove [style] marker (the AI uses this as a short token)
    result = result.replace("[style]", "").replace("  ", " ").strip()
    # Remove trailing style if present
    suffix = result.rstrip().rstrip(",").rstrip()
    if suffix.endswith(style_anchor):
        result = suffix[: -len(style_anchor)].rstrip(", —")
    elif suffix.endswith(style_anchor.rstrip(",")):
        result = suffix[: -len(style_anchor.rstrip(","))].rstrip(", —")
    if not result.startswith(style_anchor):
        result = f"{style_anchor}, {result}"
    return result


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


def merge_inputs(
    files: list[Path],
    enrich: bool = True,
) -> tuple[
    dict[int, list[tuple[int, str]]],
    list[tuple[str, str, str, str]] | None,
    str,
]:
    """Parse Haiku output files, extract prompts and (if enrich=True) bibles.

    Returns (parsed_chapters, reference_index_or_None, style_anchor).
    """
    merged: dict[int, list[tuple[int, str]]] = {}
    origin: dict[int, str] = {}
    all_characters: dict[str, str] = {}
    all_locations: dict[str, str] = {}
    style_anchor: str = ""

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

        # Collect bibles for enrichment
        if enrich:
            style_text = sections.get("===STYLE_BIBLE===", "")
            if style_text and not style_anchor:
                style_anchor = parse_style_anchor(style_text)

            char_text = sections.get("===CHARACTER_BIBLE===", "")
            loc_text = sections.get("===LOCATION_BIBLE===", "")
            if char_text:
                parsed_chars = parse_bible_lines(char_text)
                all_characters.update(parsed_chars)
            if loc_text:
                parsed_locs = parse_bible_lines(loc_text)
                all_locations.update(parsed_locs)

    ref_index: list[tuple[str, str, str, str]] | None = None
    if enrich and (all_characters or all_locations):
        ref_index = build_reference_index(all_characters, all_locations)
        print(
            f"  bible: {len(all_characters)} character(s), "
            f"{len(all_locations)} location(s) indexed"
        )
    elif enrich:
        print("  bible: no character or location entries found — skipping enrichment")

    if style_anchor:
        print(f"  style: \"{style_anchor[:80]}{'...' if len(style_anchor) > 80 else ''}\"")

    return merged, ref_index, style_anchor


def write_prompts(
    books: list[Path],
    parsed: dict[int, list[tuple[int, str]]],
    force: bool,
    ref_index: list[tuple[str, str, str, str]] | None = None,
    style_anchor: str = "",
) -> None:
    """Map [ChapterN] sections to the Nth book (1-indexed, alphabetical order).

    If ref_index is provided, each prompt is enriched with character and
    location descriptions from the bible before writing.
    If style_anchor is provided, it is prepended to enriched prompts so the
    artistic style is the first thing the image model processes.
    """
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
    enriched_count = 0

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

            # Enrich with bible descriptions if index is available
            final_text = prompt_text
            if ref_index is not None:
                enriched = detect_and_enrich(
                    prompt_text, ref_index, style_anchor=style_anchor
                )
                if enriched != prompt_text:
                    enriched_count += 1
                final_text = enriched

            out.write_text(final_text + "\n", encoding="utf-8")
        total += len(images)
        print(
            f"  Chapter{chap_num}: {len(images)} prompt(s)  →  Prompts/{stem}/"
        )

    print(f"\nWrote {total} prompt(s) across {len(pairs)} chapter folder(s).")
    if ref_index is not None:
        print(f"  {enriched_count} prompt(s) enriched with bible descriptions.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert AI structured output into Prompts/<chapter>/ImageN.txt files.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing prompt files.",
    )
    ap.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip bible enrichment — write raw prompts exactly as AI produced them.",
    )
    args = ap.parse_args()

    books = list_english_chapters()
    do_enrich = not args.no_enrich

    if do_enrich:
        print("Bible enrichment: ENABLED (use --no-enrich to skip)")
    else:
        print("Bible enrichment: DISABLED (--no-enrich flag)")

    files = collect_input_files()
    print(f"Processing {len(files)} Haiku output file(s):")
    parsed, ref_index, style_anchor = merge_inputs(files, enrich=do_enrich)

    if not parsed:
        sys.exit(
            "ERROR: no prompts were parsed. Check the format of your input file(s)."
        )

    write_prompts(
        books, parsed, force=args.force,
        ref_index=ref_index, style_anchor=style_anchor,
    )


if __name__ == "__main__":
    main()
