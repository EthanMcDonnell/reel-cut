#!/usr/bin/env python3
"""One-time migration: import existing JSON/YAML data into the SQLite database.

Safe to run multiple times — uses INSERT OR IGNORE to skip duplicates.

Usage:
  python scrape/migrate.py
"""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, article_to_params

ROOT = Path(__file__).parent.parent
SCRAPE_DIR = ROOT / "scrape"
DB_DIR = SCRAPE_DIR / "db"
RUNS_DIR = SCRAPE_DIR / "runs"


def migrate_articles(conn, series: str) -> int:
    path = DB_DIR / f"{series}.json"
    if not path.exists():
        print(f"  [{series}] {path} not found — skipping")
        return 0
    data = json.loads(path.read_text())
    articles = data.get("articles", [])
    count = 0
    for article in articles:
        params = article_to_params(article)
        cur = conn.execute(
            f"""INSERT OR IGNORE INTO {series}
                (id, source_name, company, title, url, published_date, description,
                 scraped_at, read, relevance_tier, relevance_score, matched_keywords)
                VALUES (:id, :source_name, :company, :title, :url, :published_date, :description,
                        :scraped_at, :read, :relevance_tier, :relevance_score, :matched_keywords)
            """,
            params,
        )
        count += cur.rowcount
    conn.commit()
    skipped = len(articles) - count
    print(f"  [{series}] {count} inserted, {skipped} skipped (already existed) — {len(articles)} total in JSON")
    return count


def migrate_rejected(conn) -> int:
    entries: list[dict] = []

    yaml_path = DB_DIR / "rejected.yaml"
    if yaml_path.exists():
        raw = yaml.safe_load(yaml_path.read_text()) or []
        if isinstance(raw, list):
            entries.extend(raw)
        elif isinstance(raw, dict) and "rejected" in raw:
            entries.extend(raw["rejected"])
        print(f"  [rejected] Loaded {len(entries)} entries from YAML")

    json_path = DB_DIR / "rejected.json"
    if json_path.exists():
        raw = json.loads(json_path.read_text()) or []
        seen_slugs = {e.get("slug") for e in entries}
        added = 0
        for item in raw:
            if item.get("slug") not in seen_slugs:
                entries.append(item)
                seen_slugs.add(item.get("slug"))
                added += 1
        print(f"  [rejected] +{added} additional entries merged from JSON")

    count = 0
    for entry in entries:
        cur = conn.execute(
            "INSERT OR IGNORE INTO rejected (series, topic, slug, angle, source_url, rejected_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry.get("series", ""),
                entry.get("topic", ""),
                entry.get("slug", ""),
                entry.get("angle"),
                entry.get("source_url"),
                entry.get("rejected_at", ""),
            ),
        )
        count += cur.rowcount
    conn.commit()
    print(f"  [rejected] {count} inserted, {len(entries) - count} skipped")
    return count




if __name__ == "__main__":
    print("Migrating to SQLite…\n")
    conn = get_db()

    migrate_articles(conn, "tbbt")
    migrate_articles(conn, "updates")
    migrate_rejected(conn)

    print("\nRow counts after migration:")
    for table in ("tbbt", "updates", "rejected"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n} rows")

    print("\nDone. Safe to re-run.")
