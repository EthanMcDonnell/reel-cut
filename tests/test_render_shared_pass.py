"""`render()` writes N outputs from ONE extraction pass.

Segment extraction is ~80% of a render's wall clock, and it depends only on the EDL — which
is identical for a hook and its flipped duplicate. Rendering the duplicate as a second full
render doubled the time for nothing; these tests pin the shared pass so that can't regress.
"""
import pytest

from reelcut import renderer
from reelcut.config import ReelCutConfig
from reelcut.edl import EDLEntry


@pytest.fixture
def spy(monkeypatch, tmp_path):
    """Stub out every ffmpeg-touching step and record what got called."""
    calls = {"extract": 0, "concat": 0, "level": 0, "encode": []}

    def fake_extract(entries, tmpdir, progress, task, n_workers, fps):
        calls["extract"] += 1
        return [tmp_path / "seg_0000.mkv"]

    def fake_concat(paths, output):
        calls["concat"] += 1

    def fake_level(voice_path, audio_tracks, ducking_lufs):
        calls["level"] += 1

    def fake_encode(input_path, output_path, config, caption_seq, audio_tracks, flip):
        calls["encode"].append((output_path.name, flip))
        output_path.write_bytes(b"")

    monkeypatch.setattr(renderer, "_extract_segments", fake_extract)
    monkeypatch.setattr(renderer, "_concatenate", fake_concat)
    monkeypatch.setattr(renderer, "_level_audio_tracks", fake_level)
    monkeypatch.setattr(renderer, "_final_encode", fake_encode)
    return calls


@pytest.fixture
def edl():
    return [EDLEntry(start=0.0, end=3.0, keep=True, source_clip="clip.mov", reason="speech")]


def test_two_outputs_extract_once_and_encode_twice(spy, edl, tmp_path):
    written = renderer.render(edl, [], ReelCutConfig(), outputs=[
        (tmp_path / "hook.mp4", False),
        (tmp_path / "hook-flipped.mp4", True),
    ])
    assert spy["extract"] == 1, "the flipped duplicate must reuse the hook's segments"
    assert spy["concat"] == 1
    assert spy["encode"] == [("hook.mp4", False), ("hook-flipped.mp4", True)]
    assert written == [tmp_path / "hook.mp4", tmp_path / "hook-flipped.mp4"]


def test_single_output_is_unchanged(spy, edl, tmp_path):
    written = renderer.render(edl, [], ReelCutConfig(), outputs=[(tmp_path / "solo.mp4", False)])
    assert spy["extract"] == 1
    assert spy["encode"] == [("solo.mp4", False)]
    assert written == [tmp_path / "solo.mp4"]


def test_audio_is_leveled_once_for_all_outputs(spy, edl, tmp_path):
    # _level_audio_tracks runs two loudnorm analysis passes; the voice is the same concat
    # file for every output, so re-measuring per output is pure waste.
    renderer.render(edl, [], ReelCutConfig(), outputs=[
        (tmp_path / "a.mp4", False),
        (tmp_path / "b.mp4", True),
    ], audio_tracks=[{"path": "music.mp3", "start": 0.0, "end": 3.0}])
    assert spy["level"] == 1


def test_no_audio_tracks_skips_leveling(spy, edl, tmp_path):
    renderer.render(edl, [], ReelCutConfig(), outputs=[(tmp_path / "a.mp4", False)])
    assert spy["level"] == 0


def test_defaults_to_a_single_unflipped_output(spy, edl, tmp_path):
    cfg = ReelCutConfig()
    cfg.output.location = str(tmp_path)
    written = renderer.render(edl, [], cfg)
    assert spy["encode"] == [("output.mp4", False)]
    assert written == [tmp_path / "output.mp4"]


def test_empty_edl_still_raises(spy, tmp_path):
    dropped = [EDLEntry(start=0.0, end=1.0, keep=False, source_clip="c.mov", reason="silence")]
    with pytest.raises(ValueError, match="no keep segments"):
        renderer.render(dropped, [], ReelCutConfig(), outputs=[(tmp_path / "x.mp4", False)])
