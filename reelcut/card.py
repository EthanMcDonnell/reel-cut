"""Designed cards — HTML fragments rendered to transparent PNG overlays.

A card is `assets/<slug>/cards/<name>.html`: a fragment Claude writes for a line with nothing
to show from a source (numbered points, a side-by-side, a flow, code). It is wrapped in
`<div class="card">` with `card.css` and the bundled fonts, and rendered by headless Chromium
to `<name>.png` beside it. The PNG is re-rendered whenever the fragment or the stylesheet is
newer, so images.json can point at the .html and always show its current text.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_CSS = _HERE / "card.css"
_FONTS = {  # @font-face family → (bundled file, weight range, style)
    "Inter": ("Inter.ttf", "100 900", "normal"),
    "Playfair Display": ("PlayfairDisplay.ttf", "400 900", "normal"),
}


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
    from playwright.sync_api import sync_playwright

    out = []
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 2000})
        for html_path in map(Path, html_paths):
            page_file = Path(tmp) / "card.html"
            page_file.write_text(_page(html_path))
            page.goto(page_file.as_uri())
            page.evaluate("document.fonts.ready")
            png = html_path.with_suffix(".png")
            page.locator(".card").screenshot(path=str(png), omit_background=True)
            out.append(png)
        browser.close()
    return out


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
