"""Tests for the per-hook EDL splitter used by `reelcut render-hooks`."""
from reelcut.captions_doc import CaptionWord, EdlEntry
from reelcut.hook_split import _section_of, build_hook_edl, drop_covered
from reelcut.image_spec import ImageSpec


def _keep(start, end, clip="c.mp4"):
    return EdlEntry(source_clip=clip, start=start, end=end, keep=True, reason="speech")


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
