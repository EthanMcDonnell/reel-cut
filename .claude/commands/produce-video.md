---
name: produce-video
description: Phase 2 — Assign screenshot and person image timings to captions.json, then render the final video via reelcut.
tools: Read, Edit, Bash
model: sonnet
permissionMode: default
---

Populates image overlays in the captions.json and renders the final video.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Example: `/produce-video netflix-cdn-architecture`

## Step 1 — Locate captions file and generate output timeline

List `assets/<video-slug>/` to find the `.captions.json` file — it may be named after the footage stem, not the slug (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). Use whatever file is present; there will be exactly one.

```bash
.venv/bin/reelcut timeline "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

Use this to understand what is spoken when in the final video. **Do not use these times in image entries** — they are for orientation only.

## Step 2 — Read inputs

Read both:

1. **Screenshot manifest**: `assets/<video-slug>/manifest.json`
2. **captions.json**: `assets/<video-slug>/<actual-captions-filename>.captions.json` (the file found in Step 1)

The manifest maps each `snippet-NN.png` to two fields: `snippet` (verbatim source text captured from the article) and `context` (the script sentence or section it supports, written at produce-script time). Use `context` as the primary guide when locating the timestamp — it directly names the script line being visualised. Fall back to matching words from `snippet` against the `words` array if `context` is absent.

## Step 3 — Assign image timings

Image timings are stored in **source-clip time** (same as `words` and `edl`). The renderer remaps them to output-timeline at render time.

Work through every screenshot in the manifest (skip `body.png`). **Skip any screenshot whose `context` or `snippet` cannot be matched to words in the `words` array — do not invent a placement.**

1. Use the `context` field to identify the moment the screenshot supports. If `context` is absent, match words from `snippet` against the `words` array
2. Find the words covering that moment in the `words` array of captions.json — use their `start`, `end`, and `source_clip` values
3. Set the image to span 3–4 seconds centred on that moment, using source-clip timestamps from the `words` array. Cap at the sentence duration if shorter
4. Set `type: "screenshot"`, `source_clip` to the `source_clip` from the anchor words, and `path` to the absolute path: `/Users/ethanmcdonnell/Documents/reel-cut/assets/<video-slug>/<file>` where `<file>` is the `file` field from the manifest (may include a subdirectory)

Then scan the `words` array for person names (consecutive capitalised words that form a full name, e.g. "Reed Hastings", "Sam Altman"). For each name found:
- Use the source-clip timestamps from those words
- Add a `type: "person"` entry with `name: "<Full Name>"`, `source_clip` from the anchor word, and `path: ""` — the renderer resolves Wikipedia headshots automatically

Build the complete `images` array — one entry per screenshot, plus any person entries.

## Step 4 — Update captions.json

Write the `images` array into the captions file found in Step 1 using the Edit tool. Do not modify `edl` or `words`.

Example entries:
```json
{ "type": "screenshot", "start": 12.935, "end": 16.402, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "/Users/ethanmcdonnell/Documents/reel-cut/assets/slug/snippet-01.png" }
{ "type": "person", "start": 4.205, "end": 7.444, "source_clip": "assets/slug/clip.MP4", "name": "Reed Hastings", "path": "" }
```

All `start`/`end` values are **source-clip seconds** taken from the `words` array in captions.json.

## Step 5 — Render

```bash
.venv/bin/reelcut render config.yaml "assets/<video-slug>/<video-slug>.captions.json"
```

The final video is written to `output/<video-slug>.mp4`.

Report the output path when done.
