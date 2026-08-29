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


def _run(tmp_path, *, words, edl, gaps=None, retakes=None, retrans=None, dropped=0,
         retake_ranges=None, script=None):
    cfg = ReelCutConfig()
    cfg.cuts.repetition_detection = True
    base = tmp_path / "clip"
    if script is not None:
        (tmp_path / "script.md").write_text(script)
    write_debug_report(
        base, clip_paths=[CLIP], config=cfg, raw_words=words, aligned_words=words,
        gaps_by_clip=gaps or {CLIP: []}, edl=edl, caption_words=words,
        clip_info=[{"clip": CLIP, "align_method": "x", "vad_method": "y",
                    "hallucinations_dropped": dropped}],
        retrans_log=retrans, retake_candidates=retakes, retake_ranges=retake_ranges,
        image_cues=[],
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


def test_digest_flags_abandoned_aside(tmp_path):
    """A short low-confidence clause with no cut before the next sentence is flagged.

    Regression for a real clip: "So you add a replica, so why not?" (no lexical
    overlap with what follows, no trail-off ellipsis) ran straight into "Database
    splits." with a sub-threshold gap — invisible to both the retake matcher
    (needs shared wording) and the aborted-restart pass (needs an ellipsis).
    """
    words = [
        _w("So", 33.58, 34.79, c=0.21), _w("you", 34.81, 34.95, c=0.75),
        _w("add", 35.05, 35.17, c=0.54), _w("a", 35.21, 35.25, c=0.99),
        _w("replica,", 35.29, 35.84, c=0.69), _w("so", 35.90, 36.00, c=0.88),
        _w("why", 36.02, 36.16, c=0.21), _w("not?", 36.16, 36.16, c=0.43),
        _w("Database", 36.20, 36.58, c=0.82), _w("splits.", 36.62, 36.94, c=0.85),
    ]
    edl = [EDLEntry(33.58, 36.94, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "possible abandoned aside" in review
    assert "So you add a replica, so why not?" in review


def test_confident_short_sentence_not_flagged_as_aside(tmp_path):
    """A short but high-confidence clause before the next sentence isn't flagged."""
    words = [
        _w("Quick", 0.0, 0.3, c=0.95), _w("point.", 0.3, 0.6, c=0.9),
        _w("Now", 0.6, 0.9, c=0.9), _w("the", 0.9, 1.0, c=0.9), _w("rest.", 1.0, 1.3, c=0.9),
    ]
    edl = [EDLEntry(0.0, 1.3, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "possible abandoned aside" not in review


def test_clean_run_flags_nothing(tmp_path):
    words = [_w("all", 0.0, 0.3), _w("good.", 0.4, 0.8)]
    edl = [EDLEntry(0.0, 0.8, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "✓ nothing flagged" in review


def test_timeline_distinguishes_the_two_edl_declines(tmp_path):
    """A cut gap the EDL declines must name the real reason, not always the floor.

    Reporting both as [mid_sentence_floor] hid a live defect: the trailing scan walked
    through an exhale, speech_end landed on the next word's start, and the whole gap
    survived while the report blamed the floor.
    """
    words = [_w("bits", 0.0, 0.4), _w("that.", 0.4, 0.8),   # sentence end → floor n/a
             _w("one", 1.4, 1.8),
             _w("giant", 1.8, 2.2), _w("list", 2.2, 2.6)]   # mid-sentence, short gap
    gaps = {CLIP: [
        # Cut gap the EDL declines for lack of room: speech_end sits at the next
        # word's start, so cut_end (onset - pad) lands before cut_start.
        Gap(start=0.8, end=1.4, effective_start=0.8, speech_end=1.4, duration_ms=600,
            gap_type="breath", cut=True, speech_onset=1.4),
    ]}
    edl = [EDLEntry(0.0, 2.6, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl, gaps=gaps)
    timeline = Path(f"{base}.debug.5.timeline.txt").read_text()

    assert "no room" in timeline
    assert "mid_sentence_floor" not in timeline


_SCRIPT = """**VIDEO TYPE**
interesting-tech
**HOOK**
HOOK 1: There is no such thing as plain text.
**SCRIPT**
UTF-32 gives every character four bytes, which is enormous.
UTF-8 skips that problem, because each byte marks its own place so minimum can be one byte and scales up to four bytes.
Nothing in the file says which encoding it used.
**CONCLUSION**
Text is just numbers plus a promise about how to read them.
**CTA**
Comment "UNICODE" for it.
**REFERENCES:**
https://example.com/unicode
"""


def _script_words(text, t0, keep=True):
    """Lay a sentence out as one word per 0.4s from t0."""
    return [_w(tok, t0 + i * 0.4, t0 + i * 0.4 + 0.3, keep=keep)
            for i, tok in enumerate(text.split())]


def test_digest_flags_a_script_line_that_was_cut(tmp_path):
    """Regression (utf-8-character-encoding): a whole script line was cut from the
    video and nothing in the digest said so.

    The line was spoken — it is right there in the aligned words — but every span
    carrying it is keep=False, so it survives nowhere. The digest must name it, and
    say it was spoken-then-cut rather than never delivered.
    """
    words = (
        _script_words("UTF-32 gives every character four bytes, which is enormous.", 0.0)
        + _script_words(
            "UTF-8 skips that problem, because each byte marks its own place so "
            "minimum can be one byte and scales up to four bytes.", 10.0, keep=False)
        + _script_words("Nothing in the file says which encoding it used.", 30.0)
        + _script_words("Text is just numbers plus a promise about how to read them.", 40.0)
        + _script_words('Comment "UNICODE" for it.', 50.0)
    )
    edl = [EDLEntry(0.0, 9.9, True, CLIP, "speech"),
           EDLEntry(9.9, 29.9, False, CLIP, "retake"),
           EDLEntry(29.9, 60.0, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl, script=_SCRIPT)
    review = Path(f"{base}.debug.0.review.txt").read_text()

    assert "SCRIPT LINE MISSING" in review
    assert "UTF-8 skips that problem" in review.split("SCRIPT COVERAGE")[0]
    assert "but cut" in review
    # The lines that did survive must not be flagged, and hooks are never checked.
    assert review.count("SCRIPT LINE MISSING") == 1
    assert "(5 spoken lines, 1 missing)" in review
    assert "no such thing as plain text" not in review.split("FINAL TRANSCRIPT")[0]


def test_ad_libbed_delivery_is_not_flagged_as_missing(tmp_path):
    """Reworded delivery is normal and must not trip the coverage check."""
    words = (
        _script_words("So UTF-32 gives you every character in four bytes, which is enormous.", 0.0)
        + _script_words(
            "See, UTF-8 skips that problem, because each byte marks its own place, so "
            "the minimum can be one byte and it scales up to four bytes.", 10.0)
        + _script_words("Nothing in the file actually says which encoding it used.", 30.0)
        + _script_words("Text is just numbers, plus a promise about how to read them.", 40.0)
        + _script_words('Comment "UNICODE" for it and I will send it through.', 50.0)
    )
    edl = [EDLEntry(0.0, 60.0, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl, script=_SCRIPT)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "SCRIPT LINE MISSING" not in review
    assert "(5 spoken lines, 0 missing)" in review


def test_no_script_md_reports_nothing_to_check(tmp_path):
    words = [_w("x", 0.0, 0.3)]
    edl = [EDLEntry(0.0, 0.3, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl)
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "no script.md beside this clip" in review
    assert "SCRIPT LINE MISSING" not in review


def test_digest_flags_a_long_applied_retake_cut(tmp_path):
    """Only SKIPPED retakes used to be reported, so an over-reaching cut was silent."""
    words = (_script_words("one two three four five six seven eight nine ten", 0.0, keep=False)
             + _script_words("the keeper survives here.", 20.0))
    edl = [EDLEntry(0.0, 19.9, False, CLIP, "retake"),
           EDLEntry(19.9, 25.0, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl, retake_ranges={CLIP: [(0.0, 12.0)]})
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "long retake cut 12.0s" in review
    assert "one two three" in review.split("FINAL TRANSCRIPT")[0]


def test_short_retake_cut_is_not_flagged(tmp_path):
    words = _script_words("a b c d", 0.0, keep=False) + _script_words("a b c d.", 5.0)
    edl = [EDLEntry(0.0, 4.9, False, CLIP, "retake"),
           EDLEntry(4.9, 8.0, True, CLIP, "speech")]
    base = _run(tmp_path, words=words, edl=edl, retake_ranges={CLIP: [(0.0, 5.0)]})
    review = Path(f"{base}.debug.0.review.txt").read_text()
    assert "long retake cut" not in review
