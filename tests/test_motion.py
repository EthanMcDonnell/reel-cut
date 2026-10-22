"""Tests for motion — how layers resolve, and that every animated layer settles to exactly the
frame it would draw standing still (so motion never changes what a held frame shows)."""
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from reelcut.caption import render_caption_frames
from reelcut.config import CaptionsConfig, HeadingsConfig, ImagesConfig
from reelcut.heading import HeadingSpec, render_heading_frames
from reelcut.image_finder import ImageCue
from reelcut.image_overlay import render_image_frames
from reelcut.image_spec import ImageSpec, load_images, save_images
from reelcut.motion import resolve
from reelcut.transcriber import WordTimestamp

RES = (200, 400)
NO_FADE = ImagesConfig(enabled=True, fade_duration_s=0.0, start_delay_s=0)


def _solid(tmp_path, name, color, size=(40, 40)):
    p = tmp_path / f"{name}.png"
    Image.new("RGBA", size, color).save(p)
    return str(p)


def _cue(path, start, end, motion=None):
    return ImageCue(keyword=Path(path).stem, start=start, end=end, image_path=path,
                    type="person", motion=motion or {})


def _frames(cues, tmp_path, motion, name="out"):
    return {f.frame_number: f.image_path for f in
            render_image_frames(cues, NO_FADE, tmp_path / name, fps=30, resolution=RES, motion=motion)}


def _colors(path):
    img = Image.open(path).convert("RGBA")
    return {c[:3] for _, c in img.getcolors(img.width * img.height) if c[3] == 255}


def _shows(path, rgb):
    """Whether any visible pixel is `rgb`, at any opacity."""
    img = Image.open(path).convert("RGBA")
    return any(c[:3] == rgb and c[3] > 0 for _, c in img.getcolors(img.width * img.height))


def _same(a, b):
    return ImageChops.difference(Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")).getbbox() is None


class TestResolve:
    def test_a_later_look_resets_fields_an_earlier_layer_set(self):
        m = resolve({"look": "editorial", "hold": "still"}, {"look": "calm", "enter": "pop"})
        # calm's own hold (push) replaces editorial's override; the calm layer's enter wins.
        assert (m.hold, m.enter, m.transition) == ("push", "pop", "dissolve")

    def test_palette_is_the_last_look_applied(self):
        from reelcut.motion import off_palette
        m = resolve({"look": "editorial"}, {"look": "calm"})
        assert off_palette(m.look, {"enter": "rise", "exit": "fade"}) == []
        assert off_palette(m.look, {"enter": "stamp"}) == ["enter 'stamp'"]

    def test_unknown_name_is_refused(self):
        with pytest.raises(ValueError, match="swoosh"):
            resolve({"enter": "swoosh"})


class TestOverlayMotion:
    def test_settled_overlay_draws_exactly_as_a_still_one(self, tmp_path):
        red = _solid(tmp_path, "red", (255, 0, 0, 255))
        moving = _frames([_cue(red, 0.0, 2.0)], tmp_path, resolve({"enter": "swing", "exit": "snap"}), "m")
        still = _frames([_cue(red, 0.0, 2.0)], tmp_path, resolve({"enter": "snap", "exit": "snap"}), "s")
        assert not _same(moving[2], still[2])   # mid-swing
        assert _same(moving[45], still[45])     # settled

    def test_entrance_glides_into_its_resting_tilt(self, tmp_path):
        # A swing hinged at the top used to hand its tilt back to the centre when it ended,
        # jumping the overlay sideways on the frame the entrance finished.
        import numpy as np
        red = _solid(tmp_path, "red", (255, 0, 0, 255), size=(40, 60))
        m = resolve({"enter": "swing", "tilt": 4, "hold": "still", "exit": "snap"})
        frames = _frames([_cue(red, 0.0, 2.0)], tmp_path, m)
        xs = []
        for f in sorted(frames)[:30]:
            a = np.asarray(Image.open(frames[f]).getchannel("A"), dtype=float)
            xs.append((a.sum(axis=0) * np.arange(a.shape[1])).sum() / a.sum())
        steps = np.abs(np.diff(xs))
        slowed = int(np.argmax(steps < 0.5))
        assert steps[slowed:].max() < 0.5

    def test_stack_keeps_the_outgoing_overlay_under_the_incoming_one(self, tmp_path):
        red = _solid(tmp_path, "red", (255, 0, 0, 255))
        blue = _solid(tmp_path, "blue", (0, 0, 255, 255))
        m = resolve({"enter": "rise", "transition": "stack", "exit": "snap"})
        frames = _frames([_cue(red, 0.0, 1.0), _cue(blue, 1.0, 2.0)], tmp_path, m)
        assert _shows(frames[33], (255, 0, 0)) and _shows(frames[33], (0, 0, 255))
        assert _colors(frames[55]) == {(0, 0, 255)}

    def test_an_overlay_leaving_reveals_the_older_one_beneath(self, tmp_path):
        red = _solid(tmp_path, "red", (255, 0, 0, 255))
        blue = _solid(tmp_path, "blue", (0, 0, 255, 255))
        m = resolve({"enter": "snap", "exit": "sink"})
        frames = _frames([_cue(red, 0.0, 3.0), _cue(blue, 1.0, 2.0)], tmp_path, m)
        assert _colors(frames[58]) >= {(255, 0, 0)}  # blue's exit, red already back under it

    def test_per_entry_override_beats_the_video_motion(self, tmp_path):
        red = _solid(tmp_path, "red", (255, 0, 0, 255))
        snap = resolve({"enter": "snap", "exit": "snap"})
        plain = _frames([_cue(red, 0.0, 2.0)], tmp_path, snap, "a")
        popped = _frames([_cue(red, 0.0, 2.0, {"enter": "pop"})], tmp_path, snap, "b")
        assert not _same(plain[2], popped[2])


class TestCaptionMotion:
    WORDS = [WordTimestamp(word=w, start=i * 1.0, end=i * 1.0 + 0.9, confidence=1.0)
             for i, w in enumerate(["alpha", "beta", "gamma"])]

    def _render(self, tmp_path, motion):
        cfg = CaptionsConfig(size=20, shadow=False)
        return {f.frame_number: f.image_path for f in render_caption_frames(
            self.WORDS, cfg, tmp_path / motion, fps=30, resolution=RES, motion=motion)}

    def test_words_shows_only_what_has_been_said(self, tmp_path):
        words, plain = self._render(tmp_path, "words"), self._render(tmp_path, "none")
        def width(p):
            box = Image.open(p).getchannel("A").getbbox()
            return box[2] - box[0]
        assert width(words[15]) < width(plain[15])  # "beta" and "gamma" not yet said
        assert _same(words[80], plain[80])          # all said and settled

    def test_popped_line_settles_to_the_still_line(self, tmp_path):
        pop, plain = self._render(tmp_path, "pop"), self._render(tmp_path, "none")
        assert not _same(pop[1], plain[1])
        assert _same(pop[50], plain[50])


class TestHeadingMotion:
    def _render(self, tmp_path, start, motion):
        heads = [HeadingSpec(title="Hello There", start=start, end=start + 2.0)]
        return {f.frame_number: f.image_path for f in render_heading_frames(
            heads, HeadingsConfig(), tmp_path / f"{motion}{start}", fps=30, resolution=(216, 384),
            total_output_s=10.0, motion=motion)}

    def test_title_enters_then_matches_the_still_card(self, tmp_path):
        from reelcut.heading import settled_s
        moving, still = self._render(tmp_path, 0.0, "slot"), self._render(tmp_path, 0.0, "none")
        assert Image.open(moving[0]).getchannel("A").getbbox() is None
        f = int(settled_s("snappy") * 30)
        from PIL import ImageStat
        ink = lambda p: ImageStat.Stat(Image.open(p).getchannel("A")).sum[0]
        assert abs(ink(moving[f]) / ink(still[f]) - 1) < 0.05  # all there; only pushed in a little

    @pytest.mark.parametrize("entrance", ["ink", "stamp", "split"])
    def test_every_entrance_lands_on_the_still_card(self, tmp_path, entrance):
        from PIL import ImageStat
        from reelcut.heading import settled_s
        moving, still = self._render(tmp_path, 0.0, entrance), self._render(tmp_path, 0.0, "none")
        f = int(settled_s("snappy") * 30)
        ink = lambda p: ImageStat.Stat(Image.open(p).getchannel("A")).sum[0]
        assert abs(ink(moving[f]) / ink(still[f]) - 1) < 0.05

    def test_later_card_enters(self, tmp_path):
        moving = self._render(tmp_path, 1.0, "slot")
        assert Image.open(moving[30]).getchannel("A").getbbox() is None
        assert Image.open(moving[45]).getchannel("A").getbbox() is not None


def test_motion_override_survives_the_per_hook_images_round_trip(tmp_path):
    # render-hooks rewrites images.json per hook; a dropped override would silently revert.
    path = tmp_path / "images.json"
    save_images([ImageSpec(type="person", start=0, end=1, name="A", motion={"enter": "pop"})], path)
    assert load_images(path)[0].motion == {"enter": "pop"}


class TestCameraZoom:
    ZOOM = {"scale": 1.2, "in": 0.5, "hold": [1.0, 1.0], "out": 0.5, "every": [1.0, 1.0],
            "eyes": [0.5, 0.3]}

    def test_zoom_keeps_the_eyes_in_place(self, tmp_path):
        # A dot at the anchor stays put while a dot elsewhere is pushed outward.
        import subprocess
        from reelcut.motion import zoom_corners
        frame = Image.new("RGB", (200, 400), "white")
        for x, y in ((100, 120), (40, 300)):  # the eyes; somewhere else
            frame.paste((0, 0, 0), (x - 3, y - 3, x + 3, y + 3))
        frame.save(tmp_path / "f.png")
        opts = zoom_corners([(0.0, 0.5, 1.5, 2.0, 1.2)], self.ZOOM, fps=10)
        vf = "perspective=" + ":".join(f"{k}='{v}'" for k, v in opts.items() if k != "enable")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "10", "-i",
                        str(tmp_path / "f.png"), "-vf", vf, "-frames:v", "10", str(tmp_path / "o%02d.png")],
                       check=True)
        held = Image.open(tmp_path / "o10.png").convert("L")  # 0.9s in: fully zoomed
        dark = lambda box: held.crop(box).getextrema()[0]
        assert dark((97, 117, 103, 123)) < 60      # the eyes have not moved
        assert dark((37, 297, 43, 303)) > 200      # the other dot has

    def test_placed_zoom_in_a_cut_is_dropped(self):
        from reelcut.cli import _camera_zooms
        from reelcut.edl import EDLEntry
        edl = [EDLEntry(start=0, end=10, keep=True, source_clip="c", reason=""),
               EDLEntry(start=10, end=20, keep=False, source_clip="c", reason=""),
               EDLEntry(start=20, end=30, keep=True, source_clip="c", reason="")]
        video = {"zooms": [{"start": 2, "end": 6, "source_clip": "c"},
                           {"start": 12, "end": 16, "source_clip": "c"},
                           {"start": 22, "end": 26, "source_clip": "c"}]}
        zooms = _camera_zooms(resolve({"zoom": self.ZOOM}), video, edl, [], 20.0, "x")
        assert [(round(a, 2), round(d, 2)) for a, _, _, d, _ in zooms] == [(2, 6), (12, 16)]

    def test_overlapping_placed_zooms_never_stack(self):
        from reelcut.motion import placed_zooms
        zooms = placed_zooms(self.ZOOM, [(0.0, 4.0, None), (3.0, 7.0, None)])
        assert zooms[1][0] >= zooms[0][3]
