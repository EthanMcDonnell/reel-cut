"""Tests for the Instagram title sidecar — filename slugging, loading, and the
transcribe-time stub scaffold."""
import json

from reelcut.cli import _scaffold_titles
from reelcut.title import TitleSpec, load_titles, safe_slug


def test_safe_slug_strips_emoji_and_punctuation():
    assert safe_slug("reddit & kafka -> kubernetes w/ no 🧑❓") == "reddit-kafka-kubernetes-w-no"
    assert safe_slug("why reddit ditched kafka 😵") == "why-reddit-ditched-kafka"


def test_safe_slug_empty_when_nothing_usable():
    # A title that is only emoji/punctuation leaves no ASCII stem — caller falls back.
    assert safe_slug("🧑❓") == ""
    assert safe_slug("  --,,--  ") == ""


def test_load_titles_missing_or_empty(tmp_path):
    assert load_titles(tmp_path / "nope.json") == []
    (tmp_path / "title.json").write_text("[]")
    assert load_titles(tmp_path / "title.json") == []


def test_load_titles_reads_entries(tmp_path):
    tp = tmp_path / "title.json"
    tp.write_text(json.dumps([
        {"title": "reddit & kafka -> k8s 🧑", "slug": "reddit-kafka-k8s"},
        {"title": "why reddit ditched kafka 😵"},  # slug omitted → ""
    ]))
    got = load_titles(tp)
    assert got == [
        TitleSpec(title="reddit & kafka -> k8s 🧑", slug="reddit-kafka-k8s"),
        TitleSpec(title="why reddit ditched kafka 😵", slug=""),
    ]


def test_scaffold_titles_creates_stub_and_never_clobbers(tmp_path):
    cap = tmp_path / "clip.captions.json"
    cap.write_text("{}")

    _scaffold_titles(cap)
    tp = tmp_path / "title.json"
    assert json.loads(tp.read_text()) == []

    # A filled-in title.json must survive a second scaffold (idempotent, non-clobbering).
    tp.write_text('[{"title": "kept", "slug": "kept"}]')
    _scaffold_titles(cap)
    assert json.loads(tp.read_text()) == [{"title": "kept", "slug": "kept"}]
