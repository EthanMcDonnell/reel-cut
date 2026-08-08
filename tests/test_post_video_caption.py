"""Caption lookup in scrape/post_video.py — including the flipped-duplicate filenames
that `output.flip.apply: duplicate` writes alongside each hook.
"""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_post_video", Path(__file__).parent.parent / "scrape" / "post_video.py"
)
post_video = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(post_video)


def _slug_with_titles(tmp_path, monkeypatch, entries):
    monkeypatch.setattr(post_video, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "title.json").write_text(json.dumps(entries))
    return "demo"


TITLES = [
    {"slug": "postgres-queue-unfair", "title": "Figma's Postgres queue is deliberately unfair"},
    {"slug": "twenty-outages-one-quarter", "title": "20 outages stopped in one quarter"},
]


def test_exact_stem_wins(tmp_path, monkeypatch):
    slug = _slug_with_titles(tmp_path, monkeypatch, TITLES)
    assert post_video.caption_for(slug, "postgres-queue-unfair") == TITLES[0]["title"]


def test_flipped_duplicate_inherits_its_hooks_caption(tmp_path, monkeypatch):
    slug = _slug_with_titles(tmp_path, monkeypatch, TITLES)
    assert post_video.caption_for(slug, "postgres-queue-unfair-flipped") == TITLES[0]["title"]


def test_suffix_is_not_assumed_to_be_flipped(tmp_path, monkeypatch):
    # The suffix is configurable, so the match is by title-slug prefix, not a literal "-flipped".
    slug = _slug_with_titles(tmp_path, monkeypatch, TITLES)
    assert post_video.caption_for(slug, "postgres-queue-unfair-b") == TITLES[0]["title"]


def test_longest_matching_title_slug_wins(tmp_path, monkeypatch):
    # One title slug being a prefix of another must not steal the longer one's caption.
    entries = [
        {"slug": "postgres-queue", "title": "Short one"},
        {"slug": "postgres-queue-unfair", "title": "Long one"},
    ]
    slug = _slug_with_titles(tmp_path, monkeypatch, entries)
    assert post_video.caption_for(slug, "postgres-queue-unfair-flipped") == "Long one"


def test_unknown_stem_falls_back_to_the_filename(tmp_path, monkeypatch):
    slug = _slug_with_titles(tmp_path, monkeypatch, TITLES)
    assert post_video.caption_for(slug, "hook3") == "hook3"


def test_missing_title_json_falls_back_to_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(post_video, "ROOT", tmp_path)
    assert post_video.caption_for("nope", "hook1") == "hook1"
