"""The YouTube cross-post in scrape/schedule_video.py.

Three things have to hold for a slot booked against a slug's pool to post the
right video days later: every Instagram hook enrols itself in the pool, the
YouTube job carries no file of its own, and it carries a title — because
YouTube refuses an untitled upload and the pool's fallback is the mp4 filename.
"""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_schedule_video", Path(__file__).parent.parent / "scrape" / "schedule_video.py"
)
schedule_video = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(schedule_video)


class _Recorder:
    """Stands in for requests.post, keeping the payload it was handed."""

    def __init__(self):
        self.payloads = []

    def __call__(self, url, json=None, timeout=None):
        self.payloads.append(json)

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"job": {"id": "job-1", "status": "pending"}}

        return _Resp()


VIDEOS = [
    {"id": "unfair", "filename": "postgres-queue-unfair",
     "title": "Figma's Queue\nIs Unfair On Purpose",
     "caption": "Figma's Postgres queue is deliberately unfair"},
    {"id": "unfair-flipped", "of": "unfair", "filename": "queue-unfair-mirrored",
     "title": "A Mirror Of The First", "caption": "same clip, mirrored"},
]


def _slug(tmp_path, monkeypatch, entries=VIDEOS):
    monkeypatch.setattr(schedule_video, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "videos.json").write_text(json.dumps(entries))
    return "demo"


def test_hook_enrols_itself_in_the_pool(tmp_path, monkeypatch):
    """Without `slug` on the Instagram job the pool never fills, and the
    cross-post has nothing to pick at fire time."""
    post = _Recorder()
    monkeypatch.setattr(schedule_video.requests, "post", post)
    mp4 = tmp_path / "hook.mp4"
    mp4.write_bytes(b"")

    schedule_video.schedule(mp4, "a caption", "2026-09-01T09:30", "demo")

    payload = post.payloads[0]
    assert payload["slug"] == "demo"
    assert payload["video"] == "demo"
    assert payload["video_path"] == str(mp4.resolve())


def test_youtube_job_books_the_pool_not_a_file(tmp_path, monkeypatch):
    post = _Recorder()
    monkeypatch.setattr(schedule_video.requests, "post", post)

    schedule_video.schedule_youtube("2026-09-03T09:30", "demo", "Some Title")

    payload = post.payloads[0]
    assert payload["platform"] == "yt"
    assert payload["slug"] == "demo"
    assert payload["selection_method"] == "most_views"
    assert payload["title"] == "Some Title"
    # A file would defeat the whole point: the video is chosen at fire time.
    assert "video_path" not in payload
    # The cockpit attaches automations to Instagram only, and drops one here.
    assert "automation" not in payload


def test_title_flattens_the_primary_entrys_card(tmp_path, monkeypatch):
    """The card's "\\n" is a line break for the burned-in title, not for YouTube."""
    slug = _slug(tmp_path, monkeypatch)
    assert schedule_video.title_for(slug) == "Figma's Queue Is Unfair On Purpose"


def test_title_ignores_mirrored_entries(tmp_path, monkeypatch):
    """A mirror is the same video flipped; the original names it."""
    slug = _slug(tmp_path, monkeypatch, [VIDEOS[1], VIDEOS[0]])
    assert schedule_video.title_for(slug) == "Figma's Queue Is Unfair On Purpose"


def test_title_falls_back_to_the_slug(tmp_path, monkeypatch):
    """An untitled upload is refused by YouTube, so this can never be empty."""
    slug = _slug(tmp_path, monkeypatch, [{"id": "x", "filename": "x", "caption": "c"}])
    assert schedule_video.title_for(slug) == "demo"


def test_cross_post_is_claimed_in_the_ledger(tmp_path, monkeypatch):
    """Without a claim, a second run books a second YouTube post for the slug."""
    post = _Recorder()
    monkeypatch.setattr(schedule_video.requests, "post", post)
    slug = _slug(tmp_path, monkeypatch)
    log = tmp_path / ".published"

    class _Args:
        pass

    args = _Args()
    args.slug, args.youtube, args.dry_run = slug, "2026-09-03T09:30", False

    booked, failed = [], []
    schedule_video.book_youtube(args, log, set(), booked, failed)
    assert booked == ["demo/@youtube"] and not failed
    assert log.read_text().startswith("demo/@youtube\t2026-09-03T09:30")

    # Second run, now that the key is claimed.
    booked, failed = [], []
    schedule_video.book_youtube(args, log, {"demo/@youtube"}, booked, failed)
    assert failed == ["demo/@youtube"] and not booked
    assert len(post.payloads) == 1
