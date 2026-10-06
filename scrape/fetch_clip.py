#!/usr/bin/env python3
"""
Clip Fetcher

Finds the videos a page embeds, and cuts a few seconds of one into assets/<slug>/clips/ for
a `type: "video"` overlay.

Usage:
  python scrape/fetch_clip.py list --url "<page url>"
  python scrape/fetch_clip.py get --url "<video url>" --slug <slug> --name <name>
  python scrape/fetch_clip.py get --url "<video url>" --slug <slug> --name <name> --start 12 --end 16
  python scrape/fetch_clip.py get --url "<embed url>" --referer "<page url>" --slug <slug> --name <name>

`list` prints the page's own <video> files and the YouTube, Vimeo, X and Loom videos it
embeds or links to. An embed-only player (most Vimeo embeds) refuses a download unless
`get` passes the page it was listed from as --referer.

`get` without a range downloads the video (yt-dlp) to clips/.source/ and writes a contact
sheet beside it: a frame every few seconds, each labelled with its time, to choose the
seconds from. With --start/--end it cuts that range from the download (fetching it first if
needed) to clips/<name>.mp4: H.264, no audio, at most 1080 wide.

Output (stdout): JSON.
"""

import argparse
import asyncio
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent

SHEET_FRAMES = 40   # most frames on one contact sheet; longer videos are sampled more sparsely
SHEET_COLS = 5
THUMB_W = 320

# Video pages and players worth handing to yt-dlp. Specific videos only: a channel or
# profile link in a page footer is not a clip.
_VIDEO_URL_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:"
    r"youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|shorts/)[\w-]+"
    r"|youtu\.be/[\w-]+"
    r"|(?:player\.)?vimeo\.com/(?:video/)?\d+"
    r"|(?:x|twitter)\.com/\w+/status/\d+"
    r"|loom\.com/(?:share|embed)/\w+"
    r")"
)
_VIDEO_FILE_RE = re.compile(r"\.(?:mp4|webm|mov|m4v|m3u8)(?:[?#]|$)", re.I)

# Every URL the page could play: <video>/<source> files, iframe players, links. A video fed
# by a blob: URL (a streaming player) has no fetchable file; it is only counted.
_JS_VIDEO_URLS = """() => {
  const abs = u => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
  const files = [], blobs = [];
  document.querySelectorAll('video').forEach(v => {
    for (const u of [v.currentSrc, v.src, v.dataset.src, ...[...v.querySelectorAll('source')].flatMap(s => [s.src, s.dataset.src])]) {
      if (!u) continue;
      (u.startsWith('blob:') ? blobs : files).push(abs(u));
    }
  });
  const frames = [...document.querySelectorAll('iframe[src]')].map(f => abs(f.src));
  const links = [...document.querySelectorAll('a[href]')].map(a => abs(a.href));
  return {files, frames, links, blob_videos: new Set(blobs).size};
}"""


def video_urls(found: dict) -> list[dict]:
    """The distinct playable videos in a page's URLs, its own files first."""
    out, seen = [], set()
    for kind, urls, test in (
        ("file", found.get("files", []), lambda u: True),
        ("embed", found.get("frames", []), _VIDEO_URL_RE.match),
        ("link", found.get("links", []), _VIDEO_URL_RE.match),
    ):
        for u in urls:
            if u and u not in seen and test(u):
                seen.add(u)
                out.append({"kind": kind, "url": u})
    return out


async def list_videos(url: str) -> dict:
    from playwright.async_api import async_playwright

    sys.path.insert(0, str(ROOT / "scrape"))
    from figure_finder import _prepare
    from playwright_utils import STEALTH_ARGS, stealth_context

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        try:
            page = await _prepare(await stealth_context(browser), url)
            found = await page.evaluate(_JS_VIDEO_URLS)
        finally:
            await browser.close()
    return {"url": url, "videos": video_urls(found), "blob_videos": found["blob_videos"]}


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def fetch(url: str, source_dir: Path, name: str, referer: str | None = None) -> Path:
    """The downloaded video for `name`, downloading it first unless it is already there."""
    have = sorted(p for p in source_dir.glob(f"{name}.*") if p.suffix not in (".jpg", ".part"))
    if have:
        return have[0]
    source_dir.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--quiet", "--no-warnings", "--no-playlist",
         "-f", "bv*[height<=1080]/b[height<=1080]/bv*/b",
         *(["--referer", referer] if referer else []),
         "-o", str(source_dir / f"{name}.%(ext)s"), "--print", "after_move:filepath", url],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {out.stderr.strip() or out.stdout.strip()}")
    return Path(out.stdout.strip().splitlines()[-1])


def contact_sheet(src: Path, out: Path) -> float:
    """A grid of frames from `src`, each labelled m:ss. Returns the seconds between frames."""
    from PIL import Image, ImageDraw, ImageFont

    every = max(1, math.ceil(_duration(src) / SHEET_FRAMES))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(src),
             "-vf", f"fps=1/{every},scale={THUMB_W}:-2", f"{tmp}/%04d.png"],
            check=True,
        )
        frames = [Image.open(p).convert("RGB") for p in sorted(Path(tmp).glob("*.png"))]
    w, h = frames[0].size
    rows = math.ceil(len(frames) / SHEET_COLS)
    sheet = Image.new("RGB", (SHEET_COLS * w, rows * h), "black")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=28)
    for i, frame in enumerate(frames):
        x, y = (i % SHEET_COLS) * w, (i // SHEET_COLS) * h
        sheet.paste(frame, (x, y))
        t = i * every
        draw.text((x + 8, y + 6), f"{t // 60}:{t % 60:02d}", font=font, fill="yellow",
                  stroke_width=3, stroke_fill="black")
    sheet.save(out, quality=85)
    return every


def cut(src: Path, out: Path, start: float, end: float) -> None:
    """`start`–`end` seconds of `src` as a silent H.264 clip no wider than 1080."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-to", str(end), "-i", str(src),
         "-an", "-vf", "scale='min(1080,iw)':-2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", str(out)],
        check=True,
    )


def get(url: str, slug: str, name: str, start: float | None, end: float | None,
        referer: str | None = None) -> dict:
    clips = ROOT / "assets" / slug / "clips"
    src = fetch(url, clips / ".source", name, referer)
    if start is None or end is None:
        sheet = src.with_suffix(".sheet.jpg")
        every = contact_sheet(src, sheet)
        return {"source": str(src), "duration": round(_duration(src), 2),
                "sheet": str(sheet), "every_s": every}
    out = clips / f"{name}.mp4"
    cut(src, out, start, end)
    return {"clip": str(out), "duration": round(_duration(out), 2)}


def main():
    parser = argparse.ArgumentParser(description="Find and cut video clips for overlays")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="List the videos a page plays, embeds or links to")
    ls.add_argument("--url", required=True)
    g = sub.add_parser("get", help="Download a video; with --start/--end, cut a clip from it")
    g.add_argument("--url", required=True, help="Video file, or a YouTube/Vimeo/X/Loom page")
    g.add_argument("--referer", help="The page an embed was listed from; embed-only players need it")
    g.add_argument("--slug", required=True)
    g.add_argument("--name", required=True, help="Clip name: clips/<name>.mp4")
    g.add_argument("--start", type=float, help="Seconds into the video")
    g.add_argument("--end", type=float, help="Seconds into the video")
    args = parser.parse_args()

    if args.cmd == "list":
        result = asyncio.run(list_videos(args.url))
    else:
        result = get(args.url, args.slug, args.name, args.start, args.end, args.referer)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
