#!/usr/bin/env python3
"""CLI for agents to query and update the influencer SQLite database.

Outputs JSON to stdout. Designed for use by Claude agents via the Bash tool.

Usage:
  python scrape/query.py articles tbbt [--limit N] [--tier passing|low_score|excluded|all] [--status new|viewed|done|all] [--search KEYWORD]
  python scrape/query.py articles updates [--limit N] [--status new|viewed|done|all]
  python scrape/query.py rejected [--series tbbt|updates|misc]
  python scrape/query.py mark-viewed <series> <url>
  python scrape/query.py mark-done <series> <url>
  python scrape/query.py add-rejected <series> <slug> <topic> <source_url> [--angle TEXT] [--rejected-at YYYY-MM-DD]
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, row_to_article, VALID_SERIES, VALID_STATUSES


def cmd_articles(args: argparse.Namespace) -> None:
    series = args.series
    if series not in VALID_SERIES:
        print(json.dumps({"error": f"Unknown series '{series}'. Valid: {sorted(VALID_SERIES)}"}))
        sys.exit(1)

    conditions: list[str] = []
    params: list = []

    if args.tier and args.tier != "all":
        conditions.append("relevance_tier = ?")
        params.append(args.tier)

    # --status and --unread (alias for --status new) are mutually exclusive
    status_filter = args.status if hasattr(args, "status") else None
    if getattr(args, "unread", False):
        status_filter = "new"
    if status_filter and status_filter != "all":
        if status_filter not in VALID_STATUSES:
            print(json.dumps({"error": f"Unknown status '{status_filter}'. Valid: {sorted(VALID_STATUSES)}"}))
            sys.exit(1)
        conditions.append("status = ?")
        params.append(status_filter)

    if args.search:
        conditions.append("(title LIKE ? OR description LIKE ?)")
        kw = f"%{args.search}%"
        params.extend([kw, kw])

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    if series == "tbbt":
        order = " ORDER BY relevance_score DESC, published_date DESC"
    else:
        order = " ORDER BY published_date DESC"

    limit = f" LIMIT {args.limit}" if args.limit else ""

    query = f"SELECT * FROM {series}{where}{order}{limit}"
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    print(json.dumps([row_to_article(r) for r in rows], indent=2, ensure_ascii=False))


def cmd_rejected(args: argparse.Namespace) -> None:
    conn = get_db()
    if args.series:
        rows = conn.execute(
            "SELECT series, topic, slug, angle, source_url, reason, rejected_at FROM rejected WHERE series = ? ORDER BY rejected_at DESC",
            (args.series,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT series, topic, slug, angle, source_url, reason, rejected_at FROM rejected ORDER BY rejected_at DESC"
        ).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False))


def _mark_status(series: str, url: str, status: str) -> None:
    if series not in VALID_SERIES:
        print(json.dumps({"error": f"Unknown series '{series}'"}))
        sys.exit(1)
    if status not in VALID_STATUSES:
        print(json.dumps({"error": f"Unknown status '{status}'. Valid: {sorted(VALID_STATUSES)}"}))
        sys.exit(1)
    target_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    conn = get_db()
    cur = conn.execute(
        f"UPDATE {series} SET status = ? WHERE id = ? OR url = ?",
        (status, target_id, url),
    )
    conn.commit()
    if cur.rowcount == 0:
        print(json.dumps({"error": f"Article not found in {series}: {url}"}))
        sys.exit(1)
    print(json.dumps({"ok": True, "updated": cur.rowcount, "status": status}))


def cmd_mark_viewed(args: argparse.Namespace) -> None:
    _mark_status(args.series, args.url, "viewed")


def cmd_mark_done(args: argparse.Namespace) -> None:
    _mark_status(args.series, args.url, "done")


def cmd_add_rejected(args: argparse.Namespace) -> None:
    conn = get_db()
    rejected_at = args.rejected_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        conn.execute(
            "INSERT OR IGNORE INTO rejected (series, topic, slug, angle, source_url, rejected_at) VALUES (?, ?, ?, ?, ?, ?)",
            (args.series, args.topic, args.slug, args.angle, args.source_url, rejected_at),
        )
        conn.commit()
        print(json.dumps({"ok": True}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the influencer SQLite database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_articles = subparsers.add_parser("articles", help="Query articles from a series table")
    p_articles.add_argument("series", help="Series name: tbbt or updates")
    p_articles.add_argument("--limit", type=int, help="Max number of results")
    p_articles.add_argument("--tier", choices=["passing", "low_score", "excluded", "all"], default="all")
    p_articles.add_argument("--status", choices=["new", "viewed", "done", "all"], default="all",
                            help="Filter by status (default: all)")
    p_articles.add_argument("--unread", action="store_true", help="Alias for --status new")
    p_articles.add_argument("--search", metavar="KEYWORD", help="Filter by keyword in title/description")

    p_rejected = subparsers.add_parser("rejected", help="List rejected topics")
    p_rejected.add_argument("--series", help="Filter by series (tbbt, updates, misc)")

    p_viewed = subparsers.add_parser("mark-viewed", help="Mark an article as viewed")
    p_viewed.add_argument("series", help="Series name: tbbt or updates")
    p_viewed.add_argument("url", help="Article URL")

    p_done = subparsers.add_parser("mark-done", help="Mark an article as done (script produced)")
    p_done.add_argument("series", help="Series name: tbbt or updates")
    p_done.add_argument("url", help="Article URL")

    p_add = subparsers.add_parser("add-rejected", help="Add a rejected topic entry")
    p_add.add_argument("series", help="Series name (tbbt, updates, misc)")
    p_add.add_argument("slug", help="Topic slug (lowercase, hyphen-joined, max 6 words)")
    p_add.add_argument("topic", help="Full topic title")
    p_add.add_argument("source_url", help="Primary source URL")
    p_add.add_argument("--angle", help="Counter-intuitive angle description")
    p_add.add_argument("--rejected-at", metavar="DATE", help="Rejection date (YYYY-MM-DD), defaults to today")

    args = parser.parse_args()

    if args.command == "articles":
        cmd_articles(args)
    elif args.command == "rejected":
        cmd_rejected(args)
    elif args.command == "mark-viewed":
        cmd_mark_viewed(args)
    elif args.command == "mark-done":
        cmd_mark_done(args)
    elif args.command == "add-rejected":
        cmd_add_rejected(args)
