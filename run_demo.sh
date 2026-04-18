#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# run_demo.sh — One-command launcher for the Smart Seat system
#
# Uses shortened timeouts so hoarding triggers in ~30s instead of 30min.
# Usage:
#   chmod +x run_demo.sh && ./run_demo.sh
# ──────────────────────────────────────────────────────────────

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
FLASK_DIR="$ROOT/flask"
SIM_DIR="$ROOT/simulator"

# ── Demo timeouts (shortened for live demo) ──────────────────
export HOARD_TIMEOUT_S=30
export HOARD_CONFIRM_WINDOW_S=10
export GHOST_TIMEOUT_S=15
export RESERVE_MAX_S=60

# ── Install deps if needed ───────────────────────────────────
echo "==> Checking Python dependencies..."
pip install -q -r "$FLASK_DIR/requirements.txt"
pip install -q -r "$SIM_DIR/requirements.txt"

# ── Start Flask server in background ─────────────────────────
echo "==> Starting Flask server (port 5000)..."
cd "$FLASK_DIR"
python app.py &
SERVER_PID=$!
cd "$ROOT"

# Wait for server to come up
echo "    Waiting for server..."
for i in $(seq 1 15); do
    if curl -s http://localhost:5000/api/seats > /dev/null 2>&1; then
        echo "    Server ready!"
        break
    fi
    sleep 1
done

# ── Start simulator ──────────────────────────────────────────
echo "==> Starting sensor simulator (4 seats, 2s interval)..."
echo "    Dashboard: http://localhost:5000"
echo ""
echo "    Simulator commands:"
echo "      rfid <seat> <student_id>   — simulate RFID tap"
echo "      reserve <seat> <student_id> — reserve a seat"
echo "      reset <seat>               — staff reset"
echo "      quit                       — stop everything"
echo ""

cd "$SIM_DIR"
python stub.py --interval 2

# ── Cleanup ──────────────────────────────────────────────────
echo "==> Stopping server..."
kill $SERVER_PID 2>/dev/null || true
echo "Done."
