#!/usr/bin/env python3
"""
Single Article Scraper

Fetches the full content of a specific article URL using the same fetch method
(rss/scrape/playwright/reddit) that the regular scraper would use for that source.

Usage:
  python scrape/single_scrape.py <url>
  python scrape/single_scrape.py <url> --json   # structured JSON output

Output (stdout):
  title, source, company, fetch method used, full article text

The fetch method is determined by matching the URL's domain against sources in
sources-tbbt.yaml and sources-updates.yaml. Falls back to plain HTTP + BeautifulSoup
if no matching source is found.
"""

import argparse
import asyncio
import json
import os
import re
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
SCRAPE_DIR = ROOT / "scrape"
SOURCES_FILES = [
    SCRAPE_DIR / "sources-tbbt.yaml",
    SCRAPE_DIR / "sources-updates.yaml",
]

USER_AGENT = "local reddit article viewer/1.0"

# ---------------------------------------------------------------------------
# Source lookup
# ---------------------------------------------------------------------------

def load_all_sources() -> list[dict]:
    sources = []
    for path in SOURCES_FILES:
        if not path.exists():
            continue
        cfg = yaml.safe_load(path.read_text())
        series = "tbbt" if "tbbt" in path.name else "updates"
        for s in cfg.get("sources", []):
            sources.append({**s, "_series": series})
    return sources


def find_source_for_url(url: str, sources: list[dict]) -> dict | None:
    """Match a URL to a source config by domain (and path for Reddit) comparison."""
    parsed = urlparse(url)
    url_domain = parsed.netloc.lower().lstrip("www.")
    url_path = parsed.path.lower()

    is_reddit = url_domain in ("reddit.com", "old.reddit.com")

    exact_matches = []
    for source in sources:
        homepage = source.get("homepage", "")
        hp = urlparse(homepage)
        source_domain = hp.netloc.lower().lstrip("www.")
        if not source_domain:
            continue

        domain_match = (url_domain == source_domain
                        or url_domain.endswith("." + source_domain)
                        or source_domain.endswith("." + url_domain))
        if not domain_match:
            continue

        if is_reddit:
            # For Reddit URLs, prefer the source whose homepage path is a prefix of the URL path
            source_path = hp.path.lower().rstrip("/")
            if source_path and url_path.startswith(source_path):
                return source  # specific subreddit match — return immediately
            # Otherwise keep as fallback
            exact_matches.append(source)
        else:
            return source

    if exact_matches:
        return exact_matches[0]

    # Reddit URL with no source match — default to updates series stub
    if is_reddit:
        return {"name": "Reddit", "company": "Reddit", "fetch": "reddit", "_series": "updates"}

    return None

# ---------------------------------------------------------------------------
# Content extraction helpers
# ---------------------------------------------------------------------------

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


def extract_content_from_html(html: str) -> tuple[str, str]:
    """Return (title, body_text) from article HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noise
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "[class*='sidebar']", "[class*='menu']",
                     "[class*='cookie']", "[class*='banner']"]):
        tag.decompose()

    title = ""
    title_el = soup.find("h1") or soup.find("title")
    if title_el:
        title = title_el.get_text(" ", strip=True)

    # Try article-specific selectors first
    for selector in ARTICLE_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 200:  # skip empty/nav matches
                return title, _clean_text(text)

    # Fallback: largest text block
    paragraphs = soup.find_all("p")
    text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
    return title, _clean_text(text)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------------------------------------------------------------------
# Fetch strategies
# ---------------------------------------------------------------------------

async def fetch_http(url: str, insecure: bool = False) -> str:
    """Fetch a URL with httpx, return HTML."""
    verify = not insecure
    ssl_ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=20,
    ) as client:
        resp = await client.get(url, extensions={"ssl_context": ssl_ctx})
        resp.raise_for_status()
        return resp.text


async def fetch_playwright_content(url: str, headed: bool = False) -> str:
    """Fetch a JS-rendered page using Playwright, return HTML."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed: pip install playwright && playwright install chromium")

    from playwright_utils import STEALTH_ARGS, stealth_context
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed, args=STEALTH_ARGS)
        ctx = await stealth_context(browser)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        await browser.close()
    return html


async def fetch_reddit_content(url: str) -> tuple[str, str]:
    """Fetch a Reddit post via PRAW. Returns (title, content)."""
    import praw
    import re as _re

    match = _re.search(r"/comments/([a-z0-9]+)", url)
    if not match:
        raise ValueError(f"Could not extract submission ID from URL: {url}")
    submission_id = match.group(1)

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "Accessing Reddit threads"),
    )
    submission = reddit.submission(id=submission_id)
    title = submission.title
    selftext = submission.selftext or ""

    # If it's a link post (no selftext), fetch the linked article directly
    if not selftext and submission.url and not submission.url.startswith("https://www.reddit.com"):
        linked = await scrape_single(submission.url)
        content = linked.get("content", "")
        if linked.get("title"):
            title = linked["title"]
        return title, content if content else f"[Link post to {submission.url} — could not extract content]"

    # Grab top comments for context
    submission.comments.replace_more(limit=0)
    comment_texts = []
    for c in submission.comments[:3]:
        body = getattr(c, "body", "")
        if body and len(body) > 100:
            comment_texts.append(body)

    content = selftext
    if comment_texts:
        content += "\n\n--- Top comments ---\n" + "\n\n".join(comment_texts)

    return title, _clean_text(content)

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

async def scrape_single(url: str, force_method: str | None = None, headed: bool = False) -> dict:
    sources = load_all_sources()
    source = find_source_for_url(url, sources)

    fetch_method = "http"  # default
    source_name = "Unknown"
    company = "Unknown"
    insecure = False
    series = None

    if source:
        fetch_method = source.get("fetch", "rss")
        source_name = source.get("name", source_name)
        company = source.get("company", company)
        insecure = source.get("insecure", False)
        series = source.get("_series")

    # Reddit domain always uses reddit fetch
    if urlparse(url).netloc.lower().lstrip("www.") in ("reddit.com", "old.reddit.com"):
        fetch_method = "reddit"

    if force_method:
        fetch_method = force_method

    # manual sources can't be auto-fetched
    if fetch_method == "manual":
        return {
            "url": url,
            "source_name": source_name,
            "company": company,
            "series": series,
            "fetch_method": "manual",
            "title": "",
            "content": "",
            "word_count": 0,
            "error": f"Source '{source_name}' is marked manual — cannot auto-fetch. Visit: {source.get('homepage', url)}",
        }

    title = ""
    content = ""
    error = None

    try:
        if fetch_method == "reddit":
            title, content = await fetch_reddit_content(url)
        elif fetch_method == "playwright":
            html = await fetch_playwright_content(url, headed=headed)
            title, content = extract_content_from_html(html)
        else:
            # rss, scrape, or unknown — try HTTP first, fall back to Playwright on 4xx
            try:
                html = await fetch_http(url, insecure=insecure)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 401, 429):
                    html = await fetch_playwright_content(url, headed=headed)
                    fetch_method = "playwright"
                else:
                    raise
            title, content = extract_content_from_html(html)
    except Exception as exc:
        error = str(exc)

    return {
        "url": url,
        "source_name": source_name,
        "company": company,
        "series": series,
        "fetch_method": fetch_method,
        "title": title,
        "content": content,
        "word_count": len(content.split()) if content else 0,
        **({"error": error} if error else {}),
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch full content of a single article URL")
    parser.add_argument("url", help="Article URL to fetch")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    parser.add_argument("--method", choices=["http", "playwright", "reddit"], default=None,
                        help="Force a specific fetch method (overrides source config)")
    parser.add_argument("--headed", action="store_true", help="Run Playwright in headed (visible) mode")
    args = parser.parse_args()

    result = asyncio.run(scrape_single(args.url, force_method=args.method, headed=args.headed))

    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Human-readable output
    if result.get("error") and not result.get("content"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"Title:   {result['title']}")
    print(f"Source:  {result['source_name']} ({result['company']})")
    print(f"Series:  {result['series'] or 'unknown'}")
    print(f"Method:  {result['fetch_method']}")
    print(f"Words:   {result['word_count']}")
    if result.get("error"):
        print(f"Warning: {result['error']}")
    print()
    print("--- CONTENT ---")
    print(result["content"])


if __name__ == "__main__":
    main()
