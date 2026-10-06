"""Designed cards — HTML fragments rendered to transparent PNG or webm overlays.

A card is `assets/<slug>/cards/<name>.html`: a fragment Claude writes for a line with nothing
to show from a source (numbered points, a side-by-side, a flow, code). It is wrapped in
`<div class="card">` with `card.css` and the bundled fonts, and rendered by headless Chromium.

A still card renders to `<name>.png` beside it, re-rendered whenever the fragment or the
stylesheet is newer, so images.json can point at the .html and always show its current text.

An animated card renders to `<name>.<key>.webm` (VP9 with alpha). Elements marked
`data-beat="N"` enter at the Nth offset, so a list or flow builds in time with the words;
`data-hot="N"` lights an element at the Nth offset until the next one lights, and a `.count`
number counts up.
The card's CSS animations are paused and stepped frame by frame, so the capture is exact
whatever the machine's speed. Capture stops once every animation has finished; the overlay
holds the last frame for the rest of its window.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

_HERE = Path(__file__).parent
_CSS = _HERE / "card.css"
_FONTS = {  # @font-face family → (bundled file, weight range, style)
    "Inter": ("Inter.ttf", "100 900", "normal"),
    "Playfair Display": ("PlayfairDisplay.ttf", "400 900", "normal"),
}

# Marks the card animated and gives each [data-beat] its entrance time as --at. A [data-hot]
# lights up at its beat (--hot-at) and dims at the next higher data-hot's beat (--hot-off), so
# the highlight moves through the card. A whole-number .count counts up from 0.
# Returns the highest beat number used, so a fragment with more beats than times is caught.
_JS_SET_BEATS = """offs => {
  document.querySelector('.card').classList.add('animated');
  let top = 0;
  const at = n => (offs[n - 1] ?? 0) + 's';
  document.querySelectorAll('[data-beat]').forEach(el => {
    const n = parseInt(el.dataset.beat, 10) || 0;
    top = Math.max(top, n);
    el.style.setProperty('--at', at(n));
  });
  const hots = [...document.querySelectorAll('[data-hot]')].map(el => [parseInt(el.dataset.hot, 10) || 0, el]);
  hots.forEach(([n, el]) => {
    top = Math.max(top, n);
    el.style.setProperty('--hot-at', at(n));
    const next = Math.min(...hots.map(([m]) => m).filter(m => m > n));
    if (Number.isFinite(next)) { el.style.setProperty('--hot-off', at(next)); el.dataset.cools = ''; }
  });
  document.querySelectorAll('.count').forEach(el => {
    const s = el.textContent.trim();
    if (!/^[0-9]+$/.test(s)) return;
    el.style.setProperty('--to', s);
    el.style.minWidth = s.length + 'ch';
    el.textContent = '';
    el.classList.add('counting');
  });
  return top;
}"""

# Pauses every animation and returns the card's layout box (untransformed, so it holds still
# while the card scales in) and the seconds until the last finite animation ends.
_JS_PAUSE = """() => {
  const anims = document.getAnimations();
  anims.forEach(a => a.pause());
  const end = Math.max(0, ...anims.map(a => {
    const t = a.effect.getComputedTiming().endTime;
    return Number.isFinite(t) ? t : 0;
  }));
  const c = document.querySelector('.card');
  return [{x: c.offsetLeft, y: c.offsetTop, width: c.offsetWidth, height: c.offsetHeight}, end / 1000];
}"""

_JS_SEEK = "ms => document.getAnimations().forEach(a => { a.currentTime = ms; })"

# A still shows the card's finished state, even when its fragment carries its own animations.
_JS_FINISH = "() => document.getAnimations().forEach(a => { try { a.finish(); } catch (e) {} })"


def card_png(html_path: Path) -> Path:
    """The rendered PNG for a card fragment, rendering it first if it is missing or stale."""
    html_path = Path(html_path)
    png = html_path.with_suffix(".png")
    src_mtime = max(html_path.stat().st_mtime, _CSS.stat().st_mtime)
    if not png.exists() or png.stat().st_mtime < src_mtime:
        render_cards([html_path])
    return png


def render_cards(html_paths: list[Path]) -> list[Path]:
    """Render each fragment to `<stem>.png` beside it, in one browser session."""
    out = []
    with _card_page() as load:
        for html_path in map(Path, html_paths):
            page = load(html_path)
            page.evaluate(_JS_FINISH)
            png = html_path.with_suffix(".png")
            page.locator(".card").screenshot(path=str(png), omit_background=True)
            out.append(png)
    return out


def card_webm(html_path: Path, beats: list[float], fps: int) -> tuple[Path, int]:
    """The animated render of a card whose Nth `data-beat` enters `beats[N-1]` seconds in.

    Named by a hash of the fragment, stylesheet, frame-rounded beats and fps, so each hook's
    render reuses it and any edit renders a fresh one. Also returns the highest `data-beat`
    in the fragment, for the caller to check against len(beats).
    """
    html_path = Path(html_path)
    beats = [round(max(0.0, b) * fps) / fps for b in beats]
    key = hashlib.sha1(
        json.dumps([html_path.read_text(), _CSS.read_text(), beats, fps]).encode()
    ).hexdigest()[:10]
    webm = html_path.with_name(f"{html_path.stem}.{key}.webm")
    meta = webm.with_suffix(".json")
    if webm.exists() and meta.exists():
        return webm, json.loads(meta.read_text())["top_beat"]

    with _card_page() as load, tempfile.TemporaryDirectory() as frames:
        page = load(html_path)
        top_beat = page.evaluate(_JS_SET_BEATS, beats)
        box, end_s = page.evaluate(_JS_PAUSE)
        for f in range(math.ceil(end_s * fps) + 1):
            page.evaluate(_JS_SEEK, f * 1000 / fps)
            page.screenshot(path=f"{frames}/f{f:05d}.png", clip=box, omit_background=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
             "-i", f"{frames}/f%05d.png", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
             "-b:v", "0", "-crf", "20", "-auto-alt-ref", "0", str(webm)],
            check=True,
        )
    meta.write_text(json.dumps({"top_beat": top_beat}))
    return webm, top_beat


@contextmanager
def _card_page():
    """A browser page and a `load(html_path)` that opens a fragment in it, fonts ready."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 2000})
        page_file = Path(tmp) / "card.html"

        def load(html_path: Path):
            page_file.write_text(_page(html_path))
            page.goto(page_file.as_uri())
            page.evaluate("document.fonts.ready")
            return page

        try:
            yield load
        finally:
            browser.close()


def _page(html_path: Path) -> str:
    """The full document for one fragment. `<base>` lets it reference images beside it."""
    faces = "".join(
        f'@font-face {{ font-family: "{family}"; font-weight: {weight}; font-style: {style}; '
        f'src: url(data:font/ttf;base64,{_font_b64(file)}) format("truetype"); }}\n'
        for family, (file, weight, style) in _FONTS.items()
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<base href='{html_path.resolve().parent.as_uri()}/'>"
        f"<style>{faces}{_CSS.read_text()}</style></head>"
        f"<body><div class='card'>{html_path.read_text()}</div></body></html>"
    )


def _font_b64(name: str) -> str:
    return base64.b64encode((_HERE / "fonts" / name).read_bytes()).decode()
