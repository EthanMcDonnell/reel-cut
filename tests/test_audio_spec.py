"""Tests for the audio.json loader/saver — schema loading and round-trip."""
import json

from reelcut.audio_spec import AudioSpec, load_audio, save_audio


class TestLoadAudio:
    def test_parses_fields_and_defaults(self, tmp_path):
        p = tmp_path / "audio.json"
        p.write_text(json.dumps([
            {"path": "/abs/music.mp3", "start": 2, "end": 30, "gain_db": -3},
            {"path": "/abs/sfx.wav"},
        ]))
        tracks = load_audio(p)
        assert [t.path for t in tracks] == ["/abs/music.mp3", "/abs/sfx.wav"]
        assert tracks[0].start == 2.0 and tracks[0].end == 30.0   # coerced to float
        assert tracks[0].gain_db == -3.0
        assert tracks[1].start == 0.0 and tracks[1].end == -1.0   # defaults: full length
        assert tracks[1].gain_db == 0.0

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_audio(tmp_path / "nope.json") == []

    def test_rejects_non_list(self, tmp_path):
        p = tmp_path / "audio.json"
        p.write_text(json.dumps({"path": "/abs/music.mp3"}))
        try:
            load_audio(p)
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestRoundTrip:
    def test_save_then_load(self, tmp_path):
        p = tmp_path / "audio.json"
        tracks = [
            AudioSpec(path="/abs/music.mp3", start=0.0, end=-1.0, gain_db=-3.0),
            AudioSpec(path="/abs/sfx.wav", start=5.0, end=8.0),
        ]
        save_audio(tracks, p)
        assert load_audio(p) == tracks
