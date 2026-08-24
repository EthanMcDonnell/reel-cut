#!/usr/bin/env bash
# Install the phone-upload receiver and serial production worker as LaunchAgents.
#
#   ./scripts/install-upload-agent.sh          # install / reinstall
#   ./scripts/install-upload-agent.sh --uninstall
#
# Paths are resolved from this script's location, so the agents follow the repo
# if it moves — rerun after moving. See README "Inbound footage".

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="gui/$(id -u)"
PYTHON="$REPO/.venv/bin/python"
SERVER="$REPO/scripts/upload_server.py"
WORKER="$REPO/scripts/production_queue.py"
WORKER_SETTINGS="$REPO/scripts/worker-settings.json"
CLAUDE_BIN="$(command -v claude || true)"
PORT=8770
UPLOAD_LABEL="com.reelcut.upload"
PRODUCE_LABEL="com.reelcut.produce"
UPLOAD_PLIST="$HOME/Library/LaunchAgents/$UPLOAD_LABEL.plist"
PRODUCE_PLIST="$HOME/Library/LaunchAgents/$PRODUCE_LABEL.plist"

for label in "$UPLOAD_LABEL" "$PRODUCE_LABEL"; do
  launchctl bootout "$TARGET/$label" 2>/dev/null || true
done

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$UPLOAD_PLIST" "$PRODUCE_PLIST"
  echo "uninstalled $UPLOAD_LABEL and $PRODUCE_LABEL"
  exit 0
fi

[[ -x "$PYTHON" ]] || { echo "no venv at $PYTHON — create it first (see README Quickstart)"; exit 1; }
[[ -f "$SERVER" ]] || { echo "missing $SERVER"; exit 1; }
[[ -f "$WORKER" ]] || { echo "missing $WORKER"; exit 1; }
[[ -f "$WORKER_SETTINGS" ]] || { echo "missing $WORKER_SETTINGS"; exit 1; }
[[ -n "$CLAUDE_BIN" && -x "$CLAUDE_BIN" ]] || { echo "claude executable not found on PATH"; exit 1; }

mkdir -p "$(dirname "$UPLOAD_PLIST")"
cat > "$UPLOAD_PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$UPLOAD_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SERVER</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/reelcut-upload.log</string>
  <key>StandardErrorPath</key><string>/tmp/reelcut-upload.err</string>
</dict>
</plist>
PLIST_EOF

cat > "$PRODUCE_PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$PRODUCE_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$WORKER</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
    <key>CLAUDE_BIN</key><string>$CLAUDE_BIN</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/reelcut-produce.log</string>
  <key>StandardErrorPath</key><string>/tmp/reelcut-produce.err</string>
</dict>
</plist>
PLIST_EOF

launchctl bootstrap "$TARGET" "$UPLOAD_PLIST"
launchctl bootstrap "$TARGET" "$PRODUCE_PLIST"
echo "installed $UPLOAD_LABEL and $PRODUCE_LABEL"

HOST="$(tailscale ip -4 2>/dev/null | sed -n '1p' || true)"
[[ -n "$HOST" ]] || { echo "tailnet IP unavailable — run 'tailscale up'"; HOST=127.0.0.1; }

# A nonexistent target must answer 404 — that proves the receiver is up and routing,
# without needing a real asset folder to exist yet. Importing the worker/config modules
# can take longer than one second on a cold launch, so wait briefly instead of false-failing.
code=""
for _ in {1..10}; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 \
         "http://$HOST:$PORT/upload/probe-not-a-slug" || true)
  [[ "$code" == "404" ]] && break
  sleep 1
done
if [[ "$code" == "404" ]]; then
  echo "ready: http://$HOST:$PORT/upload/<script-slug-or-series>"
else
  echo "server not responding (got '${code:-no reply}') — check /tmp/reelcut-upload.err"
fi
