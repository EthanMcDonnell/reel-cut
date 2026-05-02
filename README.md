# ReelCut

AI-powered CLI video editor for Instagram Reels. Drop in raw footage, run one command, get a tight 9:16 vertical video with silences removed and captions burned in.

## Setup

```bash
.venv/bin/python -m pip install -e .
```

Always use `.venv/bin/python` for all Python and pip commands in this project.

## Usage

```bash
reelcut init                      # generate a default config.yaml
reelcut run config.yaml           # run the full pipeline
reelcut run config.yaml --dry-run # build EDL only, skip render
reelcut run config.yaml --verbose # show per-step detail
reelcut transcribe <video.mp4>    # standalone transcription smoke-test
reelcut preview-edl <file.edl.json>  # print EDL summary table
```

## Two Modes

| Mode | How to activate | What gets cut |
|------|----------------|---------------|
| **Scriptless** | Omit `input.script` in config | Silences, breaths, dead air — all speech kept |
| **Script** | Set `input.script` to a `.txt` file | Silences + outtakes (anything not in the script) |

---

## Processing Pipeline

Each video placed in `input/` is run through the following steps in order.

### Step 1 — Audio Extraction
**File:** `audio.py` · **Package:** `ffmpeg-python`

Pulls the audio track out of the video file as a mono 16 kHz WAV. Then loudness-normalises it to EBU R128 −23 LUFS using FFmpeg's `loudnorm` filter (two-pass). This ensures consistent volume levels before any analysis runs.

The WAV is written to a temporary directory and deleted after the run.

---

### Step 2 — Transcription
**File:** `transcriber.py` · **Package:** `faster-whisper`

Runs the WAV through faster-whisper (OpenAI Whisper, optimised for CPU via CTranslate2) to produce word-level timestamps. Each word gets a `start`, `end`, and confidence score.

VAD pre-filtering inside faster-whisper is disabled on macOS due to an OpenMP conflict between CTranslate2 and PyTorch — hallucination filtering is handled in Step 3b instead using Silero VAD via ONNX, which avoids the conflict entirely.

---

### Step 3 — Forced Alignment
**File:** `transcriber.py` · **Package:** `whisperx`

WhisperX re-aligns the Whisper word timestamps using a wav2vec2 model, improving per-word precision from ±100 ms down to ±30 ms. Falls back to the original Whisper timestamps if the alignment model can't load.

---

### Step 3b — VAD Hallucination Filter
**File:** `vad.py` · **Package:** `onnxruntime`

Whisper frequently invents words over silent or breathing sections (hallucinations). To catch these, every word is validated using **Silero VAD via ONNX runtime** — a neural network that classifies each 32 ms audio frame as speech or non-speech. Words whose audio window contains no detected speech are dropped before any further processing.

Using ONNX runtime (instead of the PyTorch-based `silero-vad` package) avoids a macOS deadlock where CTranslate2 (faster-whisper) and PyTorch both try to load OpenMP simultaneously. Falls back to a simpler energy amplitude check if the ONNX model is unavailable.

The Silero ONNX model (~2 MB) is downloaded once on first run and cached at `~/.cache/reelcut/silero_vad.onnx`.

**Output:** `output/<name>.transcript.json` — word-level timestamps with confidence scores.

---

### Step 3b — Retake Detection *(scriptless mode only)*
**File:** `retake_detector.py` · **Package:** stdlib only

Scans the transcript for repeated phrases of ≥ 4 consecutive words (configurable via `cuts.min_retake_words`). When a phrase appears more than once, everything from the first occurrence up to where the speaker restarted is marked for cutting. This removes fumbled takes and the pause between them automatically. Set `min_retake_words: 0` to disable.

---

### Step 4 — Gap Detection
**File:** `gap_detector.py` · **Package:** `scipy`

Analyses the audio between every consecutive pair of words to classify inter-word gaps:

| Type | Criteria | Default cut threshold |
|------|----------|-----------------------|
| `silence` | RMS below −40 dBFS | ≥ 100 ms |
| `breath` | Spectrally flat + amplitude < 15% of peak + duration 80–700 ms | ≥ 60 ms |
| `noise` | Above silence floor, doesn't fit breath criteria | ≥ 100 ms |

Spectral flatness (Wiener entropy) is computed via a short-time Fourier transform — breaths have high flatness (~1.0), speech has low flatness (~0.0). A failure-tolerance check prevents a single transient (mouth click, mic pop) from misclassifying an otherwise silent gap.

---

### Step 5 — EDL Generation
**File:** `edl.py` · **Package:** stdlib only

Builds an Edit Decision List — a JSON array of time-stamped keep/cut instructions covering every second of the source clip.

- **Scriptless mode:** keeps all speech, cuts every gap marked in Step 4.
- **Script mode:** additionally removes outtakes — any words not matched to the script are cut. The script aligner (`script_aligner.py`) does exact word matching with contraction folding (e.g. "gonna" → "going to"), keeping only the last take of any repeated section.
- Each cut boundary keeps 80 ms of audio before the next word starts (`speech_pad_ms`) to avoid clipping word edges.
- Short keep segments under 50 ms are dropped and surrounding cuts merged.

**Output:** `output/<name>.edl.json`

---

### Step 6 — Caption Frame Rendering *(if enabled)*
**File:** `caption.py` · **Package:** `Pillow`

Generates a transparent PNG overlay for every frame of the edited video. Two styles:

- **`word_highlight`** — current word shown in a coloured block, surrounding words in white. The active word advances in sync with playback.
- **`full_line`** — all words in the current 4-word group shown at once.

Frames with identical content reuse the same image file to keep disk usage low. Font cascades: bundled fonts → macOS system fonts → Pillow default.

**Output:** `output/<name>.srt` — subtitle file with the same grouping as the caption overlay, useful for debugging caption timing.

---

### Step 6b — Render
**File:** `renderer.py` · **Package:** `ffmpeg-python`

Three-stage FFmpeg pipeline:

1. **Segment extraction** — each keep EDL entry is trimmed to a temporary `.mkv` file using the `trim`/`atrim` filters (frame-accurate, not keyframe-dependent). Audio is encoded as FLAC to avoid encoder delay. Runs in parallel across up to 8 workers.
2. **Concatenation** — all segments are joined with the FFmpeg concat demuxer (stream copy, no re-encode).
3. **Final encode** — concatenated file is re-encoded to H.264 + AAC at the target resolution (default 1080×1920). If Silero VAD caption frames exist, they are overlaid in the same pass. Uses VideoToolbox hardware encoder on macOS if available, falls back to libx264.

**Output:** `output/<name>.mp4`

---

### After the Run

| File | Location | Description |
|------|----------|-------------|
| `<name>.mp4` | `output/` | Final edited video, 9:16, H.264 |
| `<name>.edl.json` | `output/` | Full edit decision list with keep/cut reasons |
| `<name>.transcript.json` | `output/` | Word-level timestamps + confidence scores |
| `<name>.srt` | `output/` | Subtitle file matching caption groups |
| Original clip | `done/` | Source footage moved here after successful processing |

---

## Key Configuration (`config.yaml`)

```yaml
input:
  footage: ./input/          # folder to scan (or single file path)
  script: ./script.txt       # optional — enables outtake removal

cuts:
  min_silence_ms: 100        # cut silences longer than this
  min_breath_ms: 60          # cut breaths longer than this
  speech_pad_ms: 80          # ms of audio kept before each word on a cut
  silence_threshold_db: -40  # raise if over-cutting quiet speech
  min_retake_words: 4        # min words for duplicate-take detection (0 = off)

captions:
  enabled: true
  style: word_highlight      # word_highlight | full_line | none
  position: center           # top | center | bottom
```
