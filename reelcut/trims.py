"""Trims — optional body lines a hook variant can drop, resolved to exact EDL spans.

The script marks a removable body sentence with a `[cut-N]` prefix (N = removal priority;
lines sharing N are one unit, always cut together). This module finds each marked line in
the transcript and turns it into a source-time span that a variant render flips to a cut.

A trim only ever runs from one existing EDL cut to the next — never from a word timestamp.
The pipeline already cuts the silence at almost every sentence break, from the previous
word's measured speech end to the next word's onset minus the speech pad. A trim covering
exactly the keep spans between two of those cuts merges with them, so the new splice is
built from the same measured edges as every other join in the video. A line with no cut on
one side (the speaker ran two sentences together) is rejected rather than cut at a word
timestamp, because that join would sound like an edit.

No I/O — pure functions; `reelcut trims` reads the files and writes trims.json.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

MARKER = re.compile(r"^\[cut-(\d+)\]\s*")

# Same bar as script coverage (debug_report.SCRIPT_COVERAGE_MIN): an ad-libbed delivery of
# a line scores >= 0.84 against its sentence while a different line scores ~0.4.
MATCH_MIN = 0.65

# Words outside the line a trim may take with it when snapping out to the nearest cut —
# an ad-libbed opener ("See,", "So") delivered without a pause.
MAX_EXTRA = 2

# A lowercase one of these right across a trim edge means the line was delivered joined to
# its neighbour.
_CONNECTIVES = {"and", "but", "so", "or", "because", "which", "that", "then", "than"}

_TERMINAL = (".", "!", "?")

# Slack when comparing a cut edge to a word edge. A gap cut starts at the measured speech
# end (>= the word's end) and ends a speech pad before the next word.
_TOL = 0.05


def marked_lines(script_text: str) -> list[tuple[int, str]]:
    """`(unit, text)` for every `[cut-N]` line in the script's **SCRIPT** section."""
    section, out = None, []
    for raw in script_text.splitlines():
        line = raw.strip()
        header = re.match(r"^\*\*(.+?)\*\*\s*$", line)
        if header:
            section = header.group(1).rstrip(":")
            continue
        m = MARKER.match(line)
        if section == "SCRIPT" and m:
            out.append((int(m.group(1)), line[m.end():]))
    return out


def _norm(s: str) -> str:
    """Lowercase words for alignment. A hyphen splits ("UTF-32" → "utf 32") because Whisper
    writes the same thing as two words ("UTF", "-32")."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("'", "")).strip()


def _cut_boundaries(kept: list, runs: dict) -> set[int]:
    """Indices k where a cut (or a clip edge) sits between kept[k-1] and kept[k]."""
    out = {0, len(kept)}
    for k in range(1, len(kept)):
        a, b = kept[k - 1], kept[k]
        if a.source_clip != b.source_clip or any(
            s >= a.end - _TOL and e <= b.start + _TOL for s, e in runs.get(a.source_clip, [])
        ):
            out.add(k)
    return out


def _locate(line: str, kept: list, lo: int) -> tuple[float, int, int]:
    """`(ratio, i, j)`: the words kept[i:j] that deliver `line`, searching from index `lo`.

    A fuzzy window finds the line (same matcher and bar as script coverage), then a word-level
    alignment pins its first and last words — the window's own edges flex by two words to
    tolerate re-wording, which is too loose for a cut.
    """
    from .debug_report import _best_window

    ratio, wi, wj = _best_window(line, kept[lo:])
    if ratio < MATCH_MIN:
        return ratio, 0, 0
    r0 = max(lo, lo + wi - 3)
    region = kept[r0:lo + wj + 3]
    blocks = [b for b in SequenceMatcher(
        None, _norm(line).split(), [_norm(w.word) for w in region], autojunk=False,
    ).get_matching_blocks() if b.size]
    return ratio, r0 + blocks[0].b, r0 + blocks[-1].b + blocks[-1].size


def _span(kept: list, a: int, b: int, edl: list, runs: dict) -> tuple[float, float]:
    """Source span for kept[a:b], whose edges are cut boundaries: from the end of the cut
    after kept[a-1] to the start of the cut before kept[b] (or the clip's own edges)."""
    clip = kept[a].source_clip
    clip_keeps = [e for e in edl if e.keep and e.source_clip == clip]
    prev, nxt = (kept[a - 1] if a > 0 else None), kept[b]
    if prev is None or prev.source_clip != clip:
        start = clip_keeps[0].start
    else:
        start = next(e for s, e in runs[clip] if s >= prev.end - _TOL)
    if nxt.source_clip != clip:
        end = clip_keeps[-1].end
    else:
        end = [s for s, e in runs[clip] if e <= nxt.start + _TOL][-1]
    return start, end


def _edge_problem(kept: list, i: int, j: int, a: int, b: int) -> str:
    """Why the cuts at kept[a] / kept[b] are not the line's own edges, or "".

    Snapping out to the nearest cut can take a stray word or two with the line (an ad-libbed
    "See,"), which is fine; a whole sentence, or more than MAX_EXTRA words, means the line
    has no cut of its own on that side. A lowercase connective across an edge means it was
    delivered joined to its neighbour ("…16 bits, but it's not…"), so cutting either side
    strands the other.
    """
    if a < i and (i - a > MAX_EXTRA or any(w.word.rstrip().endswith(_TERMINAL) for w in kept[a:i])):
        return f'no cut before "{kept[i].word}": it runs straight on from "{kept[i - 1].word}"'
    if b > j and (b - j > MAX_EXTRA or any(w.word.rstrip().endswith(_TERMINAL) for w in kept[j - 1:b - 1])):
        return f'no cut after "{kept[j - 1].word}": it runs straight on into "{kept[j].word}"'
    for k in (a, b):
        if 0 < k < len(kept) and kept[k].word.strip().rstrip(",") in _CONNECTIVES:
            return (f'delivered joined to its neighbour: "{kept[k - 1].word} {kept[k].word}" '
                    "— cutting here strands the other half")
    return ""


def resolve_trims(doc, marked: list[tuple[int, str]], body_start: float,
                  overlays: list[tuple[str, str, float, float]]) -> list[dict]:
    """Resolve marked lines to trim spans.

    `body_start` is the output time the body begins (the last hook window's end): a trim
    before it would shift the burned-in title cards. `overlays` are `(label, source_clip,
    start, end)` for everything on screen in source time — images and placed zooms. One that
    starts inside a trim vanishes from that variant (the render drops overlays by start
    time); one already on screen when the trim starts would be cut off at the splice
    mid-move, so it rejects the trim.

    Lines of one unit delivered back to back (up to MAX_EXTRA ad-libbed words between
    them) merge into one span. Returns one row per span:
    unit, text, source_clip, start, end, seconds, also_removes (words outside the line that
    go with it), status ("ok" | "rejected"), reason, vanishes.
    """
    from .cli import _build_edl_remap, _cut_runs, _in_cut_run

    remap, _ = _build_edl_remap(doc.edl)
    runs = _cut_runs(doc.edl)
    clip_order = {c: n for n, c in enumerate(doc.source_clips)}
    kept = sorted(
        (w for w in doc.words if not _in_cut_run(w.source_clip, w.start, runs)),
        key=lambda w: (clip_order.get(w.source_clip, 0), w.start),
    )
    lo = next((k for k, w in enumerate(kept)
               if remap(w.source_clip, w.start) >= body_start - 1e-3), len(kept))
    bounds = sorted(b for b in _cut_boundaries(kept, runs) if b >= lo)

    # Locate every line, then merge a unit's lines that were delivered back to back.
    located: dict[int, list[list]] = {}
    rows = []
    for unit, text in marked:
        ratio, i, j = _locate(text, kept, lo)
        if ratio < MATCH_MIN:
            rows.append({"unit": unit, "text": text, "status": "rejected",
                         "reason": f"not found in the body (best match {ratio:.2f})"})
            continue
        spans = located.setdefault(unit, [])
        if spans and 0 <= i - spans[-1][1] <= MAX_EXTRA:
            spans[-1][1], spans[-1][2] = j, spans[-1][2] + " " + text
        else:
            spans.append([i, j, text])

    for unit, spans in located.items():
        for i, j, text in spans:
            row = {"unit": unit, "text": text, "source_clip": kept[i].source_clip}
            a = max((b for b in bounds if b <= i), default=None)
            b = min((b for b in bounds if b >= j), default=None)
            if a is None:
                problem = "starts inside the hooks"
            elif kept[a].source_clip != kept[b - 1].source_clip:
                problem = "spans two source clips"
            else:
                problem = _edge_problem(kept, i, j, a, b) or (
                    "is the last line of the video" if b >= len(kept) else "")
            if problem:
                rows.append({**row, "status": "rejected", "reason": f"line {problem}"})
                continue
            start, end = _span(kept, a, b, doc.edl, runs)
            crossing, vanishes = [], []
            for label, clip, s, e in overlays:
                if clip != row["source_clip"] or not (s < end and e > start):
                    continue
                if s >= start - _TOL:
                    vanishes.append(label)
                else:
                    crossing.append(f"{label} ({s:.2f}–{e:.2f}s)")
            seconds = sum(max(0.0, min(e.end, end) - max(e.start, start))
                          for e in doc.edl if e.keep and e.source_clip == row["source_clip"])
            row.update(start=round(start, 4), end=round(end, 4), seconds=round(seconds, 2),
                       also_removes=" ".join(w.word for w in kept[a:i] + kept[j:b]))
            if crossing:
                rows.append({**row, "status": "rejected",
                             "reason": "on screen when the trim starts: " + "; ".join(crossing)
                             + f" — end it by {start:.2f}"})
            else:
                rows.append({**row, "status": "ok", "reason": "", "vanishes": vanishes})
    return sorted(rows, key=lambda r: (r["unit"], r.get("start", 0.0)))


def usable_units(rows: list[dict]) -> dict[int, list[tuple[str, float, float]]]:
    """`{unit: [(source_clip, start, end), …]}` for every unit whose lines all resolved."""
    out: dict[int, list] = {}
    bad = {r["unit"] for r in rows if r["status"] != "ok"}
    for r in rows:
        if r["unit"] not in bad:
            out.setdefault(r["unit"], []).append((r["source_clip"], r["start"], r["end"]))
    return out


def stale_spans(edl: list, spans: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Spans whose edges no longer sit on the EDL's cuts (or clip edges).

    trims.json is resolved against one EDL; re-running /prepare-video rebuilds it, and a span
    from the old one would cut into speech without any error.
    """
    from .cli import _cut_runs

    runs = _cut_runs(edl)
    out = []
    for clip, s, e in spans:
        keeps = [x for x in edl if x.keep and x.source_clip == clip]
        starts = [ce for _, ce in runs.get(clip, [])] + [x.start for x in keeps[:1]]
        ends = [cs for cs, _ in runs.get(clip, [])] + [x.end for x in keeps[-1:]]
        if not any(abs(s - t) < 2e-3 for t in starts) or not any(abs(e - t) < 2e-3 for t in ends):
            out.append((clip, s, e))
    return out


def apply_trims(edl: list, spans: list[tuple[str, float, float]]) -> list:
    """`edl` with each span flipped to a cut (reason "trim"), splitting keep entries at its
    edges — a span normally covers whole keep entries already, but a per-hook EDL is split
    at section boundaries."""
    import dataclasses

    out = list(edl)
    for clip, s, e in spans:
        nxt = []
        for x in out:
            if x.source_clip != clip or not x.keep or x.end <= s or x.start >= e:
                nxt.append(x)
                continue
            if x.start < s:
                nxt.append(dataclasses.replace(x, end=s))
            nxt.append(dataclasses.replace(x, start=max(x.start, s), end=min(x.end, e),
                                           keep=False, reason="trim"))
            if x.end > e:
                nxt.append(dataclasses.replace(x, start=e))
        out = nxt
    return out
