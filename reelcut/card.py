"""Designed cards — HTML fragments rendered to transparent PNG or webm overlays.

A card is `assets/<slug>/cards/<name>.html`: a fragment Claude writes for a line with nothing
to show from a source (numbered points, a side-by-side, a flow, code). It is wrapped in
`<div class="card">` with `card.css` and the bundled fonts, and rendered by headless Chromium.

A full-screen card (`full=True`) is a solid 9:16 slide covering the frame instead; its renders
are named `<name>.full.png` / `<name>.full.<key>.webm`.

A still card renders to `<name>.png` beside it, re-rendered whenever the fragment or the
stylesheet is newer, so images.json can point at the .html and always show its current text.

An animated card renders to `<name>.<key>.webm` (VP9 with alpha). Elements marked
`data-beat="N"` enter at the Nth offset, so a list or flow builds in time with the words;
`data-hot="N"` lights an element at the Nth offset until the next one lights, a `.count`
number counts up, `data-focus="N"` moves a camera in on an element (`data-focus-out="M"` pulls
back), and `data-swap="N"` rolls an element's words over to its `data-to` text. Entrances run on the video's spring (reelcut.motion), injected as the CSS
`--spring` easing and `--spring-s` duration. A fragment's own script can animate too: it
defines `window.reelcutSeek(seconds)` and `window.reelcutDuration`, and reads its beat times
from `window.reelcutBeats`.
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

from .motion import css_vars

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
  window.reelcutBeats = offs;
  let top = 0;
  const sec = n => offs[n - 1] ?? 0;
  const at = n => sec(n) + 's';
  // Camera: measured before anything animates, so every element is where it rests.
  const cam = document.querySelector('.cam');
  const shots = [];
  if (cam) {
    const c = cam.getBoundingClientRect();
    document.querySelectorAll('[data-focus]').forEach(el => {
      // Aim at what the element shows (its text and children), not its full-width box, and
      // never so close that it won't fit.
      const range = document.createRange();
      range.selectNodeContents(el);
      const r = range.getBoundingClientRect();
      const z = Math.max(1, Math.min(parseFloat(el.dataset.zoom) || 1.6,
                                     0.92 * c.width / r.width, 0.92 * c.height / r.height));
      const tx = z * (c.width / 2 - (r.left + r.width / 2 - c.left));
      const ty = z * (c.height / 2 - (r.top + r.height / 2 - c.top));
      top = Math.max(top, +el.dataset.focus);
      shots.push([sec(+el.dataset.focus), `translate(${tx}px, ${ty}px) scale(${z})`]);
      if (el.dataset.focusOut) {
        top = Math.max(top, +el.dataset.focusOut);
        shots.push([sec(+el.dataset.focusOut), 'none']);
      }
    });
  }
  document.querySelector('.card').classList.add('animated');
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
  // An SVG stroke marked .draw is measured as length 1, so CSS can draw it on with a dash.
  document.querySelectorAll('svg .draw').forEach(el => el.setAttribute('pathLength', '1'));
  // A .stagger's children enter one after another from the stagger's own entrance time.
  document.querySelectorAll('.stagger').forEach(el => {
    const base = parseFloat(getComputedStyle(el).getPropertyValue('--at')) || 0;
    [...el.children].forEach((c, i) => c.style.setProperty('--at', (base + i * 0.09) + 's'));
  });
  // data-swap="N": at beat N the words roll over to data-to, in place.
  document.querySelectorAll('[data-swap]').forEach(el => {
    top = Math.max(top, +el.dataset.swap);
    const next = document.createElement('span');
    next.className = 'swap-new';
    next.textContent = el.dataset.to || '';
    const old = document.createElement('span');
    old.className = 'swap-old';
    old.append(...el.childNodes);
    el.append(old, next);
    el.classList.add('swapping');
    el.style.setProperty('--swap-at', at(+el.dataset.swap));
  });
  if (shots.length) {
    const root = getComputedStyle(document.documentElement);
    const ease = root.getPropertyValue('--spring').trim() || 'ease-out';
    const move = parseFloat(root.getPropertyValue('--spring-s')) * 1600;  // a camera moves slower
    shots.sort((a, b) => a[0] - b[0]);
    const end = shots[shots.length - 1][0] * 1000 + move;
    const frames = [{offset: 0, transform: 'none', easing: 'linear'}];
    let last = 'none', at0 = 0;  // a shot called before the last one lands starts from there
    shots.forEach(([t, tf]) => {
      at0 = Math.max(at0, t * 1000 / end);
      frames.push({offset: at0, transform: last, easing: ease});
      at0 = Math.min(1, Math.max(at0, (t * 1000 + move) / end));
      frames.push({offset: at0, transform: tf, easing: 'linear'});
      last = tf;
    });
    cam.animate(frames, {duration: end, fill: 'both'});
  }
  return top;
}"""

# Pauses every animation and returns the card's layout box (untransformed, so it holds still
# while the card scales in) and the seconds until the last finite animation ends.
_JS_PAUSE = """() => {
  const anims = document.getAnimations();
  anims.forEach(a => a.pause());
  const end = Math.max((window.reelcutDuration || 0) * 1000, ...anims.map(a => {
    const t = a.effect.getComputedTiming().endTime;
    return Number.isFinite(t) ? t : 0;
  }));
  const c = document.querySelector('.card');
  return [{x: c.offsetLeft, y: c.offsetTop, width: c.offsetWidth, height: c.offsetHeight}, end / 1000];
}"""

_JS_SEEK = """ms => {
  document.getAnimations().forEach(a => { a.currentTime = ms; });
  if (window.reelcutSeek) window.reelcutSeek(ms / 1000);
}"""

# A still shows the card's finished state, even when its fragment carries its own animations.
_JS_FINISH = """() => {
  document.getAnimations().forEach(a => { try { a.finish(); } catch (e) {} });
  if (window.reelcutSeek) window.reelcutSeek(window.reelcutDuration || 0);
}"""


def card_png(html_path: Path, full: bool = False) -> Path:
    """The rendered PNG for a card fragment, rendering it first if it is missing or stale."""
    html_path = Path(html_path)
    png = _png_path(html_path, full)
    src_mtime = max(html_path.stat().st_mtime, _CSS.stat().st_mtime)
    if not png.exists() or png.stat().st_mtime < src_mtime:
        render_cards([html_path], full)
    return png


def render_cards(html_paths: list[Path], full: bool = False) -> list[Path]:
    """Render each fragment to `<stem>.png` (or `<stem>.full.png`) beside it, in one browser session."""
    out = []
    with _card_page(full) as load:
        for html_path in map(Path, html_paths):
            page = load(html_path)
            page.evaluate(_JS_FINISH)
            png = _png_path(html_path, full)
            page.locator(".card").screenshot(path=str(png), omit_background=True)
            out.append(png)
    return out


def _png_path(html_path: Path, full: bool) -> Path:
    return html_path.with_suffix(".full.png" if full else ".png")


def card_webm(html_path: Path, beats: list[float], fps: int, full: bool = False,
              spring: str = "snappy") -> tuple[Path, int]:
    """The animated render of a card whose Nth `data-beat` enters `beats[N-1]` seconds in.

    Named by a hash of the fragment, stylesheet, frame-rounded beats, fps and spring, so each
    hook's render reuses it and any edit renders a fresh one. Also returns the highest
    `data-beat` in the fragment, for the caller to check against len(beats).
    """
    html_path = Path(html_path)
    beats = [round(max(0.0, b) * fps) / fps for b in beats]
    key = hashlib.sha1(
        json.dumps([html_path.read_text(), _CSS.read_text(), beats, fps, spring]).encode()
    ).hexdigest()[:10]
    webm = html_path.with_name(f"{html_path.stem}.{'full.' if full else ''}{key}.webm")
    meta = webm.with_suffix(".json")
    if webm.exists() and meta.exists():
        return webm, json.loads(meta.read_text())["top_beat"]

    with _card_page(full, spring) as load, tempfile.TemporaryDirectory() as frames:
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


def card_strip(webm: Path, out: Path, fps: int, n: int = 12) -> Path:
    """A filmstrip of `n` frames spread over an animated card's render, to check it by eye."""
    from PIL import Image

    from .motion import contact_sheet

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-c:v", "libvpx-vp9", "-i", str(webm),
                        f"{tmp}/f%05d.png"], check=True)
        files = sorted(Path(tmp).glob("f*.png"))
        picks = sorted({round(i * (len(files) - 1) / max(1, n - 1)) for i in range(n)})
        contact_sheet([(f"{i / fps:.2f}s", Image.open(files[i]))
                       for i in picks], cols=4, cell_w=360).save(out)
    return out


@contextmanager
def _card_page(full: bool = False, spring: str = "snappy"):
    """A browser page and a `load(html_path)` that opens a fragment in it, fonts ready."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 2000})
        page_file = Path(tmp) / "card.html"

        def load(html_path: Path):
            page_file.write_text(_page(html_path, full, spring))
            page.goto(page_file.as_uri())
            page.evaluate("document.fonts.ready")
            return page

        try:
            yield load
        finally:
            browser.close()


def _page(html_path: Path, full: bool = False, spring: str = "snappy") -> str:
    """The full document for one fragment. `<base>` lets it reference images beside it.
    A fragment that uses `data-focus` is wrapped in a `.cam` the camera moves."""
    body = html_path.read_text()
    if "data-focus" in body:
        body = f"<div class='cam'>{body}</div>"
    faces = "".join(
        f'@font-face {{ font-family: "{family}"; font-weight: {weight}; font-style: {style}; '
        f'src: url(data:font/ttf;base64,{_font_b64(file)}) format("truetype"); }}\n'
        for family, (file, weight, style) in _FONTS.items()
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<base href='{html_path.resolve().parent.as_uri()}/'>"
        f"<style>{faces}{_CSS.read_text()}\n{css_vars(spring)}</style></head>"
        f"<body><div class='card{' full' if full else ''}'>{body}</div></body></html>"
    )


def _font_b64(name: str) -> str:
    return base64.b64encode((_HERE / "fonts" / name).read_bytes()).decode()
