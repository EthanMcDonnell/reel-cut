# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ReelCut** — AI-powered CLI video editor for Instagram Reels. Takes raw footage + a script and produces tight, caption-burned 9:16 vertical video by detecting and removing silences, breaths, and dead air.

## Development Setup

```bash
.venv/bin/python -m pip install -e .          # Editable install (exposes `reelcut` CLI)
```

**Always use `.venv/bin/python` for all Python and pip commands in this project.** Never use the system `python`, `python3`, or `pip` directly.

No test suite or linter is currently configured.

## CLI Commands

```bash
reelcut init                        # Generate default config.yaml
reelcut run config.yaml             # Full pipeline (--dry-run, --verbose flags available)
reelcut transcribe <video.mp4>      # Standalone transcription smoke-test
reelcut preview-edl <edl.json>      # Print EDL summary table
```

## Architecture

The pipeline is linear and lives entirely in `reelcut/`:

```
audio.py          → Extract mono 16kHz WAV, normalize to EBU R128 -23 LUFS
transcriber.py    → faster-whisper STT → WhisperX wav2vec2 forced alignment (30s timeout, falls back to whisper timestamps)
vad.py            → Silero VAD via ONNX runtime; filters hallucinated words after alignment (avoids PyTorch/CTranslate2 OpenMP conflict)
gap_detector.py   → Classify inter-word gaps as silence/breath/noise via scipy spectral flatness + amplitude
script_aligner.py → Fuzzy-match transcript to provided script; last take wins
retake_detector.py → Detect repeated phrases and cut earlier takes (scriptless mode)
edl.py            → Build Edit Decision List; sentence-boundary snapping (±0.6s window); merge adjacent cuts
caption.py        → Frame-by-frame PNG captions via Pillow (word_highlight or full_line style); writes .srt
renderer.py       → Parallel segment extraction → concat → caption burn-in via FFmpeg
```

Entry point is `cli.py` (Typer). Config schema is validated by Pydantic models in `config.py`.

## Key Data Structures

- **`WordTimestamp`** (`transcriber.py`) — `word`, `start`, `end`, `confidence`, `clip_path`
- **`Gap`** (`gap_detector.py`) — `start`, `end`, `duration_ms`, `gap_type`, `cut`
- **`EDLEntry`** (`edl.py`) — `start`, `end`, `keep`, `source_clip`, `reason`

## Configuration

The YAML config has five top-level sections: `input`, `cuts`, `output`, `captions`, `whisper`. See `config.yaml` for a fully-annotated example. `cuts` section controls the gap-detection thresholds (silence/breath amplitude ratios, VAD threshold, jumpcutter failure tolerance).

## Important Implementation Details

- **Multi-clip**: footage can be a `clips_folder`; clips ordered by file creation time, each transcribed independently, then stitched in script order.
- **macOS quirks**: multiprocessing uses `spawn` mode; OpenMP duplicate-lib warning suppressed at startup.
- **Font loading**: cascades bundled → system dirs → Pillow default.
- **Rendering workers**: parallel segment extraction, default 4 workers (configurable).
- **Exit codes**: 0 = success, 1 = error, 2 = warnings (e.g., script lines unmatched, output exceeds `max_duration_s`).
