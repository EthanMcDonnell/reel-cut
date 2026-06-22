"""Tests for the concept-image resolver — local-file priority, unknown handling,
and the emoji cache path (no network)."""
from pathlib import Path

from PIL import Image

import reelcut.concept_resolver as cr
from reelcut.concept_resolver import load_concepts, resolve_concept


def _write_concepts(d: Path, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "concepts.yaml").write_text(body)


class TestLoadConcepts:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_concepts(tmp_path) == {}

    def test_parses_entries(self, tmp_path):
        _write_concepts(tmp_path, 'bug: {emoji: "1F41B"}\nhandcuffs: {emoji: "1F46E", file: cuffs.png}\n')
        c = load_concepts(tmp_path)
        assert c["bug"]["emoji"] == "1F41B"
        assert c["handcuffs"]["file"] == "cuffs.png"


class TestResolveConcept:
    def test_local_file_wins(self, tmp_path):
        _write_concepts(tmp_path, 'handcuffs: {emoji: "1F46E", file: cuffs.png}\n')
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(tmp_path / "cuffs.png")
        assert resolve_concept("handcuffs", tmp_path) == tmp_path / "cuffs.png"

    def test_unknown_returns_none(self, tmp_path):
        _write_concepts(tmp_path, 'bug: {emoji: "1F41B"}\n')
        assert resolve_concept("nope", tmp_path) is None

    def test_emoji_cache_hit_no_network(self, tmp_path, monkeypatch):
        _write_concepts(tmp_path, 'bug: {emoji: "1F41B"}\n')
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "1F41B.png").write_bytes(b"x")
        monkeypatch.setattr(cr, "_CACHE_DIR", cache)
        assert resolve_concept("bug", tmp_path) == cache / "1F41B.png"

    def test_missing_local_file_falls_back_to_emoji(self, tmp_path, monkeypatch):
        # file declared but absent → use the cached emoji instead of failing
        _write_concepts(tmp_path, 'handcuffs: {emoji: "1F46E", file: cuffs.png}\n')
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "1F46E.png").write_bytes(b"x")
        monkeypatch.setattr(cr, "_CACHE_DIR", cache)
        assert resolve_concept("handcuffs", tmp_path) == cache / "1F46E.png"
