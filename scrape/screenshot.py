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
import fcntl
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

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

SNIPPET_MIN_HEIGHT = 280   # smallest crop — keeps short stats from drowning in whitespace
SNIPPET_MAX_HEIGHT = 560    # largest crop — caps tall blocks so the highlight stays legible
SNIPPET_PADDING = 80        # context (px) shown above and below the matched element
SNIPPET_CONCURRENCY = 3     # max pages capturing snippets in parallel


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

# JS expressions built from bytes — immune to quote-mangling formatters
_JS_ISNULL = bytes([101,32,61,62,32,33,101,32,124,124,32,33,101,46,116,97,103,78,97,109,101]).decode()
# returns [x, y, width, height] as an array to avoid string-key dict accesses
_JS_RECT = bytes([101,32,61,62,32,123,32,99,111,110,115,116,32,114,32,61,32,101,46,103,101,116,66,111,117,110,100,105,110,103,67,108,105,101,110,116,82,101,99,116,40,41,59,32,114,101,116,117,114,110,32,91,114,46,120,44,32,114,46,121,44,32,114,46,119,105,100,116,104,44,32,114,46,104,101,105,103,104,116,93,59,32,125]).decode()
# scrollIntoView handles custom scroll containers; fall back to window.scrollTo for SPAs
_JS_SCROLL_ABS = (
    "e => {"
    " e.scrollIntoView({block: 'center', behavior: 'instant'});"
    " const r = e.getBoundingClientRect();"
    " if (r.top < 0 || r.top > window.innerHeight) {"
    "   const absY = r.top + window.pageYOffset;"
    "   window.scrollTo({top: Math.max(0, absY - window.innerHeight/2 + r.height/2), behavior: 'instant'});"
    " }"
    " }"
)

# Per-snippet match metadata set on window by _ss_find.js (found / confidence / matchType).
_JS_LASTMATCH = "() => window.__ssLastMatch || {found: false, confidence: 0, matchType: 'none'}"


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


def _caption_to_filename(text: str, index: int, ext: str) -> str:
    """Turn caption/alt text into a safe filename."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]
    if not slug:
        slug = f"image-{index:02d}"
    return f"{slug}{ext}"


async def _extract_article_images(page, page_url: str, dest_dir: Path) -> list[str]:
    """Download all meaningful images from the article body."""
    ARTICLE_SELECTORS = [
        "article", "main", '[class*="post-content"]', '[class*="article-body"]',
        '[class*="entry-content"]', '[class*="story-body"]', '[itemprop="articleBody"]',
    ]

    # Build JS to collect image info from the first matching article container
    js = """(selectors) => {
        let container = null;
        for (const sel of selectors) {
            container = document.querySelector(sel);
            if (container) break;
        }
        if (!container) container = document.body;

        return Array.from(container.querySelectorAll('img')).map(img => {
            const src = img.currentSrc || img.src || '';
            const alt = (img.alt || '').trim();
            // Look for figcaption sibling or parent figure's caption
            let caption = '';
            const fig = img.closest('figure');
            if (fig) {
                const cap = fig.querySelector('figcaption');
                if (cap) caption = cap.innerText.trim();
            }
            const naturalW = img.naturalWidth || 0;
            const naturalH = img.naturalHeight || 0;
            return { src, alt, caption, naturalW, naturalH };
        });
    }"""

    try:
        images = await page.evaluate(js, ARTICLE_SELECTORS)
    except Exception:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": page_url,
    }

    saved = []
    seen_srcs = set()
    idx = 0
    for img in images:
        src = img.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue
        # Skip tiny images (icons / tracking pixels) — require at least 100px in both dims
        w, h = img.get("naturalW", 0), img.get("naturalH", 0)
        if w > 0 and h > 0 and (w < 100 or h < 100):
            continue
        abs_src = urljoin(page_url, src)
        # Deduplicate by resolved URL (strip query strings for comparison)
        src_key = abs_src.split("?")[0]
        if src_key in seen_srcs:
            continue
        seen_srcs.add(src_key)

        # Determine extension
        path_part = urlparse(abs_src).path
        raw_ext = Path(path_part).suffix.lower()
        ext = raw_ext if raw_ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"} else ".jpg"

        label = img.get("caption") or img.get("alt") or ""
        fname = _caption_to_filename(label, idx, ext)
        # Avoid collisions
        dest = dest_dir / fname
        collision = 0
        while dest.exists():
            collision += 1
            dest = dest_dir / f"{dest.stem}-{collision}{ext}"

        try:
            req = urllib.request.Request(abs_src, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                dest.write_bytes(resp.read())
            saved.append(dest.name)
            idx += 1
        except Exception:
            continue

    return saved


def _crop_window(el_top: float, el_height: float, vh: int) -> tuple[float, float]:
    """Return (y, height) for a snippet crop sized to the matched element.

    The crop hugs the element (plus SNIPPET_PADDING of context above and below),
    clamped to [SNIPPET_MIN_HEIGHT, SNIPPET_MAX_HEIGHT] and the viewport, then centred
    on the element. Short stats stay tight; tall blocks no longer get clipped by a
    one-size-fits-all window.
    """
    crop_h = max(SNIPPET_MIN_HEIGHT, min(SNIPPET_MAX_HEIGHT, int(el_height) + 2 * SNIPPET_PADDING))
    crop_h = min(crop_h, vh)
    el_center_y = el_top + el_height / 2
    y = max(0, el_center_y - crop_h / 2)
    y = min(y, max(0, vh - crop_h))
    return y, min(crop_h, vh - y)


def _write_manifest(output_dir: Path, url: str, source_entry: dict) -> None:
    """Append/replace this URL's entry in manifest.json under an exclusive file lock.

    The lock serialises the read-modify-write so concurrent screenshot processes writing
    to the same output dir can't clobber each other's entries.
    """
    manifest_path = output_dir / "manifest.json"
    lock_path = output_dir / ".manifest.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
        if not isinstance(existing, list):
            existing = [existing]  # migrate old single-object format
        existing = [s for s in existing if s.get("url") != url]  # replace if re-run for same URL
        existing.append(source_entry)
        manifest_path.write_text(json.dumps(existing, indent=2))


async def _prepare_page(ctx, url: str):
    """Open a mobile-viewport page, load the URL, and dismiss consent overlays."""
    page = await ctx.new_page()
    await page.set_viewport_size({_KW: 390, _KH: 844})
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        # networkidle can time out on pages with persistent background requests — fall back
        await page.goto(url, wait_until="load", timeout=30000)
    await page.wait_for_load_state("load")
    await page.wait_for_timeout(600)  # brief settle for late layout shifts / lazy content
    try:
        await _dismiss_overlays(page)
    except Exception:
        pass
    return page


async def _capture_snippet(
    page, source_dir: Path, index: int, snippet: str, context: str,
    js_find: str, js_highlight: str, js_unhighlight: str,
) -> dict:
    """Locate, highlight, and screenshot one snippet.

    Always returns a status dict. On success it carries "found": True plus the written
    "fname"; on failure it carries "found": False and a "reason", so the caller can report
    which claims lost their on-screen evidence instead of dropping them silently.
    """
    raw = snippet.strip().lower()
    anchor = raw[:80]
    if len(raw) > 80 and ' ' in anchor:
        anchor = anchor[:anchor.rfind(' ')]

    def _miss(reason: str, meta: dict | None = None) -> dict:
        meta = meta or {}
        return {
            "index": index, "found": False, "snippet": snippet, "context": context,
            "match_type": meta.get("matchType", "none"),
            "confidence": meta.get("confidence", 0.0), "reason": reason,
        }

    try:
        # Pass the full snippet and the script context so find can disambiguate when the
        # anchor matches several blocks (e.g. paragraphs sharing an opening phrase).
        el = await page.evaluate_handle(
            js_find, {"anchor": anchor, "snippet": raw, "context": context.strip().lower()}
        )
        meta = await page.evaluate(_JS_LASTMATCH)
        if not el or await page.evaluate(_JS_ISNULL, el):
            return _miss("text not found on page", meta)

        await page.evaluate(_JS_SCROLL_ABS, el)
        await page.wait_for_timeout(600)

        r = await page.evaluate(_JS_RECT, el)
        if not r or r[2] == 0:
            return _miss("matched element has no size", meta)
        vw, vh = 390, 844
        if r[0] > vw or r[1] > vh or r[0] + r[2] < 0 or r[1] + r[3] < 0:
            return _miss("matched element off-screen", meta)

        y, crop_h = _crop_window(r[1], r[3], vh)
        clip = {_KX: 0, _KY: y, _KW: vw, _KH: crop_h}

        await page.evaluate(js_highlight, anchor)
        fname = f"snippet-{index:02d}.png"
        await page.screenshot(path=str(source_dir / fname), clip=clip)
        await page.evaluate(js_unhighlight)
        return {
            "index": index, "found": True, "fname": fname,
            "snippet": snippet, "context": context,
            "match_type": meta.get("matchType", "exact"),
            "confidence": meta.get("confidence", 1.0),
        }
    except Exception as exc:
        return _miss(f"capture error: {exc}")


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
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        ctx = await stealth_context(browser, device_scale_factor=2)

        try:
            main_page = await _prepare_page(ctx, url)
        except Exception as exc:
            await browser.close()
            return {"dir": str(output_dir), "files": [], "skipped": f"page load failed: {exc}"}

        # --- Download embedded article images ---
        try:
            await _extract_article_images(main_page, url, source_dir)
        except Exception:
            pass

        # --- Load snippet-targeting JS helpers ---
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

        # --- Capture snippets across a small pool of pages (bounded concurrency) ---
        statuses: list[dict] = []
        if snippet_texts:
            queue: asyncio.Queue = asyncio.Queue()
            for i, (snippet, context) in enumerate(zip(snippet_texts, snippet_contexts), start=1):
                queue.put_nowait((i, snippet, context))

            async def _worker(page):
                while True:
                    try:
                        i, snippet, context = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    statuses.append(await _capture_snippet(
                        page, source_dir, i, snippet, context,
                        _js_find, _js_highlight, _js_unhighlight,
                    ))

            # main_page is the first worker; spin up extra prepared pages for parallelism.
            # If an extra page fails to load, the remaining workers still drain the queue.
            worker_pages = [main_page]
            for _ in range(min(SNIPPET_CONCURRENCY, len(snippet_texts)) - 1):
                try:
                    worker_pages.append(await _prepare_page(ctx, url))
                except Exception:
                    pass

            await asyncio.gather(*[_worker(p) for p in worker_pages])

        await browser.close()

    statuses.sort(key=lambda s: s["index"])
    subdir = source_dir.name
    hits = [s for s in statuses if s["found"]]
    misses = [s for s in statuses if not s["found"]]

    snippet_entries = [
        {
            "file": f"{subdir}/{h['fname']}",
            "snippet": h["snippet"],
            "context": h["context"],
            "match_type": h["match_type"],
            "confidence": round(h["confidence"], 2),
        }
        for h in hits
    ]
    source_entry = {"url": url, "screenshots": snippet_entries}
    if misses:
        source_entry["missed"] = [
            {"snippet": m["snippet"], "context": m["context"], "reason": m["reason"]}
            for m in misses
        ]
    _write_manifest(output_dir, url, source_entry)

    return {
        "dir": str(output_dir),
        "files": [e["file"] for e in snippet_entries],
        "skipped": None,
        "snippets": [
            {
                "index": s["index"],
                "found": s["found"],
                "snippet": s["snippet"],
                "match_type": s.get("match_type", "none"),
                "confidence": round(s.get("confidence", 0.0), 2),
                "reason": s.get("reason"),
            }
            for s in statuses
        ],
    }


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
