# ReelCut portfolio media — review pack

This is the review gate for portfolio media.

**In use now:**

- **Identity mark** — `identity/playcut.svg`, the root README header and the
  ReelCut row artwork on the personal site.
- **"One take, six Reels" figure** — an exploded assembly drawing of a single
  real run (the `claude-text-watermark` package), organised as **TAKE → CUT →
  SHIP**: three hook variants recorded back to back, the shared body auto-cut
  once, then six output Reels drawn aligned on the hook→body *splice* so the
  shared body reads as one column and the hooks vary in length. Covers the
  retake detector keeping the hook openers, captions, per-Reel title cards, the
  five article screenshots and two concept images (shared, drawn once under the
  body), retranscription, and the six-way trail. It is *not a file in this pack*
  — it lives as an ASCII block in the root [`README.md`](../../README.md) and as
  a rendered component on the personal-site ReelCut page. Time blocks and text
  only; no footage, audio, or face, so it carries no clearance hold.

The figure replaced the earlier before/after thesis. A single rendered frame
reads as a caption tool; one 111-second phone recording that holds three hooks
and a body, cut once and split into six posted Reels, is the actual argument for
an *editor*, and none of it shows in one frame.

> [!IMPORTANT]
> The three **poster** stills show an identifiable person. They are superseded by
> the figure and not planned for use; if they are ever wanted, they stay at
> `candidate` until the owner confirms the footage, music, and spoken material
> may appear on a public portfolio.

## Candidates

| Asset | Role | Source / provenance | Privacy / accuracy check | Status | Draft alt text |
| --- | --- | --- | --- | --- | --- |
| "One take, six Reels" figure | Primary portfolio media | The real `claude-text-watermark` package — `captions.json`, `debug.*.txt`, `images.json`, `videos.json`, `output/.published` | Time blocks and text only; no person, footage, or audio | `approved` — root README + personal site | "An exploded assembly drawing: a 111s take holding three hooks and a shared body, auto-cut, then six Reels aligned on the hook-to-body splice." |
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
