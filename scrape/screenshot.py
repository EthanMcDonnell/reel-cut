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

SNIPPET_MIN_HEIGHT = 280   # smallest crop — keeps short stats from drowning in whitespace
SNIPPET_MAX_HEIGHT = 560    # largest crop — caps tall blocks so the highlight stays legible
SNIPPET_PADDING = 80        # context (px) shown above and below the matched element
SNIPPET_CONCURRENCY = 3     # max pages capturing snippets in parallel


def _parse_snippet_spec(s: str | dict) -> dict:
    """Normalise a bare string or partial dict to a full four-field spec."""
    if isinstance(s, dict):
        return {
            "article_snippet": s.get("article_snippet", ""),
            "script_context": s.get("script_context", ""),
            "trigger_show_word": s.get("trigger_show_word", ""),
            "trigger_go_away_word": s.get("trigger_go_away_word", ""),
        }
    return {"article_snippet": s, "script_context": "", "trigger_show_word": "", "trigger_go_away_word": ""}


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
# Scroll the tagged element to viewport centre and read its live bounding rect. Used instead
# of the highlighter's Range rect (window.__ssRegion), which goes stale on pages that reflow
# after scrolling — Reddit lazy-loads comments and collapses the post body, leaving the Range's
# cached rect pointing at a viewport slot that now holds a different element (a comment / a
# "Related posts" card). The live element rect, measured after a settle, stays correct.
_JS_SCROLL_TARGET = "() => { const t = document.querySelector('[data-snippet-target]'); if (t) t.scrollIntoView({block: 'center', behavior: 'instant'}); }"
_JS_TARGET_RECT = (
    "() => { const t = document.querySelector('[data-snippet-target]'); if (!t) return null;"
    " const b = t.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; }"
)

# The highlighted region set by _ss_highlight.js: a Range for a tight match, the block Element
# for a whole_block fallback. Both answer getBoundingClientRect, so one pair of helpers covers
# them. Centring on the region rather than the block is what keeps the proof in frame: a tight
# highlight near the end of a tall paragraph falls outside a crop centred on that paragraph.
_JS_SCROLL_REGION = (
    "() => { const r = window.__ssRegion; if (!r || !r.getBoundingClientRect) return false;"
    " const b = r.getBoundingClientRect(); if (!b.width && !b.height) return false;"
    " window.scrollBy(0, b.top + b.height / 2 - window.innerHeight / 2); return true; }"
)
_JS_REGION_RECT = (
    "() => { const r = window.__ssRegion; if (!r || !r.getBoundingClientRect) return null;"
    " const b = r.getBoundingClientRect(); if (!b.width && !b.height) return null;"
    " return [b.x, b.y, b.width, b.height]; }"
)

# Per-snippet match metadata set on window by _ss_find.js (found / confidence / matchType).
_JS_LASTMATCH = "() => window.__ssLastMatch || {found: false, confidence: 0, matchType: 'none'}"

# Which highlight path won, set on window by _ss_highlight.js: a tight 'range' / 'fuzzy_range',
# the blunt 'whole_block' fallback that colours the entire paragraph, or 'anchor_range' — the
# full snippet was not found and only its first 80 characters got highlighted, so the screenshot
# shows the run-up to the claim and stops before the proof. `match_type`/`confidence` come from
# find(), which matches on that same 80-char anchor, so they report a clean exact hit either way:
# this field is the only signal that the highlight is a prefix.
_JS_HIGHLIGHT = "() => window.__ssHighlight || 'none'"

_ANCHOR_MAX_CHARS = 80


def _snippet_anchor(raw: str) -> str:
    """The short prefix find() locates the snippet's block by, cut at a word boundary.

    A long snippet is more likely to hit typography drift between the scraped text and the
    live DOM, so find matches on this prefix instead. That makes the anchor a *strict*
    prefix of the proof whenever the snippet runs past `_ANCHOR_MAX_CHARS`, which is what
    lets _ss_highlight.js end up highlighting only the run-up to a claim — it reports that
    case as `anchor_range` rather than the plain `range` a full match earns.
    """
    if len(raw) <= _ANCHOR_MAX_CHARS:
        return raw
    anchor = raw[:_ANCHOR_MAX_CHARS]
    return anchor[:anchor.rfind(" ")] if " " in anchor else anchor


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


async def _expand_truncations(page) -> None:
    """Click "Read more"/"See more" expanders so collapsed bodies are fully rendered.

    Long Reddit self-posts collapse behind a "Read more" fade; text below the fold renders
    greyed-out and clipped, so a snippet that lands there screenshots as a washed-out highlight.
    Clicking the expander first makes the whole body solid and measurable. Two passes catch
    expanders that only appear once an outer one opens. Expand-only, so it can't re-collapse.
    """
    for _ in range(2):
        clicked = await page.evaluate("""() => {
            let n = 0;
            for (const el of document.querySelectorAll('button, [role="button"], a, summary')) {
                if (!/^\\s*(read|see|show)\\s+more\\b/i.test(el.innerText || '')) continue;
                if (el.tagName === 'A') {
                    const href = el.getAttribute('href') || '';
                    if (href && !href.startsWith('#') && !href.startsWith('javascript:')) continue;  // navigational link, not an in-page expander
                }
                try { el.click(); n++; } catch (e) {}
            }
            return n;
        }""")
        if not clicked:
            break
        await page.wait_for_timeout(500)


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


def _unproven_figures(context: str, snippet: str) -> list[str]:
    """Numbers the script says out loud that the highlighted snippet doesn't contain.

    The highlight is drawn over `article_snippet` alone, so a figure outside it is
    unproven even when it sits in the captured crop — the viewer's eye follows the
    colour, not the paragraph. Digits only: a spelled-out number in the script has no
    verbatim form to match against the article anyway.
    """
    want = set(re.findall(r"\d+(?:\.\d+)?", context))
    return sorted(want - set(re.findall(r"\d+(?:\.\d+)?", snippet)), key=float)


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
    from playwright_utils import wait_out_challenge
    await wait_out_challenge(page)  # proof-of-work walls clear themselves; the rest fall to the retry loop
    try:
        await _dismiss_overlays(page)
    except Exception:
        pass
    try:
        await _expand_truncations(page)
    except Exception:
        pass
    return page


async def _capture_snippet(
    page, source_dir: Path, index: int, spec: dict,
    js_find: str, js_highlight: str, js_unhighlight: str,
) -> dict:
    """Locate, highlight, and screenshot one snippet.

    `spec` carries the snippet's metadata: `article_snippet` (verbatim source text to
    locate), `script_context` (the script line it supports, used to disambiguate), and the
    optional `trigger_show_word` / `trigger_go_away_word` anchors that produce-video uses to
    bound the on-screen window. Only `article_snippet` and `script_context` drive capture;
    the trigger words are passed straight through to the manifest.

    Always returns a status dict. On success it carries "found": True plus the written
    "fname"; on failure it carries "found": False and a "reason", so the caller can report
    which claims lost their on-screen evidence instead of dropping them silently.
    """
    snippet = spec["article_snippet"]
    context = spec["script_context"]
    raw = snippet.strip().lower()
    anchor = _snippet_anchor(raw)

    # Renamed/added metadata carried verbatim onto every status dict (hit or miss).
    meta_fields = {
        "article_snippet": snippet,
        "script_context": context,
        "trigger_show_word": spec.get("trigger_show_word", ""),
        "trigger_go_away_word": spec.get("trigger_go_away_word", ""),
        "unproven_figures": _unproven_figures(context, snippet),
    }

    def _miss(reason: str, meta: dict | None = None) -> dict:
        meta = meta or {}
        return {
            "index": index, "found": False, **meta_fields,
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

        # Highlight first: this locates the snippet across inline tags and marks it. Then centre
        # on the highlighted *region* and measure its rect only after the scroll has settled —
        # on pages that reflow after scrolling (Reddit), a rect read before the scroll goes stale
        # and the crop lands on the wrong place. Centring on the block instead is what put a
        # highlight near the end of a long paragraph outside its own crop, so fall back to the
        # tagged element only when there is no usable region.
        await page.evaluate(js_highlight, {"anchor": anchor, "snippet": raw})
        if await page.evaluate(_JS_SCROLL_REGION):
            await page.wait_for_timeout(700)
            r = await page.evaluate(_JS_REGION_RECT)
        else:
            r = None
        if not r:
            await page.evaluate(_JS_SCROLL_TARGET)
            await page.wait_for_timeout(700)
            r = await page.evaluate(_JS_TARGET_RECT)
        if not r or r[2] == 0:
            return _miss("matched element has no size", meta)
        vw, vh = 390, 844
        if r[0] > vw or r[1] > vh or r[0] + r[2] < 0 or r[1] + r[3] < 0:
            return _miss("matched element off-screen", meta)

        y, crop_h = _crop_window(r[1], r[3], vh)
        clip = {_KX: 0, _KY: y, _KW: vw, _KH: crop_h}

        highlight = await page.evaluate(_JS_HIGHLIGHT)
        fname = f"snippet-{index:02d}.png"
        await page.screenshot(path=str(source_dir / fname), clip=clip)
        await page.evaluate(js_unhighlight)
        return {
            "index": index, "found": True, "fname": fname, **meta_fields,
            "match_type": meta.get("matchType", "exact"),
            "confidence": meta.get("confidence", 1.0),
            "highlight": highlight,
        }
    except Exception as exc:
        return _miss(f"capture error: {exc}")


async def capture(url: str, output_dir: Path, snippets: list[str | dict] | None = None,
                  solve_captcha: bool = False, solve_timeout: int = 300) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"dir": str(output_dir), "files": [], "skipped": "playwright not installed"}

    sys.path.insert(0, str(ROOT / "scrape"))
    from playwright_utils import (
        BOT_BLOCK_RETRIES, STEALTH_ARGS, is_bot_block, stealth_context,
        stealth_persistent_context,
    )
    from single_scrape import CAPTCHA_PROFILE

    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / _url_prefix(url)
    source_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = ctx = main_page = None

        async def _close():
            if browser:
                await browser.close()
            elif ctx:
                await ctx.close()

        # A wall is a per-request dice roll that never clears on its own, so the only retry
        # that helps is a brand new context. --solve-captcha gets one attempt: tearing the
        # browser down would close the window the human is solving in.
        attempts = 1 if solve_captcha else BOT_BLOCK_RETRIES
        for attempt in range(1, attempts + 1):
            if solve_captcha:
                # Reuses the profile primed by `single_scrape.py --solve-captcha`, so a wall
                # already cleared for this source usually needs no interaction here.
                ctx = await stealth_persistent_context(pw, str(CAPTCHA_PROFILE), device_scale_factor=2)
            else:
                browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
                ctx = await stealth_context(browser, device_scale_factor=2)
            try:
                main_page = await _prepare_page(ctx, url)
            except Exception as exc:
                await _close()
                return {"dir": str(output_dir), "files": [], "skipped": f"page load failed: {exc}"}
            if not is_bot_block(await main_page.content()):
                break
            if attempt < attempts:
                print(f"Anti-bot wall hit (attempt {attempt}/{attempts}) — retrying with a "
                      f"fresh browser context...", file=sys.stderr, flush=True)
                await _close()
                browser = ctx = None

        if is_bot_block(await main_page.content()):
            if solve_captcha:
                print(f"Anti-bot wall hit — solve it in the open browser window "
                      f"(waiting up to {solve_timeout}s)...", file=sys.stderr, flush=True)
                for _ in range(solve_timeout // 2):
                    if not is_bot_block(await main_page.content()):
                        break
                    await main_page.wait_for_timeout(2000)
            if is_bot_block(await main_page.content()):
                # Without this the CAPTCHA page itself gets screenshotted as "evidence".
                await _close()
                return {"dir": str(output_dir), "files": [],
                        "skipped": f"blocked by anti-bot protection after {attempts} attempt(s) "
                                   f"— no screenshots captured. Re-running often clears it; "
                                   f"otherwise use --solve-captcha to clear it by hand."}

        # --- Load snippet-targeting JS helpers ---
        # bytes([95,115,115,95,42,46,106,115]) == b'_ss_*.js'
        _js_dir = Path(__file__).parent
        _js_find, _js_highlight, _js_unhighlight = (
            f.read_text() for f in sorted(_js_dir.glob(bytes([95, 115, 115, 95, 42, 46, 106, 115]).decode()))
        )

        # Normalise each requested snippet to a spec dict.
        specs: list[dict] = [_parse_snippet_spec(s) for s in (snippets or [])]

        # --- Capture snippets across a small pool of pages (bounded concurrency) ---
        statuses: list[dict] = []
        if specs:
            queue: asyncio.Queue = asyncio.Queue()
            for i, spec in enumerate(specs, start=1):
                queue.put_nowait((i, spec))

            async def _worker(page):
                while True:
                    try:
                        i, spec = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    statuses.append(await _capture_snippet(
                        page, source_dir, i, spec,
                        _js_find, _js_highlight, _js_unhighlight,
                    ))

            # main_page is the first worker; spin up extra prepared pages for parallelism.
            # If an extra page fails to load, the remaining workers still drain the queue.
            worker_pages = [main_page]
            for _ in range(min(SNIPPET_CONCURRENCY, len(specs)) - 1):
                try:
                    worker_pages.append(await _prepare_page(ctx, url))
                except Exception:
                    pass

            await asyncio.gather(*[_worker(p) for p in worker_pages])

        await _close()

    statuses.sort(key=lambda s: s["index"])
    subdir = source_dir.name
    hits = [s for s in statuses if s["found"]]
    misses = [s for s in statuses if not s["found"]]

    snippet_entries = [
        {
            "file": f"{subdir}/{h['fname']}",
            "article_snippet": h["article_snippet"],
            "script_context": h["script_context"],
            "trigger_show_word": h["trigger_show_word"],
            "trigger_go_away_word": h["trigger_go_away_word"],
            "match_type": h["match_type"],
            "confidence": round(h["confidence"], 2),
            "highlight": h["highlight"],
            **({"unproven_figures": h["unproven_figures"]} if h["unproven_figures"] else {}),
        }
        for h in hits
    ]
    source_entry = {"url": url, "screenshots": snippet_entries}
    if misses:
        source_entry["missed"] = [
            {"article_snippet": m["article_snippet"], "script_context": m["script_context"],
             "reason": m["reason"]}
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
                "article_snippet": s["article_snippet"],
                "match_type": s.get("match_type", "none"),
                "confidence": round(s.get("confidence", 0.0), 2),
                "highlight": s.get("highlight", "none"),
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
                        help='JSON array of snippet specs to locate and crop. Each is an object '
                             '{"article_snippet": "...", "script_context": "...", '
                             '"trigger_show_word": "...", "trigger_go_away_word": "..."} '
                             '(context/trigger fields optional), or a bare string for article_snippet only.')
    parser.add_argument("--solve-captcha", action="store_true",
                        help="Use the persistent browser profile shared with single_scrape.py and, "
                             "if a wall still appears, open it visibly and wait for you to clear it.")
    parser.add_argument("--solve-timeout", type=int, default=300, metavar="SECONDS",
                        help="How long --solve-captcha waits for you (default: 300)")
    args = parser.parse_args()

    snippets = json.loads(args.snippets) if args.snippets else None
    output_dir = Path(args.output_dir)
    result = asyncio.run(capture(args.url, output_dir, snippets=snippets,
                                 solve_captcha=args.solve_captcha,
                                 solve_timeout=args.solve_timeout))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
