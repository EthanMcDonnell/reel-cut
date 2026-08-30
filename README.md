<div align="center">

<img src="docs/portfolio/identity/playcut.svg" alt="ReelCut" width="112" />

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
| **0** | `/produce-script <url/title>` | Article → script + screenshots (`assets/<slug>/`) |
| **1** | `/prepare-video <slug>` | Transcribe footage, review and fix the EDL |
| **2** | `/produce-video <slug>` | Assign image timings, render `output/<slug>.mp4` |

> **Content discovery** lives in `scrape/`: scraper, SQLite DB (`scrape/db/influencer.db`), Telegram triage.

---

## One run, end to end

The `reddit-kafka-kubernetes-dns` package: a Reddit thread through
`/produce-script` → `/prepare-video` → `/produce-video`, ending as an 87-second
Reel. A 257-word script from the article, then:

> Reddit moved a petabyte of live Kafka with zero downtime. ~~Reddit moved 500
> Kafka brokers to—~~ **← retake, cut automatically.** Reddit moved 500 Kafka
> brokers to Kubernetes without a single user noticing. … They wanted to move all
> 500-plus brokers **[⊞ article screenshot]** off Amazon and onto Kubernetes. …
> Its metadata is **[◉ concept image: Welding]** welded to broker identity, so you
> can't clone the cluster and repoint everyone.

```
SOURCE   ██░███░░░░░██▓▓████████████████████████████░████░██████████░█░░░░███  130s
         auto-cut — retake ×5 · silence ×12 · breath ×10 · noise ×10 — 42.6s removed

RENDER   ████████████████████████████████████████████  87s
  title  ███████                                          "Reddit Migrated a Petabyte…"
  caps   ────────────────────────────────────────────     word-level, burned in
  images           ▲         △    ▲   ▲   ▲   ▲            ▲ 5 screenshots  △ concept (Welding)
```

**130s take → 87s Reel, 67% kept.** In one pass ReelCut:

- **Auto-cut** — removed 42.6s: 5 retakes, 12 silences, 10 breaths, 10 noise
  gaps. The retake detector *cut* the fumbled *"Reddit moved 500 Kafka
  brokers…"* (0.86 match) and *kept* the one candidate that was really the
  script repeating a phrase (0.19).
- **Retranscribed ×2** against raw Whisper to fix low-confidence alignment; one
  hit the 20s hard cap. Dropped one wordless fragment at a retake boundary.
- **Captions** — word-level, burned in over the whole 87s.
- **Title card** — *"Reddit Migrated a Petabyte of Data With Nobody Noticing"*,
  templated subtitle, first 13s.
- **Article images** — pulled 6 screenshots from the thread, each triggered by a
  script word (`show@"500+" … hide@"Kubernetes"`, exact match); 5 placed.
- **Concept image** — one, *Welding*, on *"metadata is welded to broker
  identity."*
- **Trail variants** — the same cut renders twice with a different title card and
  caption for the Instagram trail.

Every figure is from that package's `.captions.json`, `.debug.*.txt`,
`images.json`, `manifest.json` and `headings.json`.

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

## Script out, footage in (phone ↔ `assets/`)

`/produce-script` sends a script page and an upload link to Telegram. The script is served live
from `assets/<slug>/script.md`; edits made after it is sent appear after a phone-page refresh.

```
/produce-script ────links────▶ Telegram "file-exchange" ────▶ phone
                                                              │
                     http://100.x.y.z:8770/script/<slug> ────┤ read while filming
                     http://100.x.y.z:8770/upload/<slug> ────┘ upload the take
                                                              ▼
                                                     assets/<slug>/
                                                              ▼
                                                serial Claude production queue
```

The take is uploaded straight into the script's own `assets/<slug>/`, and production runs:

```bash
claude -p "/produce-reel <slug> --auto"
```

A second take through the same link is refused (`409`), not isolated into a new folder — delete
the existing clip from `assets/<slug>/` first if you need to retake.

### Permanent direct-recording links

The same `/upload/<target>` endpoint also serves configured direct-recording series. Each key in
`config.yaml` under `inbound.series` is a permanent link, for example:

```yaml
inbound:
  series:
    hot-take:
      slug_prefix: hot-take
      series: hot-takes
      hook_policy: single
```

`http://100.x.y.z:8770/upload/hot-take` creates a fresh flat
`assets/hot-take-<timestamp>/` job every time. No code is specific to `hot-take`: add another
profile for another permanent series link. A direct recording must be one finished hook plus
body; its intake receipt tells `/produce-reel` that the missing script is intentional.

The upload page has an optional name field for a direct-series link — type e.g. `ai-bubble-take`
to land in `assets/ai-bubble-take/` instead of a timestamped folder. Like a script slug, naming
it reuses that folder once; a second take under the same name is refused (`409`).

**Setup** — once, after `tailscale up`:

```bash
./scripts/install-upload-agent.sh        # --uninstall to remove both agents
```

This installs `com.reelcut.upload` (the Tailnet receiver) and `com.reelcut.produce` (the one-job
production worker). They start at login and respawn after a crash. Rerun the installer after
moving the repo; it writes absolute paths into the plists. The LaunchAgent logs are
`/tmp/reelcut-upload.{log,err}` and `/tmp/reelcut-produce.{log,err}`.

The receiver binds this machine's **tailnet IP**, not loopback, so links work from any Tailnet
device but are not exposed on local wi-fi. The worker uses `scripts/worker-settings.json`: a
scoped Claude tool allowlist with no permission-bypass mode. If the workflow needs an unapproved
tool, the job is left failed with its Claude output instead of silently expanding permissions.

**Status and recovery**

- Each completed upload returns a `/job/<id>` page that polls `pending`, `running`, `succeeded`,
  `blocked`, `failed`, or `interrupted` status. Telegram receives the same lifecycle updates.
- The job page reveals **View Claude output** as soon as the worker creates its combined
  stdout/stderr log. The link is available only over the Tailnet and serves
  `/job/<id>/log`.
- Queue state and per-job Claude logs live under `.reelcut/production-queue/`. Retrying a job
  replaces its log with the latest attempt's output.
- A worker restart moves an in-flight job to `interrupted`; it never retries model or render work
  automatically. Inspect the job's Claude output, then run
  `.venv/bin/python scripts/production_queue.py retry <job-id>` to requeue it deliberately.
- Uploads stage as `<name>.part`, renamed only when complete. Only `.mp4`, `.mov`, and `.mkv`
  files are accepted; the server never buffers the body in memory.
- In Safari, *Browse → Files* sends original bytes; the photo picker may re-encode.

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
