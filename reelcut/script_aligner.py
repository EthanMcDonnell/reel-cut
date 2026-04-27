"""Script aligner — exact word matching and best-take selection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .transcriber import WordTimestamp


@dataclass
class AlignedSegment:
    """A contiguous run of words matched to a portion of the script."""
    script_start_idx: int       # index into script word list
    script_end_idx: int         # inclusive
    words: list[WordTimestamp]
    clip_path: str
    is_last_take: bool = True   # False if this take was superseded


@dataclass
class AlignmentResult:
    segments: list[AlignedSegment]
    missing_lines: list[str]    # script words/phrases with no matching footage
    outtakes: list[list[WordTimestamp]]  # word runs that didn't match the script


def load_script(script_path: str | Path) -> list[str]:
    """Read script file and return a normalized list of words."""
    text = Path(script_path).read_text(encoding="utf-8")
    return _normalize_words(text)


def align_to_script(
    words: list[WordTimestamp],
    script_path: str | Path,
) -> AlignmentResult:
    """Align word timestamps to the script using exact word matching.

    Strategy:
    - Slide a window over the transcript words trying to match each script word.
    - When multiple takes of the same script region exist, keep only the last one.
    - Words not matching the script are collected as outtakes.
    - Script words with no matching transcript are reported as missing.
    """
    script_words = load_script(script_path)
    if not script_words:
        raise ValueError("Script is empty.")

    transcript_normalized = [_normalize(w.word) for w in words]

    # Find all contiguous runs in the transcript that match the script
    runs = _find_matching_runs(transcript_normalized, script_words)

    # Select best take: for overlapping script regions, keep the last run
    best_runs = _select_last_takes(runs, len(script_words))

    # Build AlignedSegment objects
    segments: list[AlignedSegment] = []
    covered_transcript_indices: set[int] = set()

    for run in best_runs:
        t_start, t_end, s_start, s_end = run
        seg_words = words[t_start : t_end + 1]
        segments.append(AlignedSegment(
            script_start_idx=s_start,
            script_end_idx=s_end,
            words=seg_words,
            clip_path=seg_words[0].clip_path if seg_words else "",
        ))
        covered_transcript_indices.update(range(t_start, t_end + 1))

    segments.sort(key=lambda s: s.script_start_idx)

    # Outtakes: transcript words not in any aligned segment
    outtakes: list[list[WordTimestamp]] = []
    current_outtake: list[WordTimestamp] = []
    for i, w in enumerate(words):
        if i not in covered_transcript_indices:
            current_outtake.append(w)
        else:
            if current_outtake:
                outtakes.append(current_outtake)
                current_outtake = []
    if current_outtake:
        outtakes.append(current_outtake)

    # Missing script words: script positions not covered by any segment
    covered_script = set()
    for seg in segments:
        covered_script.update(range(seg.script_start_idx, seg.script_end_idx + 1))
    missing_lines = [script_words[i] for i in range(len(script_words)) if i not in covered_script]

    return AlignmentResult(
        segments=segments,
        missing_lines=missing_lines,
        outtakes=outtakes,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common spoken contractions → expanded forms (and vice-versa).
# Both sides are stored already-normalized (no apostrophes, lowercase).
_CONTRACTION_MAP: dict[str, str] = {
    "gonna": "going",   # "gonna" → first word of "going to"
    "wanna": "want",
    "gotta": "got",
    "kinda": "kind",
    "sorta": "sort",
    "lotta": "lot",
    "shouldve": "should",
    "wouldve": "would",
    "couldve": "could",
    "mustve": "must",
    "mightve": "might",
    "shouldnt": "should",
    "wouldnt": "would",
    "couldnt": "could",
    "didnt": "did",
    "doesnt": "does",
    "dont": "do",
    "isnt": "is",
    "arent": "are",
    "wasnt": "was",
    "werent": "were",
    "hasnt": "has",
    "havent": "have",
    "hadnt": "had",
    "wont": "will",
    "cant": "can",
    "its": "it",
    "im": "i",
    "ive": "i",
    "youre": "you",
    "youve": "you",
    "youll": "you",
    "theyre": "they",
    "theyve": "they",
    "theyll": "they",
    "weve": "we",
    "hes": "he",
    "shes": "she",
    "thats": "that",
    "whats": "what",
    "hows": "how",
    "whos": "who",
    "theres": "there",
    "heres": "here",
    "wheres": "where",
}


def _normalize(word: str) -> str:
    """Lowercase, strip all punctuation including apostrophes, apply contraction folding."""
    cleaned = re.sub(r"[^a-z0-9]", "", word.lower())
    # Fold contracted/spoken forms to their base so "gonna" matches "going", etc.
    return _CONTRACTION_MAP.get(cleaned, cleaned)


def _normalize_words(text: str) -> list[str]:
    return [w for w in (_normalize(t) for t in text.split()) if w]


def _find_matching_runs(
    transcript: list[str],
    script: list[str],
) -> list[tuple[int, int, int, int]]:
    """Find all (t_start, t_end, s_start, s_end) runs where transcript[t_start:t_end+1]
    matches script[s_start:s_end+1] as a contiguous sequence."""
    runs: list[tuple[int, int, int, int]] = []
    n_t = len(transcript)
    n_s = len(script)

    t = 0
    while t < n_t:
        best_run = None
        for s in range(n_s):
            # Try to extend a match starting at t, s
            length = 0
            while (
                t + length < n_t
                and s + length < n_s
                and transcript[t + length] == script[s + length]
            ):
                length += 1
            if length > 0 and (best_run is None or length > best_run[1]):
                best_run = (s, length)

        if best_run:
            s_start, length = best_run
            runs.append((t, t + length - 1, s_start, s_start + length - 1))
            t += length
        else:
            t += 1

    return runs


def _select_last_takes(
    runs: list[tuple[int, int, int, int]],
    n_script: int,
) -> list[tuple[int, int, int, int]]:
    """For each script position, keep only the last (latest in transcript) matching run."""
    # Map script_start → list of runs covering that script position
    by_script_pos: dict[int, list[tuple[int, int, int, int]]] = {}
    for run in runs:
        t_start, t_end, s_start, s_end = run
        for s in range(s_start, s_end + 1):
            by_script_pos.setdefault(s, []).append(run)

    # For each script position, pick the run with the highest t_start (last take)
    selected: set[tuple[int, int, int, int]] = set()
    for s_pos, candidates in by_script_pos.items():
        last = max(candidates, key=lambda r: r[0])
        selected.add(last)

    # Return deduplicated list in transcript order
    return sorted(selected, key=lambda r: r[0])
