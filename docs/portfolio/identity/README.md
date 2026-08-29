# ReelCut icon directions

ReelCut has no standalone identity asset. These are **three review directions**,
drawn as clean vectors against the gold-on-charcoal title-card system already in
`config.yaml` (`#F3C84E` on `#0B0A09`). None is an official logo yet.

They share one idea rather than three unrelated ones: a single diagonal cut, or
the kerf it leaves, is the constant, and what gets cut is what changes. Whichever
is picked, the other two stay usable as a family — a favicon, a social avatar and
an in-app mark that read as one thing.

| Option | File | What it communicates | Trade-off |
| --- | --- | --- | --- |
| **Cut** *(recommended)* | [`cut.svg`](cut.svg) | A 9:16 output frame severed by one cut, the halves slid apart along it. Says "short-form video" and "edit" in one shape. | The most abstract of the three; says nothing about transcripts. |
| **Playcut** | [`playcut.svg`](playcut.svg) | The same cut through a play triangle, knocked out of a solid gold tile. The only inverted option, so it is the loudest at avatar size. | A play triangle is the most generic video symbol there is; the cut is what makes it specific. |
| **Transcript** | [`transcript.svg`](transcript.svg) | Transcript lines with the spoken one at full strength, cut through by the playhead. This is literally what ReelCut does — trim to the transcript. | Most detailed of the three; the line fragments start to close up below about 32px. |

All three are drawn on the same 512 grid with the cut on the same axis
(`y = 358 - 0.4x`), so they can be compared without allowing for construction
differences.

[`options.png`](options.png) is the review sheet. It is generated from the three
files above, so edit those and re-run:

```
python3 docs/portfolio/make_identity_sheet.py
```

If one direction is approved, redraw only that option into final multi-size
SVG/PNG exports in a follow-up. Avoid creating a new wordmark; the existing
Playfair Display title-card treatment remains ReelCut's primary typographic
identity.
