#!/usr/bin/env python3
"""Serve a slug's script and receive its footage back, over the tailnet.

GET  /script/<slug>            → assets/<slug>/script.md, read fresh, laid out for filming
GET  /script/<slug>?mtime=1    → that file's mtime, so an open page can spot an edit
GET  /upload/<slug>            → a one-input page (tap the Telegram link, pick the clip)
PUT  /upload/<slug>?name=<fn>  → streams the raw request body to assets/<slug>/<fn>

The script is read on every request rather than pasted into Telegram at produce time,
so an edit made after the script was sent is live on the phone at the next refresh.

The body is the file itself, not multipart — so both the browser page and an iOS
Shortcut ("Get Contents of URL", method PUT, request body = file) hit the same route,
and the server never buffers a 200 MB clip in memory.

Binds the machine's tailnet IP, so the URL is a plain
`http://100.x.y.z:8770/upload/<slug>` reachable from any device on the tailnet —
no MagicDNS, no TLS cert, no `tailscale serve` config to go stale. That address
lives in the 100.64.0.0/10 CGNAT range and only routes between tailnet peers, so
binding it does NOT expose the server on local wi-fi.

    .venv/bin/python scripts/upload_server.py           # auto-detects the tailnet IP
    .venv/bin/python scripts/upload_server.py 127.0.0.1 # or pin a host
"""

import os
import re
import subprocess
import sys
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PORT = 8770
ASSETS = Path(__file__).resolve().parent.parent / "assets"
CHUNK = 1024 * 1024

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HEADING_RE = re.compile(r"^\*\*(.+?):?\*\*$")
HOOK_PREFIX_RE = re.compile(r"^HOOK\s+\d+:\s*")
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


SCRIPT_PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{slug}</title>
<style>
 body{{font:20px/1.55 -apple-system,sans-serif;margin:0;padding:1.5rem 1.25rem 4rem;
      background:#111;color:#eee;-webkit-text-size-adjust:100%}}
 h1{{font-size:1rem;font-weight:600;color:#888;margin:0 0 1.5rem}}
 h2{{font-size:.72rem;font-weight:600;color:#6a6a6a;letter-spacing:.12em;
     margin:2rem 0 .6rem}}
 p{{margin:0 0 1rem}}
 ol{{margin:0;padding:0;list-style:none;counter-reset:h}}
 ol li{{margin:0 0 1rem;padding-left:2rem;position:relative}}
 ol li:before{{counter-increment:h;content:counter(h);position:absolute;left:0;top:.2em;
      width:1.4rem;height:1.4rem;border-radius:50%;background:#2a2a2a;color:#999;
      font-size:.8rem;line-height:1.4rem;text-align:center}}
 .refs{{font-size:.8rem;color:#777;line-height:1.4}}
 .refs p{{margin:0 0 .5rem}}
 .refs a{{color:#5a9bd8;word-break:break-all}}
 .up{{display:block;margin-top:2.5rem;padding:1rem;border-radius:12px;background:#1d4ed8;
      color:#fff;text-align:center;text-decoration:none;font-size:1rem}}
 #stale{{position:fixed;left:0;right:0;bottom:0;padding:.9rem;background:#b45309;
      color:#fff;text-align:center;font-size:.9rem;display:none}}
</style>
<h1>{slug}</h1>
{body}
<a class=up href="/upload/{slug}">Upload the take</a>
<div id=stale>Script updated. Tap to reload.</div>
<script>
const seen='{mtime}',bar=document.getElementById('stale');
bar.onclick=()=>location.reload();
setInterval(async()=>{{
  try{{
    const r=await fetch(location.pathname+'?mtime=1',{{cache:'no-store'}});
    if(r.ok && (await r.text())!==seen) bar.style.display='block';
  }}catch(e){{}}
}},5000);
</script>
"""


def script_file(parts: list[str]) -> Path | None:
    """assets/<slug>/script.md for the path parts after `/script`, or None."""
    if len(parts) != 1 or not SLUG_RE.match(parts[0]):
        return None
    target = ASSETS / parts[0] / "script.md"
    return target if target.is_file() else None


def sections(text: str) -> list[tuple[str, list[str]]]:
    """The script's **HEADING** blocks as (name, lines), in file order."""
    out: list[tuple[str, list[str]]] = []
    name, buf = None, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if heading := HEADING_RE.match(line):
            if name:
                out.append((name, buf))
            name, buf = heading.group(1), []
        elif name:
            buf.append(line)
    if name:
        out.append((name, buf))
    return out


def script_body(text: str) -> str:
    """Render the sections for filming: hooks numbered, spoken prose in reading type.

    Hooks become a numbered list because they are recorded as separate takes, and
    references stay small because they are the one block that is never read aloud.
    """
    out = []
    for name, lines in sections(text):
        out.append(f"<h2>{escape(name)}</h2>")
        if name == "HOOK":
            items = "".join(
                f"<li>{escape(HOOK_PREFIX_RE.sub('', line))}</li>" for line in lines
            )
            out.append(f"<ol>{items}</ol>")
        elif name in ("REFERENCES", "VIEWER RESOURCES"):
            body = "".join(
                f'<p><a href="{escape(line)}">{escape(line)}</a></p>'
                if line.startswith("http")
                else f"<p>{escape(line)}</p>"
                for line in lines
            )
            out.append(f"<div class=refs>{body}</div>")
        else:
            out.append("".join(f"<p>{escape(line)}</p>" for line in lines))
    return "".join(out)


def script_page(script: Path) -> str:
    """The full page. Read at request time, so an edit is live on the next refresh."""
    return SCRIPT_PAGE.format(
        slug=script.parent.name,
        body=script_body(script.read_text()),
        mtime=script.stat().st_mtime,
    )

def slug_dir(path: str) -> Path | None:
    """assets/<slug> for an upload path, or None if the slug is bad or unknown.

    The `/upload` prefix is optional — a `tailscale serve --set-path /upload` front
    end strips it before proxying, so both forms are accepted for that setup.
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
        url = urlparse(self.path)
        parts = [p for p in unquote(url.path).strip("/").split("/") if p]
        if parts[:1] == ["script"]:
            script = script_file(parts[1:])
            if script is None:
                self._reply(404, "no script for that slug")
            elif parse_qs(url.query).get("mtime"):
                self._reply(200, str(script.stat().st_mtime))
            else:
                self._reply(200, script_page(script), "text/html; charset=utf-8")
            return

        directory = slug_dir(url.path)
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


def tailnet_ip() -> str:
    """This machine's tailnet IP, or loopback if Tailscale isn't up."""
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        )
        if ip := out.stdout.strip().splitlines()[:1]:
            return ip[0]
    except (OSError, subprocess.SubprocessError):
        pass
    print("tailnet IP unavailable — binding loopback (phone uploads won't reach)", flush=True)
    return "127.0.0.1"


def main() -> None:
    if not ASSETS.is_dir():
        sys.exit(f"assets dir not found: {ASSETS}")
    host = sys.argv[1] if len(sys.argv) > 1 else tailnet_ip()
    print(f"reelcut server on http://{host}:{PORT}/script/<slug> and /upload/<slug>", flush=True)
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
