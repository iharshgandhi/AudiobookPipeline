#!/bin/bash
# =============================================================================
#  setup.command — ONE-TIME SETUP for the New Audio Book Pipeline
#
#  Double-click ONCE. After it finishes, you:
#    1. Drop English chapter .txt files into EnglishSource/
#    2. Use AI megaprompts to generate image prompts + Hindi translations
#    3. Double-click 1 → 2 → 3 → 4a/4b → 5 → 6 in order
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

say()  { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
info() { printf "  %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*"; }

say "New Audio Book Pipeline — One-Time Setup"
info "Working folder: $SCRIPT_DIR"

# ---------- 1. Homebrew ----------
say "[1/5] Homebrew"
if command -v brew >/dev/null 2>&1; then
  ok "Already installed: $(brew --version | head -n1)"
else
  info "Not found — installing (you may be asked for your Mac password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  BREW_BIN="$(command -v brew || true)"
  if [ -n "$BREW_BIN" ] && ! grep -q 'brew shellenv' "$HOME/.zprofile" 2>/dev/null; then
    echo "eval \"\$($BREW_BIN shellenv)\"" >> "$HOME/.zprofile"
  fi
fi

# Make brew available regardless of launch method
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

# ---------- 2. ffmpeg ----------
say "[2/5] ffmpeg"
if command -v ffmpeg >/dev/null 2>&1; then
  ok "Already installed: $(ffmpeg -version 2>&1 | head -n1 | cut -d' ' -f1-3)"
else
  info "Installing via Homebrew (this may take a few minutes)..."
  brew install ffmpeg
  ok "ffmpeg installed"
fi

if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
  ok "Apple VideoToolbox hardware encoder available"
else
  info "h264_videotoolbox not found — video merge will use CPU (libx264)"
fi

# ---------- 3. Python venv ----------
say "[3/5] Python virtual environment"

PY=""
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  info "No Python 3 found — installing via Homebrew..."
  brew install python
  PY="python3"
fi
ok "Using $($PY --version) at $(which $PY)"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  info "Creating .venv/ ..."
  "$PY" -m venv "$SCRIPT_DIR/.venv"
  ok ".venv created"
else
  ok ".venv already exists"
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/.venv/bin/activate"
info "Installing Python packages (edge-tts, requests, Pillow)..."
pip install --quiet --upgrade pip
pip install --quiet edge-tts requests Pillow
ok "Python packages installed"

# ---------- 4. Config ----------
say "[4/5] Configuration"

# Create tracked config.json (no secrets — safe for git)
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
  info "Creating config.json (safe to commit — no API keys)..."
  cat > "$SCRIPT_DIR/config.json" << 'JSONEOF'
{
  "language": "hi",
  "voice": "hi-IN-MadhurNeural",
  "voice_hi": "hi-IN-MadhurNeural",
  "voice_en": "en-IN-NeerjaNeural",
  "rate": "+0%",
  "pitch": "+0Hz",
  "parallel_chunks": 4,
  "chunk_chars": 2800,
  "narrator_voice": "hi-IN-MadhurNeural",
  "gap_same_ms": 220,
  "speaker_gap_ms": 420,
  "heading_gap_ms": 750,
  "paragraph_gap_ms": 450,
  "default_pause_ms": 550,
  "lead_in_ms": 250,
  "pollinations_token": "",
  "poll_model": "flux",
  "poll_width": 1280,
  "poll_height": 720,
  "poll_gap_sec": 0.5,
  "video_bitrate_mbps": 2.5,
  "video_fps": 30,
  "transition_duration_sec": 1.0,
  "transition_styles": [
    "fade", "fadeblack", "fadewhite", "fadegrays",
    "dissolve", "pixelize", "hblur", "distance", "radial",
    "circleopen", "circleclose",
    "smoothleft", "smoothright", "smoothup", "smoothdown"
  ]
}
JSONEOF
  ok "config.json created (safe for git)"
else
  ok "config.json already exists"
fi

# Create/update config.local.json (gitignored — holds your real API key)
echo ""
echo "  Your Pollinations API key (secret — stored in config.local.json, never committed to git)"
echo ""
if [ -f "$SCRIPT_DIR/config.local.json" ]; then
  EXISTING_TOKEN=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.local.json')).get('pollinations_token',''))" 2>/dev/null || echo "")
  if [ -n "$EXISTING_TOKEN" ]; then
    echo "  Current key: ${EXISTING_TOKEN:0:10}... (press Enter to keep)"
  fi
else
  echo "  No existing key found."
fi
printf "  Enter your Pollinations secret key (sk_...): "
read -r TOKEN
if [ -n "$TOKEN" ]; then
  cat > "$SCRIPT_DIR/config.local.json" << JSONEOF
{
  "pollinations_token": "$TOKEN"
}
JSONEOF
  ok "config.local.json created (gitignored — never committed)"
elif [ ! -f "$SCRIPT_DIR/config.local.json" ]; then
  # Create an empty placeholder so the file exists
  cat > "$SCRIPT_DIR/config.local.json" << 'JSONEOF'
{
  "pollinations_token": ""
}
JSONEOF
  info "No token provided — you can add it later to config.local.json"
fi

echo ""
info "Secret keys (sk_...) have NO rate limits on Pollinations.ai."
info "poll_gap_sec is set to 0.5s — images generate as fast as possible."

# ---------- 5. Create working folders ----------
say "[5/5] Creating working folders"

mkdir -p "$SCRIPT_DIR/EnglishSource"
mkdir -p "$SCRIPT_DIR/HaikuOutput"
mkdir -p "$SCRIPT_DIR/HindiTagged"
mkdir -p "$SCRIPT_DIR/Prompts"
mkdir -p "$SCRIPT_DIR/Images"
mkdir -p "$SCRIPT_DIR/HindiClean"
mkdir -p "$SCRIPT_DIR/AudioSingle"
mkdir -p "$SCRIPT_DIR/AudioMulti"
mkdir -p "$SCRIPT_DIR/Videos"

ok "EnglishSource/  — drop English chapter .txt files here"
ok "HaikuOutput/   — drop AI image-prompt reply here"
ok "HindiTagged/   — drop AI-translated tagged Hindi chapters here"
ok "Other folders created (Prompts, Images, HindiClean, AudioSingle, AudioMulti, Videos)"

# ---------- Done ----------
say "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Drop English chapter .txt files into EnglishSource/"
echo "  2. Read README.md for the full step-by-step guide"
echo "  3. Double-click 1_split_prompts.command to begin"
echo ""
read -r -p "Press Enter to close this window..." _
