# ReelCut — Issues & Optimisations

## Critical

### 1. Empty words list crashes sentence snapping (`edl.py:219`)
`min()` on an empty sequence raises `ValueError`. Happens when a clip has no detected speech.
```python
return min(words, key=lambda w: abs(w.end - t)).end  # crashes if words=[]
```

### 2. Broken symlinks crash caption render (`renderer.py:208`)
`dest.exists()` returns `False` for broken symlinks, so the check is bypassed and `os.symlink()` crashes.
```python
if not dest.exists():
    os.symlink(src, dest)  # fails if broken symlink already exists
```

### 3. Silent normalization failure (`audio.py:56–67`)
If the two-pass loudnorm probe fails, it falls back to single-pass silently — callers never know normalization was degraded.

### 4. `signal.SIGALRM` is Unix-only (`transcriber.py:91`)
The 30s timeout for WhisperX model load uses `SIGALRM`, which doesn't exist on Windows. Will crash immediately on Windows before any transcription.

---

## Bugs

### 5. Duplicate filename collision in `done/` (`cli.py:126`)
`video.rename(dest)` crashes if a file with the same name already exists in `done/`. Happens if you reprocess the same input folder twice.

### 6. `caption.py:46` — IndexError on empty words
```python
total_duration = words[-1].end  # IndexError if caption_words is empty
```
Triggered when the script has no matching footage so nothing is remapped.

### 7. `renderer.py:201–203` — `min()`/`max()` on empty dict
If `caption_frames` is passed but `frame_map` ends up empty, `min(frame_map)` raises `ValueError`.

### 8. `_collect_clips()` sorts three times then sorts again (`cli.py:352–363`)
Globs `.mp4`, `.mov`, `.mkv` separately, sorts each, combines, converts to `set`, then sorts again. The intermediate sorts are wasted work, and `set()` destroys ordering before the final sort anyway.

### 9. Unreliable clip ordering via `st_ctime` (`cli.py:88`, `cli.py:316–322`)
`ctime` is inode-change time on Linux (not creation time), making ordering non-deterministic across platforms. Use filename sort or `st_mtime` instead.

### 10. Dead `render_multi_clip()` function (`renderer.py:83–92`)
Function exists but is never called and does nothing beyond delegating to `render()` with an unused `clips` parameter.

### 11. Unused `config` parameter in `_extract_segments()` (`renderer.py:104`)
Parameter was likely planned but never implemented. Should be removed.

---

## Performance

### 12. Redundant audio resampling (`gap_detector.py:55–64`)
`detect_gaps()` resamples audio to 16kHz, but the caller already extracted a 16kHz WAV via FFmpeg. Doubles the computation.

### 13. O(n²) transcript matching (`script_aligner.py:114–146`)
For every transcript position, the algorithm scans all script positions. For a 30-min transcript (~5k words) against a 1k-word script, worst case is ~10M inner-loop iterations.

### 14. Caption frame cache rebuilds word-to-line mapping redundantly (`caption.py:277–310`)
Builds both `word_to_line` and `all_words_flat` as separate structures then iterates both per frame. For long videos at 30fps the redundant allocation is significant.

### 15. Progress bar updated on every segment (`renderer.py:157–158`)
Calls `progress.update()` for every extracted segment. For large EDLs (1000+ segments) this creates excessive terminal I/O.

---

## Error Handling

### 16. `_run_pipeline` exceptions lose stack traces (`cli.py:110–115`)
```python
except Exception as exc:
    err_console.print(f"[red]Failed:[/red] {video.name} — {exc}")
    continue
```
The full traceback is swallowed. Add `--verbose` traceback output or at minimum `traceback.format_exc()`.

### 17. `torch.set_num_threads(1)` called on every `align()` invocation (`transcriber.py:76`)
Repeatedly sets global torch thread count on every call. Should be set once at startup.

---

## Configuration

### 18. No validation for negative/zero resolution (`config.py:51–56`)
`[0, 0]` or `[-1920, 1080]` pass validation. Should check both values are positive integers above a minimum (e.g. 320).

### 19. No GPU check for `float16` compute type (`config.py:74`)
Config allows `compute_type: float16` with no validation that a GPU is present. Crashes at transcription time on CPU-only machines.

---

## Code Quality

### 20. Hardcoded 0.3s caption grace period (`caption.py:324`)
```python
if t > words[last_idx].end + 0.3:
```
Not configurable. Too short for slow speech, potentially too long for fast speech.

### 21. Hardcoded 64-sample minimum chunk in gap detection (`gap_detector.py:95`)
```python
if len(chunk) < 64:
    return "silence"
```
Magic number with no config or comment explaining the choice.

### 22. `os.symlink` instead of `Path.symlink_to()` (`caption.py:214`)
Inconsistent with the rest of the codebase which uses `pathlib.Path` throughout.
