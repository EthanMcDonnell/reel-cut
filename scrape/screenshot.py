#!/usr/bin/env python3
"""
Article Screenshot Capture

Captures the article text body and, optionally, specific paragraphs containing
supplied text snippets — for use as visual evidence during video filming.

Usage:
  python scrape/screenshot.py --url "<url>" --output-dir "<path>"
  python scrape/screenshot.py --url "<url>" --output-dir "<path>" \
      --snippets '["text to find", "another phrase"]'

Output (stdout):
  JSON: { "dir": "...", "files": [...], "skipped": "<reason or null>" }
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent

# Ordered list of selectors for the page's main heading
TITLE_SELECTORS = [
    "article h1",
    "main h1",
    '[itemprop="headline"]',
    '[class*="post-title"] h1',
    '[class*="article-title"]',
    '[class*="entry-title"]',
    "h1",
]

# Block-level ancestors to expand to when snapshotting a found text node
BLOCK_TAGS = {"p", "li", "blockquote", "section", "div", "figure", "pre"}

SNIPPET_HEIGHT = 420  # fixed viewport height for snippet crops — ensures consistent context


def _url_prefix(url: str) -> str:
    """Derive a short, unique-ish filename prefix from a URL."""
    parsed = urlparse(url)
    host = re.sub(r"[^a-z0-9]+", "-", parsed.netloc.replace("www.", "").split(".")[0].lower()).strip("-")
    path_parts = [p for p in parsed.path.split("/") if p]
    last = re.sub(r"[^a-z0-9]+", "-", path_parts[-1].lower()).strip("-")[:20] if path_parts else "page"
    return f"{host}-{last}"


# Playwright dict keys built from bytes — immune to quote-mangling formatters
_KX = bytes([120]).decode()
_KY = bytes([121]).decode()
_KW = bytes([119, 105, 100, 116, 104]).decode()
_KH = bytes([104, 101, 105, 103, 104, 116]).decode()


async def _dismiss_overlays(page) -> None:
    """Click cookie/consent accept buttons, then hide remaining fixed overlays."""
    _consent_selectors = [
        "button[id*='accept' i]", "button[class*='accept' i]",
        "button[id*='agree' i]", "button[class*='agree' i]",
        "button[id*='consent' i]", "button[class*='consent' i]",
        "button[data-testid*='accept' i]", "button[data-tracking*='accept' i]",
        "[aria-label*='Accept' i]", "[aria-label*='agree' i]",
        "#onetrust-accept-btn-handler", ".cc-accept", ".js-accept-cookies",
    ]
    for sel in _consent_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(400)
                break
        except Exception:
            pass

    # Hide any remaining fixed/sticky overlays (z-index > 100) and unlock scroll
    await page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const s = window.getComputedStyle(el);
            if ((s.position === 'fixed' || s.position === 'sticky') && parseInt(s.zIndex) > 100) {
                el.style.setProperty('display', 'none', 'important');
            }
        }
        document.body.style.setProperty('overflow', 'auto', 'important');
        document.documentElement.style.setProperty('overflow', 'auto', 'important');
    }""")


async def _find_title(page) -> object | None:
    """Return the first visible heading element, or None."""
    for selector in TITLE_SELECTORS:
        el = await page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box and box[_KH] > 0:
                return el
    return None


async def _block_ancestor(page, el) -> object:
    """Walk up the DOM to find the nearest block-level ancestor."""
    current = el
    for _ in range(6):
        tag = await page.evaluate("e => e.tagName.toLowerCase()", current)
        if tag in BLOCK_TAGS:
            return current
        parent = await page.evaluate_handle("e => e.parentElement", current)
        if not parent:
            break
        current = parent
    return el


async def capture(url: str, output_dir: Path, snippets: list[str | dict] | None = None) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"dir": str(output_dir), "files": [], "skipped": "playwright not installed"}

    sys.path.insert(0, str(ROOT / "scrape"))
    from playwright_utils import STEALTH_ARGS, stealth_context

    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / _url_prefix(url)
    source_dir.mkdir(parents=True, exist_ok=True)
    files = []
    file_entries = []  # (fname, snippet_text, context) for each successfully captured snippet

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        ctx = await stealth_context(browser)
        page = await ctx.new_page()
        await page.set_viewport_size({_KW: 390, _KH: 844})

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
        except Exception as exc:
            await browser.close()
            return {"dir": str(output_dir), "files": [], "skipped": f"page load failed: {exc}"}

        try:
            await _dismiss_overlays(page)
        except Exception:
            pass

        # --- Snippet-targeted paragraph screenshots ---
        # bytes([95,115,115,95,42,46,106,115]) == b'_ss_*.js'
        _js_dir = Path(__file__).parent
        _js_find, _js_highlight, _js_unhighlight = (
            f.read_text() for f in sorted(_js_dir.glob(bytes([95, 115, 115, 95, 42, 46, 106, 115]).decode()))
        )

        snippet_texts = []
        snippet_contexts = []
        for s in (snippets or []):
            if isinstance(s, dict):
                snippet_texts.append(s.get("text", ""))
                snippet_contexts.append(s.get("context", ""))
            else:
                snippet_texts.append(s)
                snippet_contexts.append("")

        if snippet_texts:
            for i, (snippet, context) in enumerate(zip(snippet_texts, snippet_contexts), start=1):
                anchor = snippet[:80].strip().lower()
                try:
                    el = await page.evaluate_handle(_js_find, anchor)

                    _js_isnull = bytes([101,32,61,62,32,33,101,32,124,124,32,33,101,46,116,97,103,78,97,109,101]).decode()
                    _js_scroll = bytes([101,32,61,62,32,101,46,115,99,114,111,108,108,73,110,116,111,86,105,101,119,40,123,98,108,111,99,107,58,34,99,101,110,116,101,114,34,44,32,105,110,108,105,110,101,58,34,99,101,110,116,101,114,34,125,41]).decode()
                    # returns [x, y, width, height] as array to avoid string key dict accesses
                    _js_rect = bytes([101,32,61,62,32,123,32,99,111,110,115,116,32,114,32,61,32,101,46,103,101,116,66,111,117,110,100,105,110,103,67,108,105,101,110,116,82,101,99,116,40,41,59,32,114,101,116,117,114,110,32,91,114,46,120,44,32,114,46,121,44,32,114,46,119,105,100,116,104,44,32,114,46,104,101,105,103,104,116,93,59,32,125]).decode()

                    if not el or await page.evaluate(_js_isnull, el):
                        continue

                    block = await _block_ancestor(page, el)
                    await page.evaluate(_js_scroll, block)
                    await page.wait_for_timeout(600)

                    r = await page.evaluate(_js_rect, block)
                    if not r or r[2] == 0:
                        continue
                    vw = 390
                    vh = 844
                    if r[0] > vw or r[1] > vh or r[0] + r[2] < 0 or r[1] + r[3] < 0:
                        continue
                    # Center the element vertically in a fixed-height window so every
                    # snippet shows consistent surrounding context above and below.
                    el_center_y = r[1] + r[3] / 2
                    y = max(0, el_center_y - SNIPPET_HEIGHT / 2)
                    y = min(y, max(0, vh - SNIPPET_HEIGHT))
                    clip = {
                        _KX: 0,
                        _KY: y,
                        _KW: vw,
                        _KH: min(SNIPPET_HEIGHT, vh - y),
                    }

                    await page.evaluate(_js_highlight, anchor)
                    fname = f"snippet-{i:02d}.png"
                    await page.screenshot(path=str(source_dir / fname), clip=clip)
                    files.append(fname)
                    file_entries.append((fname, snippet, context))
                    await page.evaluate(_js_unhighlight)
                except Exception:
                    continue

        await browser.close()

    subdir = source_dir.name
    snippet_entries = [
        {"file": f"{subdir}/{f}", "snippet": s, "context": c}
        for f, s, c in file_entries
    ]
    source_entry = {
        "url": url,
        "screenshots": snippet_entries,
    }
    manifest_path = output_dir / "manifest.json"
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    if not isinstance(existing, list):
        existing = [existing]  # migrate old single-object format
    existing = [s for s in existing if s.get("url") != url]  # replace if re-run for same URL
    existing.append(source_entry)
    manifest_path.write_text(json.dumps(existing, indent=2))

    return {"dir": str(output_dir), "files": [f"{subdir}/{f}" for f in files], "skipped": None}


def main():
    parser = argparse.ArgumentParser(description="Capture article text screenshots via Playwright")
    parser.add_argument("--url", required=True, help="Article URL")
    parser.add_argument("--output-dir", required=True, help="Directory to save screenshots")
    parser.add_argument("--snippets", default=None,
                        help='JSON array of text strings to locate and crop, e.g. \'["phrase one", "phrase two"]\'')
    args = parser.parse_args()

    snippets = json.loads(args.snippets) if args.snippets else None
    output_dir = Path(args.output_dir)
    result = asyncio.run(capture(args.url, output_dir, snippets=snippets))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
