#!/usr/bin/env python3
"""Serve a slug's script and receive its footage back, over the tailnet.

GET  /script/<slug>            → assets/<slug>/script.md, read fresh, laid out for filming
GET  /script/<slug>?mtime=1    → that file's mtime, so an open page can spot an edit
GET  /upload/<slug>            → a one-input page (tap the Telegram link, pick the clip);
                                  a direct series link also offers an optional name field
PUT  /upload/<slug>?name=<fn>&slug=<custom>
                                → streams the raw request body to assets/<slug-or-custom>/<fn>;
                                  `slug` only applies to a direct series link (ignored otherwise)
GET  /job/<id>                 → a production job's status and Claude output link
GET  /job/<id>/log             → the worker's captured Claude output, once it exists
GET  /reels/<slug>/<name>.mp4  → a rendered hook video from output/<slug>/, with Range
                                  support so it plays inline on iOS

config.yaml's production.ai_provider picks what a finished upload triggers: the
queued `claude-cli` worker (job tracking, Telegram status, the routes above) or a
fire-and-forget `mission-control` session per upload, with none of that tracking.

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

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from production_queue import QUEUE_ROOT, enqueue, find_job
from reelcut.config import load_config

PORT = 8770
ASSETS = REPO / "assets"
OUTPUT = REPO / "output"
CHUNK = 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

# Intake slugs end in an uppercase UTC stamp (…T083529Z), so existing folders may hold capitals.
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
CUSTOM_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
HEADING_RE = re.compile(r"^\*\*(.+?):?\*\*$")
HOOK_PREFIX_RE = re.compile(r"^HOOK\s+\d+:\s*")
UPLOADS_RE = re.compile(r"^\*\*Uploads:\*\*\s*(\w+)", re.MULTILINE)
UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

NAME_FIELD = """<label class=namefield>Name (optional)
  <input type=text id=slugname placeholder="leave blank for {slug}-&lt;timestamp&gt;"
         autocapitalize=none autocorrect=off spellcheck=false>
</label>
"""

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
 input[type=file]{{display:none}}
 .namefield{{padding:0;border:0;text-align:left;font-size:.85rem;margin-bottom:1.25rem}}
 .namefield input{{display:block;width:100%;box-sizing:border-box;margin-top:.4rem;
      padding:.7rem;border-radius:8px;border:1px solid #444;background:#1a1a1a;
      color:#eee;font:inherit}}
 progress{{width:100%;height:10px;margin-top:1.5rem;display:none}}
 #msg{{margin-top:1rem;text-align:center}}
</style>
<h1>{slug}</h1>
<p>Pick the take. Browse → Files uploads the original; the photo picker may re-encode.</p>
{name_field}<label>
  <input type=file accept="video/*" id=f>
  Choose video
</label>
<progress id=bar max=100 value=0></progress>
<div id=msg></div>
<script>
const f=document.getElementById('f'),bar=document.getElementById('bar'),
      msg=document.getElementById('msg'),nameInput=document.getElementById('slugname');
f.onchange=()=>{{
  const file=f.files[0]; if(!file) return;
  bar.style.display='block'; msg.textContent='Uploading '+file.name;
  const x=new XMLHttpRequest();
  let url='?name='+encodeURIComponent(file.name);
  const wanted=nameInput&&nameInput.value.trim();
  if(wanted) url+='&slug='+encodeURIComponent(wanted);
  x.open('PUT',url);
  x.upload.onprogress=e=>{{ if(e.lengthComputable) bar.value=e.loaded/e.total*100; }};
  x.onload=()=>{{
    if(x.status===202){{
      const job=JSON.parse(x.responseText);
      msg.innerHTML=job.job_url?'✅ Queued · <a href="'+job.job_url+'">View progress</a>':'✅ Sent';
    }}else msg.textContent='❌ '+x.responseText;
    bar.style.display='none';
  }};
  x.onerror=()=>{{ msg.textContent='❌ upload failed'; bar.style.display='none'; }};
  x.send(file);
}};
</script>
"""


JOB_PAGE = """<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Production job</title>
<style>
 body{{font:17px -apple-system,sans-serif;margin:0;padding:2rem 1.5rem;background:#111;color:#eee}}
 h1{{font-size:1.1rem;margin:0 0 1.5rem}} dt{{color:#888;margin-top:1rem}} dd{{margin:.2rem 0;word-break:break-word}}
 a{{display:inline-block;margin-top:1.5rem;color:#93c5fd}}
</style>
<h1>Production job</h1><dl id=job>Loading…</dl><a id=log hidden>View Claude output</a>
<script>
const fields=['asset_slug','status','created_at','updated_at','reason','error'];
async function refresh(){{
  const r=await fetch(location.pathname+'?json=1',{{cache:'no-store'}}); if(!r.ok)return;
  const job=await r.json(), box=document.getElementById('job'), link=document.getElementById('log');
  box.innerHTML=fields.filter(k=>job[k]).map(k=>'<dt>'+k.replace('_',' ')+'</dt><dd>'+job[k]+'</dd>').join('');
  if(job.log_url){{ link.href=job.log_url; link.hidden=false; }}
  if(!['succeeded','blocked','failed','interrupted'].includes(job.status)) setTimeout(refresh,2000);
}}
refresh();
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
 .copy{{display:block;width:100%;margin-top:1rem;padding:1rem;border:0;border-radius:12px;
      background:#2a2a2a;color:#eee;font:inherit;font-size:1rem;-webkit-appearance:none}}
 #raw{{position:fixed;left:-9999px;top:0}}
 #stale{{position:fixed;left:0;right:0;bottom:0;padding:.9rem;background:#b45309;
      color:#fff;text-align:center;font-size:.9rem;display:none}}
</style>
<h1>{slug}</h1>
{body}
<button class=copy id=copy>Copy the whole script</button>
<a class=up href="/upload/{slug}">Upload the take</a>
<textarea id=raw readonly>{raw}</textarea>
<div id=stale>Script updated. Tap to reload.</div>
<script>
const seen='{mtime}',bar=document.getElementById('stale');
bar.onclick=()=>location.reload();
const btn=document.getElementById('copy'),raw=document.getElementById('raw');
btn.onclick=async()=>{{
  // navigator.clipboard is undefined over plain http on a tailnet IP, so the
  // select-and-execCommand path is the one that actually runs there.
  try{{
    if(navigator.clipboard) await navigator.clipboard.writeText(raw.value);
    else{{raw.select();raw.setSelectionRange(0,raw.value.length);document.execCommand('copy');}}
    btn.textContent='Copied';
  }}catch(e){{btn.textContent='Copy failed — select by hand';}}
  setTimeout(()=>btn.textContent='Copy the whole script',2000);
}};
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


def reel_file(parts: list[str]) -> Path | None:
    """output/<slug>/<name>.mp4 for the path parts after `/reels`, or None."""
    if len(parts) != 2 or not SLUG_RE.fullmatch(parts[0]) or not parts[1].endswith(".mp4"):
        return None
    if safe_name(parts[1]) != parts[1]:
        return None
    target = OUTPUT / parts[0] / parts[1]
    return target if target.is_file() else None


def byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive (start, end) for a single `bytes=` Range header, or None to send it all."""
    match = RANGE_RE.match(header or "")
    if not match or match.groups() == ("", ""):
        return None
    first, last = match.groups()
    if first:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    else:
        start, end = max(size - int(last), 0), size - 1
    return (start, end) if start <= end else None


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
    text = script.read_text()
    return SCRIPT_PAGE.format(
        slug=script.parent.name,
        body=script_body(text),
        raw=escape(text),
        mtime=script.stat().st_mtime,
    )

def script_series(script: Path) -> str:
    """The series slug under the script's **VIDEO TYPE** heading, or "" if it has none."""
    found = dict(sections(script.read_text())).get("VIDEO TYPE")
    return found[0] if found else ""


def individual_uploads(series: str) -> bool:
    """Whether series/<series>.md declares `**Uploads:** individual`."""
    path = REPO / "series" / f"{series}.md"
    if not SLUG_RE.fullmatch(series) or not path.is_file():
        return False
    found = UPLOADS_RE.search(path.read_text())
    return bool(found) and found.group(1) == "individual"


def upload_target(path: str) -> str | None:
    """The one safe target segment from an upload URL, if present."""
    parts = [p for p in unquote(path).strip("/").split("/") if p]
    if parts[:1] == ["upload"]:
        parts = parts[1:]
    if len(parts) != 1 or not SLUG_RE.fullmatch(parts[0]):
        return None
    return parts[0]


def new_asset_dir(prefix: str) -> Path:
    """Allocate a flat assets/<prefix>-<UTC timestamp> directory."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = ASSETS / f"{prefix}-{stamp}"
    n = 2
    while candidate.exists():
        candidate = ASSETS / f"{prefix}-{stamp}-{n}"
        n += 1
    candidate.mkdir()
    return candidate


class FootageAlreadyUploaded(Exception):
    """A slug already has a video file — refuse a second take, don't isolate it."""


class SlugConflict(Exception):
    """A custom hot-take name collides with an existing script-created asset slug."""


def allocate_upload(target: str, custom_slug: str = "") -> tuple[Path, dict[str, str]] | None:
    """The workspace for a direct series or script-linked upload, or None if no such target.

    A permanent series link (`hot-take`) gets a fresh flat folder every time by default — it
    is meant to take many recordings over time. Naming it via `custom_slug` instead reuses
    assets/<custom_slug>/ across calls, but only once: a second video for that same name is
    refused via FootageAlreadyUploaded, same as a script-linked slug below, and a name that
    collides with an existing script slug is refused via SlugConflict rather than mixing a
    direct recording's receipt into a script's own folder.

    A script-linked slug uploads straight into its own assets/<target>/, once: a second video
    for the same slug is refused via FootageAlreadyUploaded rather than silently isolated into
    a `-take-<timestamp>` folder, so a slug's footage is never ambiguous. Delete the existing
    clip to retake.

    Unless the script's series declares `**Uploads:** individual`: then each upload is a whole
    video (one hook plus body), so it gets its own fresh assets/<target>-<timestamp>/ with a
    direct single-hook receipt, as many times as you like. The script stays behind in
    assets/<target>/ and production never reads it — the take's own transcript is the authority.
    """
    config = load_config(REPO / "config.yaml")
    if series := config.inbound.series.get(target):
        metadata = {"kind": "direct", "series": series.series, "hook_policy": series.hook_policy}
        if not custom_slug:
            return new_asset_dir(series.slug_prefix), metadata
        directory = ASSETS / custom_slug
        if (directory / "script.md").is_file():
            raise SlugConflict(custom_slug)
        if directory.is_dir() and any(item.suffix.lower() in VIDEO_EXTENSIONS for item in directory.iterdir() if item.is_file()):
            raise FootageAlreadyUploaded(custom_slug)
        directory.mkdir(exist_ok=True)
        return directory, metadata

    source = ASSETS / target
    if not (source / "script.md").is_file():
        return None
    series = script_series(source / "script.md")
    if individual_uploads(series):
        return new_asset_dir(target), {"kind": "direct", "series": series, "hook_policy": "single"}
    if any(item.suffix.lower() in VIDEO_EXTENSIONS for item in source.iterdir() if item.is_file()):
        raise FootageAlreadyUploaded(target)
    return source, {}


def spawn_mission_control(slug: str, model: str = "") -> None:
    """Fire-and-forget: open a Mission Control session that runs the pipeline.

    `--no-wait` returns as soon as the session exists, without waiting for the
    command to be typed in or for the pipeline to finish — there is no queue,
    no status tracking, and no log capture on this path; progress is watched
    in the Mission Control dashboard instead.

    `model`, when set, is passed through as `mission-control --model`, which the
    dashboard appends to the `claude` it launches in the session.
    """
    cmd = ["mission-control", "--no-wait"]
    if model:
        cmd += ["--model", model]
    cmd += ["--", "/produce-reel", slug, "--auto"]
    subprocess.Popen(
        cmd,
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        # Inherited, so a spawn that dies after the 202 still lands in the agent's error log.
    )


def write_intake(directory: Path, metadata: dict[str, str], filename: str) -> Path:
    """Leave the worker and Claude an explicit record of why this asset exists."""
    path = directory / ".reelcut-intake.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "asset_slug": directory.name,
        "filename": filename,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **metadata,
    }, indent=2) + "\n")
    return path


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

    def _reply_json(self, code: int, data: dict[str, object]) -> None:
        self._reply(code, json.dumps(data), "application/json; charset=utf-8")

    def _send_reel(self, video: Path, head: bool) -> None:
        # iOS Safari won't play a video unless the server honours Range requests.
        size = video.stat().st_size
        span = byte_range(self.headers.get("Range"), size)
        start, end = span or (0, size - 1)
        self.send_response(206 if span else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if span:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        with video.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining and (chunk := handle.read(min(CHUNK, remaining))):
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        parts = [p for p in unquote(urlparse(self.path).path).strip("/").split("/") if p]
        video = reel_file(parts[1:]) if parts[:1] == ["reels"] else None
        if video is None:
            self.send_response(404)
            self.end_headers()
        else:
            self._send_reel(video, head=True)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        parts = [p for p in unquote(url.path).strip("/").split("/") if p]
        if parts[:1] == ["reels"]:
            video = reel_file(parts[1:])
            if video is None:
                self._reply(404, "no such reel")
            else:
                self._send_reel(video, head=False)
            return

        if parts[:1] == ["script"]:
            script = script_file(parts[1:])
            if script is None:
                self._reply(404, "no script for that slug")
            elif parse_qs(url.query).get("mtime"):
                self._reply(200, str(script.stat().st_mtime))
            else:
                self._reply(200, script_page(script), "text/html; charset=utf-8")
            return

        if parts[:1] == ["job"] and len(parts) in (2, 3) and JOB_ID_RE.fullmatch(parts[1]):
            found = find_job(parts[1])
            if found is None:
                self._reply(404, "no such job")
                return
            log_path = QUEUE_ROOT / "logs" / f"{parts[1]}.log"
            if len(parts) == 3:
                if parts[2] != "log" or not log_path.is_file():
                    self._reply(404, "no worker output yet")
                else:
                    self._reply(200, log_path.read_text(errors="replace"), "text/plain; charset=utf-8")
                return
            _, job = found
            public = {key: job[key] for key in ("id", "asset_slug", "status", "created_at", "updated_at", "reason", "error") if key in job}
            if log_path.is_file():
                public["log_url"] = f"/job/{parts[1]}/log"
            if parse_qs(url.query).get("json"):
                self._reply_json(200, public)
            else:
                self._reply(200, JOB_PAGE, "text/html; charset=utf-8")
            return

        target = upload_target(url.path)
        if target is None:
            self._reply(404, "no such upload target")
            return
        config = load_config(REPO / "config.yaml")
        is_direct = target in config.inbound.series
        if not is_direct and not (ASSETS / target / "script.md").is_file():
            self._reply(404, "no such upload target")
            return
        name_field = NAME_FIELD.format(slug=target) if is_direct else ""
        self._reply(200, PAGE.format(slug=target, name_field=name_field), "text/html; charset=utf-8")

    def do_PUT(self) -> None:
        url = urlparse(self.path)
        target = upload_target(url.path)
        if target is None:
            self._reply(404, "no such upload target")
            return

        raw = (parse_qs(url.query).get("name") or [""])[0]
        name = safe_name(raw)
        if not name:
            self._reply(400, "missing ?name=<filename>")
            return
        if Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
            self._reply(415, "supported video types: .mp4, .mov, .mkv")
            return

        custom_slug = (parse_qs(url.query).get("slug") or [""])[0].strip()
        if custom_slug and not CUSTOM_SLUG_RE.fullmatch(custom_slug):
            self._reply(400, "slug must be lowercase letters, digits and hyphens")
            return

        length = self.headers.get("Content-Length")
        if length is None:
            self._reply(411, "Content-Length required")
            return
        try:
            remaining = int(length)
        except ValueError:
            self._reply(400, "invalid Content-Length")
            return
        if remaining < 0:
            self._reply(400, "invalid Content-Length")
            return

        try:
            allocated = allocate_upload(target, custom_slug)
        except FootageAlreadyUploaded as exc:
            self._reply(409, f"footage already uploaded for {exc} — delete the existing clip to retake")
            return
        except SlugConflict as exc:
            self._reply(409, f"{exc} is a script slug, not a hot-take name — pick another")
            return
        except Exception as exc:
            self._reply(500, f"could not prepare upload: {exc}")
            return
        if allocated is None:
            self._reply(404, "no script or inbound series for that target")
            return
        directory, metadata = allocated

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
            try:
                directory.rmdir()  # only succeeds if empty — never touches a script folder's real content
            except OSError:
                pass
            self._reply(500, f"upload failed: {exc}")
            return

        part.replace(dest)
        intake = directory / ".reelcut-intake.json"
        if metadata:
            try:
                write_intake(directory, metadata, dest.name)
            except Exception as exc:
                self._reply(500, f"upload saved but could not prepare it: {exc}")
                return

        rel = dest.relative_to(ASSETS.parent)
        production = load_config(REPO / "config.yaml").production
        if production.ai_provider == "mission-control":
            try:
                spawn_mission_control(directory.name, production.ai_model)
            except Exception as exc:
                self._reply(500, f"upload saved but could not start production: {exc}")
                return
            print(f"received {rel} ({dest.stat().st_size / 1e6:.1f} MB) → mission-control", flush=True)
            self._reply_json(202, {"asset_slug": directory.name})
            return

        try:
            job = enqueue(directory.name, intake)
        except Exception as exc:
            self._reply(500, f"upload saved but could not queue it: {exc}")
            return
        print(f"received {rel} ({dest.stat().st_size / 1e6:.1f} MB) → {job['id'][:8]}", flush=True)
        self._reply_json(202, {"asset_slug": directory.name, "job_id": job["id"], "job_url": f"/job/{job['id']}"})

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
