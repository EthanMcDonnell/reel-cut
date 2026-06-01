# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ReelCut** — Full video production workflow for short-form content (Instagram Reels / YouTube Shorts).

Four-phase pipeline:
- **Discover** — Scrape tech engineering articles into SQLite; triage via Telegram
- **Phase 0** — `/produce-script` converts an article to a script + source screenshots
- **Phase 1** — `/prepare-video <slug>` transcribes footage, reviews and fixes the EDL
- **Phase 2** — `/produce-video <slug>` assigns image timings and renders the final video

## Directory Structure

```
reelcut/     Python package — video editing pipeline (transcription → EDL → render)
scrape/      Content discovery — scraper, SQLite DB, Telegram triage, article screenshots
assets/      Per-video working files: assets/<slug>/ holds captions.json, debug.txt, screenshots, manifest.json
output/      Final rendered videos: output/<slug>.mp4
scripts/     Operational shell scripts (cron wrappers)
.claude/
  commands/produce-script.md   — Phase 0: article → script + screenshots
  commands/prepare-video.md    — Phase 1: transcribe + fix EDL anomalies
  commands/produce-video.md    — Phase 2: assign image timings + render
```

## Development Setup

```bash
.venv/bin/python -m pip install -e .    # installs reelcut + all scrape deps
playwright install chromium             # one-time: required for screenshot.py and JS-heavy sources
```

**Always use `.venv/bin/python` for all Python and pip commands.** Never use system python/pip.

No test suite or linter is currently configured.

## Content Discovery

```bash
.venv/bin/python scrape/scraper.py --config scrape/sources-tbbt.yaml    # scrape articles to DB
.venv/bin/python scrape/query.py articles tbbt --status new --limit 20  # list unread articles
.venv/bin/python scrape/query.py mark-done tbbt "<url>"                 # mark article as done
scripts/refresh_scrapes.sh                                     # cron: refresh all series
```

Database at `scrape/db/influencer.db` (SQLite, gitignored). Series: `tbbt` (eng blog posts), `updates` (AI/Claude tooling).

## Phase 0 — Script Production

Use `/produce-script`. Accepts a URL, DB title/ID, Obsidian note, or plain phrase. Outputs:
- Script saved to Obsidian `Videos/Videos To Do/<slug>.md`
- Screenshots + manifest to `assets/<slug>/` — `manifest.json` maps each `snippet-NN.png` to its verbatim source snippet

Scripts always go to Obsidian. All other assets go to `assets/<slug>/`.

## Phase 1 — Prepare Video

Use `/prepare-video <slug>`. See `.claude/commands/prepare-video.md`.

1. User drops footage into `assets/<slug>/`.
2. Runs `reelcut transcribe config.yaml --slug <slug> --footage assets/<slug>/`. config.yaml is never edited.
3. Reviews EDL for anomalies: multiple takes, bad silence cuts, over-cutting, hallucinated words
4. Edits captions.json to fix what it finds

```bash
.venv/bin/reelcut transcribe config.yaml --slug <slug> --footage assets/<slug>/   # transcribe → assets/<slug>/<slug>.captions.json + .debug.txt
.venv/bin/reelcut preview-edl <f>.captions.json  # print EDL summary table
.venv/bin/reelcut timeline <f>.captions.json     # print output-timeline word positions
```

### reelcut transcribe internals (cli.py `_phase1`)

1. Extract audio → temp 16kHz mono WAV, normalize to EBU R128
2. Whisper transcription → approximate word-level timestamps
3. WhisperX alignment → precise source-clip-time word timestamps
4. Silero VAD filter → drop hallucinated words
5. Retake detection → mark outtake regions (scriptless mode only)
6. Gap detection → classify inter-word gaps as silence/breath/noise; mark cut=True/False
7. Script alignment → mark outtake words keep=False (script mode only)
8. EDL generation → keep/cut segments in source-clip time
9. Word remapping → output-timeline positions (for debug report only)

Outputs written to `assets/<slug>/`:
- **`<slug>.captions.json`** — EDL + source-clip-time words + empty images list (human/LLM editable)
- **`<slug>.debug.txt`** — full pipeline trace (raw words, aligned words, gaps, EDL)

## Phase 2 — Produce Video

Use `/produce-video <slug>`. See `.claude/commands/produce-video.md`.

1. Runs `.venv/bin/reelcut timeline assets/<slug>/<slug>.captions.json` → output-timeline word positions (orientation only — do not use these times in image entries)
2. Reads script from Obsidian + manifest from `assets/<slug>/`
3. Assigns image timings in **source-clip time** (from the `words` array in captions.json), populates `images` array
4. Runs `.venv/bin/reelcut render config.yaml assets/<slug>/<slug>.captions.json` → `output/<slug>.mp4`

```bash
.venv/bin/reelcut render config.yaml <f>.captions.json   # render → output/<slug>.mp4
.venv/bin/reelcut run config.yaml                        # end-to-end without LLM editing step
```

### reelcut render internals (cli.py `_phase2`)

1. Load captions.json
2. Remap words from source-clip-time → output-timeline using current EDL (`_remap_kept_words`)
3. Render caption PNG frames (Pillow, word_highlight or full_line style)
4. Auto-detect logo cues from transcript words (gilbarbara/logos)
5. Remap manual image overlays from source-clip-time → output-timeline, resolve (person → Wikipedia, screenshot → local file)
6. Render image overlay PNG frames, merge with caption frames
7. FFmpeg: extract kept segments → concat → burn caption frames

Output: **`output/<slug>.mp4`**

### captions.json Schema

```json
{
  "source_clips": ["<path>"],
  "edl": [
    { "source_clip": "<path>", "start": 0.42, "end": 3.81, "keep": true, "reason": "speech" }
  ],
  "words": [
    { "word": "Netflix", "start": 0.42, "end": 0.80, "source_clip": "<path>" }
  ],
  "images": [
    { "type": "person", "start": 1.2, "end": 3.5, "source_clip": "<path>", "name": "Sam Altman", "path": "" },
    { "type": "screenshot", "start": 4.0, "end": 6.0, "source_clip": "<path>", "name": "", "path": "/abs/path.png" }
  ]
}
```

**Key timing rule**: `edl`, `words`, and `images` timestamps are all in **source-clip time**. Phase 2 remaps `words` and `images` to output-timeline at render time using the current EDL — so editing the EDL between phases keeps everything in sync.

## reelcut Architecture

```
audio.py           → Extract mono 16kHz WAV, normalize to EBU R128 -23 LUFS
transcriber.py     → faster-whisper STT → WhisperX wav2vec2 forced alignment (30s timeout, falls back to whisper timestamps)
vad.py             → Silero VAD via ONNX runtime; filters hallucinated words after alignment
gap_detector.py    → Classify inter-word gaps as silence/breath/noise via scipy spectral flatness + amplitude
script_aligner.py  → Fuzzy-match transcript to provided script; last take wins
retake_detector.py → Detect repeated phrases and cut earlier takes (scriptless mode)
edl.py             → Build Edit Decision List; sentence-boundary snapping (±0.6s window); merge adjacent cuts
caption.py         → Frame-by-frame PNG captions via Pillow (word_highlight or full_line style)
image_finder.py    → Match transcript words against logos manifest + Wikipedia people headshots
image_overlay.py   → Composite logo/person PNGs onto caption frames with fade
renderer.py        → Parallel segment extraction → concat → caption burn-in via FFmpeg
entity_resolver.py → Wikipedia thumbnail fetch + cache (~/.cache/reelcut/entity_images/)
image_resolver.py  → gilbarbara/logos SVG download → cairosvg PNG + cache (~/.cache/reelcut/logos/)
debug_report.py    → Write .debug.txt after Phase 1 (raw words, alignment, gaps, EDL)
captions_doc.py    → captions.json schema, serialisation, deserialisation
```

Entry point is `cli.py` (Typer). Config schema validated by Pydantic in `config.py`.

## Key Data Structures

- **`WordTimestamp`** (`transcriber.py`) — `word`, `start`, `end`, `confidence`, `clip_path`, `keep`
- **`Gap`** (`gap_detector.py`) — `start`, `end`, `duration_ms`, `gap_type`, `cut`
- **`EDLEntry`** (`edl.py`) — `start`, `end`, `keep`, `source_clip`, `reason`
- **`CaptionWord`** (`captions_doc.py`) — `word`, `start`, `end`, `source_clip` (all source-clip time)
- **`ImageCue`** (`image_finder.py`) — `keyword`, `start`, `end`, `image_path`

## Configuration

YAML config sections: `cuts`, `output`, `assets`, `captions`, `images`, `whisper`. See `config.yaml` for an annotated example.

**Never edit config.yaml during any phase.** All footage paths are passed via `--footage` CLI arg. config.yaml has no `input:` section — that block is only used internally by the `reelcut run` end-to-end command (not the phase-by-phase workflow).

**Slug derivation**: always pass `--slug <slug>` explicitly. When no slug is given, output goes to a timestamped subdirectory of `output.location`.

Key `images` fields (config.yaml):
- `images.auto_detect` — match all capitalised transcript words against gilbarbara/logos manifest
- `images.keywords` — explicit logo slugs to always match regardless of capitalisation
- `images.exclude` — logo slugs to never match

People and screenshot overlays are specified in the captions.json `images` array (filled in by `/produce-video`), not in config.yaml.

## Important Implementation Details

- **Multi-clip**: `clips_folder` orders by file creation time, transcribes independently, stitches in script order.
- **macOS quirks**: multiprocessing uses `spawn` mode; OpenMP duplicate-lib warning suppressed at startup.
- **Font loading**: cascades bundled → system dirs → Pillow default.
- **Rendering workers**: parallel segment extraction, default 8 workers (configurable via `output.render_workers`).
- **Exit codes**: 0 = success, 1 = error, 2 = warnings (unmatched script lines, output exceeds `max_duration_s`).
- **Image cache**: logos and entity images cached in `~/.cache/reelcut/`; delete directory to force refresh.
