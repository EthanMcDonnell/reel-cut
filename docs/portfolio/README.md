# ReelCut portfolio media — review pack

This is the review gate for potential portfolio media. Nothing in this folder has been copied to the personal site.

The before/after candidates deliberately use the existing, user-designated **`ht-ghd-better-gitcli`** package. They demonstrate a real raw phone take becoming an actual ReelCut render; they do not use a fabricated timeline, simulated terminal output, or a separately styled mockup.

> [!IMPORTANT]
> The source take shows an identifiable person. Keep every candidate below at `candidate` until the owner confirms the footage, music, and spoken material may appear on a public portfolio.

## Candidates

| Asset | Role | Source / provenance | Privacy / accuracy check | Status | Draft alt text |
| --- | --- | --- | --- | --- | --- |
| [`posters/01-source-take.jpg`](posters/01-source-take.jpg) | “Before” still | Frame at 00:05 from `assets/ht-ghd-better-gitcli/DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV` | Labelled “Source Take / Unedited”; raw source duration is 88.436667s | `candidate` | “An unedited vertical phone-video source take, labelled as an 88.4-second original.” |
| [`posters/02-final-render.jpg`](posters/02-final-render.jpg) | “After” still | Frame at 00:01.8 from `output/ht-ghd-better-gitcli/git-cli-isnt-a-personality.mp4` | Labelled “ReelCut Output”; final H.264 render duration is 39.603s | `candidate` | “A final ReelCut render with gold serif title card, GitHub logo overlay, and burned-in captions.” |
| [`posters/03-before-after.jpg`](posters/03-before-after.jpg) | Proof comparison still | The two exact frames above, shown side by side | Explicitly says that the frames are sampled at different elapsed times | `candidate` | “Side-by-side comparison of an unedited source take and the finished ReelCut render.” |
| [`screenshots/01-timeline.jpg`](screenshots/01-timeline.jpg) | Editing-model still | Real `.venv/bin/reelcut timeline` invocation against the associated captions document | Shows only the first 24 lines of the real output to keep the capture compact; no credentials, endpoints, or home path | `candidate` | “ReelCut terminal output listing word-level positions on the 39.47-second output timeline.” |
| [`screenshots/02-render-artifacts.jpg`](screenshots/02-render-artifacts.jpg) | Render-output still | Real `ffprobe` / `ls` commands in the terminal proof recording | Verifies 88.436667-second source, 39.603000-second render, and both actual output filenames | `candidate` | “Terminal output comparing source and final durations and listing two existing ReelCut render files.” |
| [`recordings/01-terminal-proof.mp4`](recordings/01-terminal-proof.mp4) | CLI proof | A real `vhs` terminal session defined by [`01-cli-before-after.tape`](recordings/01-cli-before-after.tape) | Commands are non-publishing; it runs `reelcut timeline`, `ffprobe`, and `ls` only. Prompt is intentionally generic. | `candidate` | “A terminal recording that runs ReelCut’s timeline command and verifies source/render durations and output files.” |
| [`recordings/01-cli-before-after.mp4`](recordings/01-cli-before-after.mp4) | Complete before-and-after proof | Concatenates the genuine terminal capture with clearly labelled clips from the source take and final render | Every stage is labelled; title cards make edits between the separate real stages explicit | `candidate` | “A proof sequence: ReelCut timeline and artifact commands, the original source take, then the final captioned render.” |
| [`identity/options.png`](identity/options.png) | Icon-direction sheet | Clean vector concepts redrawn after a limited image-generation exploration | Original geometry only; no claim that any option is a final product logo | `candidate` | “Three ReelCut icon options in gold on charcoal: Frame Cut, Splice, and Caption Cursor.” |

## Identity review

See [`identity/README.md`](identity/README.md) for the three proposed standalone ReelCut icon directions and their trade-offs:

1. **Frame Cut** — recommended: the clearest signal of a vertical video edit.
2. **Splice** — emphasizes joining rendered media segments.
3. **Caption Cursor** — emphasizes the transcription and timeline workflow.

Each option has a clean SVG, but none should be treated as an official logo until one is selected and exported at final sizes.

## Capture notes

- Capture date: 2026-08-29.
- Existing raw source: `DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV`, 1080 × 1920, 88.436667 seconds.
- Existing final render: `git-cli-isnt-a-personality.mp4`, 1080 × 1920 H.264, 39.603000 seconds.
- The terminal tape is intentionally committed alongside the recording so its factual provenance is inspectable. It does not run `render-hooks`, Tailscale, Telegram, or any publishing action, and it does not modify the existing source package or output folder.
- Raw source footage and original final MP4s remain in ignored `assets/` and `output/` directories. This documentation pack contains only review derivatives.

## Approval gate

Before promoting any asset to `approved for personal site`, confirm public use of the visible person, the GitHub overlay, the spoken material, and the music. Once approved, copy selected web-sized derivatives into the personal site; do not move or delete the original provenance files.
