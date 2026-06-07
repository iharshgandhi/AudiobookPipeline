"""Cloud image generation via Pollinations.ai (gen.pollinations.ai).

Reads prompts from:    Prompts/<chapter>/Image<N>.txt
Writes images to:      Images/<chapter>/Image<N>.png

Uses API key from config.local.json (gitignored) or POLLINATIONS_API_KEY env var.
Re-run safety: skips any prompt whose .png already exists.
Delete a .png and re-run to regenerate just that image.
"""

from __future__ import annotations

import io
import sys
import time
import urllib.parse
from pathlib import Path

import requests

from common import IMAGES_DIR, PROMPTS_DIR, load_config

ENDPOINT = "https://gen.pollinations.ai/image/"
TIMEOUT = 180
WARN_THRESHOLD = 500


def main() -> None:
    from PIL import Image

    cfg = load_config()
    TOKEN = cfg.get("pollinations_token", "").strip()
    MODEL = cfg.get("poll_model", "flux").strip()
    WIDTH = int(cfg.get("poll_width", 1280))
    HEIGHT = int(cfg.get("poll_height", 720))

    DEFAULT_GAP = 16.0 if not TOKEN else 6.0
    GAP_SEC = float(cfg.get("poll_gap_sec", DEFAULT_GAP))

    if not PROMPTS_DIR.exists():
        sys.exit("Prompts/ folder not found. Run step 1 (split_prompts) first.")

    # Find all prompt files: Prompts/*/Image*.txt
    all_prompt_files = sorted(PROMPTS_DIR.glob("*/Image*.txt"))
    if not all_prompt_files:
        sys.exit(
            "No prompt files found under Prompts/*/Image*.txt.\n"
            "Run step 1 (split_prompts) first."
        )

    # Build queue: skip prompts whose image already exists
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    queue: list[tuple[Path, Path]] = []
    for p in all_prompt_files:
        chapter_name = p.parent.name  # e.g. "chapter_01"
        out_dir = IMAGES_DIR / chapter_name
        out = out_dir / p.with_suffix(".png").name
        if not out.exists():
            queue.append((p, out))

    tier = (
        "authenticated (no watermark, no logo)"
        if TOKEN
        else "unauthenticated (may show watermark)"
    )
    print(
        f"[pollinations] model={MODEL}  {WIDTH}x{HEIGHT}  "
        f"gap={GAP_SEC}s  tier={tier}"
    )
    print(
        f"[pollinations] {len(all_prompt_files)} prompts total, "
        f"{len(queue)} pending, "
        f"{len(all_prompt_files) - len(queue)} already rendered"
    )

    if not queue:
        print("[pollinations] Nothing to do — all images already exist.")
        return

    if len(queue) > WARN_THRESHOLD:
        eta_min = (len(queue) * GAP_SEC) / 60.0
        print(
            f"[pollinations] {len(queue)} images at {GAP_SEC}s/each "
            f"= roughly {eta_min:.0f} minutes total. "
            f"Ctrl+C any time, re-run to resume."
        )

    headers = {"User-Agent": "audiobook-pipeline/2.0"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    rendered = 0
    failed = 0
    last_call_ts = 0.0
    total = len(queue)

    for idx, (prompt_path, out_path) in enumerate(queue, start=1):
        chapter_name = prompt_path.parent.name
        img_name = prompt_path.stem
        label = f"{chapter_name}/{img_name}"

        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        if not prompt_text:
            print(f"[skip] {label} (empty prompt)")
            continue

        # Pace requests
        elapsed = time.time() - last_call_ts
        if elapsed < GAP_SEC:
            time.sleep(GAP_SEC - elapsed)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        seed = abs(hash(prompt_path.name)) % (2 ** 31)
        params = {
            "model": MODEL,
            "width": WIDTH,
            "height": HEIGHT,
            "seed": seed,
        }
        url = ENDPOINT + urllib.parse.quote(prompt_text, safe="")

        print(f"\n[{idx}/{total}] {label}")
        preview = (
            prompt_text if len(prompt_text) <= 110
            else prompt_text[:107] + "..."
        )
        print(f'        "{preview}"')

        attempt = 0
        last_err: str | None = None
        while attempt < 3:
            attempt += 1
            last_call_ts = time.time()
            try:
                resp = requests.get(
                    url, params=params, headers=headers, timeout=TIMEOUT
                )
                if resp.status_code == 429:
                    backoff = 30 * attempt
                    print(
                        f"        429 rate-limited; "
                        f"waiting {backoff}s and retrying..."
                    )
                    time.sleep(backoff)
                    continue
                if resp.status_code >= 500:
                    backoff = 20 * attempt
                    print(
                        f"        {resp.status_code} server error; "
                        f"waiting {backoff}s..."
                    )
                    time.sleep(backoff)
                    continue
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    break

                try:
                    img = Image.open(io.BytesIO(resp.content))
                    img.load()
                except Exception as e:
                    last_err = f"invalid image data: {e}"
                    break

                img.save(out_path, "PNG")
                size_kb = len(resp.content) // 1024
                print(
                    f"        → Images/{chapter_name}/{out_path.name} "
                    f"({size_kb} KB)"
                )
                rendered += 1
                last_err = None
                break

            except requests.exceptions.Timeout:
                backoff = 20 * attempt
                print(f"        timeout after {TIMEOUT}s; retrying in {backoff}s...")
                time.sleep(backoff)
                last_err = "timeout"
                continue
            except requests.exceptions.RequestException as e:
                last_err = f"{e.__class__.__name__}: {e}"
                backoff = 15 * attempt
                print(f"        network error; retrying in {backoff}s...")
                time.sleep(backoff)
                continue

        if last_err is not None:
            print(f"        FAILED after {attempt} attempts: {last_err}")
            failed += 1

    print(
        f"\n[done] rendered={rendered}  failed={failed}  "
        f"remaining={max(0, total - rendered - failed)}"
    )


if __name__ == "__main__":
    main()
