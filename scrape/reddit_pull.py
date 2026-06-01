#!/usr/bin/env python3
"""
Reddit Pull — fetch posts from any Reddit user via PRAW.

Saves runs to scrape/runs/reddit/{timestamp}/ alongside other run types.

Requires in .env:
  REDDIT_CLIENT_ID=...
  REDDIT_CLIENT_SECRET=...
  REDDIT_USER_AGENT=...   (optional)

Usage:
  python scrape/reddit_pull.py
  python scrape/reddit_pull.py --user ClaudeOfficial --limit 25
  python scrape/reddit_pull.py --user someotheruser --company SomeCo
"""

import json
import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
RUNS_DIR = ROOT / "scrape" / "runs"
RUN_TYPE = "reddit"

load_dotenv(ROOT / ".env")


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ts_to_iso(utc_timestamp: float) -> str:
    return datetime.fromtimestamp(utc_timestamp, tz=timezone.utc).isoformat()


def load_sources_scraped() -> dict[str, str]:
    path = RUNS_DIR / RUN_TYPE / "sources_scraped.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_sources_scraped(source_name: str) -> None:
    type_dir = RUNS_DIR / RUN_TYPE
    type_dir.mkdir(parents=True, exist_ok=True)
    existing = load_sources_scraped()
    (type_dir / "sources_scraped.json").write_text(
        json.dumps({**existing, source_name: now_iso()}, indent=2)
    )


def find_latest_run() -> Path | None:
    type_dir = RUNS_DIR / RUN_TYPE
    if not type_dir.exists():
        return None
    runs = sorted(p for p in type_dir.iterdir() if p.is_dir())
    return runs[-1] if runs else None


def load_prev_by_id() -> dict[str, dict]:
    latest = find_latest_run()
    if not latest:
        return {}
    scored = latest / "03_scored.json"
    if not scored.exists():
        return {}
    try:
        data = json.loads(scored.read_text())
        return {a["id"]: a for a in data.get("articles", [])}
    except Exception:
        return {}


_EXCLUDED_DOMAINS = {"i.redd.it", "v.redd.it", "i.imgur.com", "preview.redd.it", "www.reddit.com", "reddit.com", "redd.it", "youtu.be"}
_EXCLUDED_DOMAIN_SUFFIXES = {"youtube.com", "github.com", "hub.docker.com"}
_MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".gifv", ".webp", ".mp4", ".mov"}
_URL_RE = re.compile(r'https?://[^\s\)\]>\"]+')


def _is_media_url(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc in _EXCLUDED_DOMAINS:
        return True
    if any(netloc == d or netloc.endswith("." + d) for d in _EXCLUDED_DOMAIN_SUFFIXES):
        return True
    if any(parsed.path.lower().endswith(ext) for ext in _MEDIA_EXTENSIONS):
        return True
    return False


def _find_article_url(submission) -> str | None:
    """Return the first external article URL found on the submission, or None."""
    # Link posts have the URL directly on submission.url
    if not submission.is_self and not _is_media_url(submission.url):
        return submission.url
    # Self posts: search title and body text
    candidates = _URL_RE.findall(f"{submission.title} {submission.selftext or ''}")
    for url in candidates:
        if not _is_media_url(url):
            return url
    return None


def fetch_reddit_subreddit(subreddit: str, limit: int = 50, sort: str = "top", time_filter: str = "day", source_name: str | None = None, company: str = "Community", require_link: bool = False) -> list[dict]:
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "Accessing Reddit threads"),
    )

    sub = reddit.subreddit(subreddit)
    resolved_source_name = source_name or f"Reddit r/{subreddit}"
    articles = []

    if sort == "top":
        submissions = sub.top(time_filter=time_filter, limit=limit)
    elif sort == "new":
        submissions = sub.new(limit=limit)
    else:
        submissions = sub.hot(limit=limit)

    for submission in submissions:
        if require_link and not _find_article_url(submission):
            continue
        url = f"https://www.reddit.com{submission.permalink}"
        articles.append({
            "id": article_id(url),
            "source_name": resolved_source_name,
            "company": company,
            "title": submission.title,
            "url": url,
            "published_date": ts_to_iso(submission.created_utc),
            "description": (submission.selftext or submission.url or "")[:500],
            "scraped_at": now_iso(),
            "read": False,
        })

    return articles


def fetch_reddit_posts(limit: int = 20, since: datetime | None = None, user: str = "ClaudeOfficial", source_name: str | None = None, company: str = "Anthropic") -> list[dict]:
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "Accessing Reddit threads"),
    )

    redditor = reddit.redditor(user)
    resolved_source_name = source_name or f"Reddit u/{user}"
    articles = []

    for submission in redditor.submissions.new(limit=limit):
        created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
        if since and created <= since:
            break  # submissions.new() is reverse-chronological — safe to stop here
        url = f"https://www.reddit.com{submission.permalink}"
        articles.append({
            "id": article_id(url),
            "source_name": resolved_source_name,
            "company": company,
            "title": submission.title,
            "url": url,
            "published_date": ts_to_iso(submission.created_utc),
            "description": (submission.selftext or submission.url or "")[:500],
            "scraped_at": now_iso(),
            "read": False,
        })

    return articles


def merge_into_articles(fresh: list[dict], source_name: str) -> None:
    prev_by_id = load_prev_by_id()

    # Preserve read status
    for a in fresh:
        if a["id"] in prev_by_id:
            a["read"] = prev_by_id[a["id"]].get("read", False)

    new_count = sum(1 for a in fresh if a["id"] not in prev_by_id)

    # Save run
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = RUNS_DIR / RUN_TYPE / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    run_data = {
        "run_type": RUN_TYPE,
        "run_at": now_iso(),
        "stage": "scored",
        "count": len(fresh),
        "articles": fresh,
    }
    (run_dir / "03_scored.json").write_text(json.dumps(run_data, indent=2, ensure_ascii=False))

    save_sources_scraped(source_name)
    print(f"Fetched {len(fresh)} posts ({new_count} new) → {run_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    import argparse
    from dateutil import parser as dateutil_parser

    parser = argparse.ArgumentParser(description="Reddit pull for any Reddit user")
    parser.add_argument("--user", default="", help="Reddit username to scrape")
    parser.add_argument("--company", default="Anthropic", help="Company name for article metadata (default: Anthropic)")
    parser.add_argument("--limit", type=int, default=20, help="Number of posts to fetch (default: 20)")
    args = parser.parse_args()

    source_name = f"Reddit u/{args.user}"

    source_timestamps = load_sources_scraped()
    ts = source_timestamps.get(source_name)
    since = None
    if ts:
        since = dateutil_parser.parse(ts)
        print(f"Fetching posts since {since.strftime('%Y-%m-%d %H:%M')} UTC")
    else:
        print("First run — fetching all posts")

    posts = fetch_reddit_posts(limit=args.limit, since=since, user=args.user, company=args.company)
    if posts:
        merge_into_articles(posts, source_name)
    else:
        print("No new posts.")
