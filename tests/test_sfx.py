"""Tests for sound-effect planning — peak alignment, rate limiting, card beats, and leveling."""
from pathlib import Path

import numpy as np
import soundfile as sf

from reelcut import sfx
from reelcut.config import SfxConfig, SfxEvent
from reelcut.image_finder import ImageCue
from reelcut.renderer import _level_audio_tracks
from reelcut.sfx import plan_sfx, sfx_events


def _cfg(**events) -> SfxConfig:
    return SfxConfig(min_gap_s=0.8, events={k: SfxEvent(sounds=v) for k, v in events.items()})


def test_effect_peak_lands_on_the_event_frame(tmp_path):
    # A whoosh-like file whose loudest sample is 0.3s in must start 0.3s before its event,
    # and one at the very start of the video is trimmed rather than shifted late.
    x = np.zeros(48000, np.float32)
    x[int(0.3 * 48000)] = 0.5
    sf.write(tmp_path / "whoosh.wav", x, 48000)
    lib = {"whoosh": tmp_path / "whoosh.wav"}

    tracks = plan_sfx([("video", 5.0, 0), ("video", 0.1, 0)], _cfg(video=["whoosh"]), lib, 30.0, [])

    early, late = tracks
    assert early["start"] == 0.0 and abs(early["source_start"] - 0.2) < 1e-3
    assert abs(late["start"] - 4.7) < 1e-3 and late["source_start"] == 0.0


def test_burst_of_overlays_gets_one_sound_from_the_first_listed_event(monkeypatch):
    monkeypatch.setattr(sfx, "analyze", lambda p: (0.0, -6.0, 0.3))
    lib = {"thud": Path("thud.wav"), "click": Path("click.wav")}
    events = [("screenshot", 0.0, 0), ("heading", 0.0, 0), ("screenshot", 0.5, 0), ("screenshot", 1.0, 0)]

    tracks = plan_sfx(events, _cfg(heading=["thud"], screenshot=["click"]), lib, 30.0, [])

    assert [(Path(t["path"]).stem, t["start"]) for t in tracks] == [("thud", 0.0), ("click", 1.0)]


def test_animated_card_fires_card_then_nth_beat_plays_nth_sound(monkeypatch):
    monkeypatch.setattr(sfx, "analyze", lambda p: (0.0, -6.0, 0.3))
    lib = {n: Path(f"{n}.wav") for n in ("pop", "tick-1", "tick-2")}
    card = ImageCue(keyword="c", start=2.0, end=6.0, image_path="c.webm", type="video", kind="card",
                    beats=[3.0, 4.0, 5.0, 7.0])  # the last beat falls after the card is cut off

    tracks = plan_sfx(sfx_events([card], []), _cfg(card=["pop"], beat=["tick-1", "tick-2"]), lib, 30.0, [])

    assert [Path(t["path"]).stem for t in tracks] == ["pop", "tick-1", "tick-2", "tick-2"]


def test_effect_peak_is_leveled_relative_to_voice_loudness(monkeypatch):
    monkeypatch.setattr("reelcut.renderer._measure_lufs", lambda p: -16.0)
    track = {"path": "click.wav", "gain_db": -2.0, "peak_db": -1.0, "level_db": 6.0}

    _level_audio_tracks(Path("voice.mkv"), [track], ducking_lufs=14)

    assert track["_gain_db"] == -2.0 + (-16.0 + 6.0) - (-1.0)


def test_placed_sound_plays_its_own_name_and_gain_and_wins_a_tie(monkeypatch):
    monkeypatch.setattr(sfx, "analyze", lambda p: (0.0, -6.0, 0.3))
    lib = {"thud": Path("thud.wav"), "impact-3": Path("impact-3.mp3")}

    tracks = plan_sfx([("heading", 0.0, 0)], _cfg(heading=["thud"]), lib, 30.0, [],
                      placed=[("impact-3", 0.0, -4.0), ("impact-3", 40.0, 0.0)])

    assert [(Path(t["path"]).stem, t["gain_db"]) for t in tracks] == [("impact-3", -4.0)]


def test_library_includes_sounds_in_subfolders(tmp_path):
    (tmp_path / "_candidates").mkdir()
    for f in ("pop.wav", "_candidates/swipe-2-123.mp3", "SOURCES.md"):
        (tmp_path / f).touch()

    assert set(sfx.sfx_library(tmp_path)) == {"pop", "swipe-2-123"}
