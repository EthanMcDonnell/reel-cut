"""Tests for image-overlay slot assignment — overlapping images of different types
are displaced from the center to top corners by priority
(screenshot > person > concept > logo), while two overlapping logos swap in place."""
from PIL import Image

from reelcut.config import ImagesConfig
from reelcut.image_finder import ImageCue
from reelcut.image_overlay import (
    _assign_slots,
    _resolve_logo_swaps,
    render_image_frames,
)


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

    def test_concept_outranks_logo_for_center(self):
        # concept (priority 2) keeps center over logo (priority 3) when overlapping.
        cues = [_cue("logo", 0.0, 2.0, "logo"), _cue("concept", 0.5, 1.5, "concept")]
        slots = dict(zip([c.type for c in cues], _assign_slots(cues)))
        assert slots == {"concept": "center", "logo": "top_left"}

    def test_freed_slot_is_reused(self):
        # logo2 starts after the overlapping pair ends → center is free again.
        cues = [
            _cue("logo1", 0.0, 2.0, "logo"),
            _cue("person", 0.5, 1.5, "person"),
            _cue("logo2", 5.0, 6.0, "logo"),
        ]
        slots = dict(zip([c.keyword for c in cues], _assign_slots(cues)))
        assert slots == {"person": "center", "logo1": "top_left", "logo2": "center"}


class TestResolveLogoSwaps:
    def test_overlapping_logos_swap_in_place(self):
        # Second logo replaces the first: first clamped to the second's start,
        # and the seam is a hard cut (no fade out on a, no fade in on b).
        cues = [_cue("a", 0.0, 2.0, "logo"), _cue("b", 1.0, 3.0, "logo")]
        ends, sin, sout = _resolve_logo_swaps(cues)
        assert ends == [1.0, 3.0]
        assert sin == [False, True]
        assert sout == [True, False]

    def test_non_overlapping_logos_untouched(self):
        cues = [_cue("a", 0.0, 2.0, "logo"), _cue("b", 3.0, 5.0, "logo")]
        ends, sin, sout = _resolve_logo_swaps(cues)
        assert ends == [2.0, 5.0]
        assert sin == [False, False]
        assert sout == [False, False]

    def test_chain_of_three_logos(self):
        cues = [
            _cue("a", 0.0, 2.0, "logo"),
            _cue("b", 1.0, 3.0, "logo"),
            _cue("c", 1.5, 3.5, "logo"),
        ]
        ends, sin, sout = _resolve_logo_swaps(cues)
        assert ends == [1.0, 1.5, 3.5]
        assert sin == [False, True, True]
        assert sout == [True, True, False]

    def test_only_logos_are_swapped(self):
        # A screenshot overlapping a logo is not a logo-vs-logo swap; the logo
        # keeps its full window and is handled by corner displacement instead.
        cues = [_cue("logo", 0.0, 2.0, "logo"), _cue("shot", 1.0, 3.0, "screenshot")]
        ends, sin, sout = _resolve_logo_swaps(cues)
        assert ends == [2.0, 3.0]
        assert sin == [False, False]
        assert sout == [False, False]


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

    def test_second_logo_replaces_first_in_center(self, tmp_path):
        # Two overlapping logos: the second replaces the first in the center
        # rather than displacing it to a corner. At t=1.5s the first (clamped to
        # end at the second's 1.0s start) is gone and only the second shows.
        red = self._solid(tmp_path, "red", (255, 0, 0, 255))
        blue = self._solid(tmp_path, "blue", (0, 0, 255, 255))
        cues = [
            _cue("red", 0.0, 2.0, "logo", image_path=red),
            _cue("blue", 1.0, 3.0, "logo", image_path=blue),
        ]
        cfg = ImagesConfig(enabled=True, fade_duration_s=0.0, position="center")
        frames = render_image_frames(
            cues, cfg, tmp_path / "out", fps=30, resolution=(200, 400),
        )

        f = next(f for f in frames if f.frame_number == 45)
        img = Image.open(f.image_path).convert("RGBA")
        colors = {c[:3] for _, c in img.getcolors(img.width * img.height) if c[3] > 0}
        assert (0, 0, 255) in colors
        assert (255, 0, 0) not in colors

        # The surviving logo sits in the center column, not a top corner.
        xs = [x for x in range(img.width) for y in range(img.height)
              if img.getpixel((x, y))[3] > 0]
        assert abs((min(xs) + max(xs)) / 2 - img.width / 2) < 5
