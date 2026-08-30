# ReelCut icon directions

**[`playcut.svg`](playcut.svg) is the selected ReelCut mark.** It is the header
of the repository's root [`README.md`](../../../README.md) and the row artwork on
the personal site. `cut.svg` and `transcript.svg` are kept, not discarded: they
were drawn as a family and stay usable as a favicon, an in-app mark, or a second
avatar that read as one thing with Playcut.

All three are clean vectors against the gold-on-charcoal title-card system in
`config.yaml` (`#F3C84E` on `#0B0A09`). They share one idea rather than three
unrelated ones: a single diagonal cut, or the kerf it leaves, is the constant,
and what gets cut is what changes.

| Direction | File | What it communicates | Trade-off |
| --- | --- | --- | --- |
| **Playcut** *(selected)* | [`playcut.svg`](playcut.svg) | A play triangle knocked out of a solid gold tile, severed by one cut. The only inverted option, so it is the loudest at avatar size. | A play triangle is the most generic video symbol there is; the cut is what makes it specific. |
| **Cut** | [`cut.svg`](cut.svg) | A 9:16 output frame severed by one cut, the halves slid apart along it. Says "short-form video" and "edit" in one shape. | The most abstract of the three; says nothing about transcripts. |
| **Transcript** | [`transcript.svg`](transcript.svg) | Transcript lines with the spoken one at full strength, cut through by the playhead. This is literally what ReelCut does — trim to the transcript. | Most detailed of the three; the line fragments start to close up below about 32px. |

All three are drawn on the same 512 grid with the cut on the same axis
(`y = 358 - 0.4x`), so they can be compared without allowing for construction
differences.

[`options.png`](options.png) is the review sheet. It is generated from the three
files above, so edit those and re-run:

```
python3 docs/portfolio/make_identity_sheet.py
```

Follow-up worth doing: redraw Playcut into final multi-size SVG/PNG exports
(favicon, 512, 1024) rather than reusing this review vector everywhere. Avoid
creating a new wordmark; the existing Playfair Display title-card treatment
remains ReelCut's primary typographic identity.
