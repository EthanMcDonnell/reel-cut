"""Real-clip regression tests.

A unit test built from a hand-made word list can pass while the detector blows up on
real footage — that is exactly how the 188s "swallow the whole video" retake bug shipped
(its test had a single synthetic retake pair, which could never exhibit a runaway across a
full clip). These tests close that gap: each fixture under tests/fixtures/retake/ is the
*complete* word list of a real, already-produced clip (text + timestamps + confidence,
copied from its `.debug.4.post-vad` report), so detection runs on the same input the
pipeline saw.

Assertions are INVARIANTS, not golden snapshots of exact cut ranges. Snapshots break on
every legitimate threshold tweak and train you to blind-update them; invariants ("no cut
exceeds the span cap", "this unique sentence survives") catch catastrophes while tolerating
honest tuning. The same fixtures also drive a sentence-segmentation sanity check — the word
list is the input to that too — so the suite is not retake-only.

To lock in a new clip: drop its post-vad word lines at tests/fixtures/retake/<slug>.txt
(see /produce-video). The generic invariants below then cover it automatically; add a
clip-specific survivor check if it has distinctive lines worth pinning.
"""
import re
from pathlib import Path

import pytest

from reelcut.config import load_config
from reelcut.transcriber import WordTimestamp, is_sentence_boundary
from reelcut.retake_detector import detect_retakes

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "retake"
_REPO_ROOT = Path(__file__).parent.parent

# Matches a post-vad word line, e.g. "  1:36.839 → 1:37.320   'shortcuts.'   conf=0.74"
# (a trailing [OUTTAKE] tag, if present, is ignored). Sub-minute timestamps carry a
# trailing 's' ("33.582s"); the optional s? captures them so _secs (which rstrips it)
# sees them — without it every word before 1:00 was silently dropped from the fixture.
#
# The report writes the word with repr(), which switches to double quotes for anything
# holding an apostrophe. Requiring single quotes therefore dropped every contraction and
# possessive — "that's", "it's", "character's" — from the parsed list, and a missing word
# merges its two neighbouring gaps into one long one that the pipeline never saw. Accept
# either quote; the lazy body still stops at the closing quote that precedes conf=.
_WORD_LINE = re.compile(r"""([\d:.]+s?)\s*→\s*([\d:.]+s?)\s+['"](.*?)['"]\s+conf=([\d.]+)""")


def _secs(t: str) -> float:
    t = t.rstrip("s")
    if ":" in t:
        m, s = t.split(":")
        return int(m) * 60 + float(s)
    return float(t)


def load_clip_words(path: Path) -> list[WordTimestamp]:
    """Parse a committed post-vad word-list fixture into WordTimestamp objects."""
    words: list[WordTimestamp] = []
    for line in path.read_text().splitlines():
        m = _WORD_LINE.search(line)
        if m:
            words.append(WordTimestamp(
                word=m.group(3), start=_secs(m.group(1)), end=_secs(m.group(2)),
                confidence=float(m.group(4)),
            ))
    return words


def _retake_kwargs() -> dict:
    """The exact retake params the pipeline runs with (mirrors cli.py's detect_retakes call)."""
    cuts = load_config(str(_REPO_ROOT / "config.yaml")).cuts
    return dict(
        min_retake_words=cuts.min_retake_words,
        max_retake_gap_s=cuts.max_retake_gap_s,
        min_match_ratio=cuts.min_match_ratio,
        max_retake_bridge_s=cuts.max_retake_bridge_s,
        max_retake_span_s=cuts.max_retake_span_s,
        min_reword_overlap=cuts.min_reword_overlap,
        min_reword_content_words=cuts.min_reword_content_words,
    )


_FIXTURES = sorted(_FIXTURE_DIR.glob("*.txt"))


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.stem)
def test_retake_detection_has_no_runaway_cut(fixture):
    """Generic invariant covering EVERY fixture: detection must not cut runaway spans.

    This is the assertion the 188s bug lacked. No single retake range may exceed the
    span cap (the detector's own safety net), and the cuts together must stay a minority
    of the clip — a correct edit removes failed takes, not the body. Catches any future
    pass that bypasses max_retake_span_s, as the reverted stumble pass did.
    """
    kw = _retake_kwargs()
    words = load_clip_words(fixture)
    assert len(words) > 20, f"{fixture.name}: fixture looks empty/unparsed"
    clip = words[-1].end - words[0].start

    ranges, _ = detect_retakes(words, **kw)
    total_cut = sum(e - s for s, e in ranges)
    max_cut = max((e - s for s, e in ranges), default=0.0)

    assert max_cut <= kw["max_retake_span_s"], (
        f"{fixture.name}: a single retake cut ({max_cut:.1f}s) exceeds the span cap "
        f"({kw['max_retake_span_s']}s) — runaway over-cut"
    )
    assert total_cut <= 0.75 * clip, (
        f"{fixture.name}: retakes cut {total_cut:.1f}s of a {clip:.1f}s clip "
        f"({total_cut / clip:.0%}) — the body is being deleted"
    )


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.stem)
def test_sentence_segmentation_is_sane(fixture):
    """Generic invariant: the word list must segment into a sane number of sentences.

    The same fixture is the input to sentence segmentation, so it guards that too: a
    regression that collapses everything into one mega-sentence (0-1 boundaries) or
    shatters it into fragments (a boundary almost every word) trips here.
    """
    words = load_clip_words(fixture)
    boundaries = sum(
        1 for a, b in zip(words, words[1:])
        if is_sentence_boundary(a.word, b.word, b.start - a.end)
    )
    # Real narration: well under one boundary per 3 words, well over a handful total.
    assert 5 <= boundaries <= len(words) // 3, (
        f"{fixture.name}: {boundaries} sentence boundaries over {len(words)} words "
        f"looks like a segmentation regression"
    )


# --- Clip-specific survivor checks (distinctive lines that can never be retakes) ------

def test_billion_laughs_unique_content_survives():
    """Regression: lines spoken exactly once must never be cut as retakes.

    These words each occur in a single, unique sentence of the billion-laughs script, so
    any cut covering them is over-cutting. Under the 188s runaway, all of them were
    deleted; they must all survive.
    """
    fixture = _FIXTURE_DIR / "billion-laughs-attack.txt"
    words = load_clip_words(fixture)
    ranges, _ = detect_retakes(words, **_retake_kwargs())

    def is_cut(t: float) -> bool:
        return any(s <= t < e for s, e in ranges)

    survivors = {"swallow", "napkin", "strangers", "amit"}
    cut_words = [
        w.word for w in words
        if w.word.lower().strip(".,!?").startswith(tuple(survivors)) and is_cut(w.start)
    ]
    assert not cut_words, f"unique content cut as retake: {cut_words}"


def test_split_brain_replica_lead_in_survives():
    """Regression (database-split-brain): the sentence lead-in "You add a replica, so
    one…" (Whisper: "So you add a replica, so why not?", ~33.6–36.2s) must not be cut.

    The reworded pass used to flag it: 3 of its 5 content words (you/add/replica) recur
    in the following run-on sentence "…so you add a tool that auto promotes a healthy
    replica to primary…" (forward overlap 0.60). But that later sentence is not a
    re-recording — it shares only 0.09 of its own content back, it's the script's
    deliberate "you add a X" parallel structure — so cutting the earlier line stranded
    "database splits into a primary…" as a subjectless fragment.
    """
    fixture = _FIXTURE_DIR / "database-split-brain.txt"
    words = load_clip_words(fixture)
    ranges, _ = detect_retakes(words, **_retake_kwargs())
    # The "replica" at ~35.3s (in "So you add a replica…") must survive.
    replica = next(w for w in words if 35.0 < w.start < 35.6 and "replica" in w.word.lower())
    assert not any(s <= replica.start < e for s, e in ranges), (
        f"'you add a replica' lead-in cut as a reworded retake; ranges={ranges}"
    )


def test_utf8_final_take_of_the_utf8_line_survives():
    """Regression (utf-8-character-encoding): the script's "UTF-8 skips that problem…"
    line was spoken twice — a trailed-off take at ~2:32 and the complete keeper at
    ~2:44 — and the END boundary snap cut BOTH, so the line never made the video.

    The keeper's own words must survive; only the earlier take may be cut. "altogether",
    "scales" and "needed" occur nowhere else in the clip, so any cut covering them is
    deleting the last occurrence.
    """
    fixture = _FIXTURE_DIR / "utf-8-character-encoding.txt"
    words = load_clip_words(fixture)
    ranges, _ = detect_retakes(words, **_retake_kwargs())

    keeper = [w for w in words if 164.7 <= w.start < 175.0]
    assert keeper, "fixture no longer covers the 2:44 keeper take"
    cut = [
        w.word for w in keeper
        if any(s <= w.start < e for s, e in ranges)
    ]
    assert not cut, f"the final take of the UTF-8 line was cut as a retake: {cut}"

    # ...and the earlier, trailed-off take at ~2:32 is still removed.
    assert any(s <= 153.0 and 160.0 <= e for s, e in ranges), (
        f"the failed 2:32 take is no longer cut; ranges={ranges}"
    )
