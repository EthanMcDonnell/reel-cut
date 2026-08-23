#!/usr/bin/env python3
"""Send links to a slug's script and its footage upload page, over the tailnet.

    .venv/bin/python scripts/send_script.py <slug>

The script is served live by upload_server.py rather than pasted into the thread,
so a later edit is on the phone at the next refresh instead of being frozen into
whatever was sent at produce time.
"""

import subprocess
import sys
from pathlib import Path

import httpx

TELEGRAM_API = "http://localhost:8765/telegram/send"
TOPIC = "file-exchange"
PORT = 8770
REPO = Path(__file__).resolve().parent.parent


def tailnet_ip() -> str | None:
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        )
        return (out.stdout.strip().splitlines() or [None])[0]
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: send_script.py <slug>")
    slug = sys.argv[1]

    if not (REPO / "assets" / slug / "script.md").is_file():
        sys.exit(f"no script at assets/{slug}/script.md")

    ip = tailnet_ip()
    if not ip:
        sys.exit("tailnet IP unavailable — run 'tailscale up'")
    script_url = f"http://{ip}:{PORT}/script/{slug}"
    upload_url = f"http://{ip}:{PORT}/upload/{slug}"

    message = f"📄 {slug}\n\nScript: {script_url}\nUpload the take: {upload_url}"
    with httpx.Client(timeout=15) as client:
        resp = client.post(TELEGRAM_API, json={"content": message, "topic": TOPIC})
        resp.raise_for_status()

    print(f"sent script + upload links to {TOPIC}: {script_url}")


if __name__ == "__main__":
    main()
