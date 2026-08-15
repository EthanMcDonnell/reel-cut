"""Manual tail trims in scrape/edit_video.py — the EDL surgery and the guard that
keeps a cut from shifting the output timeline out from under videos.json's title cards.
"""
import importlib.util
import json
from pathlib import Path

from reelcut.captions_doc import EdlEntry

_SPEC = importlib.util.spec_from_file_location(
    "rc_edit_video", Path(__file__).parent.parent / "scrape" / "edit_video.py"
)
edit_video = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(edit_video)

CLIP = "assets/demo/clip.MOV"


class _Word:
    """Stand-in for CaptionWord — only .word/.start/.end/.source_clip are read."""

    def __init__(self, word, start, end):
        self.word, self.start, self.end, self.source_clip = word, start, end, CLIP


def test_cut_inside_a_keep_span_splits_it_into_three_contiguous_spans():
    """The renderer walks the EDL as a flat contiguous list, so a cut must leave no
    gap and no overlap — only the middle piece flips."""
    edl = [EdlEntry(CLIP, 0.0, 10.0, True, "speech")]

    out = edit_video._apply_cut(edl, 4.0, 6.0)

    assert [(e.start, e.end, e.keep) for e in out] == [
        (0.0, 4.0, True),
        (4.0, 6.0, False),
        (6.0, 10.0, True),
    ]
    assert out[1].reason == edit_video.CUT_REASON
    # contiguous, and total span conserved
    assert all(a.end == b.start for a, b in zip(out, out[1:]))
    assert out[-1].end - out[0].start == 10.0


def test_cut_boundary_inside_a_word_widens_to_take_the_whole_word():
    """A boundary mid-word would render a clipped syllable, so the word goes whole."""
    words = [_Word("beat", 4.2, 4.9), _Word("it.", 5.0, 5.4)]

    start, end, snaps = edit_video._snap(4.5, 5.2, words)

    assert (start, end) == (4.2, 5.4)
    assert [s["word"] for s in snaps] == ["beat", "it."]


def test_cut_starting_before_the_last_hook_window_is_refused(tmp_path, monkeypatch):
    """Cutting before the hooks end shifts every later word earlier, sliding the
    burned-in title cards onto the wrong words. The tool must refuse, not repair."""
    monkeypatch.setattr(edit_video, "ROOT", tmp_path)
    d = tmp_path / "assets" / "demo"
    d.mkdir(parents=True)
    (d / "clip.captions.json").write_text(json.dumps({
        "source_clips": [CLIP],
        "edl": [{"source_clip": CLIP, "start": 0.0, "end": 10.0,
                 "keep": True, "reason": "speech"}],
        "words": [{"word": w, "start": s, "end": e, "source_clip": CLIP}
                  for w, s, e in [("hook", 0.0, 1.0), ("body", 5.0, 6.0)]],
    }))
    (d / "videos.json").write_text(json.dumps(
        [{"id": "h1", "title": "A Card", "start": 0.0, "end": 3.0}]
    ))

    refused = edit_video.edit("demo", ["1.5-2.5"], dry_run=True)
    allowed = edit_video.edit("demo", ["5.0-6.0"], dry_run=True)

    assert "title card" in refused["error"]
    assert allowed["cuts"][0]["text"] == "body"
