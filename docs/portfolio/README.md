# ReelCut portfolio media — review pack

This is the review gate for portfolio media. The identity mark below is
**approved** and now in use (repo README header, personal-site row artwork); the
poster stills are still on hold — see the note below.

The pack deliberately shows **the product's output, not its terminal**. ReelCut is
driven from a CLI, but a recording of a prompt is a poor argument for a video
editor and the interesting work happens in the model pass, which does not
screenshot. What is left is the thing that can be judged on sight: a raw phone
take and the Reel that came out the other end.

Both stills are the **same instant of the same take**. Output 31.500s maps back to
source 57.031s through the EDL in the package's `.captions.json`, so the pair
shows one moment before and after the pipeline rather than two unrelated frames.
The candidates use the existing, user-designated `ht-ghd-better-gitcli` package —
a real render, not a fabricated timeline or a styled mockup.

> [!IMPORTANT]
> The three **poster** stills show an identifiable person. Keep them at
> `candidate` until the owner confirms the footage, music, and spoken material
> may appear on a public portfolio. The identity mark is original geometry and is
> not subject to that hold.

## Candidates

| Asset | Role | Source / provenance | Privacy / accuracy check | Status | Draft alt text |
| --- | --- | --- | --- | --- | --- |
| [`posters/01-source-take.jpg`](posters/01-source-take.jpg) | "Before" still | Frame at 57.031s of `assets/ht-ghd-better-gitcli/DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV` | Labelled "Source Take / Unedited"; raw source duration is 88.436667s | `candidate` | "An unedited vertical phone-video source take, labelled as an 88.4-second original." |
| [`posters/02-final-render.jpg`](posters/02-final-render.jpg) | "After" still | Frame at 31.500s of `output/ht-ghd-better-gitcli/git-cli-isnt-a-personality.mp4` — the same spoken word as the frame above | Labelled "ReelCut Output"; final H.264 render duration is 39.603s | `candidate` | "A final ReelCut render with gold serif title card and burned-in captions." |
| [`posters/03-before-after.jpg`](posters/03-before-after.jpg) | Proof comparison still | The two exact frames above, shown side by side | States both timestamps and that they are the same instant of the take | `candidate` | "Side-by-side comparison of one instant of an unedited source take and the finished ReelCut render of it." |
| [`identity/playcut.svg`](identity/playcut.svg) | Icon logo | Original geometry on the shared 512 grid | Original geometry; no person, footage, or audio | `approved` — selected mark | "A charcoal play triangle knocked out of a gold tile and severed by one diagonal cut." |
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

The identity mark is cleared and in use. Before promoting any **poster** to the
personal site, confirm public use of the visible person, the spoken material, and
the music. Once approved, copy web-sized derivatives into the site; do not move or
delete the original provenance files.
