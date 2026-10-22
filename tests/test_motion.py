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

    def test_card_on_the_first_frame_is_already_up(self, tmp_path):
        # Frame 0 is the reel's cover, so it must carry the finished title.
        moving, still = self._render(tmp_path, 0.0, "slot"), self._render(tmp_path, 0.0, "none")
        diff = ImageChops.difference(Image.open(moving[0]), Image.open(still[0])).convert("L")
        assert diff.getextrema()[1] < 40

    def test_later_card_enters(self, tmp_path):
        moving = self._render(tmp_path, 1.0, "slot")
        assert Image.open(moving[30]).getchannel("A").getbbox() is None
        assert Image.open(moving[45]).getchannel("A").getbbox() is not None


def test_motion_override_survives_the_per_hook_images_round_trip(tmp_path):
    # render-hooks rewrites images.json per hook; a dropped override would silently revert.
    path = tmp_path / "images.json"
    save_images([ImageSpec(type="person", start=0, end=1, name="A", motion={"enter": "pop"})], path)
    assert load_images(path)[0].motion == {"enter": "pop"}
