#!/usr/bin/env python3
"""Persist, deliver, and approve curated video-idea batches."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import (  # noqa: E402
    series_slugs,
    VALID_IDEA_STATUSES,
    get_db,
)
from telegram import send_video_idea_messages  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idea_id(series: str, slug: str) -> str:
    return hashlib.sha256(f"{series}:{slug}".encode()).hexdigest()[:16]


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _idea_from_payload(raw: dict) -> dict:
    series = _string(raw.get("series"), "idea.series")
    if series not in series_slugs():
        raise ValueError(f"Unknown idea series '{series}'")

    slug = _string(raw.get("slug"), "idea.slug")
    if slug != slug.lower() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug):
        raise ValueError("idea.slug must use lowercase letters, numbers, and hyphens")

    sources = raw.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("idea.sources must be a list")

    return {
        "id": _idea_id(series, slug),
        "series": series,
        "slug": slug,
        "hook": _string(raw.get("hook"), "idea.hook"),
        "angle": _string(raw.get("angle"), "idea.angle"),
        "why": raw.get("why") or None,
        "intent": raw.get("intent") or None,
        "notes": raw.get("notes") or None,
        "sources": [_source_from_payload(source) for source in sources],
    }


def _source_from_payload(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("idea.sources entries must be objects")
    return {
        "title": raw.get("title") or None,
        "url": _string(raw.get("url"), "idea.sources.url"),
        "publication": raw.get("publication") or None,
        "published_date": raw.get("published_date") or None,
        "article_id": raw.get("article_id") or None,
    }


def _batch_from_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("batch payload must be an object")
    ideas = payload.get("ideas")
    if not isinstance(ideas, list) or not ideas:
        raise ValueError("batch.ideas must be a non-empty list")

    return {
        "id": _string(payload.get("batch_id"), "batch_id"),
        "generated_at": _string(payload.get("generated_at"), "generated_at"),
        "bank_path": _string(payload.get("bank_path"), "bank_path"),
        "ideas": [_idea_from_payload(idea) for idea in ideas],
    }


def save_batch(conn, payload: dict) -> list[str]:
    """Store a batch and return the IDs of ideas newly proposed by it."""
    batch = _batch_from_payload(payload)
    created: list[str] = []

    with conn:
        existing = conn.execute(
            "SELECT bank_path FROM video_idea_batches WHERE id = ?", (batch["id"],)
        ).fetchone()
        if existing and existing["bank_path"] != batch["bank_path"]:
            raise ValueError(f"Batch '{batch['id']}' already belongs to {existing['bank_path']}")

        conn.execute(
            """INSERT OR IGNORE INTO video_idea_batches (id, generated_at, bank_path)
               VALUES (?, ?, ?)""",
            (batch["id"], batch["generated_at"], batch["bank_path"]),
        )

        for idea in batch["ideas"]:
            cur = conn.execute(
                """INSERT OR IGNORE INTO video_ideas
                   (id, batch_id, series, slug, hook, angle, why, intent, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    idea["id"],
                    batch["id"],
                    idea["series"],
                    idea["slug"],
                    idea["hook"],
                    idea["angle"],
                    idea["why"],
                    idea["intent"],
                    idea["notes"],
                    _now(),
                ),
            )
            if cur.rowcount == 0:
                continue

            created.append(idea["id"])
            for source in idea["sources"]:
                conn.execute(
                    """INSERT OR IGNORE INTO video_idea_sources
                       (idea_id, title, url, publication, published_date, article_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        idea["id"],
                        source["title"],
                        source["url"],
                        source["publication"],
                        source["published_date"],
                        source["article_id"],
                    ),
                )

    return created


def batch_for_delivery(conn, batch_id: str) -> dict:
    batch = conn.execute(
        "SELECT * FROM video_idea_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if not batch:
        raise ValueError(f"Unknown video-idea batch '{batch_id}'")

    rows = conn.execute(
        "SELECT * FROM video_ideas WHERE batch_id = ? ORDER BY series, created_at", (batch_id,)
    ).fetchall()
    ideas = [dict(row) for row in rows]
    sources = conn.execute(
        "SELECT * FROM video_idea_sources WHERE idea_id IN "
        "(SELECT id FROM video_ideas WHERE batch_id = ?) ORDER BY id",
        (batch_id,),
    ).fetchall()
    sources_by_idea: dict[str, list[dict]] = {idea["id"]: [] for idea in ideas}
    for source in sources:
        source_data = dict(source)
        source_data["series"] = next(
            idea["series"] for idea in ideas if idea["id"] == source_data["idea_id"]
        )
        sources_by_idea[source_data["idea_id"]].append(source_data)
    for idea in ideas:
        idea["sources"] = sources_by_idea[idea["id"]]

    return {"batch": dict(batch), "ideas": ideas}


def dedupe_sources(sources: list[dict]) -> list[dict]:
    """Keep one Telegram link message per supporting URL, in source order."""
    seen: set[str] = set()
    unique: list[dict] = []
    for source in sources:
        url = source.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(source)
    return unique


def _pending_sources(ideas: list[dict]) -> list[dict]:
    return dedupe_sources([
        source
        for idea in ideas
        for source in idea["sources"]
        if not source.get("telegram_sent_at")
    ])


def deliver_batch(conn, batch_id: str) -> dict:
    """Send any undelivered digest, approval cards, and supporting links."""
    data = batch_for_delivery(conn, batch_id)
    batch = data["batch"]
    ideas = data["ideas"]
    digest_ideas = ideas if not batch["telegram_digest_sent_at"] else []
    pending_ideas = [idea for idea in ideas if not idea["telegram_sent_at"]]
    pending_sources = _pending_sources(ideas)
    delivery = send_video_idea_messages(batch, digest_ideas, pending_ideas, pending_sources)
    sent_at = _now()

    with conn:
        if delivery["digest_sent"]:
            conn.execute(
                "UPDATE video_idea_batches SET telegram_digest_sent_at = ? WHERE id = ?",
                (sent_at, batch_id),
            )
        for idea_id in delivery["idea_ids"]:
            conn.execute(
                "UPDATE video_ideas SET telegram_sent_at = ? WHERE id = ?", (sent_at, idea_id)
            )
        for url in delivery["source_urls"]:
            conn.execute(
                """UPDATE video_idea_sources SET telegram_sent_at = ?
                   WHERE url = ? AND idea_id IN
                   (SELECT id FROM video_ideas WHERE batch_id = ?)""",
                (sent_at, url, batch_id),
            )

    return delivery


def record_idea_response(conn, idea_id: str, response: str) -> str:
    """Apply Telegram Keep/Delete semantics to a persisted video idea."""
    response = response.lower()
    if response in {"keep", "approve"}:
        status = "viewed"
    elif response in {"delete", "reject"}:
        status = "rejected"
    else:
        raise ValueError(f"Unknown idea response '{response}'")

    idea = conn.execute("SELECT * FROM video_ideas WHERE id = ?", (idea_id,)).fetchone()
    if not idea:
        raise ValueError(f"Video idea '{idea_id}' not found")
    if idea["status"] == "rejected" and status != "rejected":
        raise ValueError(f"Video idea '{idea_id}' is permanently rejected")

    with conn:
        conn.execute("UPDATE video_ideas SET status = ? WHERE id = ?", (status, idea_id))
        sources = conn.execute(
            "SELECT url FROM video_idea_sources WHERE idea_id = ?", (idea_id,)
        ).fetchall()
        if status == "viewed" and idea["series"] in {"tbbt", "updates"}:
            for source in sources:
                conn.execute(
                    f"UPDATE {idea['series']} SET status = 'viewed' WHERE url = ?",
                    (source["url"],),
                )
        if status == "rejected":
            source = sources[0] if sources else None
            conn.execute(
                """INSERT OR IGNORE INTO rejected
                   (series, topic, slug, angle, source_url, reason, rejected_at)
                   VALUES (?, ?, ?, ?, ?, ?, date('now'))""",
                (
                    idea["series"],
                    idea["hook"],
                    idea["slug"],
                    idea["angle"],
                    source["url"] if source else None,
                    "telegram:delete",
                ),
            )

    return status


def _cmd_import(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.payload).read_text())
    conn = get_db()
    created = save_batch(conn, payload)
    result = {"created": len(created), "idea_ids": created, "batch_id": payload["batch_id"]}
    if args.send:
        result["delivery"] = deliver_batch(conn, payload["batch_id"])
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _cmd_list(args: argparse.Namespace) -> None:
    conn = get_db()
    params: list[str] = []
    where = ""
    if args.status != "all":
        where = " WHERE status = ?"
        params.append(args.status)
    rows = conn.execute(
        f"SELECT * FROM video_ideas{where} ORDER BY created_at DESC", params
    ).fetchall()
    ideas = [dict(row) for row in rows]
    for idea in ideas:
        source_rows = conn.execute(
            """SELECT title, url, publication, published_date, article_id
               FROM video_idea_sources WHERE idea_id = ? ORDER BY id""",
            (idea["id"],),
        ).fetchall()
        idea["sources"] = [dict(source) for source in source_rows]
    print(json.dumps(ideas, indent=2, ensure_ascii=False))


def _cmd_mark_done(args: argparse.Namespace) -> None:
    conn = get_db()
    with conn:
        cur = conn.execute("UPDATE video_ideas SET status = 'done' WHERE id = ?", (args.idea_id,))
    if cur.rowcount == 0:
        raise ValueError(f"Video idea '{args.idea_id}' not found")
    print(json.dumps({"ok": True, "idea_id": args.idea_id, "status": "done"}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist and deliver video-idea batches")
    commands = parser.add_subparsers(dest="command", required=True)

    p_import = commands.add_parser("import", help="Store a structured idea batch")
    p_import.add_argument("payload", help="Path to the JSON batch payload")
    p_import.add_argument("--send", action="store_true", help="Send pending Telegram messages")

    p_list = commands.add_parser("list", help="List persisted ideas")
    p_list.add_argument("--status", choices=sorted(VALID_IDEA_STATUSES | {"all"}), default="all")

    p_done = commands.add_parser("mark-done", help="Mark an approved idea as produced")
    p_done.add_argument("idea_id")

    args = parser.parse_args()
    try:
        if args.command == "import":
            _cmd_import(args)
        elif args.command == "list":
            _cmd_list(args)
        elif args.command == "mark-done":
            _cmd_mark_done(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
