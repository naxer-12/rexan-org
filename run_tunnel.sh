#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== Rexan.org Web & Cloudflare Tunnel Launcher ==="

# 1. Check cloudflared
CLOUDFLARED_BIN="$(which cloudflared || echo '/opt/homebrew/bin/cloudflared')"
if [ ! -x "$CLOUDFLARED_BIN" ]; then
    echo "cloudflared not found. Installing via brew..."
    brew install cloudflared
    CLOUDFLARED_BIN="$(which cloudflared || echo '/opt/homebrew/bin/cloudflared')"
fi

# 2. Check if local server is already running on port 8000
if lsof -i :8000 >/dev/null 2>&1; then
    echo "Local Rexan server is already running on http://127.0.0.1:8000"
else
    echo "Starting Rexan server on port 8000..."
    python3 server.py > /tmp/rexan_server.log 2>&1 &
    sleep 2
fi

# 3. Start or re-attach Cloudflare tunnel
echo "Starting Cloudflare public tunnel..."
LOG_FILE="/tmp/rexan_cloudflared.log"
> "$LOG_FILE"

"$CLOUDFLARED_BIN" tunnel --url http://127.0.0.1:8000 --logfile "$LOG_FILE" &
TUNNEL_PID=$!

echo "Waiting for tunnel to connect..."
for i in {1..30}; do
    URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" "$LOG_FILE" | head -n 1 || true)
    if [ -n "$URL" ]; then
        echo ""
        echo "=========================================================="
        echo " Rexan is LIVE on the Web at:"
        echo " $URL"
        echo "=========================================================="
        echo ""
        echo "Press Ctrl+C to stop the tunnel."
        wait $TUNNEL_PID
        exit 0
    fi
    sleep 1
done

echo "Tunnel started. Check $LOG_FILE for logs."
wait $TUNNEL_PID
