"""Full-script EDL regression tests.

The unit tests in test_edl_min_keep_floor.py run three hand-made words through
generate_scriptless_edl. That is enough to pin the arithmetic, and not enough to prove
the EDL never clips a word — the "API?" bug was one boundary out of eleven on a clip
where the other ten were fine, and it took the whole word list plus the real gap list to
show up. So these tests replay a complete clip.

Two fixtures per clip, both real:

  tests/fixtures/retake/<slug>.txt        the clip's full word list (shared with
                                          test_real_clips.py — text, timings, confidence)
  tests/fixtures/edl/<slug>.gaps.txt      the gap list detect_gaps() produced from the
                                          clip's audio

The gaps are pinned because assets/ is gitignored and speech_end — where the audio scan
found a word's real end, past a truncated alignment — cannot be recovered from the word
list alone. Regenerate with the clips present via tests/fixtures/edl/regen_gaps.py.

Assertions are INVARIANTS, not golden EDLs, for the reason test_real_clips.py gives: a
snapshot of exact cut times breaks on every honest threshold tweak and trains you to
blind-update it.
"""
from pathlib import Path

import pytest
from tests.test_real_clips import load_clip_words

from reelcut.config import load_config
from reelcut.edl import EDLEntry, generate_scriptless_edl
from reelcut.gap_detector import Gap

_GAP_DIR = Path(__file__).parent / "fixtures" / "edl"
_WORD_DIR = Path(__file__).parent / "fixtures" / "retake"
_REPO_ROOT = Path(__file__).parent.parent

_FIXTURES = sorted(_GAP_DIR.glob("*.gaps.txt"))


def _load_gaps(path: Path) -> list[Gap]:
    gaps: list[Gap] = []
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        start, end, effective, speech_end, gap_type, cut = line.split()
        gaps.append(Gap(
            start=float(start), end=float(end), effective_start=float(effective),
            speech_end=float(speech_end),
            duration_ms=(float(end) - float(effective)) * 1000,
            gap_type=gap_type, cut=(cut == "cut"),
        ))
    return gaps


def _build_edl(slug: str) -> tuple[list, list[Gap], list[EDLEntry]]:
    """Run the clip through the EDL builder with the pipeline's real config."""
    cuts = load_config(str(_REPO_ROOT / "config.yaml")).cuts
    words = load_clip_words(_WORD_DIR / f"{slug}.txt")
    for w in words:
        w.clip_path = f"{slug}.mov"
    gaps = _load_gaps(_GAP_DIR / f"{slug}.gaps.txt")
    edl = generate_scriptless_edl(
        words, gaps,
        min_keep_ms=cuts.min_keep_ms,
        speech_pad_ms=cuts.speech_pad_ms,
        mid_sentence_cut_floor_ms=cuts.mid_sentence_cut_floor_ms,
        sentence_pause_s=cuts.sentence_pause_s,
    )
    return words, gaps, edl


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.name.removesuffix(".gaps.txt"))
def test_no_cut_opens_inside_a_words_verified_speech(fixture):
    """Generic invariant over the whole clip: cuts never eat audio the scan called speech.

    detect_gaps hands the EDL a speech_end per gap — the point in the waveform where the
    preceding word's speech actually stops, which sits past the aligned word end whenever
    alignment truncated a tail. Everything from the word's start to that speech_end is
    audible speech, so no cut may overlap it.

    Under the min_keep_ms floor bug this failed on all three clips at once: any word whose
    aligned span came in under min_keep_ms had its cut forced to start + 200 ms, which on
    "API?" (aligned to 122 ms, spoken for 900 ms) landed 542 ms inside the word.
    """
    words, gaps, edl = _build_edl(fixture.name.removesuffix(".gaps.txt"))
    speech_end_by_word_end = {round(g.start, 4): g.speech_end for g in gaps}
    cuts = [e for e in edl if not e.keep]

    clipped = []
    for w in words:
        speech_end = speech_end_by_word_end.get(round(w.end, 4), w.end)
        for c in cuts:
            if c.start < speech_end and c.end > w.start:
                clipped.append(
                    f"{w.word!r} ({w.start:.3f}-{speech_end:.3f}s) cut at {c.start:.3f}s "
                    f"— {(speech_end - c.start) * 1000:.0f}ms of speech lost"
                )
    assert not clipped, "EDL cut into spoken words:\n  " + "\n  ".join(clipped)


def test_casual_talking_head_keeps_the_whole_word_api():
    """Regression: "1 million for API?" rendered as "1 million for A-p".

    wav2vec2 aligned 'API?' to 122 ms (16.405→16.527) while the word runs to 17.147s in
    the waveform. The cut that follows it must open at that speech end, not at the
    min_keep_ms floor's 16.605s.
    """
    _, _, edl = _build_edl("casual-talking-head")
    cut = next(e for e in edl if not e.keep and 16.0 < e.start < 18.5)
    assert cut.start == pytest.approx(17.147, abs=0.001)
