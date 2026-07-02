<div align="center">

# ReelCut

### A CLI-based AI video editor for short-form content

*Article → script → screenshots → transcribe → cut → render. One pipeline, from idea to publishable Reel.*

<br>

[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Whisper](https://img.shields.io/badge/STT-faster--whisper%20+%20WhisperX-FF6F00)](https://github.com/SYSTRAN/faster-whisper)
[![FFmpeg](https://img.shields.io/badge/render-FFmpeg-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Version](https://img.shields.io/badge/version-0.1.0-blue)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)](#)

</div>

---

## Quickstart

```bash
.venv/bin/python -m pip install -e .
playwright install chromium    # required for JS-heavy article screenshots
```

> [!IMPORTANT]
> Always use `.venv/bin/python`. **Never** system python/pip.

---

## The Four-Phase Workflow

| Phase | Command | What it does |
|:-----:|:--------|:-------------|
| **0** | `/produce-script <url/title>` | Article → script (Obsidian) + screenshots (`assets/<slug>/`) |
| **1** | `/prepare-video <slug>` | Transcribe footage, review and fix the EDL |
| **2** | `/produce-video <slug>` | Assign image timings, render `output/<slug>.mp4` |

> **Content discovery** lives in `scrape/`: scraper, SQLite DB (`scrape/db/influencer.db`), Telegram triage.

---

## Transcribe Pipeline

```
audio → whisper → clean → align → VAD → retakes → gaps → EDL → remap
```

1. **Extract audio** → temp 16kHz mono WAV, normalize to EBU R128
2. **faster-whisper** → raw word-level timestamps
3. **Retranscription** → detect false starts / hidden speech on raw Whisper output; surface missing words
4. **WhisperX wav2vec2 alignment** → precise source-clip-time timestamps (±30ms) on cleaned transcript
5. **Silero VAD (ONNX)** → drop hallucinated words
6. **Retake detection** → find repeated phrases, cut earlier takes (`cuts.repetition_detection`, default false)
7. **Gap detection** → classify inter-word gaps as silence/breath/noise; mark `cut=True/False`
8. **EDL generation** → keep/cut segments in source-clip time
9. **Word remapping** → output-timeline positions (debug report only)

---

## Render Pipeline

```
remap → captions → logos → overlays → composite → FFmpeg burn-in
```

1. **Remap** words/images from source-clip-time → output-timeline via EDL
2. **Render caption** PNG frames (Pillow, `word_highlight` or `full_line` style)
3. **Auto-detect logo cues** from transcript (gilbarbara/logos)
4. **Resolve image overlays** (person → Wikipedia headshot, screenshot → local file)
5. **Render image overlay frames**, merge with caption frames
6. **FFmpeg** → extract kept segments (parallel) → concat → burn caption frames → `output/<slug>.mp4`

---

## Publishing (Step 7 — Tailscale + Telegram)

After render, `/produce-video` publishes the finished `output/<slug>.mp4` and notifies you on
Telegram. Delivery is **link-based**: the file is served over your private tailnet and only a
URL is sent — so there's no file-size ceiling and the phone streams it (range requests
supported for seek/scrub).

```
output/<slug>.mp4 ──(tailscale serve)──▶ https://<host>.ts.net/reels/<slug>.mp4
                                                │
                           POST /telegram/send  ▼  (broker resolves topic name → thread id)
                                         Telegram "file-exchange" topic
```

**Dependencies**

| Tool | Purpose |
|:-----|:--------|
| [Tailscale](https://tailscale.com) | Serves `output/` privately within your tailnet |
| `jq`, `curl` | Build the JSON payload and POST it |
| `ultimate-message-broker` | Local Telegram bot API on `http://localhost:8765`; resolves a **topic name** → Telegram thread id |

**One-time setup**

1. **Tailscale** — join the tailnet and serve the output dir (idempotent; re-run each render):
   ```bash
   tailscale up
   tailscale set --operator=$USER    # lets `tailscale serve` run without sudo
   tailscale serve --bg --set-path /reels "$PWD/output"
   ```
   > The folder must live **outside** `~/Documents` (macOS TCC blocks Tailscale from reading it there).

2. **Broker** — run `ultimate-message-broker` (`main.py --platform telegram`) and register a
   video topic in its `config.yaml` under `projects:`. Notification-only topics need just four
   fields — **no `path`, no `allowed_tools`**:
   ```yaml
   - name: file-exchange
     platforms: [telegram]
     telegram_topic_id: <telegram thread id>
     claude_enabled: false
   ```
   The broker requires a `path` **only** when `claude_enabled: true` (the path is where Claude
   runs); notification topics omit it. `topic` in the send payload is this **name** — a raw
   numeric id fails with `unknown topic name`.

---

## Architecture

```
reelcut/
├─ cli.py             → Typer entry point (_phase1, _phase2)
├─ config.py          → Pydantic config schema
├─ audio.py           → Extract mono 16kHz WAV, normalize to EBU R128 -23 LUFS
├─ transcriber.py     → faster-whisper STT + WhisperX forced alignment
├─ vad.py             → Silero VAD via ONNX; fallback energy filter
├─ gap_detector.py    → Spectral flatness + amplitude gap classifier
├─ retake_detector.py → Sliding-window duplicate-phrase detector
├─ edl.py             → EDL builder; sentence-boundary snapping; merge adjacent cuts
├─ caption.py         → Frame-by-frame PNG captions via Pillow
├─ image_finder.py    → Logo manifest + Wikipedia headshot matcher
├─ image_overlay.py   → Composite PNG overlays onto caption frames with fade
├─ renderer.py        → Parallel segment extraction → concat → burn-in via FFmpeg
├─ entity_resolver.py → Wikipedia thumbnail fetch + cache (~/.cache/reelcut/entity_images/)
├─ image_resolver.py  → gilbarbara/logos SVG → cairosvg PNG + cache (~/.cache/reelcut/logos/)
├─ debug_report.py    → Write .debug.txt (raw words, alignment, gaps, EDL)
└─ captions_doc.py    → captions.json schema, serialisation, deserialisation
```

---

## Key Data Structures

| Structure | Fields |
|:----------|:-------|
| **`WordTimestamp`** | `word`, `start`, `end`, `confidence`, `clip_path`, `keep` |
| **`Gap`** | `start`, `end`, `duration_ms`, `gap_type`, `cut` |
| **`EDLEntry`** | `start`, `end`, `keep`, `source_clip`, `reason` |
| **`CaptionWord`** | `word`, `start`, `end`, `source_clip` *(all source-clip time)* |
| **`ImageCue`** | `keyword`, `start`, `end`, `image_path` |

---

## Implementation Notes

- **Multi-clip**: orders by file creation time, transcribes independently, stitches in script order.
- **macOS**: multiprocessing uses `spawn`; OpenMP duplicate-lib warning suppressed at startup.
- **Rendering workers**: parallel segment extraction, default 8 (`output.render_workers`).
- **Exit codes**: `0` = success · `1` = error · `2` = warnings (output exceeds `max_duration_s`).
- **Image cache**: `~/.cache/reelcut/` (delete to force refresh).

<div align="center">
<br>
<sub>Built for shipping Reels fast.</sub>
</div>
