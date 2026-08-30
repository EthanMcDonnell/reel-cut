# ReelCut portfolio media — review pack

This is the review gate for portfolio media.

**In use now:**

- **Identity mark** — `identity/playcut.svg`, the root README header and the
  ReelCut row artwork on the personal site.
- **"One run, end to end" figure** — a to-scale anatomy of a single real run
  (the `reddit-kafka-kubernetes-dns` package): the Claude commands, the
  transcript with a cut retake and the image triggers marked, a source ribbon
  showing the auto-cut, and a three-lane render (title / captions / images) with
  the six article-image overlays remapped onto the output timeline. It is *not a
  file in this pack* — it lives as an ASCII block in the root
  [`README.md`](../../README.md) and as a rendered component on the personal-site
  ReelCut page. Time blocks and text only; no footage, audio, or face, so it
  carries no clearance hold.

The figure replaced the earlier before/after thesis. A single rendered frame
reads as a caption tool; a 130-second take becoming an 87-second Reel — retakes
and dead air cut automatically, captions and a title card burned in, article
screenshots and a concept image placed by script word, then rendered twice for
the trail — is the actual argument for an *editor*, and none of it shows in one
frame.

> [!IMPORTANT]
> The three **poster** stills show an identifiable person. They are superseded by
> the figure and not planned for use; if they are ever wanted, they stay at
> `candidate` until the owner confirms the footage, music, and spoken material
> may appear on a public portfolio.

## Candidates

| Asset | Role | Source / provenance | Privacy / accuracy check | Status | Draft alt text |
| --- | --- | --- | --- | --- | --- |
| "One run, end to end" figure | Primary portfolio media | The real `reddit-kafka-kubernetes-dns` package — `.captions.json`, `.debug.*.txt`, `images.json`, `manifest.json`, `headings.json` | Time blocks and text only; no person, footage, or audio | `approved` — root README + personal site | "A to-scale anatomy of one run: a 130s take, its auto-cut, and a three-lane 87s render with title, captions and six article images." |
| [`identity/playcut.svg`](identity/playcut.svg) | Icon logo | Original geometry on the shared 512 grid | Original geometry; no person, footage, or audio | `approved` — selected mark | "A charcoal play triangle knocked out of a gold tile and severed by one diagonal cut." |
| [`posters/01-source-take.jpg`](posters/01-source-take.jpg) | "Before" still | Frame at 57.031s of `assets/ht-ghd-better-gitcli/DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV` | Shows an identifiable person | `superseded` — held | "An unedited vertical phone-video source take, labelled as an 88.4-second original." |
| [`posters/02-final-render.jpg`](posters/02-final-render.jpg) | "After" still | Frame at 31.500s of `output/ht-ghd-better-gitcli/git-cli-isnt-a-personality.mp4` | Shows an identifiable person | `superseded` — held | "A final ReelCut render with gold serif title card and burned-in captions." |
| [`posters/03-before-after.jpg`](posters/03-before-after.jpg) | Proof comparison still | The two frames above, side by side | Shows an identifiable person | `superseded` — held | "Side-by-side comparison of one instant of an unedited source take and the finished ReelCut render of it." |
| [`identity/options.png`](identity/options.png) | Icon-direction sheet | Generated from the three SVGs by `make_identity_sheet.py` | Original geometry only | `reference` — the family Playcut was picked from | "Three ReelCut icon directions in gold on charcoal: Playcut, Cut and Transcript." |

## Identity review

**Playcut is the selected mark** — see [`identity/README.md`](identity/README.md).
It is the header of the root [`README.md`](../../README.md) and the ReelCut row
artwork on the personal site. `cut.svg` and `transcript.svg` are kept as a
family, not discarded. A follow-up should redraw Playcut at final export sizes
rather than reusing the review vector everywhere.

## Regenerating

Both generated assets have a script, so a review comment can be answered by
changing a number rather than by hand-editing an image:

```
python3 docs/portfolio/make_posters.py          # the three posters
python3 docs/portfolio/make_posters.py --map    # reprint the output -> source time mapping
python3 docs/portfolio/make_identity_sheet.py   # identity/options.svg and .png
```

Both read the existing package and write only inside `docs/portfolio/`. Raw source
footage and the original final MP4s stay in the ignored `assets/` and `output/`
directories; this pack contains only review derivatives.

## Capture notes

- Capture date: 2026-08-29.
- Existing raw source: `DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV`, 1080 × 1920, 88.436667 seconds.
- Existing final render: `git-cli-isnt-a-personality.mp4`, 1080 × 1920 H.264, 39.603000 seconds.
- No terminal recordings or CLI screenshots are kept here. The earlier `vhs` tape
  and its two captures were removed on review: they read as filler next to the
  render, and the pipeline's real work is a model pass with nothing to show.

## Approval gate

The identity mark and "the cut" figure are cleared and in use — both are original
geometry / data with no person, audio, or footage in them. The poster stills are
superseded; if they are ever revisited, confirm public use of the visible person,
the spoken material, and the music first, and do not move or delete the original
provenance files.
