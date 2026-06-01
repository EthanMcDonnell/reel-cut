#!/usr/bin/env python3
"""
Article Aggregator

Discovers engineering articles from big tech blogs and saves candidates
to scrape/runs/<series>/<timestamp>/03_scored.json for use by the topic-researcher agent.

Pipeline:
  1. Fetch articles from each source via RSS (fallback: HTML scraping / Playwright)
  2. Filter by date, excluded keywords, excluded URL patterns, rejected list
  3. Score by keyword relevance (strong/weak/title keywords)
  4. Deduplicate against existing read articles
  5. Save to scrape/runs/<series>/<timestamp>/03_scored.json

Usage:
  python scrape/scraper.py --config scrape/sources-tbbt.yaml
  python scrape/scraper.py --config scrape/sources-updates.yaml
  python scrape/scraper.py --source "Netflix Tech Blog"  # scrape one source by name
  python scrape/scraper.py --mark-read <url>             # mark an article as read by URL
  python scrape/scraper.py --mark-all-read               # mark every article as read
  python scrape/scraper.py --reject <url>                # add URL to permanent reject list
  python scrape/scraper.py --reject <url> "reason"
  python scrape/scraper.py --probe <url>                 # probe best fetch method for a URL
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import ssl
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, row_to_article, article_to_params, VALID_SERIES
from telegram import send_articles_to_telegram

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent  # project root
SCRAPE_DIR = ROOT / "scrape"
DEFAULT_SOURCES_FILE = SCRAPE_DIR / "sources-tbbt.yaml"
RUNS_DIR = SCRAPE_DIR / "runs"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(sources_file: Path | None = None) -> dict:
    path = sources_file or DEFAULT_SOURCES_FILE
    return yaml.safe_load(path.read_text())


def load_rejected() -> set[str]:
    conn = get_db()
    rows = conn.execute("SELECT source_url FROM rejected WHERE source_url IS NOT NULL").fetchall()
    return {r["source_url"] for r in rows}


def add_rejected(url: str, reason: str | None = None) -> None:
    conn = get_db()
    existing = conn.execute("SELECT id FROM rejected WHERE source_url = ?", (url,)).fetchone()
    if existing:
        log.info(f"Already rejected: {url}")
        return
    conn.execute(
        "INSERT INTO rejected (source_url, reason, rejected_at) VALUES (?, ?, ?)",
        (url, reason, datetime.now().strftime("%Y-%m-%d")),
    )
    conn.commit()
    log.info(f"Rejected: {url}" + (f" ({reason})" if reason else ""))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


DATE_PREFIX_RE = re.compile(
    r"^(?:"
    r"\d{4}-\d{2}-\d{2}(?:T[\d:+Z.-]+)?"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"
    r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}"
    r"|\d{4}[/.\-]\d{2}[/.\-]\d{2}"
    r")\s*"
)
CATEGORY_PREFIX_RE = re.compile(r"^[A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,20}){0,2}\s+(?=[A-Z])")


def clean_title(title: str) -> str:
    title = DATE_PREFIX_RE.sub("", title)
    title = CATEGORY_PREFIX_RE.sub("", title)
    return title.strip()


def normalise_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = dateutil_parser.parse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_likely_article_url(url: str, base: str) -> bool:
    try:
        parsed = urlparse(url)
        base_parsed = urlparse(base)
        clean_path = parsed.path.rstrip("/")
        return (
            parsed.netloc == base_parsed.netloc
            and len(clean_path) > 1
            and "#" not in url
        )
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_by_date(articles: list[dict], lookback_days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    kept = []
    for a in articles:
        pub = normalise_date(a.get("published_date"))
        if not pub:
            kept.append(a)  # keep articles with no date rather than dropping them
            continue
        try:
            if dateutil_parser.parse(pub) >= cutoff:
                kept.append(a)
        except Exception:
            kept.append(a)
    return kept


def filter_excluded_keywords(articles: list[dict], excluded: list[str]) -> tuple[list[dict], list[dict]]:
    exc_lower = [k.lower() for k in excluded]
    kept, dropped = [], []
    for a in articles:
        text = f"{a['title']} {a.get('description', '')}".lower()
        matched = next((k for k in exc_lower if k in text), None)
        if matched:
            dropped.append({**a, "_excluded_reason": f"keyword: {matched}"})
        else:
            kept.append(a)
    return kept, dropped


def filter_excluded_urls(articles: list[dict], patterns: list[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for a in articles:
        url_lower = a["url"].lower()
        matched = next((p for p in patterns if p in url_lower), None)
        if matched:
            dropped.append({**a, "_excluded_reason": f"url_pattern: {matched}"})
        else:
            kept.append(a)
    return kept, dropped


def filter_rejected(articles: list[dict], rejected_urls: set[str]) -> list[dict]:
    return [a for a in articles if a["url"] not in rejected_urls]

# ---------------------------------------------------------------------------
# Relevance Scoring
# ---------------------------------------------------------------------------

def score_article(
    article: dict,
    strong_keywords: list[str],
    weak_keywords: list[str],
    title_keywords: list[str],
) -> tuple[int, list[str]]:
    title = article["title"].lower()
    excerpt = article.get("description", "").lower()
    score = 0
    matched = []

    for kw in title_keywords:
        kw_l = kw.lower()
        if kw_l in title:
            score += 3
            matched.append(f"{kw} (title-only)")

    for kw in strong_keywords:
        kw_l = kw.lower()
        if kw_l in title or kw_l in excerpt:
            score += 3
            matched.append(kw)

    for kw in weak_keywords:
        kw_l = kw.lower()
        if kw_l in title:
            score += 2
            matched.append(f"{kw} (title, weak)")
        elif kw_l in excerpt:
            score += 1
            matched.append(f"~{kw}")

    return score, matched


def score_and_filter(
    articles: list[dict],
    config: dict,
) -> tuple[list[dict], list[dict]]:
    """Return (passing, below_threshold) — both scored, passing sorted by score desc."""
    strong = config.get("strong_keywords") or []
    weak = config.get("weak_keywords") or []
    title_kw = config.get("title_keywords") or []
    min_score = config.get("min_relevance_score", 3)

    scored = []
    for a in articles:
        s, matched = score_article(a, strong, weak, title_kw)
        s += a.get("init_score", 0)
        scored.append({**a, "_score": s, "_matched_keywords": matched})

    passing = sorted([a for a in scored if a["_score"] >= min_score], key=lambda x: x["_score"], reverse=True)
    below = sorted([a for a in scored if 0 < a["_score"] < min_score], key=lambda x: x["_score"], reverse=True)
    return passing, below

# ---------------------------------------------------------------------------
# RSS Fetching
# ---------------------------------------------------------------------------

RSS_PROBE_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml",
    "/atom.xml", "/index.xml", "/blog/feed", "/blog/feed/",
]

CARD_SELECTORS = [
    "article", '[class*="post-item"]', '[class*="blog-item"]',
    '[class*="blog-post"]', '[class*="article-card"]', '[class*="post-card"]',
    '[class*="entry"]', "li",
]


async def fetch_rss(source: dict, client: httpx.AsyncClient) -> list[dict]:
    source_id = source["name"]
    base_url = source["homepage"].rstrip("/")
    insecure = source.get("insecure", False)

    candidates: list[str] = []
    if source.get("rss"):
        candidates.append(source["rss"])
    for path in RSS_PROBE_PATHS:
        candidates.append(base_url + path)

    for feed_url in dict.fromkeys(candidates):  # deduplicate, preserve order
        try:
            verify = not insecure
            resp = await client.get(feed_url, follow_redirects=True, timeout=12, extensions={"ssl_context": ssl.create_default_context() if verify else ssl._create_unverified_context()})
            if resp.status_code != 200:
                continue
            body = resp.text
            if not any(m in body[:500] for m in ["<rss", "<feed", "<atom", "<?xml"]):
                continue
            feed = feedparser.parse(body)
            if not feed.entries:
                continue

            articles = []
            for entry in feed.entries:
                url = entry.get("link", "").strip()
                if not url:
                    continue
                title = entry.get("title", "").strip()
                summary = BeautifulSoup(
                    entry.get("summary", entry.get("description", "")), "lxml"
                ).get_text(" ", strip=True)[:500]
                pub = normalise_date(entry.get("published", entry.get("updated")))
                articles.append({
                    "id": article_id(url),
                    "source_name": source_id,
                    "company": source["company"],
                    "title": title,
                    "url": url,
                    "published_date": pub,
                    "description": summary,
                    "scraped_at": now_iso(),
                    "status": "new",
                })
            if articles:
                log.info(f"  ✓ [RSS]    {source_id}: {len(articles)} items from {feed_url}")
                return articles
        except Exception as exc:
            log.debug(f"  RSS probe failed {feed_url}: {exc}")

    return []

# ---------------------------------------------------------------------------
# HTML Scraping
# ---------------------------------------------------------------------------

DATE_RE = re.compile(
    r"(?<!\d)("
    r"\d{4}-\d{2}-\d{2}(?:T[\d:+Z.-]+)?"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"
    r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}"
    r"|\d{4}[/.\-]\d{2}[/.\-]\d{2}"
    r")(?!\d)"
)

URL_DATE_RE = re.compile(r"/(\d{4})[/\-](\d{2})[/\-](\d{2})[/\-]?")

META_DATE_ATTRS = [
    ("property", "article:published_time"),
    ("property", "og:article:published_time"),
    ("name", "datePublished"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("name", "timestamp"),
    ("name", "DC.date"),
    ("name", "sailthru.date"),
    ("itemprop", "datePublished"),
]


def extract_published_date(el, page_soup=None, url: str | None = None) -> str | None:
    # 1. JSON-LD on the page
    if page_soup:
        for script in page_soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    for key in ("datePublished", "dateCreated", "uploadDate"):
                        val = item.get(key)
                        if val:
                            parsed = normalise_date(val)
                            if parsed:
                                return parsed
            except Exception:
                pass

    # 2. Meta tags on the page
    if page_soup:
        for attr, val in META_DATE_ATTRS:
            tag = page_soup.find("meta", {attr: val})
            if tag and tag.get("content"):
                parsed = normalise_date(tag["content"])
                if parsed:
                    return parsed

    # 3. <time> with datetime in the card element
    time_el = el.find("time")
    if time_el:
        raw = time_el.get("datetime") or time_el.get_text(strip=True)
        parsed = normalise_date(raw)
        if parsed:
            return parsed

    # 4. Class-based date element in the card
    date_el = el.find(attrs={"class": lambda c: c and any(
        x in c for x in ["date", "published", "timestamp", "meta", "agate"]
    )})
    if date_el:
        parsed = normalise_date(date_el.get("datetime") or date_el.get_text(strip=True))
        if parsed:
            return parsed

    # 5. URL date pattern (e.g. /2026/04/17/)
    if url:
        m = URL_DATE_RE.search(url)
        if m:
            parsed = normalise_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
            if parsed:
                return parsed

    # 6. Regex scan of card text
    m = DATE_RE.search(el.get_text(" ", strip=True))
    if m:
        return normalise_date(m.group(1))

    return None


def extract_article_cards(html: str, source: dict, fetch_method: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    base = source["homepage"]
    domain = urlparse(base).netloc
    seen: set[str] = set()
    articles = []

    for selector in CARD_SELECTORS:
        matches = soup.select(selector)
        if not matches:
            continue
        for el in matches:
            title_el = el.find(["h1", "h2", "h3", "h4"])
            link_el = (title_el.find("a") if title_el else None) or el.find("a", href=True)
            if not title_el or not link_el:
                continue
            title = clean_title(
                link_el.get_text(" ", strip=True) if link_el and link_el.get_text(strip=True)
                else title_el.get_text(" ", strip=True)
            )
            href = link_el.get("href", "")
            url = urljoin(base, href)
            if not title or not url or url in seen:
                continue
            if not is_likely_article_url(url, base):
                continue
            if urlparse(url).netloc != domain:
                continue
            seen.add(url)

            pub = extract_published_date(el, page_soup=soup, url=url)

            excerpt_el = el.find("p")
            excerpt = excerpt_el.get_text(" ", strip=True)[:500] if excerpt_el else ""

            articles.append({
                "id": article_id(url),
                "source_name": source["name"],
                "company": source["company"],
                "title": title,
                "url": url,
                "published_date": pub,
                "description": excerpt,
                "scraped_at": now_iso(),
                "read": False,
            })
        if articles:
            break

    return articles


async def scrape_html(source: dict, client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(source["homepage"], follow_redirects=True, timeout=15)
        resp.raise_for_status()
        articles = extract_article_cards(resp.text, source, "scraped")
        log.info(f"  ✓ [Scrape] {source['name']}: {len(articles)} items")
        return articles
    except Exception as exc:
        log.warning(f"  ✗ [Scrape] {source['name']}: {exc}")
        return []


async def scrape_playwright(source: dict) -> list[dict]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("playwright not installed: pip install playwright && playwright install chromium")
        return []
    try:
        from playwright_utils import STEALTH_ARGS, stealth_context
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
            ctx = await stealth_context(browser)
            page = await ctx.new_page()
            await page.goto(source["homepage"], wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            await browser.close()

        log.debug(f"  [Playwright] HTML length: {len(html)}")
        articles = extract_article_cards(html, source, "playwright")
        log.info(f"  [Playwright] extract_article_cards found: {len(articles)}")

        if not articles:
            # Fallback: generic link scan
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
                ctx = await stealth_context(browser)
                page = await ctx.new_page()
                await page.goto(source["homepage"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                link_results = await page.evaluate("""(baseUrl) => {
                    const base = new URL(baseUrl);
                    const skip = ["/tag/","/tags/","/category/","/topic/","/author/","/page/","/product/","/search/","/policy","/privacy","/terms","/legal","/responsible","/about","/careers","/contact"];
                    const seen = new Set();
                    const out = [];
                    for (const a of document.querySelectorAll("a[href]")) {
                        const href = a.href;
                        if (!href || seen.has(href) || href.includes("#")) continue;
                        try {
                            const p = new URL(href);
                            if (p.hostname !== base.hostname) continue;
                            if (p.pathname.split("/").filter(Boolean).length < 2) continue;
                            if (skip.some(s => p.pathname.includes(s))) continue;
                            // Prefer heading text inside the link, fall back to full link text
                            const heading = a.querySelector("h1,h2,h3,h4");
                            const text = (heading ? heading.textContent : a.textContent)?.trim() ?? "";
                            if (text.length < 10) continue;
                            // Try to find a date string inside the link
                            const dateEl = a.querySelector("time") || a.querySelector("[class*='date'],[class*='time'],[class*='published'],[class*='agate'],[class*='meta']");
                            const dateText = dateEl ? (dateEl.getAttribute("datetime") || dateEl.textContent?.trim()) : "";
                            seen.add(href);
                            out.push({title: text.slice(0, 300), url: href, date: dateText || ""});
                        } catch {}
                    }
                    return out;
                }""", source["homepage"])
                await browser.close()
            log.info(f"  [Playwright] link scan raw results: {len(link_results)}")
            for item in link_results[:3]:
                log.info(f"    {item['url']} | {item['title'][:60]}")
            for item in link_results:
                if is_likely_article_url(item["url"], source["homepage"]):
                    item["title"] = clean_title(item["title"])
                    articles.append({
                        "id": article_id(item["url"]),
                        "source_name": source["name"],
                        "company": source["company"],
                        "title": item["title"],
                        "url": item["url"],
                        "published_date": normalise_date(item.get("date")) or extract_published_date(BeautifulSoup("", "lxml"), url=item["url"]),
                        "description": "",
                        "scraped_at": now_iso(),
                        "status": "new",
                    })

        if articles:
            log.info(f"  ✓ [Playwright] {source['name']}: {len(articles)} items")
        else:
            log.warning(f"  ✗ [Playwright] {source['name']}: no articles found")
        return articles
    except Exception as exc:
        log.warning(f"  ✗ [Playwright] {source['name']}: {exc}")
        return []

# ---------------------------------------------------------------------------
# Per-source dispatch
# ---------------------------------------------------------------------------

async def fetch_from_source(source: dict, client: httpx.AsyncClient) -> list[dict]:
    fetch_type = source.get("fetch", "rss")

    if fetch_type == "manual":
        log.info(f"  · [Manual]  {source['name']} — visit: {source['homepage']}")
        return []

    if fetch_type == "reddit":
        import asyncio
        if source.get("reddit_subreddit"):
            from reddit_pull import fetch_reddit_subreddit
            subreddit = source["reddit_subreddit"]
            scrape_limit = source.get("scrape_limit", source.get("limit", 50))
            sort = source.get("reddit_sort", "hot")
            time_filter = source.get("reddit_time", "day")
            log.info(f"  · [Reddit]  r/{subreddit} ({sort})")
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: fetch_reddit_subreddit(
                    subreddit=subreddit,
                    limit=scrape_limit,
                    sort=sort,
                    time_filter=time_filter,
                    source_name=source["name"],
                    company=source.get("company", "Community"),
                    require_link=source.get("require_link", False),
                ),
            )
        from reddit_pull import fetch_reddit_posts
        reddit_user = source.get("reddit_user", "ClaudeOfficial")
        scrape_limit = source.get("scrape_limit", source.get("limit", 20))
        log.info(f"  · [Reddit]  u/{reddit_user}")
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fetch_reddit_posts(
                limit=scrape_limit,
                user=reddit_user,
                source_name=source["name"],
                company=source["company"],
            ),
        )

    if fetch_type == "rss":
        articles = await fetch_rss(source, client)
        if not articles:
            log.warning(f"  ✗ [RSS]    {source['name']}: no items")
        return articles

    if fetch_type == "playwright":
        return await scrape_playwright(source)

    # fetch: scrape
    return await scrape_html(source, client)

# ---------------------------------------------------------------------------
# Output JSON management
# ---------------------------------------------------------------------------

def find_latest_run(run_type: str) -> Path | None:
    type_dir = RUNS_DIR / run_type
    if not type_dir.exists():
        return None
    runs = sorted(p for p in type_dir.iterdir() if p.is_dir())
    return runs[-1] if runs else None



def load_prev_articles_by_id(run_type: str) -> dict[str, dict]:
    """Load articles from the master DB for status preservation."""
    if run_type not in VALID_SERIES:
        return {}
    conn = get_db()
    rows = conn.execute(f"SELECT id, status FROM {run_type}").fetchall()
    return {r["id"]: {"id": r["id"], "status": r["status"]} for r in rows}

# ---------------------------------------------------------------------------
# Mark read
# ---------------------------------------------------------------------------

def mark_read_by_url(url: str, run_type: str = "tbbt") -> None:
    if run_type not in VALID_SERIES:
        log.error(f"Unknown series '{run_type}'")
        return
    target_id = article_id(url)
    conn = get_db()
    cur = conn.execute(
        f"UPDATE {run_type} SET status = 'done' WHERE id = ? OR url = ?",
        (target_id, url),
    )
    conn.commit()
    if cur.rowcount == 0:
        log.warning(f"Article not found in {run_type}: {url}")
    else:
        log.info(f"Marked as done: {url}")


def mark_all_read(run_type: str = "tbbt") -> None:
    if run_type not in VALID_SERIES:
        log.error(f"Unknown series '{run_type}'")
        return
    conn = get_db()
    cur = conn.execute(f"UPDATE {run_type} SET status = 'done'")
    conn.commit()
    log.info(f"All {cur.rowcount} articles in '{run_type}' marked as done.")

# ---------------------------------------------------------------------------
# Probe source
# ---------------------------------------------------------------------------

async def probe_source(homepage: str) -> None:
    """Discover the best fetch method for a given homepage URL."""
    print(f"\nProbing: {homepage}\n")
    base = homepage.rstrip("/")
    domain = urlparse(homepage).netloc

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    async with httpx.AsyncClient(headers=headers) as client:

        # ── RSS discovery ──
        print("── RSS ──────────────────────────────────────")
        feed_urls: list[str] = []
        try:
            resp = await client.get(homepage, follow_redirects=True, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("link", rel=lambda r: r and "alternate" in r):
                href = link.get("href", "")
                t = link.get("type", "")
                if "rss" in t or "atom" in t or "xml" in t:
                    feed_urls.append(urljoin(base + "/", href))
        except Exception as e:
            print(f"  Could not fetch homepage: {e}")

        for path in RSS_PROBE_PATHS:
            feed_urls.append(base + path)

        rss_found = None
        for feed_url in dict.fromkeys(feed_urls):
            try:
                resp = await client.get(feed_url, follow_redirects=True, timeout=10)
                if resp.status_code != 200:
                    continue
                body = resp.text
                if not any(m in body[:500] for m in ["<rss", "<feed", "<atom", "<?xml"]):
                    continue
                feed = feedparser.parse(body)
                if feed.entries:
                    print(f"  ✓ RSS: {feed_url} ({len(feed.entries)} items)")
                    for e in feed.entries[:3]:
                        print(f"      \"{e.get('title', '').strip()}\"")
                    rss_found = feed_url
                    break
            except Exception:
                pass

        if not rss_found:
            print("  ✗ No working RSS feed found")

        # ── HTML scrape ──
        print("\n── HTTP Scrape ───────────────────────────────")
        scrape_count = 0
        try:
            resp = await client.get(homepage, follow_redirects=True, timeout=15)
            mock_source = {"name": "probe", "company": "probe", "homepage": homepage}
            articles = extract_article_cards(resp.text, mock_source, "scraped")
            scrape_count = len(articles)
            if articles:
                print(f"  ✓ Scrape: {scrape_count} articles found")
                for a in articles[:3]:
                    print(f"      \"{a['title']}\"")
            else:
                print("  ✗ Scrape: no articles found")
        except Exception as e:
            print(f"  ✗ Scrape failed: {e}")

    # ── Recommendation ──
    print("\n── Recommendation ────────────────────────────")
    if rss_found:
        fetch = "rss"
        print(f"  Best method: rss")
        print(f"\n  - name: <Name>")
        print(f"    company: <Company>")
        print(f"    fetch: rss")
        print(f"    rss: {rss_found}")
        print(f"    homepage: {homepage}")
    elif scrape_count > 0:
        fetch = "scrape"
        print(f"  Best method: scrape ({scrape_count} articles)")
        print(f"\n  - name: <Name>")
        print(f"    company: <Company>")
        print(f"    fetch: scrape")
        print(f"    homepage: {homepage}")
    else:
        print("  No automatic method worked — try playwright or manual")
        print(f"\n  - name: <Name>")
        print(f"    company: <Company>")
        print(f"    fetch: playwright  # or manual")
        print(f"    homepage: {homepage}")

# ---------------------------------------------------------------------------
# Run output helpers
# ---------------------------------------------------------------------------

def run_type_from_config(sources_file: Path | None) -> str:
    name = (sources_file or DEFAULT_SOURCES_FILE).stem  # e.g. "sources-tbbt"
    return name.removeprefix("sources-") or name        # e.g. "tbbt"


def make_run_dir(run_type: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = RUNS_DIR / run_type / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_run_stage(run_dir: Path, filename: str, articles: list[dict], run_type: str, stage: str) -> None:
    data = {
        "run_type": run_type,
        "run_at": now_iso(),
        "stage": stage,
        "count": len(articles),
        "articles": articles,
    }
    (run_dir / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log.info(f"  → {filename}: {len(articles)} articles")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(filter_name: str | None = None, sources_file: Path | None = None) -> None:
    config = load_config(sources_file)
    sources: list[dict] = config["sources"]
    rejected_urls = load_rejected()
    run_type = run_type_from_config(sources_file)
    prev_by_id = load_prev_articles_by_id(run_type)
    run_dir = make_run_dir(run_type)
    log.info(f"Run output → {run_dir.relative_to(ROOT)}")

    if filter_name:
        sources = [s for s in sources if s["name"].lower() == filter_name.lower()]
        if not sources:
            log.error(f"No source named '{filter_name}'. Check sources.yaml.")
            sys.exit(1)

    active_sources = [s for s in sources if s.get("fetch", "rss") != "manual"]
    log.info(f"Scraping {len(active_sources)} source(s) (skipping manual)…")

    headers = {"User-Agent": USER_AGENT}
    all_fresh: list[dict] = []

    async with httpx.AsyncClient(headers=headers) as client:
        for source in active_sources:
            log.info(f"→ {source['name']} ({source['company']})")
            articles = await fetch_from_source(source, client)
            output_limit = source.get("output_limit")
            if output_limit and len(articles) > output_limit:
                raw_count = len(articles)
                articles = articles[:output_limit]
                log.info(f"  · output_limit={output_limit}: kept {output_limit}/{raw_count} articles")
            init_score = source.get("init_score", 0)
            if init_score:
                articles = [{**a, "init_score": init_score} for a in articles]
            all_fresh.extend(articles)

    log.info(f"Fetched {len(all_fresh)} raw articles")
    save_run_stage(run_dir, "01_raw.json", all_fresh, run_type, "raw")

    # ── Filter pipeline ──
    after_date = filter_by_date(all_fresh, config.get("lookback_days", 360))
    log.info(f"After date filter: {len(after_date)}")

    after_keywords, kw_dropped = filter_excluded_keywords(after_date, config.get("excluded_keywords", []))
    log.info(f"After keyword exclusion: {len(after_keywords)} (dropped {len(kw_dropped)})")

    after_urls, url_dropped = filter_excluded_urls(after_keywords, config.get("excluded_url_patterns", []))
    log.info(f"After URL exclusion: {len(after_urls)} (dropped {len(url_dropped)})")

    after_rejected = filter_rejected(after_urls, rejected_urls)
    log.info(f"After rejected filter: {len(after_rejected)}")
    save_run_stage(run_dir, "02_filtered.json", after_rejected, run_type, "filtered")

    # ── Score ──
    passing, below_threshold = score_and_filter(after_rejected, config)
    log.info(
        f"After relevance scoring (min {config.get('min_relevance_score', 3)}): "
        f"{len(passing)} passing, {len(below_threshold)} below threshold"
    )

    if passing:
        log.info(f"\nTop {min(5, len(passing))} candidates:")
        for a in passing[:5]:
            kw = ", ".join(a.get("_matched_keywords", [])[:4])
            log.info(f"  [{a['_score']}] {a['title']} ({a['company']})")
            log.info(f"       {kw}")

    # Annotate every article with its tier and save all — nothing is discarded.
    # max_articles_per_run is no longer a save cap; it only controls the log display above.
    def _annotate(articles: list[dict], tier: str) -> list[dict]:
        out = []
        for a in articles:
            d = {k: v for k, v in a.items() if not k.startswith("_")}
            d["relevance_tier"] = tier
            d["relevance_score"] = a.get("_score", 0)
            if a.get("_matched_keywords"):
                d["matched_keywords"] = a["_matched_keywords"]
            if a.get("_excluded_reason"):
                d["excluded_reason"] = a["_excluded_reason"]
            out.append(d)
        return out

    all_to_save = (
        _annotate(passing, "passing")
        + _annotate(below_threshold, "low_score")
        + _annotate(kw_dropped, "excluded")
        + _annotate(url_dropped, "excluded")
    )
    log.info(
        f"Saving {len(passing)} passing + {len(below_threshold)} low_score "
        f"+ {len(kw_dropped) + len(url_dropped)} excluded"
    )

    # Preserve status from previous run
    for a in all_to_save:
        if a["id"] in prev_by_id:
            a["status"] = prev_by_id[a["id"]].get("status", "new")

    new_count = sum(1 for a in all_to_save if a["id"] not in prev_by_id)
    if new_count:
        log.info(f"  {new_count} new article(s) this run")

    save_run_stage(run_dir, "03_scored.json", all_to_save, run_type, "scored")
    save_run_stage(run_dir, "04_top.json", _annotate(passing, "passing"), run_type, "top")

    # Insert all passing articles into DB as 'new' (INSERT OR IGNORE preserves existing status)
    conn = get_db()
    insert_sql = f"""INSERT OR IGNORE INTO {run_type}
        (id, source_name, company, title, url, published_date, description,
         scraped_at, status, relevance_tier, relevance_score, matched_keywords)
        VALUES (:id, :source_name, :company, :title, :url, :published_date, :description,
                :scraped_at, :status, :relevance_tier, :relevance_score, :matched_keywords)
    """
    for a in _annotate(passing, "passing"):
        conn.execute(insert_sql, article_to_params({**a, "status": "new"}))
    conn.commit()
    log.info(f"Inserted {len(passing)} passing articles into {run_type} DB (new articles only)")

    new_passing = [a for a in passing if a["id"] not in prev_by_id]
    send_articles_to_telegram(_annotate(new_passing, "passing"), run_type)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Article Aggregator")
    parser.add_argument("--config", metavar="FILE", help="Path to sources YAML (default: scrape/sources.yaml)")
    parser.add_argument("--source", metavar="NAME", help="Scrape only this source (by name)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mark-read", metavar="URL", help="Mark a single article as read")
    group.add_argument("--mark-all-read", action="store_true", help="Mark all articles as read")
    group.add_argument("--probe", metavar="URL", help="Probe best fetch method for a homepage URL")
    group.add_argument("--reject", metavar="URL", help="Add URL to permanent reject list")
    parser.add_argument("reason", nargs="?", help="Optional reason (used with --reject)")
    args = parser.parse_args()

    sources_file = Path(args.config) if args.config else None

    run_type = run_type_from_config(sources_file)

    if args.mark_read:
        mark_read_by_url(args.mark_read, run_type=run_type)
    elif args.mark_all_read:
        mark_all_read(run_type=run_type)
    elif args.reject:
        add_rejected(args.reject, args.reason)
    elif args.probe:
        asyncio.run(probe_source(args.probe))
    else:
        if not args.config:
            parser.error("--config is required. Example: python scrape/scraper.py --config scrape/sources-tbbt.yaml")
        asyncio.run(main(filter_name=args.source, sources_file=sources_file))
