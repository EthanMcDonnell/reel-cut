#!/usr/bin/env bash
# Install the footage upload receiver as a login-persistent LaunchAgent.
#
#   ./scripts/install-upload-agent.sh          # install / reinstall
#   ./scripts/install-upload-agent.sh --uninstall
#
# Paths are resolved from this script's location, so the agent follows the repo
# if it moves — rerun after moving. See README "Inbound footage".

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.reelcut.upload"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$REPO/.venv/bin/python"
SERVER="$REPO/scripts/upload_server.py"
PORT=8770
TARGET="gui/$(id -u)"

# Tear down any previous copy first: bootstrap fails outright if the label is
# already loaded, and a stale plist would keep pointing at the repo's old path.
launchctl bootout "$TARGET/$LABEL" 2>/dev/null || true

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$PLIST"
  echo "uninstalled $LABEL"
  exit 0
fi

[[ -x "$PYTHON" ]] || { echo "no venv at $PYTHON — create it first (see README Quickstart)"; exit 1; }
[[ -f "$SERVER" ]] || { echo "missing $SERVER"; exit 1; }

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SERVER</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <!-- Back off between respawns so a crash-on-startup bug can't spin the CPU. -->
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/reelcut-upload.log</string>
  <key>StandardErrorPath</key><string>/tmp/reelcut-upload.err</string>
</dict>
</plist>
PLIST_EOF

launchctl bootstrap "$TARGET" "$PLIST"
echo "installed $LABEL → $PLIST"

# Serve config lives in tailscaled and persists across reboots, so this is
# idempotent rather than per-boot. Non-fatal: the agent is useful on localhost
# even if the tailnet isn't up yet.
if command -v tailscale >/dev/null; then
  tailscale serve --bg --set-path /upload "http://127.0.0.1:$PORT" >/dev/null \
    && echo "serving /upload → 127.0.0.1:$PORT" \
    || echo "tailscale serve failed — need 'sudo tailscale set --operator=\$USER'?"
else
  echo "tailscale not installed — upload reachable on localhost only"
fi

sleep 1
# A nonexistent slug must answer 404 — that proves the server is up and routing,
# without needing a real slug to exist yet.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
       "http://127.0.0.1:$PORT/upload/probe-not-a-slug" || true)
if [[ "$code" == "404" ]]; then
  echo "upload server responding on :$PORT"
else
  echo "server not responding (got '${code:-no reply}') — check /tmp/reelcut-upload.err"
fi
