"""Behaviour-driven retake variations.

These tests are written from first principles — "what should a retake detector
do?" — without regard to the current implementation. The policy under test:

  * A retake = the same scripted span attempted two or more times in close
    succession (within the gap window), allowing for transcription noise
    (substitutions, transpositions, inserted/dropped words, truncation).
  * KEEP THE LAST take, always. Everything from the first attempt up to the
    start of the final attempt is cut.
  * Do NOT cut genuinely distinct content, coincidental short overlaps, or
    repeats outside the time window.

Helpers build word lists from take strings with controlled within-take and
between-take gaps, so the expected cut boundaries fall out of the take starts.
"""
import pytest
from reelcut.transcriber import WordTimestamp
from reelcut.retake_detector import detect_retakes

# Production config (config.yaml). max_retake_skip/bridge use function defaults.
CFG = dict(min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)


def _w(word: str, start: float, end: float) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=end, confidence=0.9)


def build(*takes, intra=0.05, inter=0.6, dur=0.15, start=1.0):
    """Build (words, take_starts) from space-separated take strings.

    Words within a take are separated by `intra`s of silence; takes are
    separated by `inter`s (the pause between attempts). Returns the word list
    and the start time of each take's first word.
    """
    words, starts = [], []
    t = start
    for ti, take in enumerate(takes):
        if ti:
            t += inter
        starts.append(t)
        for wi, tok in enumerate(take.split()):
            if wi:
                t += intra
            words.append(_w(tok, t, t + dur))
            t += dur
    return words, starts


def R(words, **kw):
    ranges, _ = detect_retakes(words, **{**CFG, **kw})
    return ranges


def assert_keep_last(words, starts, **kw):
    """One merged cut spanning all takes except the last (kept) one."""
    r = R(words, **kw)
    assert len(r) == 1, f"expected 1 cut, got {r}"
    assert r[0][0] == pytest.approx(starts[0]), "cut should start at first take"
    assert r[0][1] == pytest.approx(starts[-1]), "cut should end at final (kept) take"


# ---------------------------------------------------------------------------
# 1. Exact repeats
# ---------------------------------------------------------------------------

def test_exact_two_takes():
    words, starts = build("the model runs locally now", "the model runs locally now")
    assert_keep_last(words, starts)


def test_exact_three_takes():
    words, starts = build("the model runs locally now",
                          "the model runs locally now",
                          "the model runs locally now")
    assert_keep_last(words, starts)


def test_exact_four_takes():
    words, starts = build(*(["the model runs locally now"] * 4))
    assert_keep_last(words, starts)


def test_exact_back_to_back_no_pause():
    words, starts = build("the model runs locally now", "the model runs locally now",
                          inter=0.05)
    assert_keep_last(words, starts)


def test_exact_long_phrase():
    p = "the context window the model can actually use is a small fraction of the limit"
    words, starts = build(p, p)
    assert_keep_last(words, starts)


def test_exact_min_length_phrase():
    words, starts = build("things like cyber", "things like cyber attacks happen")
    # cut take 1; keeper is the second (longer) take
    r = R(words)
    assert len(r) == 1
    assert r[0][0] == pytest.approx(starts[0])
    assert r[0][1] == pytest.approx(starts[1])


# ---------------------------------------------------------------------------
# 2. Substitutions (reinflection / single word changes)
# ---------------------------------------------------------------------------

def test_substitution_midphrase():
    words, starts = build("the whole prompt needed to be fixed",
                          "the whole prompt needs to be fixed")
    assert_keep_last(words, starts)


def test_substitution_near_end():
    words, starts = build("we shipped the new model yesterday",
                          "we shipped the new model today")
    assert_keep_last(words, starts)


def test_substitution_before_seed_leading_words_recovered():
    """A substitution in the leading words (before any exact 3-gram seed).

    'alpha bravo charlie delta echo foxtrot' vs 'alpha XXXX charlie delta echo
    foxtrot'. The only exact 3-gram seed is 'charlie delta echo'; the leading
    'alpha <sub>' must still be cut, not stranded as a stutter.
    """
    words, starts = build("alpha bravo charlie delta echo foxtrot",
                          "alpha zulu charlie delta echo foxtrot")
    assert_keep_last(words, starts)


def test_two_nonadjacent_substitutions():
    """Two single-word changes separated by matching words — still one sentence."""
    words, starts = build("the fast new model runs really well today",
                          "the quick new model runs pretty well today")
    assert_keep_last(words, starts)


# ---------------------------------------------------------------------------
# 3. Transpositions (adjacent word swap — common alignment artifact)
# ---------------------------------------------------------------------------

def test_transposition_midphrase():
    words, starts = build("follow for AI more fundamentals",
                          "follow for more AI fundamentals")
    assert_keep_last(words, starts)


def test_transposition_at_start():
    words, starts = build("model the is extremely fast now",
                          "the model is extremely fast now")
    assert_keep_last(words, starts)


def test_transposition_with_exact_prefix():
    words, starts = build("we know the cat sat down quietly",
                          "we know the cat down sat quietly")
    assert_keep_last(words, starts)


# ---------------------------------------------------------------------------
# 4. Truncation / abandonment
# ---------------------------------------------------------------------------

def test_truncated_middle_take_three_takes():
    """Long take, short abandoned take, full keeper (the 'memory having to' shape)."""
    full = "memory having to hold a value for every token at once"
    words, starts = build(full, "memory having to hold a", full + " done")
    assert_keep_last(words, starts)


def test_truncated_first_take():
    """Abandoned short first take, full second take (keeper)."""
    words, starts = build("the model runs", "the model runs locally every time")
    r = R(words)
    assert len(r) == 1
    assert r[0][0] == pytest.approx(starts[0])
    assert r[0][1] == pytest.approx(starts[1])


# ---------------------------------------------------------------------------
# 5. Insertions / deletions / inter-take filler
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Inserted word misaligns the leading words against the seed; the n-gram "
    "matcher has no insertion/deletion (indel) step, so 'the model um' is "
    "stranded. Needs indel-aware alignment (the utterance/LCS rewrite)."))
def test_inserted_filler_word_in_first_take():
    words, starts = build("the model um runs locally now",
                          "the model runs locally now")
    assert_keep_last(words, starts)


def test_dropped_word_in_keeper():
    words, starts = build("the model runs locally now",
                          "the model runs locally")
    r = R(words)
    assert len(r) == 1
    assert r[0][0] == pytest.approx(starts[0])
    assert r[0][1] == pytest.approx(starts[1])


def test_filler_between_takes_absorbed():
    """'uh sorry' between two attempts should be cut along with the failed take."""
    words, starts = build("the model runs locally now", "uh sorry",
                          "the model runs locally now")
    r = R(words)
    assert len(r) == 1
    assert r[0][0] == pytest.approx(starts[0])
    assert r[0][1] == pytest.approx(starts[2])  # keeper is the third segment


# ---------------------------------------------------------------------------
# 6. Leading / trailing divergence on the abandoned take
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "The stray leading 'so' has no counterpart in the keeper, so matching alone "
    "cannot recover it; cutting it requires snapping the cut back to the "
    "preceding silence (utterance) boundary — gap data this pass doesn't see."))
def test_leading_insertion_on_abandoned_take():
    """Abandoned take has an extra leading word absent from the keeper.

    'so the model runs locally now' → 'the model runs locally now'. The stray
    leading 'so' belongs to the failed take and should be cut.
    """
    words, starts = build("so the model runs locally now",
                          "the model runs locally now")
    assert_keep_last(words, starts)


# Real clip: salesforce-idle-kubernetes-agent (2026-06-24), ~1:00–1:07.
# Three segments back-to-back:
#   seg1  "they could easily see that it was."   ← flub of scripted "…see it."
#   seg2  "it was literally the no…"             ← abandoned false start
#   seg3  "it was literally that nobody could cut it."  ← the good take
# Two *different* disfluencies are stacked here, and only one is a retake:
#   • seg2→seg3 is a true retake ("it was literally" repeats) — detected & cut.
#   • seg1's tail "that it was" is a SCRIPT substitution ("see it" → "see that
#     it was"), not a repeat of anything. It leaks into the kept audio as
#     "…they could easily see that it was. It was literally that nobody…".
# These two tests pin both halves: the retake half must keep working (below),
# and the leaked-flub half is captured as the xfail spec further down.

def test_salesforce_abandoned_take_is_cut_leftover_documented():
    """The abandoned 'it was literally the no…' take is correctly cut.

    This is the half the retake detector *can* see: 'it was literally' repeats
    in seg2 and seg3, so the cut runs from seg2's start to seg3's (the keeper).
    seg1 and seg3 are kept. Regression guard: do not let a future change to the
    leading-flub problem below break this correct, repetition-based cut.

    Note what survives: seg1's tail 'that it was' stays in the kept audio. That
    is expected here and is the subject of the xfail spec immediately below — it
    is out of scope for *repetition*-based detection.
    """
    words, starts = build("they could easily see that it was",
                          "it was literally the no",
                          "it was literally that nobody could cut it")
    r = R(words)
    assert len(r) == 1, f"expected exactly the seg2 retake cut, got {r}"
    assert r[0][0] == pytest.approx(starts[1]), "cut should start at the abandoned take"
    assert r[0][1] == pytest.approx(starts[2]), "cut should end at the keeper (seg3)"


@pytest.mark.xfail(strict=True, reason=(
    "seg1's tail 'that it was' is a script substitution ('see it' → 'see that "
    "it was'), not a repeat — no counterpart exists in any later take, so "
    "repetition matching structurally cannot reach it. It is also HARDER than "
    "test_leading_insertion_on_abandoned_take: the leftover sits across the "
    "region's largest silence (the seg1→seg2 pause), so snapping the cut back "
    "to the nearest silence boundary stops short of it. Cutting it needs "
    "alignment against the teleprompter script (the cluster/script-similarity "
    "rewrite in RETAKE_DETECTION_NOTES.md), which knows the line was 'see it'."))
def test_salesforce_leading_flub_sentence_should_also_be_cut():
    """Ideal: the leading flubbed sentence is absorbed into the cut too.

    seg1 'they could easily see that it was' should collapse to the scripted
    'they could easily see', dropping the 'that it was' substitution. Combined
    with the seg2 retake cut, the single ideal cut therefore runs from seg1's
    'that' through to the keeper (seg3) — flips to XPASS when the rewrite that
    consults the script lands, forcing a deliberate review.
    """
    words, starts = build("they could easily see that it was",
                          "it was literally the no",
                          "it was literally that nobody could cut it")
    that_start = words[4].start  # they(0) could(1) easily(2) see(3) that(4)
    r = R(words)
    assert len(r) == 1, f"expected one merged cut, got {r}"
    assert r[0][0] == pytest.approx(that_start), "cut should start at the leading flub 'that'"
    assert r[0][1] == pytest.approx(starts[2]), "cut should end at the keeper (seg3)"


def test_trailing_junk_on_abandoned_take_absorbed():
    """Trailing flub on the abandoned take is between matched-end and keeper → cut."""
    words, starts = build("the model runs locally now wait no",
                          "the model runs locally now")
    assert_keep_last(words, starts)


# ---------------------------------------------------------------------------
# 7. Time window
# ---------------------------------------------------------------------------

def test_within_gap_window_is_cut():
    words, starts = build("the model runs locally now", "the model runs locally now",
                          inter=8.0)
    assert_keep_last(words, starts)


def test_beyond_gap_window_not_cut():
    words, _ = build("the model runs locally now", "the model runs locally now",
                     inter=20.0)
    assert R(words) == []


# ---------------------------------------------------------------------------
# 8. Negatives — must NOT cut
# ---------------------------------------------------------------------------

def test_unique_sentence_no_cut():
    words, _ = build("the model runs locally on a laptop without any cloud at all")
    assert R(words) == []


def test_coincidental_overlap_divergent_context_no_cut():
    """Two different sentences that briefly share a phrase but diverge → no cut."""
    words, _ = build("i really doubt the new model is anywhere near fast enough yet",
                     "everybody already agrees the new model is clearly the best option")
    assert R(words) == []


def test_two_distinct_sentences_sharing_one_trigram_no_cut():
    """Two distinct sentences sharing one 3-gram ('the model is') score
    match_len=3 / cut_len=6 = ratio 0.50, exactly at min_match_ratio. A ratio
    sitting exactly on the threshold is a coincidental overlap, not a retake, so
    it is not cut (keep condition is strict `>`)."""
    words, _ = build("i think the model is fast",
                     "we know the model is slow")
    assert R(words) == []


def test_two_word_stutter_not_a_retake():
    """A sub-min_retake_words repeat ('the the') is a stutter, out of scope here."""
    words, _ = build("the the model runs locally now")
    assert R(words) == []


def test_common_phrase_far_apart_no_cut():
    words, _ = build("the model is fast and that really matters a lot for us",
                     "the model is slow", inter=18.0)
    assert R(words) == []


# ---------------------------------------------------------------------------
# 9. Multiple independent clusters
# ---------------------------------------------------------------------------

def test_two_separate_retake_clusters():
    """Two unrelated retake events in one transcript → two distinct cuts."""
    words, starts = build(
        "the model runs locally now",       # cluster A take 1
        "the model runs locally now",       # cluster A keeper
        "context windows keep getting bigger every year",  # unrelated bridge
        "performance still degrades badly under load",      # cluster B take 1
        "performance still degrades badly under load",      # cluster B keeper
        inter=1.0,
    )
    r = R(words)
    assert len(r) == 2, f"expected 2 clusters, got {r}"
    assert r[0][0] == pytest.approx(starts[0])
    assert r[0][1] == pytest.approx(starts[1])
    assert r[1][0] == pytest.approx(starts[3])
    assert r[1][1] == pytest.approx(starts[4])


# ---------------------------------------------------------------------------
# 10. Normalization (case / punctuation must not matter)
# ---------------------------------------------------------------------------

def test_case_insensitive_match():
    words, starts = build("The Model Runs Locally Now", "the model runs locally now")
    assert_keep_last(words, starts)


def test_punctuation_insensitive_match():
    words, starts = build("the model runs, locally now.", "the model runs locally now")
    assert_keep_last(words, starts)
