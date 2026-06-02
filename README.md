# ReelCut

Full video production pipeline for short-form content (Instagram Reels / YouTube Shorts).

## Setup

```bash
.venv/bin/python -m pip install -e .
playwright install chromium    # required for JS-heavy article screenshots
```

Always use `.venv/bin/python`. Never system python/pip.

## Four-Phase Workflow

| Phase | Command | What it does |
|-------|---------|--------------|
| 0 | `/produce-script <url/title>` | Article → script (Obsidian) + screenshots (`assets/<slug>/`) |
| 1 | `/prepare-video <slug>` | Transcribe footage, review and fix the EDL |
| 2 | `/produce-video <slug>` | Assign image timings, render `output/<slug>.mp4` |

Content discovery: `scrape/` — scraper, SQLite DB (`scrape/db/influencer.db`), Telegram triage.

## reelcut transcribe pipeline

1. Extract audio → temp 16kHz mono WAV, normalize to EBU R128
2. faster-whisper → approximate word-level timestamps
3. WhisperX wav2vec2 alignment → precise source-clip-time timestamps (±30ms)
4. Silero VAD (ONNX) → drop hallucinated words
5. Retake detection → find repeated phrases, cut earlier takes (`cuts.repetition_detection`, default false)
6. Gap detection → classify inter-word gaps as silence/breath/noise; mark cut=True/False
7. EDL generation → keep/cut segments in source-clip time
8. Word remapping → output-timeline positions (debug report only)

## reelcut render pipeline

1. Remap words/images from source-clip-time → output-timeline via EDL
2. Render caption PNG frames (Pillow, word_highlight or full_line style)
3. Auto-detect logo cues from transcript (gilbarbara/logos)
4. Resolve image overlays (person → Wikipedia headshot, screenshot → local file)
5. Render image overlay frames, merge with caption frames
6. FFmpeg: extract kept segments (parallel) → concat → burn caption frames → `output/<slug>.mp4`

## Architecture

```
reelcut/
  cli.py             → Typer entry point (_phase1, _phase2)
  config.py          → Pydantic config schema
  audio.py           → Extract mono 16kHz WAV, normalize to EBU R128 -23 LUFS
  transcriber.py     → faster-whisper STT + WhisperX forced alignment
  vad.py             → Silero VAD via ONNX; fallback energy filter
  gap_detector.py    → Spectral flatness + amplitude gap classifier
  retake_detector.py → Sliding-window duplicate-phrase detector
  edl.py             → EDL builder; sentence-boundary snapping; merge adjacent cuts
  caption.py         → Frame-by-frame PNG captions via Pillow
  image_finder.py    → Logo manifest + Wikipedia headshot matcher
  image_overlay.py   → Composite PNG overlays onto caption frames with fade
  renderer.py        → Parallel segment extraction → concat → burn-in via FFmpeg
  entity_resolver.py → Wikipedia thumbnail fetch + cache (~/.cache/reelcut/entity_images/)
  image_resolver.py  → gilbarbara/logos SVG → cairosvg PNG + cache (~/.cache/reelcut/logos/)
  debug_report.py    → Write .debug.txt (raw words, alignment, gaps, EDL)
  captions_doc.py    → captions.json schema, serialisation, deserialisation
```

## Key Data Structures

- **`WordTimestamp`** — `word`, `start`, `end`, `confidence`, `clip_path`, `keep`
- **`Gap`** — `start`, `end`, `duration_ms`, `gap_type`, `cut`
- **`EDLEntry`** — `start`, `end`, `keep`, `source_clip`, `reason`
- **`CaptionWord`** — `word`, `start`, `end`, `source_clip` (all source-clip time)
- **`ImageCue`** — `keyword`, `start`, `end`, `image_path`

## Implementation Notes

- **Multi-clip**: orders by file creation time, transcribes independently, stitches in script order.
- **macOS**: multiprocessing uses `spawn`; OpenMP duplicate-lib warning suppressed at startup.
- **Rendering workers**: parallel segment extraction, default 8 (`output.render_workers`).
- **Exit codes**: 0 = success, 1 = error, 2 = warnings (output exceeds `max_duration_s`).
- **Image cache**: `~/.cache/reelcut/` — delete to force refresh.
