"""A trim must splice on edges the pipeline already measured, or not happen at all.

A trim that started or ended at a word timestamp would clip speech or leave a breath
hanging, and it would only show up by ear in one variant of one video.
"""
from reelcut.captions_doc import CaptionsDoc, CaptionWord, EdlEntry
from reelcut.trims import resolve_trims

CLIP = "c.mp4"

# hook | S1 | S2 | S3 S4 — the pipeline cut the silence at every sentence break except
# S3→S4, where the speaker ran straight on. The body starts at output 1.0 (source 1.3).
WORDS = [
    CaptionWord(word=w, start=s, end=e, source_clip=CLIP)
    for w, s, e in [
        ("Hook", 0.05, 0.3), ("line", 0.35, 0.6), ("here.", 0.65, 0.95),
        ("First", 1.35, 1.7), ("point", 1.75, 2.1), ("stands.", 2.15, 2.45),
        ("Extra", 2.85, 3.2), ("colour", 3.25, 3.6), ("here.", 3.65, 3.95),
        ("Final", 4.35, 4.7), ("point", 4.75, 5.1), ("lands.", 5.15, 5.45),
        ("Bye", 5.6, 5.8), ("now.", 5.85, 6.1),
    ]
]


def _edl(*spans):
    return [EdlEntry(source_clip=CLIP, start=s, end=e, keep=k, reason="speech" if k else "silence")
            for s, e, k in spans]


EDL = _edl((0.0, 1.0, True), (1.0, 1.3, False), (1.3, 2.5, True), (2.5, 2.8, False),
           (2.8, 4.0, True), (4.0, 4.3, False), (4.3, 6.25, True))
BODY_START = 1.0


def _resolve(marked, edl=EDL, overlays=()):
    doc = CaptionsDoc(source_clips=[CLIP], edl=edl, words=WORDS)
    return resolve_trims(doc, marked, BODY_START, list(overlays))


def test_trim_runs_exactly_between_the_existing_cuts():
    [row] = _resolve([(1, "Extra colour here.")])
    assert row["status"] == "ok"
    assert (row["start"], row["end"]) == (2.8, 4.0)


def test_line_the_speaker_ran_into_the_next_is_rejected_not_cut_at_a_word():
    [row] = _resolve([(1, "Final point lands.")])
    assert row["status"] == "rejected"
    assert "no cut after" in row["reason"]


def test_hook_line_is_never_matched():
    [row] = _resolve([(1, "Hook line here.")])
    assert row["status"] == "rejected"


def test_overlay_on_screen_when_the_trim_starts_rejects_the_trim():
    [row] = _resolve([(1, "Extra colour here.")], overlays=[("screenshot x", CLIP, 2.0, 3.5)])
    assert row["status"] == "rejected"
    assert "screenshot x" in row["reason"]


def test_unit_lines_with_no_cut_between_them_merge_into_one_span():
    # No cut between S1 and S2: either alone would be rejected, together they are one trim.
    edl = _edl((0.0, 1.0, True), (1.0, 1.3, False), (1.3, 4.0, True), (4.0, 4.3, False),
               (4.3, 6.25, True))
    [row] = _resolve([(1, "First point stands."), (1, "Extra colour here.")], edl=edl)
    assert row["status"] == "ok"
    assert (row["start"], row["end"]) == (1.3, 4.0)


def test_span_from_an_older_edl_is_stale():
    from reelcut.trims import stale_spans
    # /prepare-video re-run: the cut after S2 now ends 0.1s later, so the old span would
    # leave a sliver of silence and start into nothing it was resolved against.
    rebuilt = _edl((0.0, 1.0, True), (1.0, 1.3, False), (1.3, 2.5, True), (2.5, 2.9, False),
                   (2.9, 4.0, True), (4.0, 4.3, False), (4.3, 6.25, True))
    span = (CLIP, 2.8, 4.0)
    assert stale_spans(EDL, [span]) == []
    assert stale_spans(rebuilt, [span]) == [span]


def test_trimmed_variant_is_owed_every_word_but_the_trimmed_ones():
    from reelcut.cli import _hook_caption_survival
    doc = CaptionsDoc(source_clips=[CLIP], edl=EDL, words=WORDS)
    assert _hook_caption_survival(doc, [(0.0, 1.0)], {0: [[(CLIP, 2.8, 4.0)]]}) == []
