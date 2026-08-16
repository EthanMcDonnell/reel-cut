"""Tests for videos.json — the single sidecar describing every rendered video.

Filename slugging, the loader's authoring guards, and the transcribe-time stub scaffold.
"""
import json

import pytest

from reelcut.cli import _scaffold_videos
from reelcut.video_spec import VideoSpec, base_videos, load_videos, mirror_of, safe_slug, stem_for


def test_safe_slug_strips_emoji_and_punctuation():
    assert safe_slug("reddit & kafka -> kubernetes w/ no 🧑❓") == "reddit-kafka-kubernetes-w-no"
    assert safe_slug("why reddit ditched kafka 😵") == "why-reddit-ditched-kafka"


def test_safe_slug_empty_when_nothing_usable():
    # A caption that is only emoji/punctuation leaves no ASCII stem — caller falls back.
    assert safe_slug("🧑❓") == ""
    assert safe_slug("  --,,--  ") == ""


def test_load_videos_missing_or_empty(tmp_path):
    assert load_videos(tmp_path / "nope.json") == []
    (tmp_path / "videos.json").write_text("[]")
    assert load_videos(tmp_path / "videos.json") == []


def test_load_videos_reads_entries_and_defaults(tmp_path):
    vp = tmp_path / "videos.json"
    vp.write_text(json.dumps([
        {"id": "a", "title": "Card A", "subtitle": "sub", "start": 0, "end": 3,
         "scrim": False, "caption": "caption a 🤫", "filename": "caption-a"},
        {"id": "a-flipped", "of": "a", "title": "Card B", "caption": "caption b"},
    ]))
    assert load_videos(vp) == [
        VideoSpec(id="a", title="Card A", subtitle="sub", scrim=False, start=0.0, end=3.0,
                  caption="caption a 🤫", filename="caption-a"),
        VideoSpec(id="a-flipped", title="Card B", caption="caption b", of="a"),
    ]


def test_load_videos_rejects_duplicate_ids(tmp_path):
    # Two entries sharing an id makes `of` ambiguous and silently mis-titles a render.
    vp = tmp_path / "videos.json"
    vp.write_text(json.dumps([{"id": "a"}, {"id": "a"}]))
    with pytest.raises(ValueError, match="duplicate entry id"):
        load_videos(vp)


def test_load_videos_rejects_a_mirror_of_nothing(tmp_path):
    # A typo'd `of` would otherwise leave the entry unrendered with no complaint.
    vp = tmp_path / "videos.json"
    vp.write_text(json.dumps([{"id": "a"}, {"id": "b", "of": "typo"}]))
    with pytest.raises(ValueError, match="mirrors 'typo'"):
        load_videos(vp)


def test_base_and_mirror_split():
    videos = [
        VideoSpec(id="a", title="A"),
        VideoSpec(id="a-flipped", of="a"),
        VideoSpec(id="b", title="B"),
    ]
    assert [v.id for v in base_videos(videos)] == ["a", "b"]
    assert mirror_of(videos, "a").id == "a-flipped"
    assert mirror_of(videos, "b") is None


def test_stem_falls_back_from_filename_to_caption_to_id():
    assert stem_for(VideoSpec(id="x", filename="my-slug", caption="my caption")) == "my-slug"
    assert stem_for(VideoSpec(id="x", caption="my caption 😵")) == "my-caption"
    assert stem_for(VideoSpec(id="hook1", caption="🧑❓")) == "hook1"


def test_scaffold_videos_creates_stub_and_never_clobbers(tmp_path):
    cap = tmp_path / "clip.captions.json"
    cap.write_text("{}")
    _scaffold_videos(cap, end_s=-1)
    stub = json.loads((tmp_path / "videos.json").read_text())
    assert stub[0]["title"] == "" and stub[0]["end"] == -1

    (tmp_path / "videos.json").write_text('[{"id": "mine", "title": "Hand written"}]')
    _scaffold_videos(cap, end_s=-1)
    assert json.loads((tmp_path / "videos.json").read_text())[0]["title"] == "Hand written"
