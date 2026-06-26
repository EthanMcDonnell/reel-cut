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
# (a trailing [OUTTAKE] tag, if present, is ignored).
_WORD_LINE = re.compile(r"([\d:.]+)\s*→\s*([\d:.]+)\s+'([^']*)'\s+conf=([\d.]+)")


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
