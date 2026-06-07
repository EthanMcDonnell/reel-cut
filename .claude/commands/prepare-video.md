---
name: prepare-video
description: Phase 1 — Wire footage path into config, run reelcut transcription, then review and fix EDL anomalies (bad cuts, multiple takes, silence issues) in captions.json.
tools: Read, Edit, Bash
model: sonnet
permissionMode: default
---

Runs reelcut Phase 1 transcription for a video slug, then reviews and corrects anomalies in the resulting captions.json.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Example: `/prepare-video netflix-cdn-architecture`

## Step 1 — Locate footage

The user drops their footage into `assets/<video-slug>/` before running this command.

## Step 2 — Run transcription

```bash
.venv/bin/reelcut transcribe config.yaml --slug <video-slug> --footage "assets/<video-slug>/"
```

Do not edit config.yaml.

Output goes to `assets/<slug>/`, named after the footage stem (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). The transcription step prints the actual path.

## Step 3 — Inspect the EDL

The transcription step prints the actual captions path — use that filename. It may be named after the footage stem, not the slug (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`).

```bash
.venv/bin/reelcut preview-edl "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

Then read both output files:
1. `assets/<video-slug>/<actual-captions-filename>.captions.json` — EDL entries and words
2. `assets/<video-slug>/<actual-captions-filename>.debug.summary.txt` — config, pipeline summary, retranscription windows, retake detection, EDL

## Step 4 — Identify and fix anomalies

Work through the EDL and word list looking for the following, in order of priority:

### Multiple takes (genuine repeated content)
Look for the same sentence or near-identical phrase (allow one differing word) appearing more than once across the `words` array and the aligned debug file (`*.debug.aligned.txt`). The last occurrence is the intended take. Set `keep: false` on EDL entries covering all earlier occurrences.

### Multiple takes packed inside a single KEEP segment
If all occurrences of a repeated phrase fall within the time range of a single KEEP EDL entry (no existing entry boundary to flip), the pipeline could not split them automatically. Fix it manually:

1. **Find the split point** — use the word timestamps to locate where the false starts end and the final take begins. The final take is the last complete occurrence of the phrase; its first word's `start` is the split point.
2. **Insert new EDL entries** — replace the single KEEP entry with three consecutive entries covering the same total time range:
   - `keep: true` — `entry.start` → `final_take_first_word.start` (everything before the final take that is legitimate speech, or omit this entry if the false starts begin immediately)
   - `keep: false, reason: "false start — packed takes"` — the false-start region
   - `keep: true` — `final_take_first_word.start` → `entry.end` (the final take)
   The three entries' ranges must be contiguous and together cover exactly `entry.start` → `entry.end`. Use the same `source_clip` as the original entry.
3. **Remove false-start words** — delete from the `words` array any word whose timestamp falls within the new CUT entry's range.

### Bad silence cuts
Cut segments that are very short (< 80ms) between two kept segments — may indicate a cut landing mid-word. Cross-reference the word timestamps: if a cut's `start`/`end` overlaps with a word's `start`/`end` in the `words` array, restore it (`keep: true`, `reason: "restored — mid-word cut"`).

### Hallucinated words
Words in the `words` array with very low alignment confidence (< 0.15) and no correspondence in the spoken content, especially at clip boundaries. Remove from the `words` array. Do not touch the EDL for this.

### Mid-sentence cuts
The pipeline protects against mid-sentence cuts below ~1500ms, so any cut appearing mid-sentence (word before the cut has no sentence-ending punctuation) is unexpected. Check the words on both sides:
- If they form a continuous phrase AND the cut is < 800ms — likely a breath or hesitation, restore it (`keep: true`, `reason: "restored — mid-sentence cut"`).
- If the cut is > 800ms — do not auto-restore. Flag it in the Step 5 report as needing a human listen: the gap may contain a restart attempt or noise that would sound worse restored than cut.

### Long unexplained cuts
Cut segments > 3s in the middle of apparent speech (not at a natural paragraph break). Check `*.debug.aligned.txt` — if the region contains speech words, restore with `keep: true` and add any missing words back.

### Dropped alignment words
Words present in `*.debug.raw.txt` (raw Whisper) with good confidence (≥ 0.5) that are absent from `*.debug.aligned.txt` and the `words` array — dropped by WhisperX alignment, not hallucinations. Common victims: short function words ('at', 'for', 'a', 'the') between two longer words. If the word clearly belongs in the sentence and was spoken, add it back to the `words` array with estimated timestamps by splitting the gap evenly between the surrounding words. Use the raw timestamps as a cross-check.

**Editing rules:**
- Change `"keep"` and `"reason"` fields in `edl` entries only — never modify `start`/`end` timestamps on existing entries
- You may INSERT new EDL entries to split a packed-takes KEEP segment — new entries must use the same `source_clip` and together span the exact same time range as the entry they replace
- Remove hallucinated entries from the `words` array by deleting the object
- Remove false-start words from the `words` array when splitting a packed-takes segment (delete words whose timestamps fall in the new CUT range)
- Add back dropped-but-real words with estimated timestamps (split the surrounding gap)
- Do not touch any other fields

After edits, re-run preview to confirm:

```bash
.venv/bin/reelcut preview-edl "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

## Step 5 — Report

Summarise:
- Keep / cut duration after fixes
- Anomalies found and what was done for each
- Any remaining issues that need a human listen (ambiguous takes, uncertain boundaries)
- Next step: `/produce-video <slug>`
