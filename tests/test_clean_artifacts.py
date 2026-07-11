"""Tests for transcription-artifact cleanup — a transcribe re-run must fully reset
everything derived from the old transcript (captions, debug reports, and the
overlay files) while leaving source inputs (footage, manifest, screenshots) alone."""
from rich.console import Console

from reelcut.cli import _clean_transcription_artifacts


def _touch(path, content="x"):
    path.write_text(content)


def test_clean_removes_derived_keeps_sources(tmp_path):
    # Derived artifacts from a previous full run.
    _touch(tmp_path / "Teleprompter.captions.json")
    _touch(tmp_path / "Teleprompter.debug.1.raw.txt")
    _touch(tmp_path / "images.json", '[{"type": "screenshot"}]')
    _touch(tmp_path / "headings.json", '[{"title": "Real Title"}]')
    _touch(tmp_path / "audio.json", "[]")
    _touch(tmp_path / "title.json", '[{"title": "a title", "slug": "a-title"}]')
    clips = tmp_path / "retranscribe-clips"
    clips.mkdir()
    _touch(clips / "clip.wav")

    # Source inputs that must survive.
    _touch(tmp_path / "manifest.json", '{"topic": "x"}')
    _touch(tmp_path / "Teleprompter.MP4", "video-bytes")
    shots = tmp_path / "some-source-screenshots"
    shots.mkdir()
    _touch(shots / "snippet-01.png")

    _clean_transcription_artifacts(tmp_path, Console())

    # Derived → gone.
    assert not (tmp_path / "Teleprompter.captions.json").exists()
    assert not (tmp_path / "Teleprompter.debug.1.raw.txt").exists()
    assert not (tmp_path / "images.json").exists()
    assert not (tmp_path / "headings.json").exists()
    assert not (tmp_path / "audio.json").exists()
    assert not (tmp_path / "title.json").exists()
    assert not clips.exists()

    # Sources → kept.
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "Teleprompter.MP4").exists()
    assert (shots / "snippet-01.png").exists()


def test_clean_is_safe_when_overlays_absent(tmp_path):
    # First-ever run: no overlay files yet. Must not raise.
    _touch(tmp_path / "Teleprompter.captions.json")
    _clean_transcription_artifacts(tmp_path, Console())
    assert not (tmp_path / "Teleprompter.captions.json").exists()
