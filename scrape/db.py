#!/usr/bin/env python3
"""Shared SQLite database layer for the Influencer pipeline."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "scrape" / "db" / "influencer.db"

VALID_SERIES = {"tbbt", "updates"}
VALID_STATUSES = {"new", "viewed", "done"}


def get_db(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tbbt (
            id TEXT PRIMARY KEY,
            source_name TEXT,
            company TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_date TEXT,
            description TEXT,
            scraped_at TEXT,
            status TEXT DEFAULT 'new',
            relevance_tier TEXT,
            relevance_score REAL DEFAULT 0,
            matched_keywords TEXT
        );

        CREATE TABLE IF NOT EXISTS updates (
            id TEXT PRIMARY KEY,
            source_name TEXT,
            company TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_date TEXT,
            description TEXT,
            scraped_at TEXT,
            status TEXT DEFAULT 'new',
            relevance_tier TEXT,
            relevance_score REAL DEFAULT 0,
            matched_keywords TEXT
        );

        CREATE TABLE IF NOT EXISTS rejected (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series TEXT NOT NULL DEFAULT '',
            topic TEXT,
            slug TEXT,
            angle TEXT,
            source_url TEXT,
            reason TEXT,
            rejected_at TEXT NOT NULL,
            UNIQUE(slug, series)
        );

    """)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_tbbt_url ON tbbt(url);
        CREATE INDEX IF NOT EXISTS idx_updates_url ON updates(url);
        CREATE INDEX IF NOT EXISTS idx_rejected_source_url ON rejected(source_url);
    """)
    _migrate_rejected_schema(conn)
    _migrate_article_status(conn)
    conn.commit()


def _migrate_rejected_schema(conn: sqlite3.Connection) -> None:
    """Recreate rejected table if it has the old NOT NULL schema or is missing columns."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rejected)").fetchall()}
    if "reason" in cols:
        return
    conn.executescript("""
        CREATE TABLE rejected_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series TEXT NOT NULL DEFAULT '',
            topic TEXT,
            slug TEXT,
            angle TEXT,
            source_url TEXT,
            reason TEXT,
            rejected_at TEXT NOT NULL,
            UNIQUE(slug, series)
        );
        INSERT INTO rejected_new (id, series, topic, slug, angle, source_url, rejected_at)
        SELECT id, series, topic, slug, angle, source_url, rejected_at FROM rejected;
        DROP TABLE rejected;
        ALTER TABLE rejected_new RENAME TO rejected;
    """)


def _migrate_article_status(conn: sqlite3.Connection) -> None:
    """Add status column to article tables, migrating from read boolean if present."""
    for table in ("tbbt", "updates"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "status" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN status TEXT DEFAULT 'new'")
            if "read" in cols:
                conn.execute(f"UPDATE {table} SET status = 'done' WHERE read = 1")
                conn.execute(f"UPDATE {table} SET status = 'new' WHERE read = 0")


def article_to_params(article: dict) -> dict:
    mk = article.get("matched_keywords")
    return {
        "id": article["id"],
        "source_name": article.get("source_name"),
        "company": article.get("company"),
        "title": article["title"],
        "url": article["url"],
        "published_date": article.get("published_date"),
        "description": article.get("description"),
        "scraped_at": article.get("scraped_at"),
        "status": article.get("status", "new"),
        "relevance_tier": article.get("relevance_tier"),
        "relevance_score": article.get("relevance_score", 0),
        "matched_keywords": json.dumps(mk) if mk else None,
    }


def row_to_article(row: sqlite3.Row) -> dict:
    d = dict(row)
    mk = d.get("matched_keywords")
    if mk and isinstance(mk, str):
        try:
            d["matched_keywords"] = json.loads(mk)
        except Exception:
            d["matched_keywords"] = []
    elif mk is None:
        d["matched_keywords"] = []
    return d
