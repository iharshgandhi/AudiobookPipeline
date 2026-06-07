"""Multi-voice (character) audiobook builder via Microsoft Edge TTS.

Reads:   HindiTagged/chapter_NN_tagged.txt
         character_voices.txt (project root)
Writes:  AudioMulti/chapter_NN.mp3

Each character's dialogue is wrapped in tags in the source file, e.g.:
    घना जंगल था। <Alice>कौन है वहाँ?</Alice> उसने पूछा।

Every character speaks in the voice assigned in character_voices.txt;
ALL text outside tags is read by the NARRATOR voice.

Pauses are inserted between spans (longer when speaker changes), after
chapter headings, at paragraph breaks, and wherever <pause> or <pause:800>
tags appear.

Tags are stripped before synthesis — they only route the voice.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import edge_tts

from common import (
    AUDIO_MULTI_DIR,
    CHARACTER_VOICES_PATH,
    HINDI_TAGGED_DIR,
    chapter_stem,
    chunk_text,
    list_tagged_chapters,
    load_config,
)

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
NARRATOR = "NARRATOR"

# ---------------------------------------------------------------------------
#  Alias table:  friendly name  →  edge-tts short name
# ---------------------------------------------------------------------------
VOICE_ALIASES: Dict[str, str] = {
    # native Hindi
    "swara": "hi-IN-SwaraNeural",
    "madhur": "hi-IN-MadhurNeural",
    # Marathi (Devanagari script, reads Hindi well)
    "aarohi": "mr-IN-AarohiNeural",
    "manohar": "mr-IN-ManoharNeural",
    # Nepali (Devanagari script, reads Hindi cleanly)
    "hemkala": "ne-NP-HemkalaNeural",
    "sagar": "ne-NP-SagarNeural",
    # Multilingual (proven to handle Hindi text)
    "ava": "en-US-AvaMultilingualNeural",
    "andrew": "en-US-AndrewMultilingualNeural",
    "emma": "en-US-EmmaMultilingualNeural",
    "brian": "en-US-BrianMultilingualNeural",
    "seraphina": "de-DE-SeraphinaMultilingualNeural",
    "florian": "de-DE-FlorianMultilingualNeural",
    "vivienne": "fr-FR-VivienneMultilingualNeural",
    "remy": "fr-FR-RemyMultilingualNeural",
}


def resolve_voice(token: str) -> str:
    token = token.strip()
    alias = VOICE_ALIASES.get(token.lower())
    if alias:
        return alias
    return token


# ---------------------------------------------------------------------------
#  Voice map parsing
# ---------------------------------------------------------------------------

class VoiceSpec:
    __slots__ = ("voice", "pitch", "rate", "volume")

    def __init__(
        self, voice: str, pitch: int = 0, rate: int = 0, volume: int = 0
    ):
        self.voice = voice
        self.pitch = pitch
        self.rate = rate
        self.volume = volume

    @property
    def pitch_s(self) -> str:
        return f"{'+' if self.pitch >= 0 else ''}{self.pitch}Hz"

    @property
    def rate_s(self) -> str:
        return f"{'+' if self.rate >= 0 else ''}{self.rate}%"

    @property
    def volume_s(self) -> str:
        return f"{'+' if self.volume >= 0 else ''}{self.volume}%"


_MAP_LINE = re.compile(r"^\s*([^=#]+?)\s*=\s*\(([^)]*)\)\s*$")


def _to_int(s: str, default: int = 0) -> int:
    s = s.strip().rstrip("%").rstrip("Hz").rstrip("hz").strip()
    if not s:
        return default
    try:
        return int(round(float(s)))
    except ValueError:
        return default


def load_voice_map(cfg: dict) -> Dict[str, VoiceSpec]:
    """Parse character_voices.txt → {lowercased_name: VoiceSpec}."""
    out: Dict[str, VoiceSpec] = {}
    if CHARACTER_VOICES_PATH.exists():
        for raw in CHARACTER_VOICES_PATH.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = _MAP_LINE.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            parts = [p.strip() for p in m.group(2).split(",")]
            if not parts or not parts[0]:
                continue
            voice = resolve_voice(parts[0])
            pitch = _to_int(parts[1]) if len(parts) > 1 else 0
            rate = _to_int(parts[2]) if len(parts) > 2 else 0
            volume = _to_int(parts[3]) if len(parts) > 3 else 0
            out[name.lower()] = VoiceSpec(voice, pitch, rate, volume)
    # Guarantee a narrator exists.
    if NARRATOR.lower() not in out:
        out[NARRATOR.lower()] = VoiceSpec(
            cfg.get("narrator_voice", "hi-IN-MadhurNeural")
        )
    return out


# ---------------------------------------------------------------------------
#  Tag parsing → ordered render plan
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(
    r"<pause(?::(\d+))?\s*/?>|<([A-Za-z][A-Za-z0-9_]*)>(.*?)</\2>",
    re.DOTALL,
)
STRAY_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_]*(?::\d+)?\s*/?>")

HEADING_RE = re.compile(
    r"^\s*("
    r"अध्याय|भाग|प्रस्तावना|उपसंहार|प्रकरण|"
    r"chapter|part|prologue|epilogue|book|section"
    r")\b",
    re.IGNORECASE,
)
NUM_HEADING_RE = re.compile(r"^\s*[0-9०-९]+\s*[\.:।]?\s*$")


def is_heading(para: str) -> bool:
    if "\n" in para.strip():
        return False
    if len(para.strip()) > 60:
        return False
    return bool(HEADING_RE.match(para) or NUM_HEADING_RE.match(para))


class Plan:
    """Ordered list of audio + silence units, with smart gap insertion."""

    def __init__(self, cfg: dict):
        self.units: List[dict] = []
        self.prev_speaker: Optional[str] = None
        self.gap_same = int(cfg.get("gap_same_ms", 220))
        self.speaker_gap = int(cfg.get("speaker_gap_ms", 420))
        self.heading_gap = int(cfg.get("heading_gap_ms", 750))
        self.para_gap = int(cfg.get("paragraph_gap_ms", 450))
        self.default_pause = int(cfg.get("default_pause_ms", 550))
        self.lead_in = int(cfg.get("lead_in_ms", 250))

    def _has_audio(self) -> bool:
        return any(u["type"] == "audio" for u in self.units)

    def add_gap(self, ms: int) -> None:
        if ms <= 0:
            return
        if self.units and self.units[-1]["type"] == "sil":
            self.units[-1]["ms"] = max(self.units[-1]["ms"], ms)
        else:
            self.units.append({"type": "sil", "ms": ms})

    def add_audio(self, text: str, speaker: str, spec: VoiceSpec) -> None:
        text = STRAY_TAG_RE.sub("", text).strip()
        if not text:
            return
        trailing_sil = bool(
            self.units and self.units[-1]["type"] == "sil"
        )
        if self._has_audio() and not trailing_sil:
            self.add_gap(
                self.speaker_gap
                if speaker != self.prev_speaker
                else self.gap_same
            )
        self.units.append({
            "type": "audio",
            "text": text,
            "speaker": speaker,
            "voice": spec.voice,
            "pitch": spec.pitch_s,
            "rate": spec.rate_s,
            "volume": spec.volume_s,
        })
        self.prev_speaker = speaker


def build_plan(
    text: str, vmap: Dict[str, VoiceSpec], cfg: dict
) -> Tuple[Plan, List[str]]:
    plan = Plan(cfg)
    warnings: List[str] = []
    chunk_chars = int(cfg.get("chunk_chars", 2800))
    narr_spec = vmap[NARRATOR.lower()]
    seen_missing: set = set()

    def spec_for(name: str) -> VoiceSpec:
        spec = vmap.get(name.lower())
        if spec is None:
            if name.lower() not in seen_missing:
                seen_missing.add(name.lower())
                warnings.append(
                    f"character '{name}' has no line in character_voices.txt — "
                    f"using the NARRATOR voice for it"
                )
            return narr_spec
        return spec

    def emit_narrator(block: str) -> None:
        paragraphs = re.split(r"\n\s*\n", block)
        first = True
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if not first:
                plan.add_gap(plan.para_gap)
            first = False
            if is_heading(para):
                plan.add_audio(para, NARRATOR, narr_spec)
                plan.add_gap(plan.heading_gap)
            else:
                for ch in chunk_text(para, chunk_chars):
                    plan.add_audio(ch, NARRATOR, narr_spec)

    plan.add_gap(plan.lead_in)

    pos = 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            emit_narrator(text[pos : m.start()])
        if m.group(2) is None:
            # pause tag
            ms = int(m.group(1)) if m.group(1) else plan.default_pause
            plan.add_gap(ms)
        else:
            name, body = m.group(2), m.group(3)
            spec = spec_for(name)
            for ch in chunk_text(body, chunk_chars):
                plan.add_audio(ch, name, spec)
        pos = m.end()
    if pos < len(text):
        emit_narrator(text[pos:])

    return plan, warnings


# ---------------------------------------------------------------------------
#  Synthesis & merge
# ---------------------------------------------------------------------------

def ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        sys.exit("ffmpeg not found on PATH. Re-run setup.command first.")
    return path


async def synth_span(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    out_wav: Path,
) -> Path:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(
                text, voice, rate=rate, pitch=pitch
            )
            with open(out_wav, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            if out_wav.exists() and out_wav.stat().st_size > 0:
                return out_wav
            raise RuntimeError("empty audio output")
        except Exception as e:
            last_err = e
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            preview = text[:80].replace("\n", " ")
            print(
                f"    span failed (attempt {attempt}/{MAX_RETRIES}): {e}"
            )
            print(
                f"      voice={voice}  len={len(text)}  "
                f"text=\"{preview}{'…' if len(text) > 80 else ''}\""
            )
            print(f"      retrying in {wait:.1f}s")
            await asyncio.sleep(wait)
    raise RuntimeError(
        f"span synthesis failed after {MAX_RETRIES} attempts: {last_err}"
    )


async def synth_all_spans(
    plan: Plan, work_dir: Path, parallel: int, narr_spec: 'VoiceSpec',
    rate_limit_gap: float = 1.0,
) -> List[Path]:
    """Synthesize audio spans in parallel, produce one .mp3 per audio unit
    (silences are generated inline by merge_plan)."""
    audio_paths: List[Optional[Path]] = []
    for unit in plan.units:
        if unit["type"] == "audio":
            audio_paths.append(None)  # placeholder
        else:
            audio_paths.append(None)  # silence — no file needed

    sem = asyncio.Semaphore(parallel)
    done = {"n": 0}
    total_audio = sum(1 for u in plan.units if u["type"] == "audio")
    last_req_ts = {"t": 0.0}
    lock = asyncio.Lock()

    async def synth_one(idx: int, unit: dict) -> None:
        # Rate-limit: ensure at least `rate_limit_gap` seconds between
        # any two Edge-TTS requests to avoid server-side throttling.
        async with lock:
            now = time.monotonic()
            wait = rate_limit_gap - (now - last_req_ts["t"])
            if wait > 0:
                await asyncio.sleep(wait)
            last_req_ts["t"] = time.monotonic()
        async with sem:
            out = work_dir / f"span_{idx:04d}.mp3"
            try:
                await synth_span(
                    unit["text"],
                    unit["voice"],
                    unit["rate"],
                    unit["pitch"],
                    out,
                )
            except RuntimeError:
                # Voice failed (e.g. monolingual English voice on Hindi text).
                # Fall back to the NARRATOR voice so the book isn't missing audio.
                spk = unit.get("speaker", "?")
                print(
                    f"      → falling back to NARRATOR voice "
                    f"({narr_spec.voice}) for \"{spk}\""
                )
                await synth_span(
                    unit["text"],
                    narr_spec.voice,
                    narr_spec.rate_s,
                    narr_spec.pitch_s,
                    out,
                )
            audio_paths[idx] = out
            done["n"] += 1
            label = unit.get("speaker", "?")
            print(f"  [{done['n']:>4}/{total_audio}] {label}")

    tasks = []
    for idx, unit in enumerate(plan.units):
        if unit["type"] == "audio":
            tasks.append(synth_one(idx, unit))

    if tasks:
        await asyncio.gather(*tasks)

    return [p for p in audio_paths if p is not None]


def generate_silence(ffmpeg: str, duration_ms: int, out_mp3: Path) -> None:
    dur_sec = max(0.001, duration_ms / 1000.0)
    subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
            "-t", f"{dur_sec:.6f}",
            "-c:a", "libmp3lame", "-b:a", "64k",
            str(out_mp3),
        ],
        check=True,
    )


def merge_plan(
    ffmpeg: str,
    plan: Plan,
    audio_paths: List[Optional[Path]],
    work_dir: Path,
    out_mp3: Path,
) -> None:
    """Build a concat list: for each unit, either the synthesized audio file
    or a generated silence file, then concat them all."""
    concat_files: List[Path] = []
    audio_idx = 0

    for unit in plan.units:
        if unit["type"] == "audio":
            path = audio_paths[audio_idx]
            if path and path.exists():
                concat_files.append(path)
            audio_idx += 1
        else:
            # silence
            sil_path = work_dir / f"sil_{len(concat_files):04d}.mp3"
            generate_silence(ffmpeg, unit["ms"], sil_path)
            concat_files.append(sil_path)

    if not concat_files:
        print("  warn: nothing to merge")
        return

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        listfile = Path(f.name)
        for p in concat_files:
            esc = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{esc}'\n")
    try:
        # Always re-encode — stream-copying MP3 chunks from different
        # synthesis runs (Edge TTS + silence) causes non-monotonically-
        # increasing DTS warnings that -fflags +genpts alone cannot fix.
        subprocess.run(
            [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(listfile),
                "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3),
            ],
            check=True,
        )
    finally:
        listfile.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
#  Driver
# ---------------------------------------------------------------------------

async def process_chapter(
    txt_path: Path,
    vmap: Dict[str, VoiceSpec],
    cfg: dict,
    parallel: int,
    ffmpeg: str,
) -> None:
    stem = chapter_stem(txt_path)
    out_mp3 = AUDIO_MULTI_DIR / f"{stem}.mp3"

    if out_mp3.exists():
        print(f"\nSkipping {txt_path.name}: {out_mp3.name} already exists")
        return

    print(f"\n>>> {txt_path.name}  →  AudioMulti/{out_mp3.name}")
    text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        print("  empty file, skipping")
        return

    AUDIO_MULTI_DIR.mkdir(parents=True, exist_ok=True)
    plan, warnings = build_plan(text, vmap, cfg)
    for w in warnings:
        print(f"  ⚠ {w}")

    audio_count = sum(1 for u in plan.units if u["type"] == "audio")
    sil_count = sum(1 for u in plan.units if u["type"] == "sil")
    print(
        f"  plan: {audio_count} audio spans, {sil_count} silences, "
        f"{parallel} parallel"
    )

    with tempfile.TemporaryDirectory(
        prefix=f"tts_char_{stem}_", dir=str(AUDIO_MULTI_DIR)
    ) as tmp:
        work_dir = Path(tmp)
        t0 = time.time()

        audio_paths = await synth_all_spans(
            plan, work_dir, parallel, narr_spec=vmap[NARRATOR.lower()]
        )

        print(f"  merging {len(audio_paths)} spans + silences ...")
        merge_plan(ffmpeg, plan, audio_paths, work_dir, out_mp3)

        dt = time.time() - t0
        size_mb = out_mp3.stat().st_size / (1024 * 1024)
        print(f"  done in {dt:.1f}s — {out_mp3.name} ({size_mb:.1f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Multi-voice audiobook builder from tagged Hindi chapters."
    )
    ap.add_argument(
        "--parallel",
        type=int,
        default=None,
        help="Number of parallel synthesis tasks (default: from config.json).",
    )
    args = ap.parse_args()

    cfg = load_config()
    ffmpeg = ensure_ffmpeg()
    vmap = load_voice_map(cfg)

    tagged = list_tagged_chapters()
    if not tagged:
        print(
            "No *_tagged.txt files found in HindiTagged/.\n"
            "After translating chapters with character tags via the AI mega-prompt,\n"
            "save the tagged files to HindiTagged/, then re-run."
        )
        return 0

    parallel = args.parallel or int(cfg.get("parallel_chunks", 4))

    print("=== Multi-Voice Audio Converter (Edge TTS) ===")
    print(f"Characters mapped: {len(vmap)} voice(s)")
    print(f"Parallel: {parallel} spans at a time")
    print(f"Found {len(tagged)} tagged chapter(s) in HindiTagged/:\n")

    for ch in tagged:
        stem = chapter_stem(ch)
        out_mp3 = AUDIO_MULTI_DIR / f"{stem}.mp3"
        marker = "  [already done — will skip]" if out_mp3.exists() else ""
        print(f"  - {ch.name}  →  AudioMulti/{out_mp3.name}{marker}")

    async def run_all() -> None:
        for ch in tagged:
            await process_chapter(ch, vmap, cfg, parallel, ffmpeg)

    asyncio.run(run_all())
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
