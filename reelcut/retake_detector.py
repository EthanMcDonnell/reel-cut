"""Retake detector — find repeated phrases and return time ranges to cut."""
from __future__ import annotations

import re
from .transcriber import WordTimestamp


def detect_retakes(
    words: list[WordTimestamp],
    min_retake_words: int = 4,
) -> list[tuple[float, float]]:
    """Detect repeated phrases (retakes) in a word list.

    Scans the transcript for sequences of >= min_retake_words consecutive words that
    appear more than once. For each repeated sequence, all occurrences except the
    final one are treated as failed takes and returned as (start, end) time ranges
    to cut.

    The cut range spans from the start of the repeated phrase to the start of the
    final (kept) occurrence, so it removes both the failed words and any dead air
    between takes.

    Args:
        words: Chronologically ordered word timestamps from a single clip.
        min_retake_words: Minimum phrase length (in words) to qualify as a retake.
            Prevents common short phrases ("you know", "I think") from triggering cuts.

    Returns:
        List of (start_s, end_s) time ranges to cut, sorted by start time,
        with overlapping ranges merged.
    """
    if min_retake_words < 2 or len(words) < min_retake_words * 2:
        return []

    normalized = [_normalize(w.word) for w in words]
    n = len(normalized)

    # Build n-gram index: phrase tuple → list of word-start indices
    ngram_index: dict[tuple[str, ...], list[int]] = {}
    for i in range(n - min_retake_words + 1):
        ngram = tuple(normalized[i : i + min_retake_words])
        if not all(ngram):  # skip n-grams containing empty tokens (punctuation-only words)
            continue
        ngram_index.setdefault(ngram, []).append(i)

    # For each repeated n-gram, collect (earlier_start, later_start) pairs.
    # The cut region is [words[earlier_start].start, words[later_start].start)
    # i.e. everything from where the speaker first said the phrase up to where
    # they restarted — removing the failed take AND the pause between takes.
    raw_cuts: set[tuple[int, int]] = set()
    for starts in ngram_index.values():
        if len(starts) < 2:
            continue
        # Only pair consecutive occurrences; non-consecutive are subsumed by merging.
        for k in range(len(starts) - 1):
            i, j = starts[k], starts[k + 1]
            # Require a meaningful gap: j must be beyond the end of i's n-gram,
            # otherwise it's just a naturally overlapping phrase, not a restart.
            if j <= i + min_retake_words:
                continue
            raw_cuts.add((i, j))

    if not raw_cuts:
        return []

    # Merge overlapping word-index ranges before converting to times
    sorted_cuts = sorted(raw_cuts)
    merged_idx: list[tuple[int, int]] = [sorted_cuts[0]]
    for start, end in sorted_cuts[1:]:
        prev_start, prev_end = merged_idx[-1]
        if start <= prev_end:
            merged_idx[-1] = (prev_start, max(prev_end, end))
        else:
            merged_idx.append((start, end))

    # Convert word indices → time ranges
    return [
        (words[start].start, words[end].start)
        for start, end in merged_idx
        if start < len(words) and end < len(words)
    ]


def _normalize(word: str) -> str:
    """Lowercase and strip all non-alphabetic characters."""
    return re.sub(r"[^a-z]", "", word.lower())
