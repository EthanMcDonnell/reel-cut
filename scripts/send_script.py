#!/usr/bin/env python3
"""Send a slug's script and its footage-upload link to the Telegram file-exchange topic.

    .venv/bin/python scripts/send_script.py <slug>

The link goes last so it's the newest message in the topic — one tap from the
bottom of the thread when you've finished reading and want to send the take back.
"""

import subprocess
import sys
from pathlib import Path

import httpx

TELEGRAM_API = "http://localhost:8765/telegram/send"
TOPIC = "file-exchange"
PORT = 8770
REPO = Path(__file__).resolve().parent.parent

# Telegram's sendMessage hard-caps at 4096 chars and the broker doesn't split,
# so anything longer is dropped outright. Leave room for the chunk counter.
LIMIT = 3900


def chunk(text: str, limit: int = LIMIT) -> list[str]:
    """Split on paragraph breaks, then lines, keeping every piece under `limit`."""
    if len(text) <= limit:
        return [text]

    out: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        # A single paragraph over the limit still has to be broken somewhere.
        pieces = [para] if len(para) <= limit else para.splitlines(keepends=True)
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    out.append(current)
                # A single line longer than the limit: hard-cut it.
                while len(piece) > limit:
                    out.append(piece[:limit])
                    piece = piece[limit:]
                current = piece
    if current:
        out.append(current)
    return out


def tailnet_ip() -> str | None:
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        )
        return (out.stdout.strip().splitlines() or [None])[0]
    except (OSError, subprocess.SubprocessError):
        return None


def send(client: httpx.Client, content: str) -> None:
    resp = client.post(TELEGRAM_API, json={"content": content, "topic": TOPIC})
    resp.raise_for_status()


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: send_script.py <slug>")
    slug = sys.argv[1]

    script = REPO / "assets" / slug / "script.md"
    if not script.is_file():
        sys.exit(f"no script at {script}")
    body = script.read_text().strip()

    ip = tailnet_ip()
    if not ip:
        sys.exit("tailnet IP unavailable — run 'tailscale up'")
    url = f"http://{ip}:{PORT}/upload/{slug}"

    parts = chunk(body)
    with httpx.Client(timeout=15) as client:
        for i, part in enumerate(parts, 1):
            header = f"📄 {slug}" if len(parts) == 1 else f"📄 {slug} ({i}/{len(parts)})"
            send(client, f"{header}\n\n{part}")
        send(client, f"🎥 Upload the take: {url}")

    print(f"sent script ({len(parts)} message(s)) + link to {TOPIC}: {url}")


if __name__ == "__main__":
    main()
