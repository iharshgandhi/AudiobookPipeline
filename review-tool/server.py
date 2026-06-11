#!/usr/bin/env python3
"""Image Review Tool — lightweight HTTP server for reviewing/approving/rejecting prompt-based images.

Folder layout:
    review-tool/server.py       ← this file
    review-tool/index.html      ← the SPA frontend
    ../Prompts/<chapter>/       ← prompt .txt files (read/write)
    ../Images/<chapter>/        ← image .png files (read/delete)

Run:  python3 server.py
Open: http://localhost:8765
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from PIL import Image

PORT = 8765
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PROMPTS_DIR = PROJECT_ROOT / "Prompts"
IMAGES_DIR = PROJECT_ROOT / "Images"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}

CHAPTER_RE = re.compile(r"^chapter_\d{2}$")
IMAGE_STEM_RE = re.compile(r"^Image\d+$")


def list_chapters() -> list[dict]:
    """Scan Prompts/ and Images/ directories and return the full listing."""
    chapters: list[dict] = []
    if not PROMPTS_DIR.exists():
        return chapters

    prompt_dirs = sorted(
        d for d in PROMPTS_DIR.iterdir()
        if d.is_dir() and CHAPTER_RE.match(d.name)
    )

    for prompt_dir in prompt_dirs:
        chapter_name = prompt_dir.name
        image_dir = IMAGES_DIR / chapter_name

        prompt_files = sorted(
            (f for f in prompt_dir.iterdir() if f.suffix == ".txt" and IMAGE_STEM_RE.match(f.stem)),
            key=lambda p: int(re.search(r"\d+", p.stem).group()),  # type: ignore[union-attr]
        )

        images: list[dict] = []
        for pf in prompt_files:
            image_name = pf.stem
            image_path = image_dir / f"{image_name}.png"
            images.append({
                "name": image_name,
                "hasPrompt": True,
                "hasImage": image_path.exists(),
            })

        if images:
            chapters.append({
                "name": chapter_name,
                "images": images,
            })

    return chapters


def is_safe(name: str) -> bool:
    """Reject path-traversal characters."""
    return ".." not in name and "/" not in name and "\\" not in name


# ── Pollinations.ai config / helpers ────────────────────────────────────────

CONFIG_PATH = PROJECT_ROOT / "config.json"
CONFIG_LOCAL_PATH = PROJECT_ROOT / "config.local.json"

POLL_ENDPOINT = "https://gen.pollinations.ai/image/"
POLL_TIMEOUT = 180


def load_poll_config() -> dict:
    """Load pollinations settings from config.json + config.local.json, never
    storing the API key anywhere else."""
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    if CONFIG_LOCAL_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_LOCAL_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def pollinations_generate(prompt_text: str) -> bytes | None:
    """Call the Pollinations.ai API and return raw PNG bytes, or None on
    failure.  Retries match the logic in pollinations_generate.py."""
    cfg = load_poll_config()
    token = cfg.get("pollinations_token", "").strip()
    model = cfg.get("poll_model", "flux").strip()
    width = int(cfg.get("poll_width", 1280))
    height = int(cfg.get("poll_height", 720))

    if not prompt_text.strip():
        return None

    # Use a stable seed from the prompt text so re-runs give the same image
    seed = abs(hash(prompt_text)) % (2 ** 31)
    params = {"model": model, "width": width, "height": height, "seed": seed}

    headers = {"User-Agent": "audiobook-pipeline/2.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = POLL_ENDPOINT + urllib.parse.quote(prompt_text, safe="")
    last_err: str | None = None

    for attempt in range(1, 4):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=POLL_TIMEOUT)
            if resp.status_code == 429:
                backoff = 30 * attempt
                print(f"        429 rate-limited; waiting {backoff}s...")
                time.sleep(backoff)
                continue
            if resp.status_code >= 500:
                backoff = 20 * attempt
                print(f"        {resp.status_code} server error; waiting {backoff}s...")
                time.sleep(backoff)
                continue
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                break

            # Validate that the response is actually a PNG
            try:
                img = Image.open(io.BytesIO(resp.content))
                img.load()
            except Exception as e:
                last_err = f"invalid image data: {e}"
                break

            return resp.content

        except requests.exceptions.Timeout:
            backoff = 20 * attempt
            print(f"        timeout after {POLL_TIMEOUT}s; retrying in {backoff}s...")
            time.sleep(backoff)
            last_err = "timeout"
            continue
        except requests.exceptions.RequestException as e:
            last_err = f"{e.__class__.__name__}: {e}"
            backoff = 15 * attempt
            print(f"        network error; retrying in {backoff}s...")
            time.sleep(backoff)
            continue

    print(f"        FAILED after all attempts: {last_err}")
    return None


class ReviewHandler(BaseHTTPRequestHandler):

    # ── helpers ──────────────────────────────────────────────────────────

    def _send_json(self, data: dict, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_error("File not found", 404)
            return
        ext = path.suffix.lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self._cors()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def _read_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    # ── routes ───────────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # --- /api/scan ---
        if path == "/api/scan":
            chapters = list_chapters()
            self._send_json({"chapters": chapters})
            return

        # --- /api/prompt?chapter=X&image=Y ---
        if path == "/api/prompt":
            chapter = (params.get("chapter") or [None])[0]
            image = (params.get("image") or [None])[0]
            if not chapter or not image:
                self._send_error("Missing 'chapter' or 'image' parameter")
                return
            if not is_safe(chapter) or not is_safe(image):
                self._send_error("Invalid path component", 400)
                return
            prompt_path = PROMPTS_DIR / chapter / f"{image}.txt"
            if not prompt_path.exists():
                self._send_error("Prompt file not found", 404)
                return
            try:
                text = prompt_path.read_text(encoding="utf-8")
                self._send_json({"chapter": chapter, "image": image, "text": text})
            except Exception as e:
                self._send_error(f"Failed to read prompt: {e}", 500)
            return

        # --- /api/image?chapter=X&image=Y ---
        if path == "/api/image":
            chapter = (params.get("chapter") or [None])[0]
            image = (params.get("image") or [None])[0]
            if not chapter or not image:
                self._send_error("Missing 'chapter' or 'image' parameter")
                return
            if not is_safe(chapter) or not is_safe(image):
                self._send_error("Invalid path component", 400)
                return
            image_path = IMAGES_DIR / chapter / f"{image}.png"
            self._send_file(image_path)
            return

        # --- Static files ---
        if path == "/" or path == "":
            path = "/index.html"
        static_path = SCRIPT_DIR / path.lstrip("/")
        try:
            static_path.relative_to(SCRIPT_DIR)
        except ValueError:
            self._send_error("Forbidden", 403)
            return
        if static_path.is_dir():
            static_path = static_path / "index.html"
        self._send_file(static_path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_body()

        # --- /api/save-prompt ---
        if path == "/api/save-prompt":
            chapter = data.get("chapter")
            image = data.get("image")
            text = data.get("text")
            if not chapter or not image or text is None:
                self._send_error("Missing 'chapter', 'image', or 'text' in body")
                return
            if not is_safe(chapter) or not is_safe(image):
                self._send_error("Invalid path component", 400)
                return
            prompt_path = PROMPTS_DIR / chapter / f"{image}.txt"
            if not prompt_path.exists():
                self._send_error("Prompt file not found", 404)
                return
            try:
                prompt_path.write_text(text, encoding="utf-8")
                self._send_json({"success": True, "saved": True})
            except Exception as e:
                self._send_error(f"Failed to save prompt: {e}", 500)
            return

        # --- /api/reject ---
        if path == "/api/reject":
            chapter = data.get("chapter")
            image = data.get("image")
            text = data.get("text")
            if not chapter or not image or text is None:
                self._send_error("Missing 'chapter', 'image', or 'text' in body")
                return
            if not is_safe(chapter) or not is_safe(image):
                self._send_error("Invalid path component", 400)
                return

            # 1. Save prompt (always, even if prompt file doesn't exist yet)
            prompt_path = PROMPTS_DIR / chapter / f"{image}.txt"
            saved = False
            if prompt_path.exists():
                try:
                    prompt_path.write_text(text, encoding="utf-8")
                    saved = True
                except Exception as e:
                    self._send_error(f"Failed to save prompt: {e}", 500)
                    return
            else:
                # Create the prompt file even if it didn't exist
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(text, encoding="utf-8")
                saved = True

            # 2. Delete image
            image_path = IMAGES_DIR / chapter / f"{image}.png"
            deleted = False
            if image_path.exists():
                try:
                    image_path.unlink()
                    deleted = True
                except Exception as e:
                    self._send_error(f"Failed to delete image: {e}", 500)
                    return

            self._send_json({"success": True, "saved": saved, "imageDeleted": deleted})
            return

        # --- /api/regenerate ---
        if path == "/api/regenerate":
            chapter = data.get("chapter")
            image = data.get("image")
            text = data.get("text")
            if not chapter or not image or text is None:
                self._send_error("Missing 'chapter', 'image', or 'text' in body")
                return
            if not is_safe(chapter) or not is_safe(image):
                self._send_error("Invalid path component", 400)
                return

            # 1. Save prompt first
            prompt_path = PROMPTS_DIR / chapter / f"{image}.txt"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                prompt_path.write_text(text, encoding="utf-8")
            except Exception as e:
                self._send_error(f"Failed to save prompt: {e}", 500)
                return

            # 2. Regenerate image via Pollinations
            image_path = IMAGES_DIR / chapter / f"{image}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)

            size_kb: int | None = None
            try:
                png_data = pollinations_generate(text)
            except Exception as e:
                self._send_error(f"Pollinations API call failed: {e}", 500)
                return

            if png_data is None:
                self._send_error("Image generation failed — see server logs for details", 500)
                return

            try:
                image_path.write_bytes(png_data)
                size_kb = len(png_data) // 1024
            except Exception as e:
                self._send_error(f"Failed to write image file: {e}", 500)
                return

            self._send_json({
                "success": True,
                "promptSaved": True,
                "imageRegenerated": True,
                "sizeKb": size_kb,
            })
            return

        self._send_error("Not found", 404)

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(f"[ReviewTool] {args[0]} {args[1]} {args[2]}\n")


def main() -> None:
    server = HTTPServer(("0.0.0.0", PORT), ReviewHandler)
    print(f"\n  \U0001f5bc\ufe0f  Image Review Tool")
    print(f"  \u2500" * 35)
    print(f"  Server:  http://localhost:{PORT}")
    print(f"  Folder:  {SCRIPT_DIR}")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
