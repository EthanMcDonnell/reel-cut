---
name: produce-video
description: Assign screenshot and person image timings to images.json, then render the final video via reelcut.
tools: Read, Edit, Bash
model: sonnet
permissionMode: default
---

Populates image overlays in images.json and renders the final video.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Example: `/produce-video netflix-cdn-architecture`

## Step 1 — Locate captions file and generate output timeline

List `assets/<video-slug>/` to find the `.captions.json` file — it may be named after the footage stem, not the slug (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). Use whatever file is present; there will be exactly one.

```bash
.venv/bin/reelcut timeline "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

Use this to understand what is spoken when in the final video. **Do not use these times in image entries** — they are for orientation only.

## Step 2 — Check for manifest

Check whether `assets/<video-slug>/manifest.json` exists (it is only present when screenshots were produced by `/produce-script`).

**If no manifest exists → skip Steps 3 and 4. Go straight to Step 5 (render).**

If it does exist, read both:

1. **Screenshot manifest**: `assets/<video-slug>/manifest.json`
2. **captions.json**: `assets/<video-slug>/<actual-captions-filename>.captions.json` (the file found in Step 1)

The manifest maps each `snippet-NN.png` to two fields: `snippet` (verbatim source text captured from the article) and `context` (the script sentence or section it supports, written at produce-script time). Use `context` as the primary guide when locating the timestamp — it directly names the script line being visualised. Fall back to matching words from `snippet` against the `words` array if `context` is absent.

## Step 3 — Assign image timings

Image timings are stored in **source-clip time** (same as `words` and `edl`). The renderer remaps them to output-timeline at render time.

Work through every screenshot in the manifest (skip `body.png`). **Skip any screenshot whose `context` or `snippet` cannot be matched to words in the `words` array — do not invent a placement.**

1. Use the `context` field to identify the moment the screenshot supports. If `context` is absent, match words from `snippet` against the `words` array
2. Find the words covering that moment in the `words` array of captions.json — use their `start`, `end`, and `source_clip` values
3. **Set the image to span the full sentence the screenshot illustrates**: use the `start` of the first matched word and the `end` of the last matched word as the boundaries. If the exact sentence boundaries cannot be determined, fall back to ~5 seconds centred on the anchor moment
4. Set `type: "screenshot"`, `source_clip` to the `source_clip` from the anchor words, and `path` to the absolute path: `/Users/ethanmcdonnell/Documents/reel-cut/assets/<video-slug>/<file>` where `<file>` is the `file` field from the manifest (may include a subdirectory)

Then scan the `words` array for person names (consecutive capitalised words that form a full name, e.g. "Reed Hastings", "Sam Altman"). For each name found:
- Use the source-clip timestamps from those words
- Add a `type: "person"` entry with `name: "<Full Name>"`, `source_clip` from the anchor word, and `path: ""` — the renderer resolves Wikipedia headshots automatically

Build the complete images list — one entry per screenshot, plus any person entries.

## Step 4 — Write images.json

Write the images list into `assets/<video-slug>/images.json` (a JSON list — a `[]` stub is auto-created by `prepare-video`, so use the Edit tool to fill it in). It is separate from captions.json; do not modify `edl` or `words` in captions.json.

Example `images.json`:
```json
[
  { "type": "screenshot", "start": 12.935, "end": 16.402, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "/Users/ethanmcdonnell/Documents/reel-cut/assets/slug/snippet-01.png" },
  { "type": "person", "start": 4.205, "end": 7.444, "source_clip": "assets/slug/clip.MP4", "name": "Reed Hastings", "path": "" }
]
```

All `start`/`end` values are **source-clip seconds** taken from the `words` array in captions.json (the renderer remaps them to the output timeline).

## Optional — Text headings (title cards)

Large styled title cards (gold serif hook/section headings) live in
`assets/<video-slug>/headings.json` — a stub is auto-created by `prepare-video`, so usually you
just fill in `title` and adjust the timing. It's separate from captions.json, and the
screenshotter never touches it. Times are on the **output timeline** (the final video's clock,
readable from the `timeline` command in Step 1), so no remapping is needed.

```json
[
  { "title": "What Are\nAI Tokens?", "subtitle": "explained in 90 seconds", "start": 0.0, "end": 3.0, "scrim": true }
]
```

- `title` — heading text; use `\n` for explicit line breaks. A `{n:<series>}` token (e.g.
  `Tech Behind Big Tech #{n:tbbt}`) is auto-replaced at render with this video's episode
  number in that series — the count is allocated once in `assets/series_index.json` and stays
  stable across re-renders, so put the matching series slug from SERIES.md inside the token
- `subtitle` — optional smaller italic line below (also supports the `{n:<series>}` token)
- `start`/`end` — output-timeline seconds (when it appears in the final video)
- `scrim` — optional; `true` darkens the footage behind the text for legibility on bright/busy
  shots (omit to use the config default)

Styling (font, gold colour, size, shadow, scrim) lives in the `headings:` block of config.yaml.
An entry with an empty `title` is skipped, so the auto-created stub renders nothing until you
fill it in.

## Step 5 — Render

```bash
.venv/bin/reelcut render config.yaml "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

The final video is written to `output/<video-slug>.mp4`.

Report the output path when done.
