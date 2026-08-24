#!/usr/bin/env python3
"""Send scraped articles and curated video ideas through the local Telegram bot."""

import logging
import sys
from collections import defaultdict
from pathlib import Path

import httpx

log = logging.getLogger("telegram")

TELEGRAM_API = "http://localhost:8765/telegram/send"
HANDLE_RESPONSE_SCRIPT = str(Path(__file__).parent / "handle_response.py")
TOPIC = "Influencer Tech Updates"
MESSAGE_LIMIT = 4000


def _format_content(article: dict, run_type: str) -> str:
    series_label = run_type.upper()
    company = article.get("company") or article.get("source_name") or ""
    source = article.get("source_name") or ""
    keywords = ", ".join((article.get("matched_keywords") or [])[:5])

    lines = [
        f"[{series_label}]",
        article["title"],
        f"{company} · {source}" if company != source else company,
        "",
        article["url"],
    ]
    if keywords:
        lines.append(keywords)
    return "\n".join(lines)


def send_articles_to_telegram(articles: list[dict], run_type: str) -> int:
    """Send each article as a Telegram message with Keep/Delete buttons. Returns sent count."""
    if not articles:
        return 0

    sent = 0
    with httpx.Client(timeout=10) as client:
        for article in articles:
            payload = {
                "content": _format_content(article, run_type),
                "buttons": ["Keep", "Delete"],
                "topic": TOPIC,
                "metadata": {
                    "article_id": article["id"],
                    "title": article.get("title", ""),
                    "source_name": article.get("source_name", ""),
                    "company": article.get("company", ""),
                    "url": article["url"],
                    "published_date": article.get("published_date"),
                    "description": article.get("description", ""),
                    "scraped_at": article.get("scraped_at"),
                    "relevance_tier": article.get("relevance_tier"),
                    "relevance_score": article.get("relevance_score", 0),
                    "matched_keywords": article.get("matched_keywords") or [],
                    "run_type": run_type,
                },
                "on_response": {
                    "type": "command",
                    "command": f"{sys.executable} {HANDLE_RESPONSE_SCRIPT}",
                },
            }
            try:
                resp = client.post(TELEGRAM_API, json=payload)
                resp.raise_for_status()
                sent += 1
            except Exception as exc:
                log.warning(f"Failed to send '{article['title']}': {exc}")

    log.info(f"Sent {sent}/{len(articles)} articles to Telegram ({TOPIC})")
    return sent


def _chunk(content: str) -> list[str]:
    """Split a digest below Telegram's hard message cap without dropping text."""
    if len(content) <= MESSAGE_LIMIT:
        return [content]

    chunks: list[str] = []
    remaining = content
    while len(remaining) > MESSAGE_LIMIT:
        split_at = remaining.rfind("\n", 0, MESSAGE_LIMIT)
        if split_at <= 0:
            split_at = MESSAGE_LIMIT
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _format_digest(batch: dict, ideas: list[dict]) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for idea in ideas:
        groups[idea["series"]].append(idea)

    lines = [
        f"💡 Video ideas · {batch['id']}",
        f"{len(ideas)} curated ideas. Individual Keep/Delete cards follow.",
    ]
    for series, series_ideas in groups.items():
        lines.extend(["", f"{series.upper()} ({len(series_ideas)})"])
        for index, idea in enumerate(series_ideas, 1):
            intent = f" [{idea['intent']}]" if idea.get("intent") else ""
            lines.append(f"{index}. {idea['hook']}{intent}")
            lines.append(f"   {idea['angle']}")
    return "\n".join(lines)


def _idea_card(idea: dict) -> str:
    lines = [
        f"💡 [{idea['series'].upper()}]",
        idea["hook"],
        "",
        idea["angle"],
    ]
    if idea.get("why"):
        lines.extend(["", f"Why: {idea['why']}"])
    if idea.get("intent"):
        lines.append(f"Intent: {idea['intent']}")
    if idea.get("notes"):
        lines.extend(["", f"Notes: {idea['notes']}"])
    return "\n".join(lines)


def _source_message(source: dict) -> str:
    label = source.get("series", "source").upper()
    details = " · ".join(filter(None, [source.get("publication"), source.get("published_date")]))
    lines = [f"📎 [{label}] Supporting article", source.get("title") or source["url"]]
    if details:
        lines.append(details)
    lines.extend(["", source["url"]])
    return "\n".join(lines)


def _post(client: httpx.Client, payload: dict, description: str) -> bool:
    try:
        resp = client.post(TELEGRAM_API, json=payload)
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.warning(f"Failed to send {description}: {exc}")
        return False


def send_video_idea_messages(
    batch: dict,
    digest_ideas: list[dict],
    ideas: list[dict],
    sources: list[dict],
) -> dict:
    """Send a batch digest, individually actionable idea cards, and source links."""
    digest_sent = False
    idea_ids: list[str] = []
    source_urls: list[str] = []

    with httpx.Client(timeout=15) as client:
        if digest_ideas:
            digest_sent = all(
                _post(client, {"content": chunk, "topic": TOPIC}, "video-idea digest")
                for chunk in _chunk(_format_digest(batch, digest_ideas))
            )

        for idea in ideas:
            payload = {
                "content": _idea_card(idea),
                "buttons": ["Keep", "Delete"],
                "topic": TOPIC,
                "metadata": {
                    "kind": "video_idea",
                    "idea_id": idea["id"],
                    "series": idea["series"],
                    "slug": idea["slug"],
                    "hook": idea["hook"],
                },
                "on_response": {
                    "type": "command",
                    "command": f"{sys.executable} {HANDLE_RESPONSE_SCRIPT}",
                },
            }
            if _post(client, payload, f"video idea '{idea['hook']}'"):
                idea_ids.append(idea["id"])

        for source in sources:
            payload = {"content": _source_message(source), "topic": TOPIC}
            if _post(client, payload, f"supporting article '{source['url']}'"):
                source_urls.append(source["url"])

    return {
        "digest_sent": digest_sent,
        "idea_ids": idea_ids,
        "source_urls": source_urls,
    }
