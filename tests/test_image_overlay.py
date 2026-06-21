"""Tests for image-overlay slot assignment — overlapping images are displaced
from the center to top corners by priority (text > wikipedia > logo)."""
from PIL import Image

from reelcut.config import ImagesConfig
from reelcut.image_finder import ImageCue
from reelcut.image_overlay import _assign_slots, render_image_frames


def _cue(keyword, start, end, type, image_path=None):
    return ImageCue(
        keyword=keyword, start=start, end=end,
        image_path=image_path or f"{keyword}.png", type=type,
    )


class TestAssignSlots:
    def test_non_overlapping_all_center(self):
        cues = [_cue("a", 0.0, 2.0, "logo"), _cue("b", 3.0, 5.0, "logo")]
        assert _assign_slots(cues) == ["center", "center"]

    def test_priority_keeps_highest_in_center(self):
        # All three overlap: screenshot wins center, person→top_left, logo→top_right.
        cues = [
            _cue("logo", 0.0, 2.0, "logo"),
            _cue("person", 0.5, 2.5, "person"),
            _cue("shot", 0.2, 2.2, "screenshot"),
        ]
        slots = dict(zip([c.type for c in cues], _assign_slots(cues)))
        assert slots == {"logo": "top_right", "person": "top_left", "screenshot": "center"}

    def test_lower_priority_bumped_to_top_left(self):
        cues = [_cue("logo", 0.0, 2.0, "logo"), _cue("person", 0.5, 1.5, "person")]
        slots = dict(zip([c.type for c in cues], _assign_slots(cues)))
        assert slots == {"person": "center", "logo": "top_left"}

    def test_freed_slot_is_reused(self):
        # logo2 starts after the overlapping pair ends → center is free again.
        cues = [
            _cue("logo1", 0.0, 2.0, "logo"),
            _cue("person", 0.5, 1.5, "person"),
            _cue("logo2", 5.0, 6.0, "logo"),
        ]
        slots = dict(zip([c.keyword for c in cues], _assign_slots(cues)))
        assert slots == {"person": "center", "logo1": "top_left", "logo2": "center"}


class TestRenderConcurrent:
    def _solid(self, tmp_path, name, color):
        p = tmp_path / f"{name}.png"
        Image.new("RGBA", (40, 40), color).save(p)
        return str(p)

    def test_overlapping_cues_appear_in_same_frame(self, tmp_path):
        # Two screenshots overlapping in time: one keeps center, the other is
        # bumped to a top corner. A frame inside the overlap must show BOTH
        # (regression: previously the per-frame dict collision dropped one).
        red = self._solid(tmp_path, "red", (255, 0, 0, 255))
        blue = self._solid(tmp_path, "blue", (0, 0, 255, 255))
        cues = [
            _cue("red", 0.0, 2.0, "screenshot", image_path=red),
            _cue("blue", 0.5, 2.5, "screenshot", image_path=blue),
        ]
        cfg = ImagesConfig(enabled=True, fade_duration_s=0.0, position="center")
        frames = render_image_frames(
            cues, cfg, tmp_path / "out", fps=30, resolution=(200, 400),
        )

        # Frame 30 (t=1.0s) is inside both windows.
        overlap = next(f for f in frames if f.frame_number == 30)
        img = Image.open(overlap.image_path).convert("RGBA")
        colors = {c[:3] for _, c in img.getcolors(img.width * img.height) if c[3] > 0}
        assert (255, 0, 0) in colors
        assert (0, 0, 255) in colors
