#!/usr/bin/env bash
set -euo pipefail

DISPLAY="${DISPLAY:-:99}"
SCREEN="${BROWSER_NODE_SCREEN:-1280x720x24}"

Xvfb "$DISPLAY" -screen 0 "$SCREEN" -ac +extension RANDR &
fluxbox -display "$DISPLAY" &
x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -nopw &
/usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 7900 &

exec uvicorn app.main:app --host 0.0.0.0 --port 9300

