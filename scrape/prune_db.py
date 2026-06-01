#!/usr/bin/env python3
"""
prune_db.py — Prunes old articles from the SQLite database.

Articles are added to the DB when the user clicks Keep in Telegram (handle_response.py).
This script only handles retention pruning.

Usage:
  python scrape/prune_db.py --series tbbt --config scrape/sources-tbbt.yaml
  python scrape/prune_db.py --series updates --config scrape/sources-updates.yaml
  python scrape/prune_db.py --series tbbt --mark-read <url>
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, VALID_SERIES

ROOT = Path(__file__).parent.parent
SCRAPE_DIR = ROOT / "scrape"


def prune_old_articles(conn, series: str, retention_days: int) -> int:
    cur = conn.execute(
        f"DELETE FROM {series} WHERE published_date IS NOT NULL"
        f" AND DATE(published_date) <= DATE('now', '-{retention_days} days')",
    )
    conn.commit()
    return cur.rowcount


def prune(series: str, config_path: Path | None = None) -> None:
    if series not in VALID_SERIES:
        print(f"Unknown series '{series}'. Valid: {sorted(VALID_SERIES)}", file=sys.stderr)
        sys.exit(1)

    retention_days = None
    if config_path and config_path.exists():
        try:
            cfg = yaml.safe_load(config_path.read_text())
            retention_days = cfg.get("db_retention_days")
        except Exception:
            pass

    conn = get_db()
    pruned = 0
    if retention_days:
        pruned = prune_old_articles(conn, series, retention_days)
        if pruned:
            print(f"[{series}] Pruned {pruned} article(s) older than {retention_days} days")
        else:
            print(f"[{series}] Nothing to prune (retention: {retention_days} days)")
    else:
        print(f"[{series}] No retention config — nothing to prune")

    total = conn.execute(f"SELECT COUNT(*) FROM {series}").fetchone()[0]
    print(f"[{series}] {total} article(s) in db")


def mark_read(series: str, url: str) -> None:
    import hashlib
    if series not in VALID_SERIES:
        print(f"Unknown series '{series}'", file=sys.stderr)
        sys.exit(1)
    target_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    conn = get_db()
    cur = conn.execute(
        f"UPDATE {series} SET read = 1 WHERE id = ? OR url = ?",
        (target_id, url),
    )
    conn.commit()
    if cur.rowcount == 0:
        print(f"Article not found in {series}: {url}", file=sys.stderr)
        sys.exit(1)
    print(f"Marked as read: {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prune old articles from the SQLite database")
    parser.add_argument("--series", required=True, help="Series ID (e.g. tbbt, updates)")
    parser.add_argument("--config", metavar="FILE", help="Path to sources YAML (for retention/sort settings)")
    parser.add_argument("--mark-read", metavar="URL", help="Mark an article as read")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    if args.mark_read:
        mark_read(args.series, args.mark_read)
    else:
        prune(args.series, config_path)
