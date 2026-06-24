"""Tests for the multi-hook splitter — segment slicing, headings, image filtering, snapping."""
import json
import math
from pathlib import Path

from typer.testing import CliRunner

from reelcut.captions_doc import CaptionsDoc, CaptionWord, EdlEntry, save_captions_doc
from reelcut.cli import app
from reelcut.hook_split import (
    build_segment_doc,
    edl_edges,
    filter_images,
    make_variant_heading,
    segment_output_duration,
    snap_boundary,
)

CLIP = "clip.mp4"


def _doc() -> CaptionsDoc:
    """Two hooks + body on one source clip, with clean EDL edges between them.

    keep[1,2] hook1 | cut[2,3] | keep[3,4] hook2 | cut[4,5] | keep[5,8] body
    """
    edl = [
        EdlEntry(CLIP, 1.0, 2.0, True, "speech"),
        EdlEntry(CLIP, 2.0, 3.0, False, "outtake"),
        EdlEntry(CLIP, 3.0, 4.0, True, "speech"),
        EdlEntry(CLIP, 4.0, 5.0, False, "outtake"),
        EdlEntry(CLIP, 5.0, 8.0, True, "speech"),
    ]
    words = [
        CaptionWord("Alpha", 1.0, 1.5, CLIP),
        CaptionWord("one", 1.5, 2.0, CLIP),
        CaptionWord("Beta", 3.0, 3.5, CLIP),
        CaptionWord("two", 3.5, 4.0, CLIP),
        CaptionWord("See", 5.0, 5.5, CLIP),
        CaptionWord("the", 5.5, 6.0, CLIP),
        CaptionWord("body", 6.0, 6.5, CLIP),
        CaptionWord("here", 6.5, 7.0, CLIP),
    ]
    return CaptionsDoc(source_clips=[CLIP], edl=edl, words=words)


class TestBuildSegmentDoc:
    def test_hook1_segment_is_hook1_only(self):
        seg = build_segment_doc(_doc(), 1.0, 2.0)
        assert [w.word for w in seg.words] == ["Alpha", "one"]
        assert [(e.start, e.end, e.keep) for e in seg.edl] == [(1.0, 2.0, True)]

    def test_hook2_segment_is_hook2_only(self):
        seg = build_segment_doc(_doc(), 3.0, 4.0)
        assert [w.word for w in seg.words] == ["Beta", "two"]
        assert [(e.start, e.end, e.keep) for e in seg.edl] == [(3.0, 4.0, True)]

    def test_body_segment_is_body_only(self):
        seg = build_segment_doc(_doc(), 5.0, math.inf)
        assert [w.word for w in seg.words] == ["See", "the", "body", "here"]
        assert [(e.start, e.end, e.keep) for e in seg.edl] == [(5.0, 8.0, True)]


class TestSegmentOutputDuration:
    def test_sums_kept_overlap(self):
        assert segment_output_duration(_doc().edl, 1.0, 2.0) == 1.0
        assert segment_output_duration(_doc().edl, 5.0, math.inf) == 3.0


class TestMakeVariantHeading:
    def test_bakes_token_and_sets_window(self):
        hook = {"title": "8,000 Services\nIdle", "subtitle": "Day {n:tbbt}"}
        h = make_variant_heading(hook, 1.0, 5)
        assert h["subtitle"] == "Day 5"
        assert h["title"] == "8,000 Services\nIdle"
        assert h["start"] == 0.0 and h["end"] == 1.0

    def test_token_without_number_raises(self):
        try:
            make_variant_heading({"subtitle": "Day {n:tbbt}"}, 1.0, None)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_no_token_needs_no_number(self):
        h = make_variant_heading({"title": "Plain", "subtitle": ""}, 2.0, None)
        assert h["title"] == "Plain" and h["end"] == 2.0


class TestFilterImages:
    def test_body_image_survives_hook2_only_image_dropped_from_hook1(self):
        images = [
            {"type": "concept", "start": 3.2, "end": 3.8, "name": "hook2-thing"},
            {"type": "person", "start": 6.0, "end": 6.5, "name": "Body Person"},
        ]
        assert [i["name"] for i in filter_images(images, [(1.0, 2.0)])] == []
        assert [i["name"] for i in filter_images(images, [(3.0, 4.0)])] == ["hook2-thing"]
        assert [i["name"] for i in filter_images(images, [(5.0, math.inf)])] == ["Body Person"]


class TestSnapBoundary:
    def test_snaps_within_tolerance(self):
        edges = edl_edges(_doc().edl)
        assert snap_boundary(1.03, edges) == 1.0   # 30ms inside the word → segment edge
        assert snap_boundary(4.98, edges) == 5.0

    def test_raises_when_far_from_any_edge(self):
        edges = edl_edges(_doc().edl)
        try:
            snap_boundary(6.5, edges)  # mid-body, far from any edge
            assert False, "expected ValueError"
        except ValueError:
            pass


class TestSplitHooksCommand:
    def test_missing_hooks_json_exits_nonzero(self, tmp_path):
        config = str(Path(__file__).parent.parent / "config.yaml")
        cap = tmp_path / "vid" / "vid.captions.json"
        cap.parent.mkdir(parents=True)
        save_captions_doc(_doc(), cap)  # no hooks.json alongside
        result = CliRunner().invoke(app, ["split-hooks", config, str(cap)])
        assert result.exit_code != 0
        assert "hooks.json" in result.output

    def test_emits_body_and_hook_segments(self, tmp_path):
        config = str(Path(__file__).parent.parent / "config.yaml")
        viddir = tmp_path / "assets" / "vid"
        viddir.mkdir(parents=True)
        cap = viddir / "vid.captions.json"
        save_captions_doc(_doc(), cap)
        (viddir / "images.json").write_text(json.dumps([
            {"type": "concept", "start": 3.2, "end": 3.8, "name": "hook2-thing"},
            {"type": "person", "start": 6.0, "end": 6.5, "name": "Body Person"},
        ]))
        (viddir / "hooks.json").write_text(json.dumps({
            "source_clip": CLIP,
            "body_start": 5.0,
            "hooks": [
                {"start": 1.0, "end": 2.0, "title": "Hook 1", "subtitle": "Day {n:tbbt}"},
                {"start": 3.0, "end": 4.0, "title": "Hook 2", "subtitle": "Day {n:tbbt}"},
            ],
        }))
        result = CliRunner().invoke(app, ["split-hooks", config, str(cap)])
        assert result.exit_code == 0, result.output

        assets = tmp_path / "assets"
        body, h1, h2 = assets / "vid-body", assets / "vid-hook1", assets / "vid-hook2"

        # Body has no heading card and owns the body-anchored image.
        assert json.loads((body / "headings.json").read_text()) == []
        assert [i["name"] for i in json.loads((body / "images.json").read_text())] == ["Body Person"]

        # Each hook carries its own card, both the same episode (Day 1), and only its own image.
        for d in (h1, h2):
            assert (d / f"{d.name}.captions.json").exists()
            assert json.loads((d / "headings.json").read_text())[0]["subtitle"] == "Day 1"
        assert json.loads((h1 / "images.json").read_text()) == []
        assert [i["name"] for i in json.loads((h2 / "images.json").read_text())] == ["hook2-thing"]
