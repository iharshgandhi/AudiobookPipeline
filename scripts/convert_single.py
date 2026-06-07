"""Single-voice audiobook builder via Microsoft Edge TTS (free).

Reads:   HindiClean/chapter_NN.txt
Writes:  AudioSingle/chapter_NN.mp3

Pipeline per chapter:
  1. Read Hindi text, chunk by sentences (~2800 chars).
  2. Synthesize chunks in parallel with edge-tts.
  3. Merge chunk MP3s into one MP3 with ffmpeg concat demuxer.
  4. Skip if the output .mp3 already exists.

Hardcoded for Hindi — uses the voice from config.json (default: hi-IN-MadhurNeural).
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

import edge_tts

from common import (
    AUDIO_SINGLE_DIR,
    HINDI_CLEAN_DIR,
    chunk_text,
    list_clean_chapters,
    load_config,
)

MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


# ---------- Synthesis ----------

async def synth_chunk(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    out_mp3: Path,
) -> Path:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(
                text, voice, rate=rate, pitch=pitch
            )
            with open(out_mp3, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            if out_mp3.exists() and out_mp3.stat().st_size > 0:
                return out_mp3
            raise RuntimeError("empty audio output")
        except Exception as e:
            last_err = e
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(
                f"    chunk failed (attempt {attempt}/{MAX_RETRIES}): {e}; "
                f"retrying in {wait:.1f}s"
            )
            await asyncio.sleep(wait)
    raise RuntimeError(
        f"chunk synthesis failed after {MAX_RETRIES} attempts: {last_err}"
    )


async def synth_chapter(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    work_dir: Path,
    parallel: int,
    chunk_chars: int,
    rate_limit_gap: float = 1.0,
) -> List[Path]:
    chunks = chunk_text(text, chunk_chars)
    print(f"  split into {len(chunks)} chunk(s), {parallel} in parallel (1s gap between starts)")

    mp3_paths = [
        work_dir / f"chunk_{i:04}.mp3" for i in range(len(chunks))
    ]

    sem = asyncio.Semaphore(parallel)
    done = {"n": 0}
    total = len(chunks)
    last_req_ts = {"t": 0.0}
    lock = asyncio.Lock()

    async def run_one(i: int) -> None:
        async with sem:
            # Rate-limit: ensure at least `rate_limit_gap` seconds between
            # any two Edge-TTS requests to avoid server-side throttling.
            async with lock:
                now = time.monotonic()
                wait = rate_limit_gap - (now - last_req_ts["t"])
                if wait > 0:
                    await asyncio.sleep(wait)
                last_req_ts["t"] = time.monotonic()
            await synth_chunk(chunks[i], voice, rate, pitch, mp3_paths[i])
            done["n"] += 1
            print(f"  [{done['n']:>4}/{total}] chunk {i + 1} done")

    await asyncio.gather(*(run_one(i) for i in range(len(chunks))))
    return mp3_paths


# ---------- Merge ----------

def ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        sys.exit("ffmpeg not found on PATH. Re-run setup.command first.")
    return path


def merge_mp3s(ffmpeg: str, chunk_mp3s: List[Path], out_mp3: Path) -> None:
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        listfile = Path(f.name)
        for p in chunk_mp3s:
            esc = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{esc}'\n")
    try:
        # Always re-encode — stream-copying MP3 chunks from different
        # synthesis runs causes non-monotonically-increasing DTS warnings.
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


# ---------- Driver ----------

async def process_chapter(
    txt_path: Path,
    voice: str,
    rate: str,
    pitch: str,
    parallel: int,
    chunk_chars: int,
    ffmpeg: str,
) -> None:
    stem = txt_path.stem
    out_mp3 = AUDIO_SINGLE_DIR / f"{stem}.mp3"

    if out_mp3.exists():
        print(f"\nSkipping {txt_path.name}: {out_mp3.name} already exists")
        return

    print(f"\n>>> {txt_path.name}  →  AudioSingle/{out_mp3.name}")
    text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        print("  empty file, skipping")
        return

    AUDIO_SINGLE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"tts_{stem}_", dir=str(AUDIO_SINGLE_DIR)
    ) as tmp:
        work_dir = Path(tmp)
        t0 = time.time()
        chunk_mp3s = await synth_chapter(
            text, voice, rate, pitch, work_dir, parallel, chunk_chars
        )
        print(f"  merging {len(chunk_mp3s)} chunks ...")
        merge_mp3s(ffmpeg, chunk_mp3s, out_mp3)
        dt = time.time() - t0
        size_mb = out_mp3.stat().st_size / (1024 * 1024)
        print(f"  done in {dt:.1f}s — {out_mp3.name} ({size_mb:.1f} MB)")


def main() -> int:
    cfg = load_config()
    ffmpeg = ensure_ffmpeg()

    voice = cfg.get("voice_hi", cfg.get("voice", "hi-IN-MadhurNeural"))
    rate = cfg.get("rate", "+0%")
    pitch = cfg.get("pitch", "+0Hz")
    parallel = int(cfg.get("parallel_chunks", 4))
    chunk_chars = int(cfg.get("chunk_chars", 2800))

    chapters = list_clean_chapters()
    if not chapters:
        print(
            "No .txt files found in HindiClean/.\n"
            "Run step 3 (strip_tags) first, or place clean Hindi chapters there."
        )
        return 0

    print("=== Single-Voice Audio Converter (Edge TTS) ===")
    print(f"Voice    : {voice}")
    print(f"Rate     : {rate}  |  Pitch: {pitch}")
    print(f"Parallel : {parallel} chunks at a time")
    print(f"Found {len(chapters)} chapter(s) in HindiClean/:\n")

    for ch in chapters:
        out_mp3 = AUDIO_SINGLE_DIR / f"{ch.stem}.mp3"
        marker = "  [already done — will skip]" if out_mp3.exists() else ""
        print(f"  - {ch.name}  →  AudioSingle/{out_mp3.name}{marker}")

    async def run_all() -> None:
        for ch in chapters:
            await process_chapter(
                ch, voice, rate, pitch, parallel, chunk_chars, ffmpeg
            )

    asyncio.run(run_all())
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
