"""Tests for reconcile_manifest — re-aligning a screenshot manifest to the transcript.

The rewrite slides a window over the transcript, so it can land off one edge of the old
line and strip a trigger anchor with it. produce-video then spans the whole sentence
instead of the claim, and without `lost_anchors` nothing says so.
"""
import importlib.util
import json
import sys
from pathlib import Path

SCRAPE = Path(__file__).resolve().parent.parent / "scrape"
sys.path.insert(0, str(SCRAPE))
_SPEC = importlib.util.spec_from_file_location("rc_reconcile", SCRAPE / "reconcile_manifest.py")
reconcile_manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reconcile_manifest)


def _slug(tmp_path, monkeypatch, transcript: str, shots: list[dict]) -> str:
    """Write a minimal assets/<slug>/ with a transcript and a manifest, return the slug."""
    monkeypatch.setattr(reconcile_manifest, "ROOT", tmp_path)
    asset_dir = tmp_path / "assets" / "demo"
    asset_dir.mkdir(parents=True)
    words = [{"word": w, "start": i * 0.2, "end": i * 0.2 + 0.2}
             for i, w in enumerate(transcript.split())]
    (asset_dir / "demo.captions.json").write_text(json.dumps({"words": words}))
    (asset_dir / "manifest.json").write_text(json.dumps([{"url": "u", "screenshots": shots}]))
    return "demo"


TRANSCRIPT = "everyone agreed on the first 128 of those numbers, that's ASCII, so 65 is a capital A."


class TestAnchorMissing:
    def test_present_anchor_is_found(self):
        assert not reconcile_manifest._anchor_missing("ASCII", "that's ASCII, so 65 is")

    def test_punctuation_and_case_do_not_hide_it(self):
        # The rewritten context is transcript tokens, which carry punctuation the
        # hand-written trigger does not.
        assert not reconcile_manifest._anchor_missing("ascii", "that's ASCII, so 65")

    def test_multi_word_anchor_must_match_in_sequence(self):
        assert not reconcile_manifest._anchor_missing("capital A", "is a capital A.")
        assert reconcile_manifest._anchor_missing("capital A", "a capital, then A.")

    def test_absent_anchor_is_reported(self):
        assert reconcile_manifest._anchor_missing("128", "that's ASCII, so 65 is")

    def test_empty_anchor_is_the_documented_no_anchor_value(self):
        assert not reconcile_manifest._anchor_missing("", "anything")
        assert not reconcile_manifest._anchor_missing("   ", "anything")


def test_rewrite_that_strips_a_trigger_is_reported(tmp_path, monkeypatch):
    # The old context runs from "128" but the transcript's best window starts later,
    # so the rewrite drops "128" — the very word the screenshot was triggered on.
    slug = _slug(tmp_path, monkeypatch, TRANSCRIPT, [{
        "file": "snippet-02.png",
        "script_context": "128 of those numbers, that's ASCII",
        "trigger_show_word": "128",
        "trigger_go_away_word": "ASCII",
    }])
    monkeypatch.setattr(reconcile_manifest, "_best_window",
                        lambda ctx, toks: (0.9, 8, 11))  # "that's ASCII, so"

    report = reconcile_manifest.reconcile(slug, dry_run=True)

    assert [e["file"] for e in report["lost_anchors"]] == ["snippet-02.png"]
    assert report["lost_anchors"][0]["anchors"] == ["trigger_show_word"]
    assert report["lost_anchors"][0]["trigger_show_word"] == "128"


def test_a_rewrite_that_keeps_both_triggers_reports_nothing(tmp_path, monkeypatch):
    slug = _slug(tmp_path, monkeypatch, TRANSCRIPT, [{
        "file": "snippet-02.png",
        "script_context": "everyone agreed on the first 128 of those numbers, that's ASCII,",
        "trigger_show_word": "128",
        "trigger_go_away_word": "ASCII",
    }])

    report = reconcile_manifest.reconcile(slug, dry_run=True)

    assert report["lost_anchors"] == []


def test_screenshots_without_triggers_are_not_flagged(tmp_path, monkeypatch):
    # Empty triggers are the documented "span the whole line" value, not a fault.
    slug = _slug(tmp_path, monkeypatch, TRANSCRIPT, [{
        "file": "snippet-01.png",
        "script_context": "everyone agreed on the first 128",
        "trigger_show_word": "",
        "trigger_go_away_word": "",
    }])

    report = reconcile_manifest.reconcile(slug, dry_run=True)

    assert report["lost_anchors"] == []


def test_a_deleted_line_is_orphaned_and_removed_not_reanchored(tmp_path, monkeypatch):
    # The line the screenshot supported was cut from the script. Its neighbours still
    # clear the ratio threshold, but none of its trigger words survive in that window.
    slug = _slug(tmp_path, monkeypatch, TRANSCRIPT, [
        {
            "file": "snippet-04.png",
            "script_context": "because a model that is right 95% of the time can't be automated",
            "trigger_show_word": "because",
            "trigger_go_away_word": "automated",
        },
        {
            "file": "snippet-02.png",
            "script_context": "everyone agreed on the first 128 of those numbers, that's ASCII,",
            "trigger_show_word": "128",
            "trigger_go_away_word": "ASCII",
        },
    ])
    monkeypatch.setattr(reconcile_manifest, "_best_window",
                        lambda ctx, toks: (0.7, 8, 14) if "95%" in ctx else (1.0, 0, 11))

    report = reconcile_manifest.reconcile(slug, dry_run=False)

    assert [e["file"] for e in report["orphaned"]] == ["snippet-04.png"]
    assert report["lost_anchors"] == []
    manifest = json.loads((tmp_path / "assets" / "demo" / "manifest.json").read_text())
    assert [s["file"] for s in manifest[0]["screenshots"]] == ["snippet-02.png"]
