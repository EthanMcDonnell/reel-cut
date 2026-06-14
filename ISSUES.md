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

### 3. `_build_gaps` mutates shared word objects (`gap_detector.py:249`)
```python
word.end = true_end
```
`detect_gaps` is handed slices of `all_words` (same objects), so clamping
`word.end` silently rewrites the timestamps later used for captions and remap.
Consistent today, but an invisible side effect inside a `detect_*` function —
a trap for anyone who reorders the pipeline.

## Performance

### 4. `_remap_kept_words` is O(words × cuts) (`cli.py:744`)
`remap()` recomputes `sum(e - s for s, e in cuts if ...)` over all cuts on every
word, in both phase 1 and phase 2. Quadratic on long, heavily-cut videos. Sort
cuts once and use a prefix sum + `bisect` for O(log n) per word.

### 5. WhisperX alignment model reloaded per clip (`transcriber.py:123`)
`align()` calls `whisperx.load_align_model(...)` every invocation, and the
pipeline calls `align` once per clip. Multi-clip jobs reload wav2vec2 each time.
Load once and reuse.

### 6. Caption frame cache builds redundant word maps (`caption.py:296`)
`_build_frame_cache` builds both `word_to_line` and `all_words_flat`, then
iterates per frame. For long videos at 30fps the redundant allocation adds up.

### 7. Progress bar updated on every segment (`renderer.py:182`)
`progress.update()` fires once per completed segment in the `as_completed` loop.
For large EDLs (1000+ segments) this is excessive terminal I/O.

## Code Quality

### 8. Hardcoded 0.3s caption grace period (`caption.py:22`, used at `:337`)
```python
_CAPTION_GRACE_S = 0.3
```
Module constant, not configurable. Too short for slow speech, potentially too
long for fast speech.

### 9. Hardcoded 64-sample minimum chunk in gap detection (`gap_detector.py:98`)
```python
if len(chunk) < 64:
    return "silence"
```
Magic number with no config or comment explaining the choice.

### 10. Unused `import os` in `caption.py` (`caption.py:4`)
Orphaned after the symlink logic moved to `renderer.py`. Safe to drop.
</content>
</invoke>
