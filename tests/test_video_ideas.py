"""Tests for the persisted video-idea workflow."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrape"))

from db import get_db  # noqa: E402
from ideas import dedupe_sources, record_idea_response, save_batch  # noqa: E402
import ideas  # noqa: E402
import pytest  # noqa: E402
import telegram  # noqa: E402


@pytest.fixture(autouse=True)
def _series(monkeypatch):
    # series/ is per-user and gitignored; pin the slugs these tests use.
    monkeypatch.setattr(ideas, "series_slugs", lambda: {"updates", "tbbt"})


def _payload(batch_id="ideas-2026-08-24"):
    return {
        "batch_id": batch_id,
        "generated_at": "2026-08-24T16:00:00+00:00",
        "bank_path": f"VIDEO_IDEAS_{batch_id}.md",
        "ideas": [
            {
                "series": "updates",
                "slug": "claude-memory-controls",
                "hook": "Claude just made memory controls visible",
                "angle": "Show what users can now inspect and change.",
                "why": "A practical update with a clear viewer consequence.",
                "intent": "share",
                "sources": [
                    {
                        "title": "Memory controls",
                        "url": "https://example.com/memory",
                        "publication": "Anthropic",
                        "published_date": "2026-08-24",
                    }
                ],
            }
        ],
    }


def test_persisted_idea_dedupes_by_series_and_slug(tmp_path):
    conn = get_db(tmp_path / "ideas.db")

    first = save_batch(conn, _payload())
    second = save_batch(conn, _payload("ideas-2026-08-27"))

    assert len(first) == 1
    assert second == []
    assert conn.execute("SELECT COUNT(*) FROM video_ideas").fetchone()[0] == 1


def test_approving_an_idea_marks_it_and_its_article_viewed(tmp_path):
    conn = get_db(tmp_path / "ideas.db")
    conn.execute(
        "INSERT INTO updates (id, title, url, status) VALUES (?, ?, ?, ?)",
        ("article-1", "Memory controls", "https://example.com/memory", "new"),
    )
    conn.commit()
    idea_id = save_batch(conn, _payload())[0]

    record_idea_response(conn, idea_id, "keep")

    idea_status = conn.execute(
        "SELECT status FROM video_ideas WHERE id = ?", (idea_id,)
    ).fetchone()[0]
    article_status = conn.execute(
        "SELECT status FROM updates WHERE id = 'article-1'"
    ).fetchone()[0]
    assert idea_status == article_status == "viewed"


def test_rejecting_an_idea_persists_its_dedupe_record(tmp_path):
    conn = get_db(tmp_path / "ideas.db")
    idea_id = save_batch(conn, _payload())[0]

    record_idea_response(conn, idea_id, "delete")

    status = conn.execute("SELECT status FROM video_ideas WHERE id = ?", (idea_id,)).fetchone()[0]
    rejected = conn.execute(
        "SELECT series, slug, source_url FROM rejected WHERE series = 'updates'"
    ).fetchone()
    assert status == "rejected"
    assert tuple(rejected) == ("updates", "claude-memory-controls", "https://example.com/memory")


def test_rejected_idea_cannot_be_reapproved(tmp_path):
    conn = get_db(tmp_path / "ideas.db")
    idea_id = save_batch(conn, _payload())[0]
    record_idea_response(conn, idea_id, "delete")

    try:
        record_idea_response(conn, idea_id, "keep")
    except ValueError as exc:
        assert "permanently rejected" in str(exc)
    else:
        raise AssertionError("a rejected idea must not be reapproved")


def test_shared_supporting_url_is_sent_once_per_batch():
    sources = dedupe_sources([
        {"url": "https://example.com/article", "title": "Original", "series": "updates"},
        {"url": "https://example.com/article", "title": "Duplicate", "series": "tbbt"},
    ])

    assert sources == [{"url": "https://example.com/article", "title": "Original", "series": "updates"}]


def test_delivery_sends_approval_card_and_supporting_link(monkeypatch):
    payloads = []

    class Response:
        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json):
            payloads.append(json)
            return Response()

    monkeypatch.setattr(telegram.httpx, "Client", Client)
    idea = {
        "id": "idea-1",
        "series": "updates",
        "slug": "claude-memory-controls",
        "hook": "Claude just made memory controls visible",
        "angle": "Show what users can now inspect and change.",
        "why": "A practical update with a clear viewer consequence.",
        "intent": "share",
        "notes": None,
    }
    source = {
        "url": "https://example.com/memory",
        "title": "Memory controls",
        "publication": "Anthropic",
        "published_date": "2026-08-24",
        "series": "updates",
    }

    result = telegram.send_video_idea_messages(
        {"id": "ideas-2026-08-24"}, [idea], [idea], [source]
    )

    assert result == {
        "digest_sent": True,
        "idea_ids": ["idea-1"],
        "source_urls": ["https://example.com/memory"],
    }
    assert payloads[1]["buttons"] == ["Keep", "Delete"]
    assert payloads[1]["metadata"] == {
        "kind": "video_idea",
        "idea_id": "idea-1",
        "series": "updates",
        "slug": "claude-memory-controls",
        "hook": "Claude just made memory controls visible",
    }
    assert payloads[2] == {
        "content": "📎 [UPDATES] Supporting article\nMemory controls\nAnthropic · 2026-08-24\n\nhttps://example.com/memory",
        "topic": telegram.TOPIC,
    }
