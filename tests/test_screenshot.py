"""Unit tests for the pure helpers in scrape/screenshot.py.

The Playwright-driven capture flow (parallel snippet capture, find/highlight targeting)
needs a real browser and is exercised end-to-end via /produce-script; here we cover the
deterministic logic: element-sized crop windows and locked manifest writes.
"""
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "rc_screenshot", Path(__file__).parent.parent / "scrape" / "screenshot.py"
)
screenshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(screenshot)


class TestParseSnippetSpec:
    def test_bare_string_becomes_article_snippet_with_empty_fields(self):
        spec = screenshot._parse_snippet_spec("some text")
        assert spec == {
            "article_snippet": "some text",
            "script_context": "",
            "trigger_show_word": "",
            "trigger_go_away_word": "",
        }

    def test_full_dict_passes_through_unchanged(self):
        full = {
            "article_snippet": "a",
            "script_context": "b",
            "trigger_show_word": "c",
            "trigger_go_away_word": "d",
        }
        assert screenshot._parse_snippet_spec(full) == full

    def test_partial_dict_fills_missing_keys_with_empty_string(self):
        spec = screenshot._parse_snippet_spec({"article_snippet": "only this"})
        assert spec["script_context"] == ""
        assert spec["trigger_show_word"] == ""
        assert spec["trigger_go_away_word"] == ""


class TestCropWindow:
    def test_short_element_gets_min_height(self):
        _, h = screenshot._crop_window(el_top=400, el_height=20, vh=844)
        assert h == screenshot.SNIPPET_MIN_HEIGHT

    def test_tall_element_clamped_to_max(self):
        _, h = screenshot._crop_window(el_top=100, el_height=2000, vh=844)
        assert h == min(screenshot.SNIPPET_MAX_HEIGHT, 844)

    def test_medium_element_sized_with_padding(self):
        _, h = screenshot._crop_window(el_top=300, el_height=300, vh=844)
        assert h == 300 + 2 * screenshot.SNIPPET_PADDING

    def test_crop_brackets_the_element(self):
        y, h = screenshot._crop_window(el_top=300, el_height=100, vh=844)
        center = 300 + 100 / 2
        assert y <= center <= y + h

    def test_never_exceeds_viewport_bottom(self):
        y, h = screenshot._crop_window(el_top=820, el_height=40, vh=844)
        assert y >= 0
        assert y + h <= 844


class TestWriteManifest:
    def test_creates_manifest(self, tmp_path):
        entry = {"url": "http://a", "screenshots": []}
        screenshot._write_manifest(tmp_path, "http://a", entry)
        assert json.loads((tmp_path / "manifest.json").read_text()) == [entry]

    def test_appends_distinct_urls(self, tmp_path):
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": []})
        screenshot._write_manifest(tmp_path, "http://b", {"url": "http://b", "screenshots": []})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert [d["url"] for d in data] == ["http://a", "http://b"]

    def test_replaces_same_url(self, tmp_path):
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": [1]})
        screenshot._write_manifest(tmp_path, "http://a", {"url": "http://a", "screenshots": [2]})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert len(data) == 1
        assert data[0]["screenshots"] == [2]

    def test_migrates_legacy_single_object(self, tmp_path):
        (tmp_path / "manifest.json").write_text(json.dumps({"url": "http://old", "screenshots": []}))
        screenshot._write_manifest(tmp_path, "http://new", {"url": "http://new", "screenshots": []})
        data = json.loads((tmp_path / "manifest.json").read_text())
        assert isinstance(data, list)
        assert {d["url"] for d in data} == {"http://old", "http://new"}


class TestSnippetAnchor:
    """find() matches on this prefix, so it decides when a highlight can be partial."""

    def test_short_snippet_is_its_own_anchor(self):
        raw = "a number between 32 and 127. space was 32, the letter 'a' was 65"
        assert screenshot._snippet_anchor(raw) == raw

    def test_long_snippet_is_cut_to_a_word_boundary(self):
        # The snippet-01 case: the proof ("There Ain't No Such Thing As Plain Text.")
        # falls outside the anchor, so an anchor-only highlight covers the rhetorical
        # run-up and stops. _ss_highlight.js reports that as `anchor_range`.
        raw = ("you can no longer stick your head in the sand and pretend that "
               "“plain” text is ascii. there ain’t no such thing as plain text.")
        anchor = screenshot._snippet_anchor(raw)

        assert raw.startswith(anchor)
        assert len(anchor) <= 80
        assert not anchor.endswith(" ")
        assert "no such thing as plain text" not in anchor

    def test_unbroken_run_longer_than_the_cap_is_truncated_hard(self):
        raw = "x" * 100
        assert screenshot._snippet_anchor(raw) == "x" * 80


class TestUnprovenFigures:
    def test_figure_outside_the_highlight_is_reported(self):
        # The snippet-05 case: the highlight stops at the colon, so "> 45 GiB/s" sits
        # in the crop but outside the coloured range — visible, yet not the evidence.
        context = "Nothing branches so it gets to vectorize fully and hits over 45 gigabytes a second."
        snippet = "A loop with no data-dependent control flow is trivially vectorizable"
        assert screenshot._unproven_figures(context, snippet) == ["45"]

    def test_starting_the_snippet_later_proves_the_figure(self):
        context = "Nothing branches so it gets to vectorize fully and hits over 45 gigabytes a second."
        snippet = "LLVM emits 16-byte-at-a-time NEON and the whole thing runs at > 45 GiB/s"
        assert screenshot._unproven_figures(context, snippet) == []

    def test_a_rounded_article_figure_does_not_prove_the_spoken_one(self):
        # snippet-02: the script says 3.1, the article prose rounds to "about 3 GiB/s".
        context = "On an Apple M4, it runs at 3.1 gigabytes a second."
        snippet = "On an Apple M4 this runs at about 3 GiB/s"
        assert screenshot._unproven_figures(context, snippet) == ["3.1"]

    def test_matching_figures_pass(self):
        context = "Github's code search indexes 480 terabytes of source code."
        snippet = "more than 480TB of source code. Every byte is case-folded"
        assert screenshot._unproven_figures(context, snippet) == []

    def test_a_line_with_no_figures_is_never_flagged(self):
        assert screenshot._unproven_figures("the real problem was the break itself", "x") == []
