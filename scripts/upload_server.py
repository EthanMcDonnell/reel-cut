#!/usr/bin/env python3
"""Receive phone footage into assets/<slug>/ over the tailnet.

GET  /upload/<slug>            → a one-input page (tap the Telegram link, pick the clip)
PUT  /upload/<slug>?name=<fn>  → streams the raw request body to assets/<slug>/<fn>

The body is the file itself, not multipart — so both the browser page and an iOS
Shortcut ("Get Contents of URL", method PUT, request body = file) hit the same route,
and the server never buffers a 200 MB clip in memory.

Bind stays on loopback; `tailscale serve` fronts it:

    .venv/bin/python scripts/upload_server.py
    tailscale serve --bg --set-path /upload http://127.0.0.1:8770
"""

import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PORT = 8770
ASSETS = Path(__file__).resolve().parent.parent / "assets"
CHUNK = 1024 * 1024

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Upload · {slug}</title>
<style>
 body{{font:17px -apple-system,sans-serif;margin:0;padding:2rem 1.5rem;
      background:#111;color:#eee}}
 h1{{font-size:1.1rem;font-weight:600;margin:0 0 .25rem}}
 p{{color:#888;margin:0 0 2rem;font-size:.9rem}}
 label{{display:block;padding:2rem;border:2px dashed #444;border-radius:14px;
        text-align:center;color:#aaa}}
 input{{display:none}}
 progress{{width:100%;height:10px;margin-top:1.5rem;display:none}}
 #msg{{margin-top:1rem;text-align:center}}
</style>
<h1>{slug}</h1>
<p>Pick the take. Browse → Files uploads the original; the photo picker may re-encode.</p>
<label>
  <input type=file accept="video/*" id=f>
  Choose video
</label>
<progress id=bar max=100 value=0></progress>
<div id=msg></div>
<script>
const f=document.getElementById('f'),bar=document.getElementById('bar'),
      msg=document.getElementById('msg');
f.onchange=()=>{{
  const file=f.files[0]; if(!file) return;
  bar.style.display='block'; msg.textContent='Uploading '+file.name;
  const x=new XMLHttpRequest();
  x.open('PUT','?name='+encodeURIComponent(file.name));
  x.upload.onprogress=e=>{{ if(e.lengthComputable) bar.value=e.loaded/e.total*100; }};
  x.onload=()=>{{ msg.textContent=x.status===201?'✅ '+x.responseText:'❌ '+x.responseText;
                 bar.style.display='none'; }};
  x.onerror=()=>{{ msg.textContent='❌ upload failed'; bar.style.display='none'; }};
  x.send(file);
}};
</script>
"""


def slug_dir(path: str) -> Path | None:
    """assets/<slug> for an upload path, or None if the slug is bad or unknown.

    Accepts both `/upload/<slug>` and `/<slug>`: `tailscale serve --set-path /upload`
    strips the prefix before proxying, so the tailnet and a direct localhost hit
    arrive with different paths.
    """
    parts = [p for p in unquote(path).strip("/").split("/") if p]
    if parts[:1] == ["upload"]:
        parts = parts[1:]
    if len(parts) != 1 or not SLUG_RE.match(parts[0]):
        return None
    target = ASSETS / parts[0]
    return target if target.is_dir() else None


def safe_name(raw: str) -> str | None:
    """Basename of `raw`, stripped to a safe charset. None if nothing usable is left."""
    name = UNSAFE_RE.sub("_", os.path.basename(raw)).lstrip(".")
    return name or None


def free_path(directory: Path, name: str) -> Path:
    """`directory/name`, suffixed -2, -3… if taken. Never clobbers an existing take."""
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, dot, ext = name.partition(".")
    n = 2
    while (candidate := directory / f"{stem}-{n}{dot}{ext}").exists():
        n += 1
    return candidate


class Handler(BaseHTTPRequestHandler):
    server_version = "reelcut-upload"

    def _reply(self, code: int, body: str, ctype: str = "text/plain; charset=utf-8") -> None:
        payload = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        directory = slug_dir(urlparse(self.path).path)
        if directory is None:
            self._reply(404, "no such slug")
            return
        self._reply(200, PAGE.format(slug=directory.name), "text/html; charset=utf-8")

    def do_PUT(self) -> None:
        url = urlparse(self.path)
        directory = slug_dir(url.path)
        if directory is None:
            self._reply(404, "no such slug")
            return

        raw = (parse_qs(url.query).get("name") or [""])[0]
        name = safe_name(raw)
        if not name:
            self._reply(400, "missing ?name=<filename>")
            return

        length = self.headers.get("Content-Length")
        if length is None:
            self._reply(411, "Content-Length required")
            return
        remaining = int(length)

        # Stage as .part so a dropped connection never leaves a truncated clip that
        # `reelcut transcribe` would happily pick up as real footage.
        dest = free_path(directory, name)
        part = dest.with_name(dest.name + ".part")
        try:
            with part.open("wb") as fh:
                while remaining > 0:
                    block = self.rfile.read(min(CHUNK, remaining))
                    if not block:
                        raise ConnectionError("client disconnected mid-upload")
                    fh.write(block)
                    remaining -= len(block)
        except Exception as exc:
            part.unlink(missing_ok=True)
            self._reply(500, f"upload failed: {exc}")
            return

        part.replace(dest)
        rel = dest.relative_to(ASSETS.parent)
        print(f"received {rel} ({dest.stat().st_size / 1e6:.1f} MB)", flush=True)
        self._reply(201, str(rel))

    def log_message(self, fmt: str, *args) -> None:
        pass  # uploads log themselves; skip the per-request noise


def main() -> None:
    if not ASSETS.is_dir():
        sys.exit(f"assets dir not found: {ASSETS}")
    print(f"upload server on http://127.0.0.1:{PORT}/upload/<slug> → {ASSETS}/<slug>/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
