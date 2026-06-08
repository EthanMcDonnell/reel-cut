---
name: debug-video
description: Debug a reelcut pipeline run by reading the .debug.* reports for a video slug. Use when audio has bad cuts, false starts survived, words are missing, or the output sounds wrong.
tools: Read, Bash
model: sonnet
permissionMode: default
---

Debug a reelcut pipeline run for a video slug.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

## Step 1 — Always read the summary file first

```bash
ls assets/<slug>/
```

Read `assets/<slug>/<clip-name>.debug.summary.txt` in full. This covers config, pipeline summary, retranscription windows, retake detection, image overlays, and EDL — enough to diagnose most issues.

## Step 2 — Pull additional files only if needed

Pipeline order: raw → post-retrans → post-align → post-vad

- **`*.debug.post-vad.txt`** — read when hallucinations were dropped or retake boundaries look wrong. Shows every word after VAD filtering (final word list) with confidence scores and `[OUTTAKE]` flags.
- **`*.debug.post-align.txt`** — read when a word is missing and you want to know if VAD dropped it. Shows words after WhisperX alignment, before VAD.
- **`*.debug.post-retrans.txt`** — read when a word is missing and you want to know if alignment dropped it. Shows words after retranscription, before alignment.
- **`*.debug.timeline.txt`** — read when there's a specific bad moment ("why didn't this gap get cut?"). Shows words and gaps interleaved with KEEP/CUT decisions and skip reasons.
- **`*.debug.raw.txt`** — read only when a word is missing from all other files. Shows raw Whisper output before any processing.

## Step 3 — Diagnose by section

### CONFIG
- `wide_word_threshold_s` too high → wide words not retranscribed
- `min_word_confidence` too low → bleed words survive, block gap cuts
- `mid_sentence_cut_floor_ms` too high → short gaps inside false starts not cut
- `repetition_detection: OFF` → false starts can only be removed by gap cuts
- `max_retake_gap_s` too low → real retakes far apart missed; too high → false positives

### PIPELINE SUMMARY
- Hallucinated words dropped > 0 → check if real words were lost (read post-vad)
- WhisperX fallback → timestamps are Whisper-only (±100ms); expect less precise cuts

### RETRANSCRIPTION WINDOWS
- `action=no_change` → nothing found, wide word stays as-is
- `action=boosted` → dead air confirmed, gap detection unblocked but no new words
- `action=replaced` → new words spliced in; check `kept` vs `dropped`
- `raw` empty → Whisper found nothing; clip too short/quiet, or `retranscribe_no_speech_threshold` too low
- False start survived despite window firing → `min_silence_ms` too high to split the pause between attempts; lower it so the window splits into sub-clips

### RETAKE DETECTION
- `disabled` → false starts must be caught by gap cuts alone
- No ranges despite known false start → phrase didn't match exactly (transcription error) or gap exceeded `max_retake_gap_s`

### TIMELINE (read `*.debug.timeline.txt`)
- `KEEP [hard_floor]` → adjacent word too low-conf; gap blocked regardless of duration
- `KEEP [too short]` → gap below threshold; raise `min_silence_ms` or accept
- `KEEP [mid_sentence_floor]` → gap detector said CUT but EDL suppressed it; lower `mid_sentence_cut_floor_ms`
- `KEEP [preserve_start/preserve_end]` → within protected region

### EDL ENTRIES
- Many tiny segments (< 0.5s) → over-cutting; raise `min_silence_ms` or `mid_sentence_cut_floor_ms`
- Long segment containing a known false start → retranscription didn't surface words OR retake detection didn't fire

## Step 4 — Report findings

1. The symptom
2. The root cause (which section + which value/decision)
3. The fix (config change or EDL manual edit)
