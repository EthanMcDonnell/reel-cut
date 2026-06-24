"""Tests for the heading renderer — schema loading and output-timeline frame emission."""
import json

from PIL import Image

from reelcut.config import HeadingsConfig
from reelcut.heading import HeadingSpec, _series_number, load_headings, render_heading_frames


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

    def test_back_to_back_headings_each_get_own_window(self, tmp_path):
        # Three sequential cards (e.g. stacked hooks) must each render to their own PNG
        # over their own frame range, with no collisions.
        cfg = HeadingsConfig()
        heads = [
            HeadingSpec(title="Hook One", start=0.0, end=2.0),
            HeadingSpec(title="Hook Two", start=2.0, end=4.0),
            HeadingSpec(title="Hook Three", start=4.0, end=6.0),
        ]
        frames = render_heading_frames(heads, cfg, tmp_path, fps=30, resolution=(108, 192))
        assert len(frames) == 30 * 6                      # full 6s covered, no gaps
        assert len({f.frame_number for f in frames}) == len(frames)  # no duplicate frames
        by_png = {}
        for f in frames:
            by_png.setdefault(f.image_path, []).append(f.frame_number)
        assert len(by_png) == 3                           # one distinct PNG per card
        ranges = sorted((min(v), max(v)) for v in by_png.values())
        assert ranges == [(0, 59), (60, 119), (120, 179)]

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

    def test_placeholder_needs_registry(self, tmp_path):
        # A {n:...} token with no slug/registry is a hard error, not a silent passthrough.
        try:
            render_heading_frames(
                [HeadingSpec(title="Big Tech #{n:tbbt}", start=0, end=1)],
                HeadingsConfig(), tmp_path, 30, (108, 192),
            )
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestSeriesNumber:
    def test_assigns_and_is_idempotent_per_slug(self, tmp_path):
        reg = tmp_path / "series_index.json"
        # First time a slug is seen → next number in that series; re-asking is stable.
        assert _series_number("tbbt", "openai-postgres", reg) == 1
        assert _series_number("tbbt", "dropbox-magic-pocket", reg) == 2
        assert _series_number("tbbt", "openai-postgres", reg) == 1  # idempotent
        # Counters are per-series.
        assert _series_number("intrigue", "42-zip", reg) == 1
        assert json.loads(reg.read_text()) == {
            "tbbt": ["openai-postgres", "dropbox-magic-pocket"],
            "intrigue": ["42-zip"],
        }

    def test_token_renders_the_number(self, tmp_path):
        reg = tmp_path / "series_index.json"
        # Two distinct rendered numbers must produce two distinct PNGs.
        a = render_heading_frames(
            [HeadingSpec(title="Big Tech #{n:tbbt}", start=0, end=1, scrim=False)],
            HeadingsConfig(shadow=False), tmp_path / "a", 30, (1080, 1920),
            slug="vid-a", registry_path=reg,
        )
        b = render_heading_frames(
            [HeadingSpec(title="Big Tech #{n:tbbt}", start=0, end=1, scrim=False)],
            HeadingsConfig(shadow=False), tmp_path / "b", 30, (1080, 1920),
            slug="vid-b", registry_path=reg,
        )
        assert Image.open(a[0].image_path).tobytes() != Image.open(b[0].image_path).tobytes()
