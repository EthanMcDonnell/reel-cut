#!/usr/bin/env python3
"""
Article Figure Harvester

Finds explanatory figures (charts / diagrams) embedded in an article, filters out the
junk deterministically, and downloads the survivors for a video overlay. This is the
Stage-1 (no-AI) half of the "article figures in video" feature: it produces a ranked
candidate set + local images; the produce-script agent then *reads* the images to judge
kind / legibility / relevance and pick the final ones.

Deterministic pipeline (no AI):
  1. Load the page (desktop viewport), dismiss overlays, expand "read more".
  2. Enumerate every <figure>/<img>/<svg> inside the article body.
  3. Reject icons/avatars/logos/ads/banners by size, aspect ratio, and URL/class blocklist.
  4. Score a "figure-likelihood" (figcaption, chart/diagram vocab, format, size) and cap.
  5. Download raster <img> sources directly; screenshot <svg> elements at 2x.

Usage:
  python scrape/figure_finder.py --url "<url>" --output-dir "assets/<slug>/"
  python scrape/figure_finder.py --url "<url>" --output-dir "assets/<slug>/" --max 8

Output (stdout):
  JSON: { "dir": "...", "candidates": [...], "skipped": "<reason or null>" }
Side effects:
  <output-dir>/figures/figure-NN.<ext>   — downloaded/rendered candidate images
  <output-dir>/figure_candidates.json    — candidate metadata (replaced per source URL)
"""

import argparse
import asyncio
import fcntl
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).parent.parent

# Article-body containers to search within, mirroring single_scrape.ARTICLE_SELECTORS.
ARTICLE_SELECTORS = [
    "article",
    '[itemprop="articleBody"]',
    '[class*="post-content"]',
    '[class*="article-content"]',
    '[class*="article-body"]',
    '[class*="blog-content"]',
    '[class*="entry-content"]',
    '[class*="post-body"]',
    "main",
    ".content",
]

# Tokens in an image's src/class/id/alt that mark it as chrome, not an article figure.
# Matched as whole tokens delimited by any non-alphanumeric (so "icon" fires on
# "user_icon.png" and "/icon/" but NOT inside "silicon-valley").
_SEP = r"[^a-z0-9]"
BLOCKLIST_RE = re.compile(
    rf"(?:^|{_SEP})("
    r"avatar|gravatar|emoji|sprite|logos?|icons?|author|badge|ads?|adservice|"
    r"doubleclick|promo|spacer|pixel|share|sharing|facebook|twitter|linkedin|thumbnail|"
    r"featured|hero"
    rf")(?:{_SEP}|$)",
    re.IGNORECASE,
)

# Words in a caption/alt that signal an informative chart or diagram.
VOCAB_RE = re.compile(
    r"diagram|architecture|\bflow\b|pipeline|sequence|\bchart\b|\bgraph\b|benchmark|"
    r"latency|throughput|topology|schematic|comparison",
    re.IGNORECASE,
)

MIN_SIDE = 200      # px — smaller than this is an icon/avatar/tracking pixel
MAX_ASPECT = 5.0    # wider/taller than this is a banner/rule/divider

# JS harvester: tag and describe every candidate <figure>/<img>/<svg> in the article body.
_JS_HARVEST = r"""
(args) => {
  const { selectors } = args;
  let container = null;
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && (el.innerText || '').trim().length > 200) { container = el; break; }
  }
  container = container || document.body;

  const heads = [...container.querySelectorAll('h1,h2,h3,h4,h5,h6')];
  const nearestHeading = (el) => {
    let best = '';
    for (const h of heads) {
      if (el.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_PRECEDING)
        best = (h.innerText || '').trim();
    }
    return best.slice(0, 200);
  };
  const surround = (unit) => {
    const block = unit.closest('figure') || unit;
    const parts = [];
    let p = block.previousElementSibling;
    while (p && parts.length < 1) { if (p.tagName === 'P') parts.push(p.innerText || ''); p = p.previousElementSibling; }
    let n = block.nextElementSibling;
    while (n && parts.length < 2) { if (n.tagName === 'P') parts.push(n.innerText || ''); n = n.nextElementSibling; }
    return parts.join(' ').replace(/\s+/g, ' ').trim().slice(0, 400);
  };
  const fmtOf = (src, isSvg) => {
    if (isSvg) return 'svg';
    const m = (src || '').split('?')[0].match(/\.([a-z0-9]+)$/i);
    return m ? m[1].toLowerCase() : '';
  };

  const seen = new Set();
  const out = [];
  let idx = 0;

  const record = (unit, img, svg, fig) => {
    const rect = unit.getBoundingClientRect();
    const isSvg = !!svg && !img;
    const src = img ? (img.currentSrc || img.src || img.getAttribute('data-src') || '') : '';
    const naturalW = img ? (img.naturalWidth || Math.round(rect.width)) : Math.round(rect.width);
    const naturalH = img ? (img.naturalHeight || Math.round(rect.height)) : Math.round(rect.height);
    const figcap = fig ? (fig.querySelector('figcaption')?.innerText || '').trim() : '';
    const blob = [
      src,
      img ? (img.className || '') + ' ' + (img.id || '') + ' ' + (img.alt || '') : '',
      unit.className || '', unit.id || '',
    ].join(' ').toLowerCase();
    unit.setAttribute('data-figure-idx', String(idx));
    out.push({
      idx,
      is_svg: isSvg,
      src,
      format: fmtOf(src, isSvg),
      alt: img ? (img.alt || '') : '',
      title: (img && img.title) || unit.getAttribute('title') || '',
      figcaption: figcap.slice(0, 300),
      heading: nearestHeading(unit),
      surrounding: surround(unit),
      natural_w: naturalW,
      natural_h: naturalH,
      rendered_w: Math.round(rect.width),
      rendered_h: Math.round(rect.height),
      is_figure: !!fig,
      blob: blob.slice(0, 500),
    });
    idx++;
  };

  container.querySelectorAll('figure').forEach((fig) => {
    const img = fig.querySelector('img');
    const svg = fig.querySelector('svg');
    if (!img && !svg) return;
    if (img) seen.add(img);
    if (svg) seen.add(svg);
    record(fig, img, svg, fig);
  });
  container.querySelectorAll('img').forEach((img) => {
    if (seen.has(img)) return;
    record(img, img, null, null);
  });
  container.querySelectorAll('svg').forEach((svg) => {
    if (seen.has(svg)) return;
    record(svg, null, svg, null);
  });

  return out;
}
"""


def _score(c: dict) -> dict:
    """Attach `_keep` (deterministic reject) and `score` (figure-likelihood) to a candidate."""
    w = c["natural_w"] or c["rendered_w"]
    h = c["natural_h"] or c["rendered_h"]
    fmt = c["format"]

    keep = True
    if w < MIN_SIDE or h < MIN_SIDE:
        keep = False
    elif h == 0 or w == 0 or w / h > MAX_ASPECT or h / w > MAX_ASPECT:
        keep = False
    elif fmt == "gif":  # animated demos are a separate render path — out of scope for v1
        keep = False
    elif BLOCKLIST_RE.search(c["blob"]):
        keep = False

    text = f"{c['figcaption']} {c['alt']} {c['title']}"
    score = 0
    if c["figcaption"].strip():
        score += 3
    if VOCAB_RE.search(text):
        score += 2
    if fmt in ("png", "svg"):
        score += 1
    if 400 <= w <= 1600:
        score += 1
    if c["is_figure"]:
        score += 1

    return {**c, "_keep": keep, "score": score}


def _ext_for(content_type: str, src: str) -> str:
    ct = content_type.lower()
    if "png" in ct:
        return "png"
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "webp" in ct:
        return "webp"
    path = urlparse(src).path.lower()
    for e in ("png", "webp", "gif"):
        if path.endswith("." + e):
            return e
    if path.endswith(".jpg") or path.endswith(".jpeg"):
        return "jpg"
    return "png"


async def _prepare(ctx, url: str):
    """Open a desktop-viewport page, load the URL, dismiss overlays, expand truncations."""
    sys.path.insert(0, str(ROOT / "scrape"))
    from screenshot import _dismiss_overlays, _expand_truncations

    page = await ctx.new_page()
    await page.set_viewport_size({"width": 1280, "height": 2000})
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        await page.goto(url, wait_until="load", timeout=30000)
    await page.wait_for_load_state("load")
    await page.wait_for_timeout(600)
    for step in (_dismiss_overlays, _expand_truncations):
        try:
            await step(page)
        except Exception:
            pass
    return page


async def _obtain(page, ctx, c: dict, figures_dir: Path, base_url: str, n: int):
    """Download a raster figure, or screenshot an <svg>/inline element at 2x. Returns filename or None."""
    idx, fmt, src = c["idx"], c["format"], c["src"]

    async def _element_shot():
        el = await page.query_selector(f'[data-figure-idx="{idx}"]')
        if not el:
            return None
        try:
            await el.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        out = figures_dir / f"figure-{n:02d}.png"
        try:
            await el.screenshot(path=str(out))
            return out.name
        except Exception:
            return None

    if c["is_svg"] or not src or fmt == "svg":
        return await _element_shot()

    abs_src = urljoin(base_url, src)
    try:
        resp = await ctx.request.get(abs_src, timeout=20000)
        if not resp.ok:
            raise RuntimeError(f"http {resp.status}")
        body = await resp.body()
        ext = _ext_for(resp.headers.get("content-type", ""), abs_src)
        out = figures_dir / f"figure-{n:02d}.{ext}"
        out.write_bytes(body)
        return out.name
    except Exception:
        return await _element_shot()  # fall back to a rendered screenshot


def _write_candidates(output_dir: Path, url: str, entries: list[dict]) -> None:
    """Append/replace this URL's candidates in figure_candidates.json under an exclusive lock."""
    path = output_dir / "figure_candidates.json"
    lock_path = output_dir / ".figure_candidates.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(existing, list):
            existing = []
        existing = [e for e in existing if e.get("source_url") != url]
        existing.extend(entries)
        path.write_text(json.dumps(existing, indent=2))


async def harvest(url: str, output_dir: Path, max_figures: int = 8,
                  solve_captcha: bool = False, solve_timeout: int = 300) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"dir": str(output_dir), "candidates": [], "skipped": "playwright not installed"}

    sys.path.insert(0, str(ROOT / "scrape"))
    from playwright_utils import (
        STEALTH_ARGS, is_bot_block, stealth_context, stealth_persistent_context,
    )
    from single_scrape import CAPTCHA_PROFILE

    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = None
        if solve_captcha:
            # Shares the profile primed by `single_scrape.py --solve-captcha`.
            ctx = await stealth_persistent_context(pw, str(CAPTCHA_PROFILE), device_scale_factor=2)
        else:
            browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
            ctx = await stealth_context(browser, device_scale_factor=2)

        async def _close():
            await (browser.close() if browser else ctx.close())

        try:
            page = await _prepare(ctx, url)
        except Exception as exc:
            await _close()
            return {"dir": str(output_dir), "candidates": [], "skipped": f"page load failed: {exc}"}

        if is_bot_block(await page.content()):
            if solve_captcha:
                print(f"Anti-bot wall hit — solve it in the open browser window "
                      f"(waiting up to {solve_timeout}s)...", file=sys.stderr, flush=True)
                for _ in range(solve_timeout // 2):
                    if not is_bot_block(await page.content()):
                        break
                    await page.wait_for_timeout(2000)
            if is_bot_block(await page.content()):
                await _close()
                return {"dir": str(output_dir), "candidates": [],
                        "skipped": "blocked by anti-bot protection — no figures harvested. "
                                   "Retry with --solve-captcha to clear it by hand."}

        raw = await page.evaluate(_JS_HARVEST, {"selectors": ARTICLE_SELECTORS})
        kept = sorted(
            (s for s in map(_score, raw) if s["_keep"]),
            key=lambda c: c["score"],
            reverse=True,
        )[:max_figures]

        entries: list[dict] = []
        hashes: set[str] = set()
        n = 0
        for c in kept:
            n += 1
            fname = await _obtain(page, ctx, c, figures_dir, url, n)
            if not fname:
                n -= 1
                continue
            digest = hashlib.md5((figures_dir / fname).read_bytes()).hexdigest()
            if digest in hashes:
                (figures_dir / fname).unlink(missing_ok=True)
                n -= 1
                continue
            hashes.add(digest)
            entries.append({
                "file": f"figures/{fname}",
                "source_url": url,
                "figcaption": c["figcaption"],
                "alt": c["alt"],
                "heading": c["heading"],
                "surrounding_text": c["surrounding"],
                "format": c["format"],
                "width": c["natural_w"],
                "height": c["natural_h"],
                "score": c["score"],
            })

        await _close()

    _write_candidates(output_dir, url, entries)
    return {"dir": str(output_dir), "candidates": entries, "skipped": None}


def main():
    parser = argparse.ArgumentParser(description="Harvest article figures (charts/diagrams) via Playwright")
    parser.add_argument("--url", required=True, help="Article URL")
    parser.add_argument("--output-dir", required=True, help="Directory to save figures (e.g. assets/<slug>/)")
    parser.add_argument("--max", type=int, default=8, help="Max candidates to download (default 8)")
    parser.add_argument("--solve-captcha", action="store_true",
                        help="Use the persistent browser profile shared with single_scrape.py and, "
                             "if a wall still appears, open it visibly and wait for you to clear it.")
    parser.add_argument("--solve-timeout", type=int, default=300, metavar="SECONDS",
                        help="How long --solve-captcha waits for you (default: 300)")
    args = parser.parse_args()

    result = asyncio.run(harvest(args.url, Path(args.output_dir), max_figures=args.max,
                                 solve_captcha=args.solve_captcha,
                                 solve_timeout=args.solve_timeout))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
