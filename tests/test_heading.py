"""Tests for the heading renderer — schema loading and output-timeline frame emission."""
import json

from PIL import Image

from reelcut.config import HeadingsConfig
from reelcut.heading import HeadingSpec, load_headings, render_heading_frames


class TestLoadHeadings:
    def test_parses_fields_and_defaults(self, tmp_path):
        p = tmp_path / "headings.json"
        p.write_text(json.dumps([
            {"title": "What Are\nAI Tokens?", "subtitle": "explained in 90s", "start": 0.0, "end": 3.0, "scrim": False},
            {"title": "Just a title", "start": 5, "end": 7},
        ]))
        heads = load_headings(p)
        assert [h.title for h in heads] == ["What Are\nAI Tokens?", "Just a title"]
        assert heads[0].subtitle == "explained in 90s"
        assert heads[0].scrim is False
        assert heads[1].subtitle == "" and heads[1].scrim is None  # defaults
        assert heads[1].start == 5.0 and heads[1].end == 7.0       # coerced to float

    def test_rejects_non_list(self, tmp_path):
        p = tmp_path / "headings.json"
        p.write_text(json.dumps({"title": "nope"}))
        try:
            load_headings(p)
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestRenderHeadingFrames:
    def test_emits_one_frame_per_output_frame_in_window(self, tmp_path):
        cfg = HeadingsConfig()
        heads = [HeadingSpec(title="Hello", start=1.0, end=2.0)]
        frames = render_heading_frames(heads, cfg, tmp_path, fps=30, resolution=(108, 192))
        # window [1.0, 2.0) at 30fps → frames 30..59
        assert [f.frame_number for f in frames] == list(range(30, 60))
        # one static PNG reused for every frame
        assert len({f.image_path for f in frames}) == 1
        png = frames[0].image_path
        assert Image.open(png).size == (108, 192)

    def test_skips_empty_or_zero_length(self, tmp_path):
        cfg = HeadingsConfig()
        heads = [
            HeadingSpec(title="", start=0.0, end=2.0),       # no text
            HeadingSpec(title="x", start=2.0, end=2.0),      # zero-length
        ]
        assert render_heading_frames(heads, cfg, tmp_path, fps=30, resolution=(108, 192)) == []

    def test_scrim_override_changes_output(self, tmp_path):
        cfg = HeadingsConfig(scrim=True)
        on = render_heading_frames([HeadingSpec(title="Hi", start=0, end=1, scrim=True)], cfg, tmp_path / "on", 30, (108, 192))
        off = render_heading_frames([HeadingSpec(title="Hi", start=0, end=1, scrim=False)], cfg, tmp_path / "off", 30, (108, 192))
        # the scrim adds dark pixels near the top — the two renders must differ
        a = Image.open(on[0].image_path).convert("RGBA")
        b = Image.open(off[0].image_path).convert("RGBA")
        assert a.tobytes() != b.tobytes()

    def test_long_title_stays_within_side_margins(self, tmp_path):
        # A title too wide for one line must wrap/shrink to fit the configured margins.
        res = (1080, 1920)
        cfg = HeadingsConfig(margin_pct=8.0, shadow=False)
        frames = render_heading_frames(
            [HeadingSpec(title="Can a prime number be illegal?", start=0, end=1, scrim=False)],
            cfg, tmp_path, 30, res,
        )
        # scrim + shadow off → the only painted pixels are the title glyphs themselves.
        alpha = Image.open(frames[0].image_path).convert("RGBA").split()[3]
        margin_px = int(res[0] * cfg.margin_pct / 100)
        bbox = alpha.getbbox()
        assert bbox is not None
        assert bbox[0] >= margin_px - 2, f"text overflows left edge: {bbox}"
        assert bbox[2] <= res[0] - margin_px + 2, f"text overflows right edge: {bbox}"
