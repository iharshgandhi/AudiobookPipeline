"""Shared helpers for the NewAudioBookPipeline.

Folder layout (all at project root, created on demand):

    EnglishSource/      drop your English chapter .txt files here
    HaikuOutput/        drop the AI image-prompt reply .txt here
    Prompts/            generated: per-chapter ImageN.txt prompt files
    Images/             generated: per-chapter ImageN.png from Pollinations
    HindiTagged/        drop AI-translated Hindi chapters WITH character tags
    HindiClean/         generated: tag-stripped clean Hindi chapters
    AudioSingle/        generated: single-voice MP3 per chapter
    AudioMulti/         generated: multi-voice MP3 per chapter
    Videos/             generated: final MP4 per chapter

All chapter filenames must match across folders, e.g.:
    EnglishSource/chapter_01.txt
    HindiTagged/chapter_01_tagged.txt
    HindiClean/chapter_01.txt
    AudioSingle/chapter_01.mp3
    AudioMulti/chapter_01.mp3
    Images/chapter_01/Image1.png ...
    Videos/chapter_01_single.mp4, Videos/chapter_01_multi.mp4
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Dict

# Project root = parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
CONFIG_LOCAL_PATH = ROOT / "config.local.json"  # gitignored — put your real key here
CHARACTER_VOICES_PATH = ROOT / "character_voices.txt"

# Top-level folders
ENGLISH_SOURCE_DIR = ROOT / "EnglishSource"
HAIKU_OUTPUT_DIR = ROOT / "HaikuOutput"
PROMPTS_DIR = ROOT / "Prompts"
IMAGES_DIR = ROOT / "Images"
HINDI_TAGGED_DIR = ROOT / "HindiTagged"
HINDI_CLEAN_DIR = ROOT / "HindiClean"
AUDIO_SINGLE_DIR = ROOT / "AudioSingle"
AUDIO_MULTI_DIR = ROOT / "AudioMulti"
VIDEOS_DIR = ROOT / "Videos"

ALL_GENERATED_DIRS = [
    PROMPTS_DIR, IMAGES_DIR, HINDI_CLEAN_DIR,
    AUDIO_SINGLE_DIR, AUDIO_MULTI_DIR, VIDEOS_DIR,
]

# Curated Hindi/Devanagari-capable voices for audiobook narration.
_CURATED: Dict[str, List[Dict[str, str]]] = {
    "hi": [
        {"name": "hi-IN-SwaraNeural",   "gender": "Female", "note": "Hindi female — natural narration"},
        {"name": "hi-IN-MadhurNeural",  "gender": "Male",   "note": "Hindi male — clear narration"},
    ],
    "en": [
        {"name": "en-US-AvaNeural",         "gender": "Female", "note": "US — warm, expressive"},
        {"name": "en-US-AndrewNeural",      "gender": "Male",   "note": "US — warm, confident"},
    ],
}

LANGUAGE_NAMES = {"hi": "Hindi", "en": "English"}
LANGUAGE_ORDER = ["hi", "en"]

DEFAULT_CONFIG = {
    "language": "hi",
    "voice": "hi-IN-MadhurNeural",
    "voice_hi": "hi-IN-MadhurNeural",
    "voice_en": "en-US-AvaNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    "parallel_chunks": 2,
    "chunk_chars": 2800,
    # Multi-voice (character) narration
    "narrator_voice": "hi-IN-MadhurNeural",
    "gap_same_ms": 220,
    "speaker_gap_ms": 420,
    "heading_gap_ms": 750,
    "paragraph_gap_ms": 450,
    "default_pause_ms": 550,
    "lead_in_ms": 250,
    # Pollinations image generation
    "pollinations_token": "",
    "poll_model": "flux",
    "poll_width": 1280,
    "poll_height": 720,
    "poll_gap_sec": 0.5,
    # Video merge
    "video_bitrate_mbps": 2.5,
    "video_fps": 30,
    "transition_duration_sec": 1.0,
    "transition_styles": [
        "fade", "fadeblack", "fadewhite", "fadegrays",
        "dissolve", "pixelize", "hblur", "distance", "radial",
        "circleopen", "circleclose",
        "smoothleft", "smoothright", "smoothup", "smoothdown",
    ],
}


def load_config() -> dict:
    """Load config from config.json, then merge config.local.json (if it
    exists), then override pollinations_token from POLLINATIONS_API_KEY env
    var if set. This keeps secrets out of git while still being usable."""
    cfg = dict(DEFAULT_CONFIG)

    # 1) Base config (tracked in git, no secrets)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update(data)
        except Exception:
            pass

    # 2) Local overrides (gitignored — put your real API key here)
    if CONFIG_LOCAL_PATH.exists():
        try:
            data = json.loads(CONFIG_LOCAL_PATH.read_text(encoding="utf-8"))
            cfg.update(data)
        except Exception:
            pass

    # 3) Environment variable — highest priority
    env_token = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if env_token:
        cfg["pollinations_token"] = env_token

    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------- Chapter listing ----------

def list_english_chapters() -> List[Path]:
    """Alphabetical list of .txt files in EnglishSource/."""
    if not ENGLISH_SOURCE_DIR.exists():
        return []
    return sorted(
        p for p in ENGLISH_SOURCE_DIR.glob("*.txt")
        if p.is_file() and not p.name.lower().startswith("read_me")
    )


def list_tagged_chapters() -> List[Path]:
    """Alphabetical list of _tagged.txt files in HindiTagged/."""
    if not HINDI_TAGGED_DIR.exists():
        return []
    return sorted(
        p for p in HINDI_TAGGED_DIR.glob("*_tagged.txt") if p.is_file()
    )


def list_clean_chapters() -> List[Path]:
    """Alphabetical list of .txt files in HindiClean/."""
    if not HINDI_CLEAN_DIR.exists():
        return []
    return sorted(
        p for p in HINDI_CLEAN_DIR.glob("*.txt")
        if p.is_file() and not p.name.endswith("_tagged.txt")
    )


def chapter_stem(txt_path: Path) -> str:
    """Return the stem used to group files across folders.
    'chapter_01_tagged.txt' → 'chapter_01'
    'chapter_01.txt' → 'chapter_01'
    """
    name = txt_path.stem
    if name.endswith("_tagged"):
        name = name[:-7]
    return name


def prompts_folder_for(chapter_stem: str) -> Path:
    return PROMPTS_DIR / chapter_stem


def images_folder_for(chapter_stem: str) -> Path:
    return IMAGES_DIR / chapter_stem


def audio_single_path_for(chapter_stem: str) -> Path:
    return AUDIO_SINGLE_DIR / f"{chapter_stem}.mp3"


def audio_multi_path_for(chapter_stem: str) -> Path:
    return AUDIO_MULTI_DIR / f"{chapter_stem}.mp3"


def video_single_path_for(chapter_stem: str) -> Path:
    return VIDEOS_DIR / f"{chapter_stem}_single.mp4"


def video_multi_path_for(chapter_stem: str) -> Path:
    return VIDEOS_DIR / f"{chapter_stem}_multi.mp4"


# ---------- Text chunking ----------

_SENT_SPLIT = re.compile(r"(?<=[\.\!\?।])\s+|\n{2,}")


def split_sentences(text: str) -> List[str]:
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_text(text: str, max_chars: int = 2800) -> List[str]:
    """Greedy sentence-aware chunking. Falls back to hard split if a single
    sentence exceeds max_chars."""
    sentences = split_sentences(text)
    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0
    for sent in sentences:
        if len(sent) > max_chars:
            if buf:
                chunks.append(" ".join(buf))
                buf, buf_len = [], 0
            words = sent.split(" ")
            cur: List[str] = []
            cur_len = 0
            for w in words:
                if cur_len + len(w) + 1 > max_chars and cur:
                    chunks.append(" ".join(cur))
                    cur, cur_len = [w], len(w)
                else:
                    cur.append(w)
                    cur_len += len(w) + 1
            if cur:
                chunks.append(" ".join(cur))
            continue
        if buf_len + len(sent) + 1 > max_chars and buf:
            chunks.append(" ".join(buf))
            buf, buf_len = [sent], len(sent)
        else:
            buf.append(sent)
            buf_len += len(sent) + 1
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def voices_for(language: str) -> List[Dict[str, str]]:
    return _CURATED.get(language, [])


# ---------- Safe truncation (shared by split_prompts & pollinations_generate) ----------

def safe_truncate(text: str, max_chars: int) -> str:
    """Truncate *text* to ≤ *max_chars* WITHOUT breaking parenthetical
    ``(...)`` blocks, em-dash ``—...—`` spans, or words.

    If the cut point would fall inside a ``(...)`` block, the entire
    parenthetical is removed.  Guarantees syntactically valid output —
    no orphaned ``(``, no mid-word cuts.
    """
    if len(text) <= max_chars:
        return text

    # ---- find best cut position ----
    best = 0
    for sep in (". ", ", ", " — ", "  ", " "):
        pos = text.rfind(sep, 0, max_chars)
        if pos > max_chars // 2:
            best = pos
            break
    if best == 0:
        pos = text.rfind(" ", 0, max_chars)
        best = pos if pos > 0 else max_chars

    truncated = text[:best].rstrip(", —")

    # ---- fix broken parentheticals ----
    while True:
        opens = truncated.count("(")
        closes = truncated.count(")")
        if opens <= closes:
            break
        last_open = truncated.rfind("(")
        if last_open == -1:
            break
        truncated = truncated[:last_open].rstrip(", —")

    # ---- fix broken em-dash spans ----
    while True:
        count = truncated.count("—")
        if count % 2 == 0:
            break
        last_dash = truncated.rfind("—")
        if last_dash == -1:
            break
        truncated = truncated[:last_dash].rstrip(", —")

    return truncated.strip()
