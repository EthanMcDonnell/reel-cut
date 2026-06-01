#!/usr/bin/env python3
"""
probe-source: discover the best fetch method for a sources.yaml entry.

Runs RSS discovery, HTTP scrape, and Playwright scrape in parallel.

Usage:
  python scrape/probe_source.py <homepage-url> [name] [company]

Examples:
  python scrape/probe_source.py https://eng.uber.com "Uber Engineering" "Uber"
  python scrape/probe_source.py https://shopify.engineering
"""

import asyncio
import ssl
import sys
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (compatible; InfluencerProbe/1.0)"

CARD_SELECTORS = [
    "article",
    '[class*="post-item"]',
    '[class*="blog-item"]',
    '[class*="blog-post"]',
    '[class*="article-card"]',
    '[class*="post-card"]',
    '[class*="entry"]',
    "li",
]

NON_ARTICLE_PATTERNS = [
    "/tag/", "/tags/", "/category/", "/topic/", "/topics/",
    "/author/", "/page/", "/product/", "/search/",
]

RSS_PROBE_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml",
    "/atom.xml", "/index.xml",
    "/blog/feed", "/blog/feed/", "/blog/rss.xml", "/blog/feed.xml", "/blog/index.xml",
    "/engineering/feed", "/engineering/feed/",
    "/tech/feed", "/news/feed",
    "/feed/rss",
    "/feeds/posts/default", "/feeds/all.rss.xml",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(msg):   print(f"  \u2713 {msg}")
def fail(msg): print(f"  \u2717 {msg}")
def info(msg): print(f"  \u00b7 {msg}")


def is_likely_article_url(url: str, base: str) -> bool:
    try:
        parsed = urlparse(url)
        base_parsed = urlparse(base)
        clean_path = parsed.path.rstrip("/")
        return (
            parsed.netloc == base_parsed.netloc
            and len(clean_path) > 1
            and "#" not in url
            and not any(p in parsed.path for p in NON_ARTICLE_PATTERNS)
        )
    except Exception:
        return False

# ── RSS Discovery ─────────────────────────────────────────────────────────────

async def try_rss_feed(feed_url: str) -> dict | None:
    for insecure in [False, True]:
        try:
            ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    feed_url, follow_redirects=True,
                    extensions={"ssl_context": ctx},
                )
                if resp.status_code != 200:
                    break
                body = resp.text
                if not any(m in body[:500] for m in ["<rss", "<feed", "<atom", "<?xml"]):
                    break
                feed = feedparser.parse(body)
                if not feed.entries:
                    break
                titles = [e.get("title", "").strip() for e in feed.entries[:3]]
                return {"url": feed_url, "count": len(feed.entries), "titles": titles, "insecure": insecure}
        except Exception:
            if not insecure:
                continue
    return None


async def discover_rss(homepage: str) -> list[dict]:
    print("\n\u2500\u2500 RSS Discovery \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    base = homepage.rstrip("/")
    origin = f"{urlparse(homepage).scheme}://{urlparse(homepage).netloc}"
    feed_urls: list[str] = []

    info("Fetching homepage HTML for feed links...")
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=10) as client:
            resp = await client.get(homepage, follow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                for link in soup.find_all("link", rel=lambda r: r and "alternate" in r):
                    t = link.get("type", "")
                    href = link.get("href", "")
                    if ("rss" in t or "atom" in t) and href:
                        feed_urls.append(urljoin(base + "/", href))
                if feed_urls:
                    info(f"Found {len(feed_urls)} feed link(s) in HTML")
                else:
                    info("No <link rel=alternate> feed tags found — probing common paths")
    except Exception as e:
        info(f"Could not fetch homepage HTML: {e}")

    for path in RSS_PROBE_PATHS:
        feed_urls.append(origin + path)

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for u in feed_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    info(f"Testing {len(unique)} candidate feed URLs...")
    results = await asyncio.gather(*[try_rss_feed(u) for u in unique])
    found = [r for r in results if r]

    for r in found:
        note = " (insecure TLS)" if r["insecure"] else ""
        ok(f"{r['url']} — {r['count']} items{note}")
        for t in r["titles"]:
            info(f'    "{t}"')

    if not found:
        fail("No working RSS feeds found")

    return found

# ── HTTP Scrape ───────────────────────────────────────────────────────────────

def extract_titles(html: str, homepage: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    titles: list[str] = []

    for selector in CARD_SELECTORS:
        for el in soup.select(selector):
            title_el = el.find(["h1", "h2", "h3", "h4"])
            link_el = (title_el.find("a") if title_el else None) or el.find("a", href=True)
            if not title_el or not link_el:
                continue
            title = title_el.get_text(" ", strip=True)
            href = link_el.get("href", "")
            url = urljoin(homepage, href)
            if not title or not url or url in seen:
                continue
            if not is_likely_article_url(url, homepage):
                continue
            seen.add(url)
            titles.append(title)
        if titles:
            break

    return titles


async def test_http_scrape(homepage: str) -> list[str]:
    print("\n\u2500\u2500 HTTP Scrape \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    info(f"Fetching {homepage}...")
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=15) as client:
            resp = await client.get(homepage, follow_redirects=True)
            if resp.status_code != 200:
                fail(f"HTTP {resp.status_code}")
                return []
            titles = extract_titles(resp.text, homepage)
            if titles:
                ok(f"{len(titles)} article(s) found")
                for t in titles[:3]:
                    info(f'  "{t}"')
            else:
                fail("No articles found (selectors didn't match page structure)")
            return titles
    except Exception as e:
        fail(str(e))
        return []

# ── Playwright Scrape ─────────────────────────────────────────────────────────

async def test_playwright_scrape(homepage: str) -> list[str]:
    print("\n\u2500\u2500 Playwright \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    info(f"Loading {homepage} with headless browser...")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        fail("playwright not installed: pip install playwright && playwright install chromium")
        return []

    try:
        from playwright_utils import STEALTH_ARGS, stealth_context
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
            ctx = await stealth_context(browser)
            page = await ctx.new_page()
            await page.goto(homepage, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()

            titles = extract_titles(html, homepage)

            if not titles:
                info("Selector pass found nothing — trying generic link scan...")
                link_results = await page.evaluate("""(baseUrl) => {
                    const base = new URL(baseUrl);
                    const skip = ["/tag/","/tags/","/category/","/topic/","/topics/","/author/","/page/","/product/","/search/"];
                    const seen = new Set();
                    const out = [];
                    for (const a of document.querySelectorAll("a[href]")) {
                        const href = a.href, text = a.textContent?.trim() ?? "";
                        if (!href || seen.has(href) || href.includes("#")) continue;
                        if (text.length < 30 || text.length > 200) continue;
                        try {
                            const p = new URL(href);
                            if (p.hostname !== base.hostname) continue;
                            if (p.pathname.split("/").filter(Boolean).length < 2) continue;
                            if (skip.some(s => p.pathname.includes(s))) continue;
                            seen.add(href);
                            out.push({title: text, url: href});
                        } catch {}
                    }
                    return out;
                }""", homepage)
                for item in link_results:
                    if is_likely_article_url(item["url"], homepage):
                        titles.append(item["title"])

                if titles:
                    ok(f"{len(titles)} article(s) via link scan fallback")
                else:
                    fail("No articles found (tried selectors + link scan)")
            else:
                ok(f"{len(titles)} article(s) found via selectors")

            for t in titles[:3]:
                info(f'  "{t}"')

            await browser.close()
            return titles
    except Exception as e:
        fail(str(e))
        return []

# ── Recommendation ────────────────────────────────────────────────────────────

def print_recommendation(homepage: str, name: str, company: str,
                          rss_results: list[dict], scrape_titles: list[str],
                          playwright_titles: list[str]) -> None:
    print("\n\u2500\u2500 Recommendation \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

    best_rss = max(rss_results, key=lambda r: r["count"]) if rss_results else None
    scrape_count = len(scrape_titles)
    playwright_count = len(playwright_titles)

    if best_rss:
        fetch = "rss"
        rss_line = f"\n    rss: {best_rss['url']}"
        insecure_line = "\n    insecure: true  # TLS cert not in CA bundle" if best_rss["insecure"] else ""
        ok(f"Best method: rss ({best_rss['count']} items from {best_rss['url']})")
    elif scrape_count >= playwright_count and scrape_count > 0:
        fetch = "scrape"
        rss_line = insecure_line = ""
        ok(f"Best method: scrape ({scrape_count} articles)")
    elif playwright_count > 0:
        fetch = "playwright"
        rss_line = insecure_line = ""
        ok(f"Best method: playwright ({playwright_count} articles)")
    else:
        fetch = "manual"
        rss_line = insecure_line = ""
        info("No automatic method worked — defaulting to manual")

    yaml_snippet = (
        f"\n  - name: {name}\n"
        f"    company: {company}\n"
        f"    fetch: {fetch}{rss_line}\n"
        f"    homepage: {homepage}{insecure_line}"
    )

    print("\nPaste into sources.yaml:")
    print("\u2500" * 50)
    print(yaml_snippet)
    print("\u2500" * 50)

# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python scrape/probe_source.py <homepage-url> [name] [company]")
        sys.exit(1)

    homepage = args[0].rstrip("/")
    try:
        parsed = urlparse(homepage)
        assert parsed.scheme and parsed.netloc
    except Exception:
        print(f"Invalid URL: {homepage}")
        sys.exit(1)

    name = args[1] if len(args) > 1 else parsed.netloc
    company = args[2] if len(args) > 2 else name

    print(f"\nProbing: {homepage}")
    print(f"Name:    {name}")
    print(f"Company: {company}")

    rss_results, scrape_titles, playwright_titles = await asyncio.gather(
        discover_rss(homepage),
        test_http_scrape(homepage),
        test_playwright_scrape(homepage),
    )

    print_recommendation(homepage, name, company, rss_results, scrape_titles, playwright_titles)


if __name__ == "__main__":
    asyncio.run(main())
