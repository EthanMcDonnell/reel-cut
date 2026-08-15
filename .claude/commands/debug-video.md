---
name: debug-video
description: Debug a reelcut pipeline run by reading the .debug.* reports for a video slug. Use when audio has bad cuts, false starts survived, words are missing, or the output sounds wrong.
argument-hint: "<video-slug>"
tools: Read, Bash
model: sonnet
permissionMode: default
---

Debug a reelcut pipeline run for a video slug.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

## Step 1 — Always read the review file first

```bash
ls assets/<slug>/
```

Read `assets/<slug>/<clip-name>.debug.0.review.txt` in full. It opens with **⚠ CHECK THESE** — a ranked digest of likely defects (hard caps, skipped retakes, duplicate sentence openers, low-conf survivors, micro keep-segments, large kept gaps, VAD drops) each with a timestamp — followed by the **FINAL TRANSCRIPT** rendered as prose with `⟨cuts⟩` inline and `‹low-conf›?` words flagged. This alone triages most issues: each digest line points you to the section/file below.

Then read `.debug.6.summary.txt` for the full config + EDL detail behind a flagged line.

## Step 2 — Pull additional files only if needed

Pipeline order: 0.review → 1.raw → 1b.sentences → 2.post-retrans → 3.post-align → 4.post-vad → 5.timeline → 6.summary → 7.fixlog

- **`*.debug.7.fixlog.txt`** — what the last `/prepare-video` auto-changed in the EDL and what it deliberately left for a human. Read first when the output differs from a raw transcribe; absent if that run made no certain fixes.

- **`*.debug.4.post-vad.txt`** — read when hallucinations were dropped or retake boundaries look wrong. Shows every word after VAD filtering (final word list) with confidence scores, `[OUTTAKE]` flags, and `──── CUT ────` rules interleaved at each EDL cut boundary.
- **`*.debug.3.post-align.txt`** — read when a word is missing and you want to know if VAD dropped it. Shows words after WhisperX alignment, before VAD.
- **`*.debug.2.post-retrans.txt`** — read when a word is missing and you want to know if alignment dropped it. Shows words after retranscription, before alignment.
- **`*.debug.5.timeline.txt`** — read when there's a specific bad moment ("why didn't this gap get cut?"). Shows words and gaps interleaved with KEEP/CUT decisions and skip reasons.
- **`*.debug.1.raw.txt`** — read only when a word is missing from all other files. Shows raw Whisper output before any processing.
- **`*.debug.1b.sentences.txt`** — read when captions run sentences together or cuts land mid-sentence. Shows raw words grouped into sentences by `is_sentence_boundary`, with `VIA` = `punct` (Whisper full stop) or `caps+pause` (recovered boundary). A long run with no break means a missing full stop; a `caps+pause` split where none belongs means the pause threshold is too low.

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

### TIMELINE (read `*.debug.5.timeline.txt`)
- `KEEP [too short]` → gap below threshold; raise `min_silence_ms` or accept
- `KEEP [measured onset leaves nothing to cut]` → the next word is low-confidence, so its onset was
  measured from the audio rather than trusted, and the measured onset leaves no room past
  `speech_pad_ms`. Usually a breath running straight into the word — nothing to remove
- `KEEP [mid_sentence_floor]` → gap detector said CUT but EDL suppressed it; lower
  `mid_sentence_cut_floor_ms`. **Also fires spuriously**: the label is emitted whenever
  `gap.speech_end` is missing from the EDL cut boundaries, and `edl.py`'s `min_keep_ms` floor can
  move that boundary — so a cut that *did* happen gets reported as kept. Check the EDL entries
  before trusting this one
- `KEEP [preserve_start/preserve_end]` → within protected region

### EDL ENTRIES
- Many tiny segments (< 0.5s) → over-cutting; raise `min_silence_ms` or `mid_sentence_cut_floor_ms`
- Long segment containing a known false start → retranscription didn't surface words OR retake detection didn't fire

## Step 4 — Report findings

1. The symptom
2. The root cause (which section + which value/decision)
3. The fix (config change or EDL manual edit)
