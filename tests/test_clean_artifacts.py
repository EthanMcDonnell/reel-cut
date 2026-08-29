"""Tests for transcription-artifact cleanup.

A transcribe re-run must clear everything the old transcript's timing is baked into,
while leaving source inputs (footage, manifest, screenshots) alone. By default it keeps
the overlay content nobody regenerates — videos.json's card wording and audio.json — and
clears only the hook windows; `--fresh` wipes those too.
"""
import json

from rich.console import Console

from reelcut.cli import _clean_transcription_artifacts

_VIDEOS = json.dumps([
    {"id": "hook1", "title": "Real Title", "subtitle": "Sub", "caption": "cap",
     "filename": "real-title", "scrim": True, "start": 0.0, "end": 3.1},
    {"id": "hook1-flipped", "of": "hook1", "title": "Mirror", "caption": "mirror cap",
     "filename": "mirror"},
])


def _touch(path, content="x"):
    path.write_text(content)


def _seed(tmp_path):
    """A finished run's artifacts, plus the source inputs that must survive either mode."""
    _touch(tmp_path / "Teleprompter.captions.json")
    _touch(tmp_path / "Teleprompter.debug.1.raw.txt")
    _touch(tmp_path / "images.json", '[{"type": "screenshot"}]')
    _touch(tmp_path / "videos.json", _VIDEOS)
    _touch(tmp_path / "audio.json", '[{"track": "upbeat"}]')
    clips = tmp_path / "retranscribe-clips"
    clips.mkdir()
    _touch(clips / "clip.wav")

    _touch(tmp_path / "manifest.json", '{"topic": "x"}')
    _touch(tmp_path / "Teleprompter.MP4", "video-bytes")
    shots = tmp_path / "some-source-screenshots"
    shots.mkdir()
    _touch(shots / "snippet-01.png")
    return clips, shots


def _assert_derived_gone(tmp_path, clips):
    assert not (tmp_path / "Teleprompter.captions.json").exists()
    assert not (tmp_path / "Teleprompter.debug.1.raw.txt").exists()
    assert not clips.exists()
    # images.json goes in both modes: produce-video rewrites it whole, and its source-time
    # anchors can land inside a cut once the EDL moves.
    assert not (tmp_path / "images.json").exists()


def _assert_sources_kept(tmp_path, shots):
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "Teleprompter.MP4").exists()
    assert (shots / "snippet-01.png").exists()


def test_default_keeps_card_wording_and_clears_hook_windows(tmp_path):
    clips, shots = _seed(tmp_path)

    _clean_transcription_artifacts(tmp_path, Console())

    _assert_derived_gone(tmp_path, clips)
    _assert_sources_kept(tmp_path, shots)

    base, mirror = json.loads((tmp_path / "videos.json").read_text())
    # Wording survives — it is hand-approved and nothing downstream regenerates it.
    assert (base["title"], base["caption"], base["filename"]) == ("Real Title", "cap", "real-title")
    assert base["subtitle"] == "Sub" and base["scrim"] is True
    assert (mirror["title"], mirror["of"]) == ("Mirror", "hook1")
    # The window does not — it is output-timeline, and the new EDL moves it.
    assert base["start"] == 0.0 and base["end"] == 0.0
    # audio.json has no tie to the transcript at all.
    assert json.loads((tmp_path / "audio.json").read_text()) == [{"track": "upbeat"}]


def test_fresh_wipes_the_overlay_files(tmp_path):
    clips, shots = _seed(tmp_path)

    _clean_transcription_artifacts(tmp_path, Console(), fresh=True)

    _assert_derived_gone(tmp_path, clips)
    _assert_sources_kept(tmp_path, shots)
    assert not (tmp_path / "videos.json").exists()
    assert not (tmp_path / "audio.json").exists()


def test_clean_is_safe_when_overlays_absent(tmp_path):
    # First-ever run: no overlay files yet. Must not raise in either mode.
    _touch(tmp_path / "Teleprompter.captions.json")
    _clean_transcription_artifacts(tmp_path, Console())
    _clean_transcription_artifacts(tmp_path, Console(), fresh=True)
    assert not (tmp_path / "Teleprompter.captions.json").exists()


def test_voiding_is_idempotent(tmp_path):
    # Re-running transcribe twice must not corrupt an already-voided videos.json.
    _touch(tmp_path / "videos.json", _VIDEOS)
    _clean_transcription_artifacts(tmp_path, Console())
    _clean_transcription_artifacts(tmp_path, Console())

    base, _ = json.loads((tmp_path / "videos.json").read_text())
    assert base["title"] == "Real Title"
    assert base["start"] == 0.0 and base["end"] == 0.0


def test_render_refuses_a_hook_whose_window_was_cleared():
    """The backstop: a kept card with no window must fail, not render zero-length."""
    import pytest
    import typer

    from reelcut.cli import _hook_windows
    from reelcut.video_spec import VideoSpec

    ok = [VideoSpec(id="hook1", title="A", start=0.0, end=3.1),
          VideoSpec(id="hook2", title="B", start=3.1, end=6.4)]
    assert _hook_windows(ok) == [(0.0, 3.1), (3.1, 6.4)]

    voided = ok[:1] + [VideoSpec(id="hook2", title="B", start=0.0, end=0.0)]
    with pytest.raises(typer.Exit):
        _hook_windows(voided)
