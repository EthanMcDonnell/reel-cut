"""Retake detector — find repeated phrases and return time ranges to cut."""
from __future__ import annotations

import re
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
) -> tuple[list[tuple[float, float]], list[RetakeCandidate]]:
    """Detect repeated phrases (retakes) in a word list.

    Scans the transcript for sequences of >= min_retake_words consecutive words that
    appear more than once within max_retake_gap_s seconds. For each repeated sequence,
    the match is extended greedily forward to measure true overlap. Only pairs where
    extended_match_len / cut_len > min_match_ratio are treated as retakes, preventing
    short coincidental phrase overlaps from triggering large erroneous cuts. A ratio
    exactly on the threshold is treated as a coincidental overlap and not cut.

    All occurrences except the final one are treated as failed takes and returned as
    (start, end) time ranges to cut. The cut range spans from the start of the repeated
    phrase to the start of the final (kept) occurrence.

    Returns:
        Tuple of:
        - List of (start_s, end_s) time ranges to cut, sorted and merged.
        - List of RetakeCandidate objects for every evaluated pair (kept and skipped).
    """
    if min_retake_words < 2 or len(words) < min_retake_words * 2:
        return [], []

    normalized = [_normalize(w.word) for w in words]
    n = len(normalized)

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
                # Proximity guard: real false starts happen within seconds of each other.
                gap_s = words[j].start - words[i + min_retake_words - 1].end
                if gap_s > max_retake_gap_s:
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
                ratio = match_len / cut_len

                kept = ratio > min_match_ratio
                candidates.append(RetakeCandidate(
                    ngram=ngram,
                    cut_len=cut_len,
                    match_len=match_len,
                    ratio=ratio,
                    kept=kept,
                    skip_reason="" if kept else f"ratio {ratio:.2f} <= threshold {min_match_ratio:.2f}",
                    cut_start_s=words[ci].start,
                    cut_end_s=words[cj].start,
                ))
                if kept:
                    raw_cuts.add((ci, cj))

    if not raw_cuts:
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

    merged: list[tuple[float, float]] = [time_cuts_raw[0]]
    for t_start, t_end in time_cuts_raw[1:]:
        prev_start, prev_end = merged[-1]
        if t_start < prev_end:          # overlapping → same retake event
            merged[-1] = (prev_start, min(prev_end, t_end))
        else:                           # adjacent/separate → keep distinct
            merged.append((t_start, t_end))

    # Discard any range whose span exceeds max_retake_gap_s.
    time_ranges = [
        (t_start, t_end)
        for t_start, t_end in merged
        if t_end - t_start <= max_retake_gap_s
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

    return bridged, candidates


def _normalize(word: str) -> str:
    """Lowercase and strip all non-alphabetic characters."""
    return re.sub(r"[^a-z]", "", word.lower())


def _swap_variants(ngram: tuple[str, ...]):
    """Yield the n-gram and each of its single-adjacent-swap variants.

    Lets a transposed retake ("for AI more" ↔ "for more AI") seed a candidate:
    both orderings share a swap-variant key, so they collide in the n-gram index
    even though no exact n-gram repeats between the two takes.
    """
    yield ngram
    for k in range(len(ngram) - 1):
        yield ngram[:k] + (ngram[k + 1], ngram[k]) + ngram[k + 2 :]
