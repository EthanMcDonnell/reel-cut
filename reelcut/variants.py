"""Variant planner — what makes each rendered video of a slug different.

Every video gets a `(flip, trims)` pair: mirrored footage, and the trims.json units its body
drops. The levers are switched on independently in `output.variants` and assigned here
jointly, over one list of videos, so they never collide:

1. Hook 1's first video is the core: full script, unflipped.
2. Copies of one hook differ in their trims while the trim cycle has subsets to spare.
3. Trims spread before they repeat: every unit cut, then each unit alone, then pairs, … then
   the full script again.
4. The same inputs always give the same plan.

The list runs copy-major — every hook's first video, then every hook's second — so with one
copy per hook `alternate` flips hooks 2, 4, 6… No I/O.
"""
from __future__ import annotations

from itertools import combinations


def trim_cycle(units: list[int]) -> list[list[int]]:
    """The order trim subsets are handed out: all units, each alone, then pairs, triples…,
    then none. Duplicates are dropped, so one unit gives `[[1], []]`."""
    units = sorted(units)
    seq = [units] + [[u] for u in units]
    for size in range(2, len(units)):
        seq += [list(c) for c in combinations(units, size)]
    seq.append([])
    out: list[list[int]] = []
    for t in seq:
        if t not in out:
            out.append(t)
    return out


def plan_variants(counts: list[int], flip: str, trim: str,
                  units: list[int]) -> list[list[tuple[bool, list[int]]]]:
    """`(flip, trims)` for each copy of each hook. `counts[h]` is hook h's number of videos."""
    cycle = trim_cycle(units) if trim == "rotate" and units else [[]]
    out: list[list] = [[None] * c for c in counts]
    order = [(h, c) for c in range(max(counts, default=0)) for h in range(len(counts)) if c < counts[h]]
    ptr = 0
    for k, (h, c) in enumerate(order):
        if k == 0:
            out[h][c] = (False, [])
            continue
        flipped = {"off": False, "alternate": k % 2 == 1, "copies": c > 0, "all": True}[flip]
        used = [t for _, t in out[h][:c]]
        step = next((s for s in range(len(cycle)) if cycle[(ptr + s) % len(cycle)] not in used), 0)
        out[h][c] = (flipped, cycle[(ptr + step) % len(cycle)])
        ptr += step + 1
    return out
