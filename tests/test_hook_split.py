"""Tests for the per-hook EDL splitter used by `reelcut render-hooks`."""
import pytest

from reelcut.captions_doc import CaptionWord, EdlEntry
from reelcut.hook_split import _section_of, build_hook_edl, drop_covered
from reelcut.image_spec import ImageSpec


def _keep(start, end, clip="c.mp4"):
    return EdlEntry(source_clip=clip, start=start, end=end, keep=True, reason="speech")


def _cut(start, end, clip="c.mp4"):
    return EdlEntry(source_clip=clip, start=start, end=end, keep=False, reason="silence")


# A full take with no internal cuts, so each keep entry's output start == its
# source start: hook0 [0,3), hook1 [3,6), hook2 [6,9), body [9,30).
FULL_EDL = [_keep(0, 3), _keep(3, 6), _keep(6, 9), _keep(9, 30)]
HOOK_WINDOWS = [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]


class TestSectionOf:
    def test_assigns_hooks_and_body(self):
        assert _section_of(0.0, HOOK_WINDOWS, 9.0) == 0
        assert _section_of(3.0, HOOK_WINDOWS, 9.0) == 1
        assert _section_of(6.0, HOOK_WINDOWS, 9.0) == 2
        assert _section_of(9.0, HOOK_WINDOWS, 9.0) == "body"
        assert _section_of(20.0, HOOK_WINDOWS, 9.0) == "body"

    def test_boundary_fuzz_lands_in_right_section(self):
        # A few ms either side of a card edge partitions by the card *start*.
        assert _section_of(2.998, HOOK_WINDOWS, 9.0) == 0
        assert _section_of(3.001, HOOK_WINDOWS, 9.0) == 1
        assert _section_of(5.998, HOOK_WINDOWS, 9.0) == 1
        assert _section_of(6.001, HOOK_WINDOWS, 9.0) == 2

    def test_before_first_hook_folds_into_hook_zero(self):
        assert _section_of(-0.5, HOOK_WINDOWS, 9.0) == 0


class TestBuildHookEdl:
    def test_keeps_target_hook_and_body_flips_others(self):
        new_edl, hook_dur, drop = build_hook_edl(FULL_EDL, HOOK_WINDOWS, target_idx=1)

        # hook0 and hook2 flipped to cuts; hook1 and body kept.
        keeps = [(e.start, e.end) for e in new_edl if e.keep]
        assert keeps == [(3, 6), (9, 30)]
        cuts = [(e.start, e.end) for e in new_edl if not e.keep]
        assert cuts == [(0, 3), (6, 9)]
        assert all(e.reason == "outtake" for e in new_edl if not e.keep)

        assert hook_dur == 3.0  # hook1's kept output duration → rebased card end
        assert drop == {"c.mp4": [(0, 3), (6, 9)]}

    def test_first_hook(self):
        new_edl, hook_dur, drop = build_hook_edl(FULL_EDL, HOOK_WINDOWS, target_idx=0)
        assert [(e.start, e.end) for e in new_edl if e.keep] == [(0, 3), (9, 30)]
        assert hook_dur == 3.0
        assert drop == {"c.mp4": [(3, 6), (6, 9)]}

    def test_does_not_mutate_input(self):
        build_hook_edl(FULL_EDL, HOOK_WINDOWS, target_idx=2)
        assert all(e.keep for e in FULL_EDL)  # originals untouched

    def test_splits_a_keep_entry_that_straddles_hook_boundaries(self):
        # One continuous keep entry [0,9) covers all three hooks (hooks aren't
        # separated by EDL cuts), then a body entry [9,30).
        straddle = [_keep(0, 9), _keep(9, 30)]
        new_edl, hook_dur, drop = build_hook_edl(straddle, HOOK_WINDOWS, target_idx=1)

        # Hook 1's slice [3,6) + body [9,30) survive; the entry is split, not
        # swallowed whole into hook 0.
        assert [(e.start, e.end) for e in new_edl if e.keep] == [(3, 6), (9, 30)]
        assert hook_dur == 3.0
        assert drop == {"c.mp4": [(0, 3), (6, 9)]}


class TestDropCovered:
    def test_drops_words_inside_dropped_hooks_only(self):
        drop = {"c.mp4": [(0, 3), (6, 9)]}
        words = [
            CaptionWord(word="a", start=1.0, end=1.2, source_clip="c.mp4"),   # hook0 → drop
            CaptionWord(word="b", start=4.0, end=4.2, source_clip="c.mp4"),   # hook1 → keep
            CaptionWord(word="c", start=7.0, end=7.2, source_clip="c.mp4"),   # hook2 → drop
            CaptionWord(word="d", start=10.0, end=10.2, source_clip="c.mp4"),  # body → keep
        ]
        assert [w.word for w in drop_covered(words, drop)] == ["b", "d"]

    def test_keeps_items_on_other_clips(self):
        drop = {"c.mp4": [(0, 3)]}
        imgs = [
            ImageSpec(type="screenshot", start=1.0, end=2.0, source_clip="c.mp4"),   # drop
            ImageSpec(type="screenshot", start=1.0, end=2.0, source_clip="other.mp4"),  # keep
        ]
        kept = drop_covered(imgs, drop)
        assert len(kept) == 1 and kept[0].source_clip == "other.mp4"

    def test_boundary_word_at_interval_upper_edge_is_kept(self):
        # The target section's first word starts exactly on the boundary, but the
        # drop interval's upper bound is rounded a hair *above* it by float remap
        # imprecision. Without EPS tolerance it would be swept into the dropped
        # section and its caption would vanish (the real "Dropbox on hook4" bug).
        drop = {"c.mp4": [(2.73, 26.330099999999998)]}
        words = [
            CaptionWord(word="Dropbox", start=26.33, end=26.75, source_clip="c.mp4"),
        ]
        assert [w.word for w in drop_covered(words, drop)] == ["Dropbox"]

    def test_word_on_interior_seam_of_dropped_run_is_still_dropped(self):
        # A dropped section spans two touching intervals (EDL-split seam at 10.71).
        # A word sitting on that interior seam must NOT leak through the EPS hole —
        # coalescing the run applies EPS only to its true outer edge.
        drop = {"c.mp4": [(10.56, 10.7101), (10.7101, 16.5)]}
        words = [
            CaptionWord(word="So", start=10.71, end=10.85, source_clip="c.mp4"),
        ]
        assert drop_covered(words, drop) == []


# Real numbers from the utf-8-character-encoding clip, whose last hook window ends
# exactly on a keep entry's edge — the case that shipped ten truncated renders. The
# cut entries matter: output time is derived from them, so the float accumulation that
# triggers the bug only reproduces with the real EDL, gaps included.
REAL_EDL = [
    _keep(7.405, 9.279),
    _cut(9.279, 9.657),
    _keep(9.657, 10.559),
    _cut(10.559, 12.251),
    _keep(12.251, 16.53),
    _cut(16.53, 18.09),
    _keep(18.09, 22.97),
    _cut(22.97, 24.77),
    _keep(24.77, 28.72),
    _cut(28.72, 28.81),
    _keep(28.81, 29.74),
    _cut(29.74, 36.01),
    _keep(36.01, 41.31),   # output 16.815 -> 22.115, ending exactly on body_start
    _cut(41.31, 50.42),
    _keep(50.42, 53.35),   # first body entry
]
REAL_HOOK_WINDOWS = [
    (0.0, 2.926), (2.926, 7.205), (7.205, 12.085), (12.085, 16.965), (16.965, 22.115),
]
REAL_BODY_S = 53.35 - 50.42


class TestBoundaryOnKeepEntryEdge:
    """A section boundary landing *on* a keep entry's end must not split it.

    `o_end` is accumulated through the remap, so it can land a few float-ulps above a
    boundary equal to it (here 22.115 < 22.115000000000006). Without an epsilon margin
    that boundary counts as interior and splits off a ~7e-15s piece, which ffmpeg
    extracts to a corrupt segment; the concat demuxer then stops there and silently
    truncates the render to just the hook.
    """

    def test_float_error_really_puts_o_end_above_body_start(self):
        # Pin the arithmetic the bug depends on, so the case can't silently stop
        # reproducing if the numbers are ever edited.
        o_start = 16.815
        o_end = o_start + (41.31 - 36.01)
        assert o_end > 22.115
        assert o_end - 22.115 < 1e-9

    def test_emits_no_subframe_keep_segments(self):
        # The degenerate piece is ~7e-15s long — positive, so a `<= 0` check misses it.
        # The invariant that matters is that every keep segment survives extraction:
        # anything shorter than a frame writes a corrupt segment. Legitimate splits here
        # are >=0.15s, so 1ms cleanly separates them (same margin as EPS above).
        for target in range(len(REAL_HOOK_WINDOWS)):
            new_edl, _, _ = build_hook_edl(REAL_EDL, REAL_HOOK_WINDOWS, target_idx=target)
            degenerate = [
                (e.start, e.end) for e in new_edl if e.keep and e.end - e.start < 1e-3
            ]
            assert not degenerate, f"hook {target}: sub-frame keep segment(s) {degenerate}"

    def test_entry_ending_on_body_start_is_not_split_there(self):
        # Signature of the bug: a keep sliver at the entry's own end (41.31), which is
        # what truncated the concat. Hook 4's window legitimately splits this entry at
        # 16.965, so assert on the trailing edge specifically, not on the split count.
        for target in range(len(REAL_HOOK_WINDOWS)):
            new_edl, _, _ = build_hook_edl(REAL_EDL, REAL_HOOK_WINDOWS, target_idx=target)
            assert not [
                e for e in new_edl if e.keep and e.start > 41.3 and e.end <= 41.31
            ], f"hook {target}: entry split at its own end"
