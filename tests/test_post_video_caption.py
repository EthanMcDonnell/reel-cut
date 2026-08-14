"""Caption lookup in scrape/post_video.py — including the mirrored duplicates that
`output.flip.apply: duplicate` writes alongside each hook.
"""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_post_video", Path(__file__).parent.parent / "scrape" / "post_video.py"
)
post_video = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(post_video)


def _slug_with_videos(tmp_path, monkeypatch, entries):
    monkeypatch.setattr(post_video, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "videos.json").write_text(json.dumps(entries))
    return "demo"


VIDEOS = [
    {"id": "unfair", "slug": "postgres-queue-unfair",
     "caption": "Figma's Postgres queue is deliberately unfair"},
    {"id": "outages", "slug": "twenty-outages-one-quarter",
     "caption": "20 outages stopped in one quarter"},
]


def test_exact_stem_wins(tmp_path, monkeypatch):
    slug = _slug_with_videos(tmp_path, monkeypatch, VIDEOS)
    assert post_video.caption_for(slug, "postgres-queue-unfair") == VIDEOS[0]["caption"]


def test_undescribed_duplicate_inherits_its_hooks_caption(tmp_path, monkeypatch):
    slug = _slug_with_videos(tmp_path, monkeypatch, VIDEOS)
    assert post_video.caption_for(slug, "postgres-queue-unfair-flipped") == VIDEOS[0]["caption"]


def test_suffix_is_not_assumed_to_be_flipped(tmp_path, monkeypatch):
    # The suffix is configurable, so the fallback matches by stem prefix, not "-flipped".
    slug = _slug_with_videos(tmp_path, monkeypatch, VIDEOS)
    assert post_video.caption_for(slug, "postgres-queue-unfair-b") == VIDEOS[0]["caption"]


def test_longest_matching_stem_wins(tmp_path, monkeypatch):
    # One stem being a prefix of another must not steal the longer one's caption.
    entries = [
        {"id": "short", "slug": "postgres-queue", "caption": "Short one"},
        {"id": "long", "slug": "postgres-queue-unfair", "caption": "Long one"},
    ]
    slug = _slug_with_videos(tmp_path, monkeypatch, entries)
    assert post_video.caption_for(slug, "postgres-queue-unfair-flipped") == "Long one"


def test_mirror_entry_posts_under_its_own_caption(tmp_path, monkeypatch):
    # The whole point of a described duplicate: it must not reuse the hook's caption.
    entries = VIDEOS + [{
        "id": "unfair-flipped", "of": "unfair", "slug": "queue-jumping-is-the-point",
        "caption": "queue jumping is the point",
    }]
    slug = _slug_with_videos(tmp_path, monkeypatch, entries)
    assert post_video.caption_for(slug, "queue-jumping-is-the-point") == "queue jumping is the point"
    assert post_video.caption_for(slug, "postgres-queue-unfair") == VIDEOS[0]["caption"]


def test_entry_without_a_slug_is_keyed_by_its_slugified_caption(tmp_path, monkeypatch):
    # render-hooks names that file from the caption, so the lookup has to match it.
    entries = [{"id": "x", "caption": "queue jumping is the point 💸"}]
    slug = _slug_with_videos(tmp_path, monkeypatch, entries)
    assert post_video.caption_for(slug, "queue-jumping-is-the-point") == "queue jumping is the point 💸"


def test_unknown_stem_falls_back_to_the_filename(tmp_path, monkeypatch):
    slug = _slug_with_videos(tmp_path, monkeypatch, VIDEOS)
    assert post_video.caption_for(slug, "hook3") == "hook3"


def test_missing_videos_json_falls_back_to_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(post_video, "ROOT", tmp_path)
    assert post_video.caption_for("nope", "hook1") == "hook1"
