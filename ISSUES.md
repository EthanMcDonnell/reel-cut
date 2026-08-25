# ReelCut — Issues & Optimisations

_Last reconciled against the code on 2026-06-14. Items resolved by the
scriptless-EDL migration and earlier hardening passes have been removed._

## Bugs

### 1. `run --slug` overwrites every output for a folder of clips (`cli.py:190`)
```python
stem = slug or video.stem   # slug is constant across the per-video loop
```
With `--slug` set and multiple videos, every iteration writes to the same
`{slug}.mp4` / `{slug}.captions.json`. Processing N videos silently leaves only
the last. (`transcribe`'s folder mode correctly uses `video.stem`.)

### 2. Cross-clip gap-map key collision (`edl.py:55`, fed from `cli.py:456`)
```python
gap_map[(round(g.start, 4), round(g.end, 4))] = g
```
`generate_scriptless_edl` receives every clip's gaps concatenated, but keys the
lookup on `(end, start)` with no clip identity. In `--clips-folder` mode two
clips with a word pair at the same rounded timestamps (common near `t≈0`)
collide and the second gap overwrites the first — one clip gets the wrong cut
decision. Key should include `clip_path`.

### 3. `_build_gaps` mutates shared word objects (`gap_detector.py:411`)
```python
word.end = true_end
word.start = true_start
```
`detect_gaps` is handed slices of `all_words` (same objects), so clamping
silently rewrites the timestamps later used for captions and remap. Consistent
today, but an invisible side effect inside a `detect_*` function — a trap for
anyone who reorders the pipeline. Now mutates both edges, so the blast radius
is wider than when this was filed.

### 4. Overlay reset is coarser than the drift it guards against (`cli.py:1056`)
`_clean_transcription_artifacts` deletes `images.json` / `videos.json` /
`audio.json` on every `transcribe` run. This is deliberate — `4d005bd`,
"reset overlay files on every run for a clean re-run" — it is covered by
`tests/test_clean_artifacts.py`, and `/prepare-video` warns about it in bold.
The rationale is that the overlays are keyed to the old transcript and would
drift. That is only half true:

- `videos.json` `start`/`end` are the hook window on the **output timeline**
  (`video_spec.py:8`), which does shift whenever the EDL changes. Resetting
  these is correct.
- `images.json` `start`/`end` are **source-clip** time, remapped through the new
  EDL at render (`image_spec.py:4`). They cannot drift. Nor can the authoring
  fields on `videos.json`: `title`, `subtitle`, `scrim`, `caption`, `filename`,
  `of`.

So a re-run to verify a one-word timing fix discards every image cue and title
card in the slug to protect two floats that only `videos.json` carries.
`assets/` is gitignored, so there is no undo — after re-transcribing
`hot-take-20260825T010121Z` both files were only recoverable because their
contents happened to be quoted in an earlier session transcript.

Narrow the reset to the fields that actually drift: blank `start`/`end` on
`videos.json` base entries and leave the rest, or rename the overlays to `.bak`
instead of unlinking. Note this only bites when `reelcut transcribe` is invoked
directly — going through `/prepare-video` surfaces the warning first.

## Performance

### 5. `_remap_kept_words` is O(words × cuts) (`cli.py:744`)
`remap()` recomputes `sum(e - s for s, e in cuts if ...)` over all cuts on every
word, in both phase 1 and phase 2. Quadratic on long, heavily-cut videos. Sort
cuts once and use a prefix sum + `bisect` for O(log n) per word.

### 6. WhisperX alignment model reloaded per clip (`transcriber.py:123`)
`align()` calls `whisperx.load_align_model(...)` every invocation, and the
pipeline calls `align` once per clip. Multi-clip jobs reload wav2vec2 each time.
Load once and reuse.

### 7. Caption frame cache builds redundant word maps (`caption.py:296`)
`_build_frame_cache` builds both `word_to_line` and `all_words_flat`, then
iterates per frame. For long videos at 30fps the redundant allocation adds up.

### 8. Progress bar updated on every segment (`renderer.py:182`)
`progress.update()` fires once per completed segment in the `as_completed` loop.
For large EDLs (1000+ segments) this is excessive terminal I/O.

## Testing

### 9. Real-clip fixtures pin post-clamp word lists, so the clamp is untestable
`tests/fixtures/retake/<slug>.txt` is copied from `.debug.4.post-vad`, which is
*after* `_build_gaps` has clamped over-long words, and `test_real_clip_edl.py`
loads pinned gaps rather than calling `detect_gaps`. Both fixture boundaries sit
downstream of the clamp, so no real-clip test reaches it — that is how the
tail-anchored `GitHub` bug shipped, and a post-vad fixture captured at the time
would have pinned the corrupted span as correct.

Worked around by `tests/fixtures/longword/` (pre-clamp spans from
`.debug.3.post-align` plus a 10 ms speech/silence envelope), which covers the
clamp but duplicates fixture data for the same clips. The cleaner fix is to make
`tests/fixtures/retake/` post-*align* and let `detect_gaps` run inside the test —
that needs the waveform, so it also needs the envelope trick, and it churns every
existing gaps fixture. Not attempted.

### 10. `tests/test_send_script.py` fails to import
```
ImportError: cannot import name 'LIMIT' from 'send_script'
```
`scripts/send_script.py` no longer exports `LIMIT` or `chunk`. The module has
been uncollectable for long enough that a bare `pytest tests/` errors out at
collection, which means the suite is normally run with it excluded and any other
regression in it is invisible. Either fix the import or delete the test.

## Code Quality

### 11. Hardcoded 0.3s caption grace period (`caption.py:22`, used at `:337`)
```python
_CAPTION_GRACE_S = 0.3
```
Module constant, not configurable. Too short for slow speech, potentially too
long for fast speech.

### 12. Hardcoded 64-sample minimum chunk in gap detection (`gap_detector.py:116`)
```python
if len(chunk) < 64:
    return "silence"
```
Magic number with no config or comment explaining the choice.

### 13. Captions doc stem depends on whether `--slug` was passed (`cli.py:69`, `:106`)
```python
stem = slug or input_folder.stem
```
The debug reports are always named from the clip stem, so the same clip
transcribed with and without `--slug` leaves the asset dir with
`E01BE977-….debug.*.txt` beside `hot-take-….captions.json`. Nothing breaks —
the cleaner globs `*.captions.json`, so no stale doc survives — but the pairing
is unobvious when reading an asset dir by hand.

### 14. Unused `import os` in `caption.py` (`caption.py:4`)
Orphaned after the symlink logic moved to `renderer.py`. Safe to drop.
