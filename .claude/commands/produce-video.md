---
name: produce-video
description: Assign screenshot and person image timings to images.json, then render the final video via reelcut.
tools: Read, Edit, Bash
permissionMode: default
---

Populates image overlays in images.json and renders the final video.

**Paths:** `{TOKEN}` references below are machine-specific absolute paths/endpoints defined in [glossary.md](glossary.md) — resolve each to its value before running. Repo-relative paths (`assets/…`, `output/…`, `config.yaml`, `tests/…`) are written inline as-is.

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

The manifest maps each `snippet-NN.png` to these fields:
- `article_snippet` — the verbatim source text captured from the article
- `script_context` — the script line it supports (written at produce-script time, re-aligned to the transcript by `prepare-video`)
- `trigger_show_word` / `trigger_go_away_word` — optional verbatim anchors from within `script_context` marking where the screenshot should appear and disappear (may be empty)

Use `script_context` as the primary guide when locating the timestamp — it directly names the script line being visualised. Fall back to matching words from `article_snippet` against the `words` array if `script_context` is absent.

## Step 3 — Assign image timings

Image timings are stored in **source-clip time** (same as `words` and `edl`). The renderer remaps them to output-timeline at render time.

Work through every screenshot in the manifest (skip `body.png`). **Skip any screenshot whose `script_context` or `article_snippet` cannot be matched to words in the `words` array — do not invent a placement.**

1. Use the `script_context` field to identify the moment the screenshot supports. If `script_context` is absent, match words from `article_snippet` against the `words` array
2. Find the words covering that moment in the `words` array of captions.json — use their `start`, `end`, and `source_clip` values
3. **Bound the on-screen window:**
   - **If `trigger_show_word` and `trigger_go_away_word` are both present and non-empty**, locate them in the `words` run for this line (search within the `script_context` span so they can't match a duplicate elsewhere): the screenshot's `start` = the matched `trigger_show_word`'s `start`, and its `end` = the matched `trigger_go_away_word`'s `end`.
   - **If a trigger anchor is empty or can't be found**, fall back to spanning the full sentence: `start` of the first matched word to `end` of the last matched word. If even the sentence boundaries can't be determined, use ~5 seconds centred on the anchor moment.
4. Set `type: "screenshot"`, `source_clip` to the `source_clip` from the anchor words, and `path` to the absolute path: `{PROJECT_ROOT}/assets/<video-slug>/<file>` where `<file>` is the `file` field from the manifest (may include a subdirectory)

Then scan the `words` array for person names (consecutive capitalised words that form a full name, e.g. "Reed Hastings", "Sam Altman"). For each name found:
- Use the source-clip timestamps from those words
- Add a `type: "person"` entry with `name: "<Full Name>"`, `source_clip` from the anchor word, and `path: ""` — the renderer resolves Wikipedia headshots automatically

Build the complete images list — one entry per screenshot, plus any person entries, plus an optional concept image (Step 3b).

## Step 3b — Concept image (optional, one per video)

A few quirky Wikipedia image can add a fun extra dimension — drop a literal photo of an unexpected *thing* onto a punchline. The gag lands when an abstract phrase is rendered as the real object behind it: "spaghetti code" → a bowl of spaghetti, "rubber-duck debugging" → a rubber duck, "the cops showed up" → a police car. Resolved exactly like a `person`, but the **name** is any Wikipedia subject, not a person.

- Add **at most three** per video, and only when a beat genuinely wants it. If nothing clearly fits, add none — restraint beats clutter.
- The **name** must be the Wikipedia title of a **concrete, photographable object** whose page shows a **real photo** of that thing. This is the whole trick — and it's also where it breaks:
  - ✅ `Spaghetti code` (its page literally shows a bowl of spaghetti), `Rubber duck debugging`, `Police car`, `Trojan Horse` — concrete nouns with a real photo.
  - ❌ Abstract terms with **no photo**: `Technical debt`, `Scalability`, `Latency` — these resolve to nothing and silently vanish.
  - ❌ Terms whose page art is a **diagram/schematic, not a photo**: e.g. `Race condition` (an SVG diagram). A chart is not a gag.
  - When in doubt, picture the literal noun and use *that* title (e.g. `Rubber duck`, not "debugging"). If you can't name an object you're confident has a real photo on Wikipedia, omit it.
- **Keep it a flash, not a hold.** These are meant to appear and vanish in under a second — a quick visual joke, not a prolonged overlay. Aim for 0.5–1.0s of screen time. A ladybug flickering on "a new bug crept into the codebase" lands; the same image lingering for 3 seconds kills the pace.
- Place it on the *meaning*, even when the exact word isn't spoken. Anchor to the words in captions.json: `start` = the anchor word's `start`, `end` = the `end` of the line it punctuates, `source_clip` from the anchor word.
- Add `{ "type": "concept", "name": "<Wikipedia subject>", "start": ..., "end": ..., "source_clip": "...", "path": "" }`.

## Step 3c — Detect hook count and output-timeline boundaries

**Purpose:** establish how many heading cards Step 4b should generate and what output-timeline windows they occupy.

**1. Identify hooks from the output timeline.**

Use the `reelcut timeline` output from Step 1. Read the first several lines of the output and use intuition: hooks are the short, punchy statements at the very start of the video — questions, shocking facts, provocative claims — that grab attention before the body explanation begins. The body starts when the speaker shifts into explaining or narrating (e.g. "Picture a...", "So how does...", "It works by...").

Each distinct hook sentence is one hook. Count them and note the output-timeline start of each. The script file at `{VAULT_VIDEOS_TODO}<slug>.md` can help confirm what the HOOK section contains, but the timeline is the ground truth for timing.

**2. Locate each hook's boundaries in the output timeline.**

For each hook, record its `start` (first word) and the start of the next hook (or body) as its `end`. Record `hook_start[N]` = the output-timeline start of the first word of hook N.

**3. Compute hook windows.**

- For hooks 1 through N-1: `end = hook_start[N+1]`
- For hook N (last): `end` = the output-timeline start of the first word **after** the last hook — i.e. the first word that belongs to the body. If the body start can't be determined, use `hook_start[N] + 3.0`

Store `hook_windows: list[(start, end)]`. This drives heading card generation in Step 4b.

## Step 4 — Write images.json

Write the images list into `assets/<video-slug>/images.json` (a JSON list — a `[]` stub is auto-created by `prepare-video`, so use the Edit tool to fill it in). It is separate from captions.json; do not modify `edl` or `words` in captions.json.

Example `images.json`:
```json
[
  { "type": "screenshot", "start": 12.935, "end": 16.402, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "{PROJECT_ROOT}/assets/slug/snippet-01.png" },
  { "type": "person", "start": 4.205, "end": 7.444, "source_clip": "assets/slug/clip.MP4", "name": "Reed Hastings", "path": "" },
  { "type": "concept", "start": 31.2, "end": 34.1, "source_clip": "assets/slug/clip.MP4", "name": "Rubber duck debugging", "path": "" }
]
```

All `start`/`end` values are **source-clip seconds** taken from the `words` array in captions.json (the renderer remaps them to the output timeline).

## Step 4b — Headings

Read `assets/<video-slug>/headings.json`. If the first entry has a non-empty `title`, it's already filled in — skip to Step 5.

If the title is empty (the stub state from `prepare-video`), generate heading suggestions.

**Inputs to draw from:**
- The video slug and topic
- The manifest `topic` / `hook` fields if present
- The series from the manifest or inferred from the slug (check SERIES.md for the tone of each series)
- `hook_windows` from Step 3c — one window per hook, each with its output-timeline `(start, end)`

**Generate 3 title/subtitle options.** A single title/subtitle is picked and stamped across all hook cards — every hook introduces the same video. Tailor to the series tone:
- *tbbt*: punchy question or shocking statement about the architecture, subtitle `Tech Behind Big Tech Day {n:tbbt}` (the literal words "Tech Behind Big Tech Day" followed by the episode number — not `#`, and never just `Day {n:tbbt}` on its own)
- *updates*: news-style headline, no series token in subtitle
- *interesting-tech / Interesting Tech*: the "impossible thing" framing ("Can a prime number be illegal?"), subtitle can include the series day count
- *AI Fundamentals*: first-principles question the viewer is already asking

Use `\n` in `title` for line breaks (2 lines usually reads better on mobile). Keep titles short enough to read in 2–3 seconds.

**Use AskUserQuestion** to present the 3 options (plus "Enter my own"). Show each as a preview with the full JSON for the **first card only** so the user can see exactly what will be written.

Once the user selects or provides a heading, write `headings.json` with **one card per hook window** from `hook_windows`, all sharing the chosen title and subtitle:

```json
[
  { "title": "What Are\nAI Tokens?", "subtitle": "explained in 90 seconds", "start": 0.0, "end": 3.1, "scrim": true },
  { "title": "What Are\nAI Tokens?", "subtitle": "explained in 90 seconds", "start": 3.1, "end": 6.4, "scrim": true },
  { "title": "What Are\nAI Tokens?", "subtitle": "explained in 90 seconds", "start": 6.4, "end": 9.8, "scrim": true }
]
```

Field reference:
- `title` — use `\n` for line breaks; `{n:<series>}` is auto-replaced with this video's episode number at render time (series slug from SERIES.md)
- `subtitle` — optional smaller italic line; also supports `{n:<series>}`
- `start`/`end` — **output-timeline seconds** from `hook_windows` (Step 3c), not source-clip time
- `scrim` — `true` darkens footage behind the text; omit to use the config default

**Logo resets:** each card's start/end is a logo-reset boundary. A brand re-mentioned after any card edge re-fires its logo in that section — no extra configuration needed.

## Step 5 — Render

```bash
.venv/bin/reelcut render config.yaml "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

The final video is written to `output/<video-slug>.mp4`.

Report the output path when done.

## Step 6 — Lock in a regression fixture

Capture this clip's full word list as a committed real-clip test fixture, so its retake
detection and sentence segmentation are pinned against future regressions (this is how the
"retake cut swallowed the whole body" class of bug gets caught — a synthetic unit test
can't, only a real full-length clip can). Cheap: the data already exists in the transcription
debug report.

```bash
grep -E "→.*conf=" assets/<video-slug>/*.debug.4.post-vad.txt > tests/fixtures/retake/<video-slug>.txt
.venv/bin/python -m pytest tests/test_real_clips.py -q
```

The generic invariants in `tests/test_real_clips.py` (no runaway retake cut; sane sentence
count) pick up the new fixture automatically via glob — no test edit needed, and they must
pass. If the clip has a distinctive line spoken exactly once that you want pinned as
"must survive", copy `test_billion_laughs_unique_content_survives` for the new slug with its
own survivor words. Note: this fixture exercises the *detector/segmenter* on real words; it
does NOT re-run Whisper, so it can't catch transcription-side regressions — those still
require an actual transcribe run to verify.

Commit the fixture alongside the video's other artifacts.

## Step 7 — Publish to Tailscale & notify Telegram

Make the rendered `output/<video-slug>.mp4` reachable over Tailscale, then post its link to
the Telegram `file-exchange` topic.

**Prerequisites** (set up once, outside this workflow):
- Tailscale installed and this machine joined to the tailnet (`tailscale up`).
- The local Telegram bot API server running on `{TELEGRAM_API}` (same server used by
  `scrape/telegram.py`).

```bash
# 1. Serve the output directory over Tailscale (idempotent — safe to re-run every render)
tailscale serve --bg --set-path /reels "{PROJECT_ROOT}/output"

# 2. Build this video's tailnet URL
TS_HOST=$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')
VIDEO_URL="https://${TS_HOST}/reels/<video-slug>.mp4"

# 3. Post the link to the local Telegram bot API — the file-exchange topic
PAYLOAD=$(jq -n --arg c "🎬 <video-slug> is ready: ${VIDEO_URL}" '{content: $c, topic: "file-exchange"}')
curl -s {TELEGRAM_API}/telegram/send -H 'Content-Type: application/json' -d "$PAYLOAD"
```

Notes:
- `--set-path /reels` serves privately **within your tailnet** — the link resolves only on
  your own devices. Swap `tailscale serve` → `tailscale funnel` if the link must work
  off-tailnet (public internet).
- `topic` is a **name** the broker resolves to a Telegram thread id via its `config.yaml`
  `projects:` list — `file-exchange` is the configured video topic. A raw numeric id in this
  field fails with `unknown topic name`.
