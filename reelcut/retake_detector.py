"""Retake detector — find repeated phrases and return time ranges to cut."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from .transcriber import WordTimestamp


@dataclass
class RetakeCandidate:
    ngram: tuple[str, ...]  # the initial matched n-gram words
    cut_len: int            # j - i (word count being cut)
    match_len: int          # extended match length after greedy forward scan
    ratio: float            # match_len / cut_len
    kept: bool              # True = cut was applied
    skip_reason: str = ""   # non-empty when kept=False
    cut_start_s: float = 0.0
    cut_end_s: float = 0.0


def detect_retakes(
    words: list[WordTimestamp],
    min_retake_words: int = 4,
    max_retake_gap_s: float = 20.0,
    min_match_ratio: float = 0.5,
    max_retake_bridge_s: float = 1.0,
    max_retake_skip: int = 1,
    take_boundary_s: float = 2.0,
    max_retake_span_s: float = 60.0,
    min_reword_overlap: float = 0.6,
    min_reword_content_words: int = 3,
    no_pause_gap_s: float = 0.45,
    no_pause_min_ratio: float = 0.75,
    detect_aborted: bool = True,
) -> tuple[list[tuple[float, float]], list[RetakeCandidate]]:
    """Detect repeated phrases (retakes) in a word list.

    Scans the transcript for sequences of >= min_retake_words consecutive words that
    recur with at most max_retake_gap_s of silence between consecutive takes. For each
    repeated sequence, the match is extended greedily forward to measure true overlap.
    Only pairs where extended_match_len / cut_len > min_match_ratio are treated as
    retakes, preventing short coincidental phrase overlaps from triggering large
    erroneous cuts. A ratio exactly on the threshold is treated as a coincidental
    overlap and not cut.

    All occurrences except the final one are treated as failed takes and returned as
    (start, end) time ranges to cut. The cut range spans from the start of the repeated
    phrase to the start of the final (kept) occurrence. A cut whose span (the duration
    of the discarded take(s)) exceeds max_retake_span_s is dropped as a safety net —
    this bounds take *length*, separate from max_retake_gap_s, which bounds the gap
    *between* takes.

    A second, independent pass (_detect_reworded_takes) then catches failed takes that
    were re-recorded with DIFFERENT wording: the positional matcher above only sees
    contiguous literal repeats, so a take reworded with different connective words
    slips through. That pass compares whole sentences by stopword-filtered content-word
    overlap (min_reword_overlap over min_reword_content_words), and its cuts are unioned
    with the positional ones. Both are then snapped to take boundaries (silence gaps or
    sentence ends), so a cut never begins or ends inside an utterance.

    Returns:
        Tuple of:
        - List of (start_s, end_s) time ranges to cut, sorted and merged.
        - List of RetakeCandidate objects for every evaluated pair (kept and skipped).
    """
    if min_retake_words < 2 or len(words) < min_retake_words * 2:
        return [], []

    normalized = [_normalize(w.word) for w in words]
    n = len(normalized)
    boundary = _take_boundaries(words, take_boundary_s)

    # Build n-gram index: phrase tuple → list of word-start indices.
    # Each n-gram is indexed under its identity AND its single-adjacent-swap
    # variants, so a transposed retake still seeds a candidate without lowering
    # min_retake_words. Transcription/alignment commonly swaps an adjacent word
    # pair ("for AI more" vs "for more AI"); the swap breaks every exact n-gram,
    # leaving too short an exact run to seed. Indexing swap variants lets the two
    # takes collide on the n-gram that spans the swap. The backward extension
    # below then recovers any leading words the (interior) seed skipped over.
    ngram_index: dict[tuple[str, ...], list[int]] = {}
    for i in range(n - min_retake_words + 1):
        ngram = tuple(normalized[i : i + min_retake_words])
        if not all(ngram):  # skip n-grams containing empty tokens (punctuation-only words)
            continue
        for key in _swap_variants(ngram):
            ngram_index.setdefault(key, []).append(i)

    raw_cuts: set[tuple[int, int]] = set()
    candidates: list[RetakeCandidate] = []
    seen: set[tuple[int, int]] = set()  # dedup seed pairs reached via multiple keys

    for ngram, starts in ngram_index.items():
        if len(starts) < 2:
            continue
        # Pair each occurrence against (a) its immediate successor and (b) the
        # final occurrence. Consecutive pairing catches an early take that matches
        # its neighbour but diverges from the keeper. Pairing against the final
        # occurrence (the take that is always kept) catches an early take whose
        # immediate successor was a truncated/abandoned fragment: that short
        # fragment makes match_len small relative to cut_len (the long first take),
        # failing the ratio gate, so the early take's leading words would otherwise
        # survive as a stutter ("memory having to" → "memory having to hold a…").
        # Non-consecutive interior pairs are subsumed by the min(end) merge below.
        last = starts[-1]
        for idx in range(len(starts) - 1):
            i = starts[idx]
            partners = [starts[idx + 1]]
            if last != starts[idx + 1]:
                partners.append(last)
            for j in partners:
                if (i, j) in seen:  # same pair can surface under several swap keys
                    continue
                seen.add((i, j))
                # Require a meaningful gap: j must be beyond the end of i's n-gram.
                if j < i + min_retake_words:
                    continue

                # Greedily extend the match forward beyond the initial n-gram.
                # A genuine retake sounds like what it replaces — it will extend far.
                # A coincidental phrase overlap in different contexts will not extend.
                # Tolerate isolated single-word differences (e.g. a reinflected word
                # like "needed" vs "needs") so one swapped word doesn't truncate an
                # otherwise-clear repeat. Skipped words don't count toward match_len,
                # and a run of > max_retake_skip consecutive mismatches means the
                # content has genuinely diverged, so the scan stops there.
                ext = min_retake_words      # words consumed from each occurrence
                match_len = min_retake_words  # words that actually matched (skips excluded)
                skips = 0
                while i + ext < n and j + ext < n:
                    if normalized[i + ext] == normalized[j + ext]:
                        match_len += 1
                        ext += 1
                        skips = 0
                    elif skips < max_retake_skip:
                        skips += 1
                        ext += 1
                    else:
                        break
                cut_len = j - i

                # Extend the match backward over preceding words, mirroring the
                # forward scan (same single-skip tolerance). A seed can land *inside*
                # the take — a swap variant splits off a shorter exact prefix, and a
                # substitution before the seed ("alpha bravo …" vs "alpha zulu …")
                # breaks every earlier n-gram — so without this the take's leading
                # words are stranded as a stutter. Both occurrences shift back
                # together, so cut_len is unchanged; recovered matches count toward
                # match_len. `back` tracks the last *matched* word so trailing skips
                # never push the boundary onto an unmatched (kept) word.
                b = back = back_match = bskips = 0
                while i - b - 1 >= 0 and j - b - 1 > i + ext - 1 and normalized[i - b - 1]:
                    if normalized[i - b - 1] == normalized[j - b - 1]:
                        b += 1
                        back = b
                        back_match += 1
                        bskips = 0
                    elif bskips < max_retake_skip:
                        b += 1
                        bskips += 1
                    else:
                        break
                match_len += back_match
                ci, cj = i - back, j - back

                # Proximity guard: a retake follows hard on the take it replaces, so the
                # silence *between* them is short. Measure that pause at the cut boundary
                # (end of the failed take's last word cj-1 → start of the keeper at cj) —
                # only known after the backward extension locates the boundary. Measuring
                # from the seed instead either spans the failed take's body (seed at take
                # start, inflating the gap so long back-to-back retakes are wrongly
                # rejected) or falls inside the keeper (interior seed, hiding a real gap).
                if words[cj].start - words[cj - 1].end > max_retake_gap_s:
                    continue
                ratio = match_len / cut_len

                kept = ratio > min_match_ratio
                why = "" if kept else f"ratio {ratio:.2f} <= threshold {min_match_ratio:.2f}"

                # Re-recording a line means stopping and starting again, so a genuine
                # retake has a break between the two occurrences: a pause of at least
                # no_pause_gap_s, or a sentence end. When there is neither — the speaker
                # ran straight from one into the other inside a single sentence — the
                # repeat is just as likely to be deliberate parallel phrasing ("one entity
                # as 10 copies of lull, the next as 10 copies of that"), which
                # min_match_ratio alone waves through at 0.57 and then cuts the first half
                # of a real sentence.
                #
                # The break is deliberately measured against a small gap rather than
                # take_boundary_s: retakes follow hard on the take they replace, so the
                # pause between them is a beat, not a take-length silence. Across the clip
                # corpus that beat is 0.66s at the tightest, while the widest gap inside a
                # continuously-spoken parallel construction is 0.30s.
                #
                # Without that break, the only evidence for a retake is the delivery:
                # either the speaker audibly cut themselves off (a trail-off ellipsis
                # inside the discarded span), or what they said is so nearly all re-said
                # that nothing is lost by dropping it. Measured across the clip corpus
                # every genuine no-pause retake clears one of those two — ratios 0.83-1.00,
                # or a trail-off at 0.60 — while parallel phrasing has neither.
                stopped = any(
                    words[k].start - words[k - 1].end >= no_pause_gap_s
                    or _is_sentence_end(words[k - 1].word)
                    for k in range(ci + 1, cj + 1)
                )
                if kept and not stopped:
                    trail_off = any(_is_trail_off(w.word) for w in words[ci:cj])
                    if not (trail_off or ratio >= no_pause_min_ratio):
                        kept = False
                        why = (f"no pause between the takes and ratio {ratio:.2f} "
                               f"< {no_pause_min_ratio:.2f} with no trail-off — reads as "
                               f"deliberate repetition, not a retake")

                candidates.append(RetakeCandidate(
                    ngram=ngram,
                    cut_len=cut_len,
                    match_len=match_len,
                    ratio=ratio,
                    kept=kept,
                    skip_reason=why,
                    cut_start_s=words[ci].start,
                    cut_end_s=words[cj].start,
                ))
                if kept:
                    raw_cuts.add((ci, cj))

    # Second, independent pass: catch REWORDED whole-sentence retakes the literal
    # n-gram matcher misses (a take re-recorded with different connective words shares
    # most of its content but no long contiguous run, so the positional ratio gate
    # rejects it). Compared on stopword-filtered content-word overlap per sentence.
    reworded = _detect_reworded_takes(
        words, min_reword_overlap, min_reword_content_words, max_retake_gap_s
    )

    # Third, independent pass: catch SHORT aborted restarts both passes above miss. A
    # 1-2 word opener that trails off and is immediately re-said ("It's called Amazon…
    # It's called Magic Pocket…") shares too short a run to seed the positional matcher,
    # and the abort lands on the first content word so the reworded overlap is near zero.
    aborted = (
        _detect_aborted_restarts(words, max_retake_gap_s, min_retake_words, take_boundary_s)
        if detect_aborted else []
    )

    if not raw_cuts and not reworded and not aborted:
        return [], candidates

    # Convert word-index pairs → time ranges, then merge overlapping ones.
    # Merging in index space with max(end) is wrong: multiple anchor points for
    # the same retake (e.g. cash→matches→the→start→of each produce a separate
    # (i,j) pair with j stepping deeper into the final take) would expand j far
    # beyond the true cut boundary. Converting first and using min(end) collapses
    # all anchor variants to the earliest boundary = start of the final take.
    time_cuts_raw = sorted(
        (words[i].start, words[j].start)
        for i, j in raw_cuts
        if i < len(words) and j < len(words)
    )

    merged: list[tuple[float, float]] = []
    for t_start, t_end in time_cuts_raw:
        if merged and t_start < merged[-1][1]:   # overlapping → same retake event
            merged[-1] = (merged[-1][0], min(merged[-1][1], t_end))
        else:                                    # adjacent/separate → keep distinct
            merged.append((t_start, t_end))

    # Discard any range whose span exceeds max_retake_span_s. The span is the duration
    # of the discarded take(s) (first failed take → final keeper), which scales with
    # sentence length, so it gets its own larger cap — decoupled from max_retake_gap_s,
    # which bounds only the silence between consecutive takes. This is a safety net
    # against a runaway merge; genuine retakes are gated by the ratio test above.
    time_ranges = [
        (t_start, t_end)
        for t_start, t_end in merged
        if t_end - t_start <= max_retake_span_s
    ]

    # Bridge tiny gaps between consecutive ranges of the same retake cluster.
    # Each range ends at the start of a later take (min-rule above), but different
    # n-grams within one cluster anchor at different word offsets — and an
    # intervening short flubbed take can break the consecutive-pairing chain for
    # the shallowest-anchored n-gram. The result is a sub-second gap between two
    # cut ranges (e.g. "See, the" stranded at the start of an otherwise-cut take).
    # Within a retake cluster there is no kept content before the final take, so
    # any small gap between two cut ranges is a failed-take fragment and must be
    # absorbed. The bridge threshold stays well under the duration of a real
    # spoken take of a >= min_retake_words phrase, so genuinely distinct retake
    # events (separated by the kept successful take) are never merged.
    bridged: list[tuple[float, float]] = []
    for t_start, t_end in time_ranges:
        if bridged and t_start - bridged[-1][1] <= max_retake_bridge_s:
            bridged[-1] = (bridged[-1][0], t_end)
        else:
            bridged.append((t_start, t_end))

    # Fold the positional and reworded-take cuts into one set, bridge sub-second gaps
    # between them (a reworded take's cut often abuts the literal cut of the next take
    # in the same cluster), then snap the unified set to take boundaries.
    combined = sorted(bridged + reworded)
    rebridged: list[tuple[float, float]] = []
    for t_start, t_end in combined:
        if rebridged and t_start - rebridged[-1][1] <= max_retake_bridge_s:
            rebridged[-1] = (rebridged[-1][0], max(rebridged[-1][1], t_end))
        else:
            rebridged.append((t_start, t_end))

    snapped = _snap_to_take_boundaries(
        rebridged, words, take_boundary_s, max_retake_span_s, min_reword_overlap
    )

    # Aborted-restart cuts are already exactly bounded (failed head's take start →
    # keeper start), so they bypass snapping: the failed head trails off with only a
    # breath before the keeper — a sub-take-boundary gap that _snap_to_take_boundaries
    # would misread as interior and walk forward across the keeper, swallowing it.
    # Union them in and merge any overlap with the snapped cuts.
    if aborted:
        allcuts = sorted(snapped + aborted)
        snapped = [allcuts[0]]
        for s, e in allcuts[1:]:
            if s <= snapped[-1][1]:
                snapped[-1] = (snapped[-1][0], max(snapped[-1][1], e))
            else:
                snapped.append((s, e))
    return snapped, candidates


def _take_boundaries(words: list[WordTimestamp], take_boundary_s: float) -> list[bool]:
    """boundary[k] is True when word k starts a new take.

    A take starts either after a silence at least take_boundary_s long OR right after
    a sentence-final word (".", "?", "!"). The punctuation case is essential: a speaker
    often runs a KEPT sentence straight into the next failed take with only a breath
    (< take_boundary_s) between them, so silence alone can't tell them apart. The clip
    start (k == 0) is deliberately NOT a boundary: snapping must only ever land on a
    real pause/sentence end, never run to the clip edge across intervening kept content.
    """
    return [
        k > 0 and (
            words[k].start - words[k - 1].end >= take_boundary_s
            or _is_sentence_end(words[k - 1].word)
        )
        for k in range(len(words))
    ]


def _snap_to_take_boundaries(
    ranges: list[tuple[float, float]],
    words: list[WordTimestamp],
    take_boundary_s: float,
    max_reach_s: float,
    reword_overlap: float,
) -> list[tuple[float, float]]:
    """Snap each cut's endpoints to take boundaries (silence gaps >= take_boundary_s).

    The pairwise matcher anchors cuts on shared *content* words, so a cut can begin
    or end inside a failed take rather than on a take boundary:

      * Its END lands mid-take when an early take's tail happens to match a later
        keeper's tail ("…virus or stolen password…") while the early take's own
        keeper is a *different, later* take. The min-end merge then stops the cut at
        that interior word, stranding the rest of the failed take as a duplicate.
      * Its START lands mid-take when the failed take opens with words that have no
        counterpart in the keeper ("With no particular…" vs "See there was no…"),
        so nothing matches them and they survive as a stutter.

    A genuine keeper always begins right after a real pause, so a cut endpoint that
    sits *inside* an utterance (no flanking silence) is never a keeper boundary —
    snap it to the enclosing take's boundary so no half-take is left behind. Which
    boundary depends on whether that take is another failed one or the keeper; see
    the END branch below.
    """
    if not ranges:
        return ranges
    n = len(words)
    boundary = _take_boundaries(words, take_boundary_s)

    snapped: list[tuple[float, float]] = []
    for t_start, t_end in ranges:
        # The range was built from word .start times, so these map back exactly.
        ci = next((k for k in range(n) if words[k].start >= t_start - 1e-6), n)
        cj = next((k for k in range(n) if words[k].start >= t_end - 1e-6), n)

        # START: cut opens mid-take → pull back to that take's first word, but only when
        # the words being absorbed are a short divergent head of a *failed take*, not a
        # unique lead-in the retake never reproduced. A genuine failed take is a whole
        # re-attempt of the keeper, so its unanchored leading words are few. When the
        # retake instead restarted MID-SENTENCE (only a tail fragment re-said, e.g.
        # "…refactor into a simple code" → "into a simple config change"), the span from
        # the take boundary to the cut start is the sentence's unique body — longer than
        # the whole keeper take. Snapping back would swallow that kept lead-in, stranding
        # the keeper as a subjectless fragment. So bail when the preamble being absorbed
        # spans more words than the keeper itself.
        #
        # Length alone is not enough, because a unique lead-in can also be SHORTER than
        # the keeper. The failed take's head is only a divergent restatement worth
        # absorbing when the keeper has a head of its own for it to diverge FROM
        # ("with no particular virus…" → "see there was no virus…": both takes open with
        # unmatched words before the shared core). When the keeper instead begins exactly
        # on the matched core, nothing in it corresponds to those leading words — they are
        # content that was never re-said, and snapping back deletes it outright ("A booting
        # gateway grabs only the last 12 hours, older ones don't matter." → "Older ones
        # don't matter, since…", where the 12-hour window survives in no other take).
        if ci < n and not boundary[ci]:
            k = ci
            while k > 0 and not boundary[k]:
                k -= 1
            ke = cj + 1
            while ke < n and not boundary[ke]:
                ke += 1
            # Walk back from the keeper's first word to ITS take boundary. Zero means the
            # keeper take opens on the match point and has no counterpart head.
            kb = min(cj, n - 1)
            while kb > 0 and not boundary[kb]:
                kb -= 1
            preamble_words = ci - k        # boundary → cut start (failed take's head)
            keeper_words = ke - cj         # keeper's first word → its take boundary
            keeper_head = cj - kb if cj < n else 0   # keeper's own unmatched head
            if (boundary[k] and t_start - words[k].start <= max_reach_s
                    and preamble_words <= keeper_words and keeper_head > 0):
                t_start = words[k].start

        # END: cut closes mid-take. The take holding cj is one of two things, and the
        # snap direction is opposite for each:
        #
        #   * ANOTHER FAILED TAKE — an early take's tail matched a later keeper's tail
        #     while its own keeper is a different, later take, so the min-end merge
        #     stopped the cut inside this intermediate take. Push FORWARD to the next
        #     take, absorbing the rest of it.
        #   * THE KEEPER ITSELF — the two takes diverge just before the anchor ("-8
        #     skips that problem…" vs "UTF-8 skips this problem altogether…"), so the
        #     backward extension stalls and cj lands mid-keeper. Pushing forward here
        #     deletes the last occurrence outright: the whole point of the pass is that
        #     every occurrence *except* the final one is cut. Pull BACK to the keeper's
        #     own take start instead, so the cut ends exactly where the keeper begins.
        #
        # A failed take is by definition re-said by what comes after it; the keeper is
        # not. So compare the material being absorbed against the take that follows it —
        # high content overlap means it is a duplicate and safe to absorb, near-zero
        # means it is content that survives in no other take.
        #
        # The forward reach is measured over the absorbed *speech* (up to the last word
        # before the boundary), not including the boundary silence — a long inter-take
        # pause must not push the span over max_reach_s and abandon a correct snap.
        if cj < n and not boundary[cj]:
            k = cj
            while k < n and not boundary[k]:
                k += 1
            k2 = k + 1
            while k2 < n and not boundary[k2]:
                k2 += 1
            absorbed = _content_words(words[cj:k])
            n_absorbed = sum(absorbed.values())
            re_said = bool(n_absorbed) and (
                sum((absorbed & _content_words(words[k:k2])).values()) / n_absorbed
                >= reword_overlap
            )
            if re_said:
                if k < n and words[k - 1].end - t_end <= max_reach_s:
                    t_end = words[k].start
            else:
                kb = cj
                while kb > 0 and not boundary[kb]:
                    kb -= 1
                if boundary[kb] and words[kb].start > t_start:
                    t_end = words[kb].start

        snapped.append((t_start, t_end))

    # Snapping can push neighbouring cuts into overlap — re-merge.
    snapped.sort()
    out: list[tuple[float, float]] = [snapped[0]]
    for s, e in snapped[1:]:
        if s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


# Generic glue words carry no topical meaning, so they would inflate the content
# overlap between two unrelated sentences that merely share grammar. Excluded from
# the reworded-take overlap so the signal is the topical words a real retake repeats.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "it", "its", "was", "were", "is", "are",
    "am", "be", "been", "to", "of", "in", "on", "at", "so", "that", "this", "these",
    "those", "with", "as", "for", "i",
})


def _is_sentence_end(word: str) -> bool:
    """True when a word ends a sentence (terminal . ? !), excluding an ellipsis (…),
    which marks a trailing-off mid-thought rather than a sentence boundary."""
    return bool(re.search(r"[.?!]$", word)) and not word.endswith("...")


def _content_words(seg: list[WordTimestamp]) -> "Counter[str]":
    """Multiset of stopword-filtered, normalized content words in a sentence."""
    return Counter(
        norm for norm in (_normalize(w.word) for w in seg)
        if norm and norm not in _STOPWORDS
    )


def _detect_reworded_takes(
    words: list[WordTimestamp],
    min_overlap: float,
    min_content_words: int,
    max_gap_s: float,
) -> list[tuple[float, float]]:
    """Find failed takes that were re-recorded with DIFFERENT wording.

    The positional matcher (above) scores match_len / (j - i): a reworded take shares
    its content words but reorders them and swaps connective tissue, so it has no long
    contiguous run and the ratio gate rejects it. Here each sentence is compared to
    later sentences by content-word overlap instead. A sentence is a failed take when a
    later sentence (within max_gap_s of silence) shares >= min_overlap of its content
    words in BOTH directions — the shared words are a majority of each sentence, so the
    two are re-reads of the same script line rather than one being a longer, different
    sentence that merely reuses a few of the other's words. The cut spans just that
    sentence (start → next sentence start), so the true keeper and any unique sentence
    sitting between the take and its reprise are left untouched — overlapping/adjacent
    cuts are unioned by the caller.
    """
    sentences: list[list[WordTimestamp]] = []
    cur: list[WordTimestamp] = []
    for w in words:
        cur.append(w)
        if _is_sentence_end(w.word):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)

    contents = [_content_words(s) for s in sentences]
    cuts: list[tuple[float, float]] = []
    for i, seg in enumerate(sentences):
        ci = contents[i]
        if sum(ci.values()) < min_content_words:
            continue
        for j in range(i + 1, len(sentences)):
            if sentences[j][0].start - seg[-1].end > max_gap_s:
                break  # later sentences only get further away
            cj = contents[j]
            if sum(cj.values()) < min_content_words:
                continue
            # Require the shared content to be a majority of BOTH sentences. A genuine
            # reworded retake re-reads the SAME script line, so the two takes overlap
            # heavily in either direction. Measuring only against the failed take lets a
            # short fragment clear the gate against a much longer, DIFFERENT later
            # sentence that merely reuses a couple of its words — e.g. deliberate
            # parallel phrasing ("you add a replica, so one…" vs a later run-on "…so you
            # add a tool that auto promotes a healthy replica to primary…", forward 0.60
            # but reverse 0.09), which would wrongly cut the earlier line's unique content.
            inter = sum((ci & cj).values())
            if (inter / sum(ci.values()) >= min_overlap
                    and inter / sum(cj.values()) >= min_overlap):
                nxt = sentences[i + 1][0].start if i + 1 < len(sentences) else seg[-1].end
                cuts.append((seg[0].start, nxt))
                break
    return cuts


def _is_trail_off(word: str) -> bool:
    """True when a word trails off mid-thought — ends in an ellipsis ('...' or '…').

    Whisper marks a speaker cutting themselves off with a trailing ellipsis; this is
    the anchor for aborted-restart detection (distinct from _is_sentence_end, which
    excludes the ellipsis precisely because it is NOT a completed sentence)."""
    return word.endswith("...") or word.endswith("…")


def _detect_aborted_restarts(
    words: list[WordTimestamp],
    max_gap_s: float,
    min_retake_words: int,
    take_boundary_s: float,
) -> list[tuple[float, float]]:
    """Find SHORT aborted restarts the positional and reworded passes both miss.

    A speaker opens a sentence, trails off after a word or two (Whisper marks the
    trail-off with an ellipsis), then restarts the SAME sentence from the top:
    "It's called Amazon… It's called Magic Pocket and it holds…". The shared run is
    too short to seed the positional matcher (< min_retake_words), and the abort lands
    on the first content word so the reworded pass sees almost no content overlap —
    both miss it and the failed opener survives as a stutter.

    Anchored on the ellipsis (the trail-off) plus an immediate re-say of the same
    opening prefix. That pairing is what separates a genuine abort from emphasis
    ("I love it. I love this whole thing." — no trail-off) or a dramatic pause (the
    next sentence doesn't repeat the opening). Each cut spans the failed head, from its
    take start to the restart; the caller unions these with the other passes' cuts.
    """
    normalized = [_normalize(w.word) for w in words]
    n = len(words)
    cuts: list[tuple[float, float]] = []
    for e in range(n - 1):
        if not _is_trail_off(words[e].word):
            continue
        r = e + 1  # the restart begins at the word right after the trail-off
        if words[r].start - words[e].end > max_gap_s:
            continue
        # Walk back to the aborted take's first word: the first word after a sentence
        # end, a take-length silence, or the clip start.
        s = e
        while s > 0 and not (
            _is_sentence_end(words[s - 1].word)
            or words[s].start - words[s - 1].end >= take_boundary_s
        ):
            s -= 1
        head_len = e - s + 1
        # Shared leading prefix between the aborted head and the restart, capped at the
        # head length so the scan never runs past the head into the keeper's body.
        p = 0
        while (p < head_len and r + p < n
               and normalized[s + p]
               and normalized[s + p] == normalized[r + p]):
            p += 1
        # Fire only for the short case the other passes miss: a >= 2-word shared opening,
        # the head is all prefix except (at most) its final abort word, and the shared
        # run is below the positional seed length (a >= min_retake_words run is that
        # pass's job). p >= head_len-1 with p < min_retake_words bounds the head short.
        if p >= 2 and p >= head_len - 1 and p < min_retake_words:
            cuts.append((words[s].start, words[r].start))
    return cuts


def _normalize(word: str) -> str:
    """Lowercase and strip everything except letters and digits.

    Digits are KEPT so a number spoken identically across two takes matches: both
    "500"s normalize to "500", not to "". Erasing digits would both bar any n-gram
    spanning the number from seeding (skipped by the `all(ngram)` empty-token guard)
    and halt the backward extension the instant it reached the empty token — stranding
    "Reddit moved 500 Kafka brokers to …" as an uncut stutter because the only usable
    seed sat after the number. Punctuation-only tokens (e.g. "…") still normalize to "".
    """
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _swap_variants(ngram: tuple[str, ...]):
    """Yield the n-gram and each of its single-adjacent-swap variants.

    Lets a transposed retake ("for AI more" ↔ "for more AI") seed a candidate:
    both orderings share a swap-variant key, so they collide in the n-gram index
    even though no exact n-gram repeats between the two takes.
    """
    yield ngram
    for k in range(len(ngram) - 1):
        yield ngram[:k] + (ngram[k + 1], ngram[k]) + ngram[k + 2 :]
