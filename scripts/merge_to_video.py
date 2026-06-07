"""Final merge step: audio + images → video with xfade transitions.

For every chapter that has both images (Images/<chapter>/*.png) and audio:
  - AudioSingle/<chapter>.mp3 → Videos/<chapter>_single.mp4
  - AudioMulti/<chapter>.mp3  → Videos/<chapter>_multi.mp4

Each video:
  1. Splits total audio duration evenly across all images
  2. Loops each PNG as its own video stream of equal length
  3. Crossfades between images with random "diffusion/merge"-style transitions
  4. Encodes via Apple hardware h264_videotoolbox at configurable bitrate

VideoToolbox is REQUIRED (Apple Silicon). No CPU fallback.
"""
from __future__ import annotations

import argparse
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from common import (
    AUDIO_MULTI_DIR,
    AUDIO_SINGLE_DIR,
    IMAGES_DIR,
    VIDEOS_DIR,
    audio_multi_path_for,
    audio_single_path_for,
    load_config,
)

AUDIO_EXTS = {".mp3"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def list_image_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def which(cmd: str) -> str:
    p = shutil.which(cmd)
    if not p:
        sys.exit(f"{cmd} not found on PATH. Re-run setup.command first.")
    return p


def require_videotoolbox(ffmpeg: str) -> None:
    try:
        out = subprocess.check_output(
            [ffmpeg, "-hide_banner", "-encoders"],
            text=True, stderr=subprocess.STDOUT,
        )
    except Exception as e:
        sys.exit(f"Could not query ffmpeg encoders: {e}")
    if "h264_videotoolbox" not in out:
        sys.exit(
            "ERROR: this Mac doesn't expose h264_videotoolbox.\n"
            "  Apple Silicon (M1/M2/M3/M4) with a recent ffmpeg from "
            "Homebrew is required."
        )


def ffprobe_duration(ffprobe: str, path: Path) -> Optional[float]:
    try:
        out = subprocess.check_output(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except Exception:
        return None


def image_size(ffprobe: str, path: Path) -> Optional[tuple[int, int]]:
    try:
        out = subprocess.check_output(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0", str(path),
            ],
            text=True,
        ).strip()
        w, h = out.split("x")
        return int(w), int(h)
    except Exception:
        return None


def concat_escape(s: str) -> str:
    return s.replace("'", "'\\''")


def build_filtergraph(
    n_images: int,
    width: int,
    height: int,
    fps: int,
    per_image_dur: float,
    transition_dur: float,
    transitions: List[str],
) -> tuple[str, str, List[str]]:
    """Build ffmpeg filter_complex for N-image slideshow with random xfade."""
    scale_chain = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps},format=yuv420p"
    )

    parts: List[str] = []
    for i in range(n_images):
        parts.append(f"[{i}:v]{scale_chain}[s{i}]")

    chosen: List[str] = []
    if n_images == 1:
        return "; ".join(parts) + "; [s0]null[vout]", "vout", []

    step = per_image_dur - transition_dur
    prev_label = "s0"
    for k in range(1, n_images):
        trans = random.choice(transitions) if transitions else "fade"
        chosen.append(trans)
        offset = k * step
        out_label = f"v{k}" if k < n_images - 1 else "vout"
        parts.append(
            f"[{prev_label}][s{k}]xfade=transition={trans}:"
            f"duration={transition_dur:.3f}:offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label

    return "; ".join(parts), "vout", chosen


def render_video(
    audio_path: Path,
    image_folder: Path,
    out_mp4: Path,
    ffmpeg: str,
    ffprobe: str,
    *,
    bitrate_mbps: float,
    fps: int,
    transition_dur: float,
    transitions: List[str],
) -> bool:
    name = out_mp4.stem
    print(f"\n▶ {name}")

    pngs = list_image_files(image_folder)
    if not pngs:
        print(f"  skip: no images in {image_folder}")
        return False
    if not audio_path.exists():
        print(f"  skip: audio not found ({audio_path})")
        return False

    print(f"  audio : {audio_path.name}")
    print(f"  images: {len(pngs)}")

    duration = ffprobe_duration(ffprobe, audio_path)
    if not duration:
        print("  fail: could not read audio duration")
        return False

    n = len(pngs)
    if n == 1:
        per_image_dur = duration
        t_dur = 0.0
    else:
        max_t = max(0.1, duration / (n * 2.0))
        t_dur = min(transition_dur, max_t)
        per_image_dur = (duration + (n - 1) * t_dur) / n

    print(
        f"  audio length: {duration:.1f}s   per image: {per_image_dur:.2f}s"
        f"   transition: {t_dur:.2f}s"
    )

    size = image_size(ffprobe, pngs[0])
    if not size:
        print("  fail: could not read image dimensions")
        return False
    w, h = size
    w -= w % 2
    h -= h % 2
    print(f"  resolution  : {w}x{h} (from {pngs[0].name})")

    filtergraph, vout_label, picks = build_filtergraph(
        n_images=n, width=w, height=h, fps=fps,
        per_image_dur=per_image_dur, transition_dur=t_dur,
        transitions=transitions,
    )
    if picks:
        counts: dict[str, int] = {}
        for p in picks:
            counts[p] = counts.get(p, 0) + 1
        summary = ", ".join(
            f"{k}×{v}" for k, v in sorted(counts.items())
        )
        print(f"  transitions : {summary}")

    target_bitrate = f"{bitrate_mbps:.2f}M"
    maxrate = f"{bitrate_mbps * 1.6:.2f}M"
    bufsize = f"{bitrate_mbps * 3.0:.2f}M"

    cmd: List[str] = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stats",
    ]
    for png in pngs:
        cmd += ["-loop", "1", "-t", f"{per_image_dur:.6f}", "-i", str(png)]
    cmd += ["-i", str(audio_path)]

    cmd += [
        "-filter_complex", filtergraph,
        "-map", f"[{vout_label}]",
        "-map", f"{n}:a",
        "-c:v", "h264_videotoolbox",
        "-b:v", target_bitrate,
        "-maxrate", maxrate,
        "-bufsize", bufsize,
        "-allow_sw", "1",
        "-pix_fmt", "yuv420p",
        "-g", str(fps * 10),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(out_mp4),
    ]

    print(
        f"  encoding via: h264_videotoolbox  @ {target_bitrate} target  "
        f"({fps} fps, GOP {fps * 10})"
    )
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"  fail: ffmpeg exited with code {rc}")
        return False

    try:
        size_mb = out_mp4.stat().st_size / (1024 * 1024)
        est = size_mb / max(duration / 60.0, 0.01)
        print(f"  ✓ {out_mp4}  —  {size_mb:.1f} MB  ({est:.1f} MB/min)")
    except OSError:
        print(f"  ✓ {out_mp4}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge audio + images → mp4 with VideoToolbox + random xfade transitions.",
    )
    ap.add_argument(
        "--mode",
        choices=["single", "multi", "both"],
        default="both",
        help="Which audio track to merge: single-voice, multi-voice, or both (default).",
    )
    args = ap.parse_args()
    mode: str = args.mode

    ffmpeg = which("ffmpeg")
    ffprobe = which("ffprobe")
    require_videotoolbox(ffmpeg)

    cfg = load_config()
    bitrate_mbps = float(cfg.get("video_bitrate_mbps", 2.5))
    fps = int(cfg.get("video_fps", 30))
    transition_dur = float(cfg.get("transition_duration_sec", 1.0))
    transitions = list(cfg.get("transition_styles", [])) or ["fade"]

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    # Discover chapter stems from Images/
    if not IMAGES_DIR.exists():
        print(
            "No Images/ folder found. Run steps 1 and 2 first\n"
            "(split_prompts + generate_images)."
        )
        return 0

    chapter_dirs = sorted(
        d for d in IMAGES_DIR.iterdir()
        if d.is_dir() and list_image_files(d)
    )
    if not chapter_dirs:
        print(
            "No chapter image folders found in Images/.\n"
            "Run steps 1 and 2 first."
        )
        return 0

    mode_label = {
        "single": "Single-Voice",
        "multi": "Multi-Voice (Character)",
        "both": "Single + Multi Voice",
    }[mode]
    print(f"=== Video Merger — {mode_label} (ffmpeg + VideoToolbox) ===")
    print(f"Bitrate: {bitrate_mbps} Mbps  |  FPS: {fps}")
    print(f"Transition: {transition_dur}s")
    print(f"Found {len(chapter_dirs)} chapter(s) with images:\n")

    rendered = 0
    for img_dir in chapter_dirs:
        stem = img_dir.name

        if mode in ("single", "both"):
            single_audio = audio_single_path_for(stem)
            if single_audio.exists():
                out = VIDEOS_DIR / f"{stem}_single.mp4"
                if render_video(
                    single_audio, img_dir, out,
                    ffmpeg, ffprobe,
                    bitrate_mbps=bitrate_mbps, fps=fps,
                    transition_dur=transition_dur, transitions=transitions,
                ):
                    rendered += 1
            else:
                print(f"\n▶ {stem}_single — skip: audio not found ({single_audio})")

        if mode in ("multi", "both"):
            multi_audio = audio_multi_path_for(stem)
            if multi_audio.exists():
                out = VIDEOS_DIR / f"{stem}_multi.mp4"
                if render_video(
                    multi_audio, img_dir, out,
                    ffmpeg, ffprobe,
                    bitrate_mbps=bitrate_mbps, fps=fps,
                    transition_dur=transition_dur, transitions=transitions,
                ):
                    rendered += 1
            else:
                print(f"\n▶ {stem}_multi — skip: audio not found ({multi_audio})")

    print(f"\nDone — rendered {rendered} video(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
