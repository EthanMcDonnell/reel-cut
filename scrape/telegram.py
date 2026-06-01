#!/usr/bin/env python3
"""Send scraped articles to Telegram via the local bot API."""

import sys
import httpx
import logging
from pathlib import Path

log = logging.getLogger("telegram")

TELEGRAM_API = "http://localhost:8765/telegram/send"
HANDLE_RESPONSE_SCRIPT = str(Path(__file__).parent / "handle_response.py")
TOPIC = "Influencer Tech Updates"


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
