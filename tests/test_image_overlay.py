"""Tests for image-overlay placement — the band each overlay sits in (top inset, under
the title while it's up, lower, or a full-screen card) and which single overlay shows when
several overlap (the newest; a video hides stills; a logo never hides a non-logo)."""
from PIL import Image

from reelcut.caption import render_caption_frames
from reelcut.config import CaptionsConfig, ImagesConfig
from reelcut.image_finder import ImageCue
from reelcut.image_overlay import (
    _shown,
    caption_lifts,
    place_cues,
    render_image_frames,
)
from reelcut.transcriber import WordTimestamp

RES = (200, 400)


def _cue(keyword, start, end, type, image_path=None, layout=""):
    return ImageCue(
        keyword=keyword, start=start, end=end,
        image_path=image_path or f"{keyword}.png", type=type, layout=layout,
    )


def _solid(tmp_path, name, color, size=(40, 40)):
    p = tmp_path / f"{name}.png"
    Image.new("RGBA", size, color).save(p)
    return str(p)


def _colors(path):
    img = Image.open(path).convert("RGBA")
    return {c[:3] for _, c in img.getcolors(img.width * img.height) if c[3] == 255}


class TestPlaceCues:
    def test_inset_sits_at_the_top_of_the_top_band(self, tmp_path):
        p, = place_cues([_cue("a", 0, 2, "person", _solid(tmp_path, "a", "red"))], ImagesConfig(), RES)
        assert p.band == "top"
        assert p.y == int(400 * 0.08)
        assert p.x == (200 - p.w) // 2

    def test_inset_moves_under_the_title_while_it_is_up(self, tmp_path):
        p, = place_cues([_cue("a", 1, 3, "person", _solid(tmp_path, "a", "red"))],
                        ImagesConfig(), RES, title_windows=[(0.0, 2.0)])
        assert (p.band, p.y) == ("under_title", int(400 * 0.26))

    def test_lower_layout_hugs_the_bottom_of_the_lower_band(self, tmp_path):
        p, = place_cues([_cue("a", 0, 2, "person", _solid(tmp_path, "a", "red"), layout="lower")],
                        ImagesConfig(), RES)
        assert (p.band, p.y + p.h) == ("lower", int(400 * 0.80))

    def test_screenshots_and_figures_are_inset_by_default(self, tmp_path):
        img = _solid(tmp_path, "a", "red")
        places = place_cues([_cue("a", 0, 2, "screenshot", img), _cue("b", 0, 2, "figure", img)],
                            ImagesConfig(), RES)
        assert [p.band for p in places] == ["top", "top"]

    def test_full_layout_covers_the_frame_for_cards_only(self, tmp_path):
        img = _solid(tmp_path, "a", "red")
        card, shot = place_cues([_cue("a", 0, 2, "card", img, layout="full"),
                                 _cue("b", 0, 2, "screenshot", img, layout="full")],
                                ImagesConfig(), RES)
        assert (card.x, card.y, card.w, card.h, card.band) == (0, 0, 200, 400, "full")
        assert shot.band == "top"

    def test_animated_card_can_go_full(self, tmp_path):
        cue = ImageCue(keyword="a", start=0, end=2, image_path=_solid(tmp_path, "a", "red"),
                       type="video", kind="card", layout="full")
        assert place_cues([cue], ImagesConfig(), RES)[0].band == "full"

    def test_tall_inset_shrinks_to_fit_its_band(self, tmp_path):
        tall = _solid(tmp_path, "tall", "red", size=(40, 400))
        p, = place_cues([_cue("a", 0, 2, "person", tall)], ImagesConfig(), RES)
        assert p.h <= int(400 * 0.30) - int(400 * 0.08)


class TestShown:
    def test_newest_overlay_wins(self):
        cues = [_cue("a", 0, 4, "screenshot"), _cue("b", 1, 2, "concept")]
        assert [_shown(cues, t) for t in (0.5, 1.5, 3.0)] == [0, 1, 0]

    def test_logo_never_hides_a_non_logo(self):
        cues = [_cue("shot", 0, 4, "screenshot"), _cue("logo", 1, 2, "logo")]
        assert _shown(cues, 1.5) == 0

    def test_newer_logo_replaces_older_logo(self):
        cues = [_cue("a", 0, 2, "logo"), _cue("b", 1, 3, "logo")]
        assert _shown(cues, 1.5) == 1

    def test_video_hides_stills(self):
        cues = [_cue("clip", 0, 4, "video"), _cue("p", 1, 2, "person")]
        assert _shown(cues, 1.5) == 0

    def test_nothing_active(self):
        assert _shown([_cue("a", 0, 1, "logo")], 2.0) is None


class TestRenderImageFrames:
    def test_only_the_newest_overlapping_overlay_is_drawn(self, tmp_path):
        red, blue = _solid(tmp_path, "red", (255, 0, 0, 255)), _solid(tmp_path, "blue", (0, 0, 255, 255))
        cues = [_cue("red", 0.0, 2.0, "person", red), _cue("blue", 0.5, 2.5, "person", blue)]
        cfg = ImagesConfig(enabled=True, fade_duration_s=0.0, start_delay_s=0)
        frames = {f.frame_number: f.image_path for f in
                  render_image_frames(cues, cfg, tmp_path / "out", fps=30, resolution=RES)}
        assert _colors(frames[30]) == {(0, 0, 255)}
        assert _colors(frames[5]) == {(255, 0, 0)}

    def test_full_card_fills_the_frame(self, tmp_path):
        red = _solid(tmp_path, "red", (255, 0, 0, 255), size=(100, 200))
        cfg = ImagesConfig(enabled=True, fade_duration_s=0.0, start_delay_s=0)
        frames = render_image_frames([_cue("a", 0.0, 1.0, "card", red, layout="full")], cfg,
                                     tmp_path / "out", fps=10, resolution=RES)
        img = Image.open(frames[0].image_path)
        assert img.getpixel((0, 0)) == img.getpixel((199, 399)) == (255, 0, 0, 255)


class TestCaptionLifts:
    def test_lower_band_overlay_lifts_captions_above_it(self, tmp_path):
        img = _solid(tmp_path, "a", "red")
        cues = [_cue("a", 1.0, 2.0, "person", img, layout="lower"), _cue("b", 3.0, 4.0, "person", img)]
        places = place_cues(cues, ImagesConfig(), RES)
        lifts = caption_lifts(cues, places, RES)
        assert lifts == [(1.0, 2.0, places[0].y - int(400 * 0.015))]

    def test_lifted_caption_ends_above_the_line(self, tmp_path):
        words = [WordTimestamp(word="hello", start=0.0, end=1.0, confidence=1.0)]
        cfg = CaptionsConfig(size=20, shadow=False)
        frames = render_caption_frames(words, cfg, tmp_path, fps=10, resolution=RES,
                                       lifts=[(0.0, 1.0, 150)])
        bbox = Image.open(frames[0].image_path).getchannel("A").getbbox()
        assert bbox[3] <= 150 + cfg.stroke_width


class TestClampToHook:
    def test_hook_overlay_ends_with_hook(self):
        from reelcut.image_overlay import clamp_to_hook
        out = clamp_to_hook([_cue("a", 1.0, 5.0, "screenshot")], hook_end=3.0)
        assert [(c.start, c.end) for c in out] == [(1.0, 3.0)]

    def test_body_overlay_untouched(self):
        from reelcut.image_overlay import clamp_to_hook
        out = clamp_to_hook([_cue("a", 3.0, 6.0, "screenshot")], hook_end=3.0)
        assert [(c.start, c.end) for c in out] == [(3.0, 6.0)]

    def test_sliver_left_by_clamp_is_dropped(self):
        from reelcut.image_overlay import clamp_to_hook
        assert clamp_to_hook([_cue("a", 2.98, 4.0, "logo")], hook_end=3.0) == []


class TestCoverageGaps:
    def test_reports_gaps_at_or_over_threshold(self):
        from reelcut.image_overlay import coverage_gaps
        cues = [_cue("a", 0.5, 2.0, "logo"), _cue("b", 2.5, 4.0, "screenshot")]
        assert coverage_gaps(cues, total_s=6.0, min_gap_s=1.0) == [(4.0, 6.0)]

    def test_overlapping_cues_merge(self):
        from reelcut.image_overlay import coverage_gaps
        cues = [_cue("a", 0.0, 5.0, "figure"), _cue("b", 1.0, 2.0, "logo")]
        assert coverage_gaps(cues, total_s=5.0, min_gap_s=0.0) == []

    def test_no_cues_is_one_gap(self):
        from reelcut.image_overlay import coverage_gaps
        assert coverage_gaps([], total_s=3.0) == [(0.0, 3.0)]
