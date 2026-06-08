#!/bin/bash
# =============================================================================
#  2.5_review_images.command — Launch the Image Review Web Tool
#
#  Starts a lightweight Python HTTP server, opens your browser, and lets you
#  review, edit prompts for, approve or reject generated images.
#
#  Prerequisites:
#    - Ran setup.command once (creates .venv)
#    - Ran 1_split_prompts.command   (Populates Prompts/)
#    - Ran 2_generate_images.command (Populates Images/)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  echo "ERROR: .venv not found. Double-click setup.command first."
  read -r -p "Press Enter to close..." _
  exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate"

PORT=8765
PID=""

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    wait "$PID" 2>/dev/null
  fi
  echo ""
  echo "  Server stopped."
}
trap cleanup EXIT

echo ""
echo "  \U0001f5bc\ufe0f  Image Review Tool"
echo "  \u2500"\\c
echo "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
echo "  Server: http://localhost:$PORT"
echo "  Press Enter to stop the server."
echo ""

python3 "$SCRIPT_DIR/review-tool/server.py" &
PID=$!

# Give the server a moment to start
sleep 1

# Open in default browser
open "http://localhost:$PORT"

# Wait for user to press Enter to stop
read -r _ >/dev/null 2>&1
