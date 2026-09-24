"""Booking order in scrape/schedule_video.py: flipped hooks are spread between
the unflipped ones, never back to back while there is an unflipped hook to put
between them."""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_schedule_video_order", Path(__file__).parent.parent / "scrape" / "schedule_video.py"
)
schedule_video = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(schedule_video)


def _flipped_adjacent(seq, mirrors):
    return [(a, b) for a, b in zip(seq, seq[1:]) if a in mirrors and b in mirrors]


def _own_mirror_adjacent(seq, mirrors):
    return [(a, b) for a, b in zip(seq, seq[1:]) if mirrors.get(a) == b or mirrors.get(b) == a]


def test_alphabetical_flipped_pair_is_split():
    """github-stars-over-money booked its two flipped hooks back to back."""
    stems = ["10-stars-100-all-day", "keep-your-100-i-want-the-stars",
             "stars-over-cash", "star-my-repo"]
    mirrors = {"keep-your-100-i-want-the-stars": "10-stars-100-all-day",
               "stars-over-cash": "star-my-repo"}
    seq = schedule_video.booking_order(stems, mirrors)
    assert sorted(seq) == sorted(stems)
    assert _flipped_adjacent(seq, mirrors) == []


def test_three_hooks_all_flipped_alternate_and_avoid_own_mirror():
    stems = ["a", "a-flipped", "b", "b-flipped", "c", "c-flipped"]
    mirrors = {"a-flipped": "a", "b-flipped": "b", "c-flipped": "c"}
    seq = schedule_video.booking_order(stems, mirrors)
    assert sorted(seq) == sorted(stems)
    assert seq[0] not in mirrors
    assert _flipped_adjacent(seq, mirrors) == []
    assert _own_mirror_adjacent(seq, mirrors) == []


def test_few_flipped_spread_among_many_originals():
    stems = ["a", "b", "c", "d", "e", "b-flipped", "d-flipped"]
    mirrors = {"b-flipped": "b", "d-flipped": "d"}
    seq = schedule_video.booking_order(stems, mirrors)
    assert sorted(seq) == sorted(stems)
    assert _flipped_adjacent(seq, mirrors) == []
    assert _own_mirror_adjacent(seq, mirrors) == []


def test_more_flipped_than_originals_still_interleaves():
    """Originals already published: flipped pairs are unavoidable, but every
    remaining original still breaks a run."""
    stems = ["x", "a-flipped", "b-flipped", "c-flipped"]
    mirrors = {"a-flipped": "a", "b-flipped": "b", "c-flipped": "c"}
    seq = schedule_video.booking_order(stems, mirrors)
    assert sorted(seq) == sorted(stems)
    assert seq[0] != "x" and seq[-1] != "x"


def test_no_flipped_keeps_order():
    assert schedule_video.booking_order(["b", "a"], {}) == ["b", "a"]


def test_mirrors_for_reads_of_and_suffix_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule_video, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "videos.json").write_text(json.dumps([
        {"id": "one", "filename": "star-my-repo"},
        {"id": "one-flipped", "of": "one", "filename": "stars-over-cash"},
        {"id": "two", "filename": "ten-stars"},
    ]))
    stems = ["star-my-repo", "stars-over-cash", "ten-stars", "ten-stars-flipped"]
    assert schedule_video.mirrors_for("demo", stems) == {
        "stars-over-cash": "star-my-repo",
        "ten-stars-flipped": "ten-stars",
    }
