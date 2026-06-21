"""Tests for the images.json loader/saver — schema loading and round-trip."""
import json

from reelcut.image_spec import ImageSpec, load_images, save_images


class TestLoadImages:
    def test_parses_fields_and_defaults(self, tmp_path):
        p = tmp_path / "images.json"
        p.write_text(json.dumps([
            {"type": "screenshot", "start": 12.935, "end": 16.402,
             "source_clip": "assets/slug/clip.MP4", "path": "/abs/snippet-01.png"},
            {"type": "person", "start": 4, "end": 7, "name": "Reed Hastings"},
        ]))
        imgs = load_images(p)
        assert [i.type for i in imgs] == ["screenshot", "person"]
        assert imgs[0].source_clip == "assets/slug/clip.MP4"
        assert imgs[0].name == "" and imgs[1].path == ""        # defaults
        assert imgs[1].start == 4.0 and imgs[1].end == 7.0      # coerced to float

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_images(tmp_path / "nope.json") == []

    def test_rejects_non_list(self, tmp_path):
        p = tmp_path / "images.json"
        p.write_text(json.dumps({"type": "person"}))
        try:
            load_images(p)
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestRoundTrip:
    def test_save_then_load(self, tmp_path):
        p = tmp_path / "images.json"
        specs = [
            ImageSpec(type="screenshot", start=1.0, end=4.0,
                      source_clip="clip.MP4", path="/abs/a.png"),
            ImageSpec(type="person", start=5.0, end=8.0, name="Sam Altman"),
        ]
        save_images(specs, p)
        assert load_images(p) == specs
