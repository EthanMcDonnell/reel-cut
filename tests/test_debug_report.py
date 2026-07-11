"""Tests for debug_report — the human-first .debug.0.review.txt and post-vad cuts."""
from pathlib import Path

from reelcut.config import ReelCutConfig
from reelcut.edl import EDLEntry
from reelcut.gap_detector import Gap
from reelcut.retake_detector import RetakeCandidate
from reelcut.transcriber import WordTimestamp
from reelcut.debug_report import write_debug_report, _collapse_cuts

CLIP = "/x/clip.mp4"


def _w(word, s, e, c=0.9, keep=True):
    return WordTimestamp(word=word, start=s, end=e, confidence=c, clip_path=CLIP, keep=keep)


def _run(tmp_path, *, words, edl, gaps=None, retakes=None, retrans=None, dropped=0):
    cfg = ReelCutConfig()
    cfg.cuts.repetition_detection = True
    base = tmp_path / "clip"
    write_debug_report(
        base, clip_paths=[CLIP], config=cfg, raw_words=words, aligned_words=words,
        gaps_by_clip=gaps or {CLIP: []}, edl=edl, caption_words=words,
        clip_info=[{"clip": CLIP, "align_method": "x", "vad_method": "y",
                    "hallucinations_dropped": dropped}],
        retrans_log=retrans, retake_candidates=retakes, image_cues=[],
    )
    return base


def test_transcript_text_equals_kept_words(tmp_path):
    """Transcript stripped of cut markers and flags == concatenated kept words."""
    words = [_w("Hello", 0.0, 0.3), _w("world.", 0.4, 0.8),
             _w("Bye", 2.0, 2.3, c=0.4), _w("now.", 2.4, 2.8)]  # one low-conf
    edl = [EDLEntry(0.0, 0.8, True, CLIP, "speech"),
           EDLEntry(0.8, 2.0, False, CLIP, "silence"),
           EDLEntry(2.0, 2.8, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    body = review.split("FINAL TRANSCRIPT")[1]
    spoken = " ".join(
        line for line in body.splitlines() if line and "⟨" not in line and "---" not in line
    )
    spoken = spoken.replace("‹", "").replace("›?", "")  # drop low-conf markers
    assert spoken.split() == ["Hello", "world.", "Bye", "now."]


def test_post_vad_cut_rules_match_edl_runs(tmp_path):
    """One ──CUT── rule per collapsed EDL cut-run."""
    words = [_w("a", 0.0, 0.3), _w("b", 5.0, 5.3), _w("c", 9.0, 9.3)]
    edl = [EDLEntry(0.0, 0.3, True, CLIP, "speech"),
           EDLEntry(0.3, 5.0, False, CLIP, "silence"),
           EDLEntry(5.0, 5.3, True, CLIP, "speech"),
           EDLEntry(5.3, 8.0, False, CLIP, "breath"),   # two adjacent cut entries
           EDLEntry(8.0, 9.0, False, CLIP, "retake"),   # collapse into one run
           EDLEntry(9.0, 9.3, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    post_vad = Path(f"{base}.debug.4.post-vad.txt").read_text()
    assert post_vad.count("──── CUT") == len(_collapse_cuts(edl)) == 2
    assert "breath/retake" in post_vad  # merged reasons


def test_digest_flags_hard_cap_and_skipped_retake(tmp_path):
    words = [_w("x", 0.0, 0.3)]
    edl = [EDLEntry(0.0, 0.3, True, CLIP, "speech")]
    retrans = [{"win_start": 83.0, "win_end": 90.0, "label": "wide", "hard_capped": True,
                "action": "replaced", "before": [], "found_raw": [],
                "found_kept": [], "found_dropped": []}]
    retakes = {CLIP: [RetakeCandidate(ngram=("the", "cloud"), cut_len=30, match_len=2,
                                      ratio=0.07, kept=False, skip_reason="ratio too low",
                                      cut_start_s=12.0, cut_end_s=27.0)]}
    base = _run(tmp_path, words=words, edl=edl, retrans=retrans, retakes=retakes)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "HARD CAP" in review
    assert 'retake SKIPPED — "the cloud"' in review


def test_clean_run_flags_nothing(tmp_path):
    words = [_w("all", 0.0, 0.3), _w("good.", 0.4, 0.8)]
    edl = [EDLEntry(0.0, 0.8, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "✓ nothing flagged" in review
