# Instagram De-dup Evasion — Technique-by-Technique Plan

**Status:** planning only. Written 2026-07-19. Companion to `INSTAGRAM_DEDUP_PLAN.md`
(the research record — read its "Research findings" section first; this doc does not repeat it).

**Goal:** make the three hook variants (`render-hooks` → `output/<slug>/<title>.mp4`, identical
body + ~3s different hook) *not* get clustered as near-duplicates by Instagram, so each gets
independent reach instead of being throttled.

**Blunt summary before you read further:** 7 of the 9 techniques below are the *exact*
transformations Meta's SSCD copy-detector and its audio fingerprinter are trained to see through —
and #9 is now measured, not estimated. Building them into the pipeline is mostly wasted effort.
This doc exists to (a) prove that technique-by-technique so we stop reconsidering it, (b) isolate
the 1–2 places where there *is* real leverage, and (c) point at the levers that actually work. It
is deliberately not a "here's how to wire up all 9 tricks" doc — that plan would fail.

---

## The one constraint that dominates everything

All three variants are **cut from the same footage**, so the **voiceover is byte-identical across
all three** — it is `main.audio` from the same input file (`renderer.py` `_final_encode`,
`main.audio.filter("aresample", …)`), not a regenerated/synthesized track. It is not TTS we can
re-seed; it's the recording.

- Meta's audio fingerprinting matches on the voice even after pitch/speed/tempo edits (~97%,
  per the research doc). A byte-identical voiceover is the strongest possible cross-variant signal.
- IG's Originality Score deprioritizes content sharing **70%+ visual OR audio** with your prior
  post — the "OR" matters: even if we somehow broke the *visual* similarity, the identical
  voiceover alone can trip the audio branch.

**Consequence:** any plan that leaves the voiceover identical has a hard ceiling. No amount of
re-encoding, cropping, or music-swapping removes an identical voice track. Keep this in mind for
every row below.

---

## The 8 techniques, scored against IG's actual detector

"Beats" = what layer the technique defeats. IG does **not** primarily dedup on file hash — it runs
content-based SSCD (visual) + audio fingerprinting. So "beats file hash" ≈ "beats nothing IG uses."

| # | Technique | Beats | Effect on IG clustering | Pipeline cost | Verdict |
|---|-----------|-------|-------------------------|---------------|---------|
| 1 | Re-encode (res/bitrate/codec) | file/perceptual hash only | ~0 — SSCD & audio-fp unaffected | trivial | Free hygiene, not the answer |
| 2 | Crop / zoom 2–5% | naive frame-diff | ~0 — SSCD trained through **large** crops | trivial | Pointless alone |
| 3 | Overlays / filters / color grade | naive frame-diff | **Light:** ~0 (trained through color/tone + watermark/overlay insertion). **Heavy** (large screen fraction, whole runtime): real — but that *is* "different body" (Tier 3) | light: trivial / heavy: high | Light useless; heavy = the real visual lever |
| 4 | Horizontal flip / mirror | naive frame-diff | **Exactly 0** — SSCD explicitly trained on flips | trivial | **Built anyway** (see below) — costs nothing, expect nothing |
| 5 | Speed / frame-rate change | naive frame-diff | ~0 — audio-fp sees through tempo; desyncs captions, changes duration, feels off | medium (caption resync) | Skip — risk > reward |
| 6 | Trim frames start/end + light color | naive frame-diff | ~0 on SSCD | trivial | Free hygiene, not the answer |
| 7 | Alter audio (swap/tweak track) | — | **Only technique with real headroom** — but capped hard by the identical voiceover (see below) | low–medium | Worthwhile *only* as a genuine, prominent music swap; tweaks are dead |
| 8 | Compress differently before upload | file hash only | ~0 | trivial | Same as #1 |
| 9 | Per-cut ±ms jitter on every EDL boundary | file hash only | **0 — measured, see below** | medium (caption/image resync + clipped-onset risk) | **Rejected on data** |

### Why #7 is the only interesting one — and why it's still capped
A genuinely **different, prominently-mixed music bed per variant** does change the audio
fingerprint's overall energy. But our voiceover sits on top and is identical, and the fingerprinter
is built to isolate/match a recurring voice under different music. So a music swap *reduces* audio
similarity but cannot get it under threshold while the voice is shared. Pitch/tempo/EQ tweaks to
the voice are explicitly defeated. Net: swapping music is a legitimate partial lever; "tweaking"
audio is not. (Also note: `INSTAGRAM_DEDUP_PLAN.md` locked "one audio track only" — a real swap
needs ≥3 distinct tracks in `assets/audio/`, which is currently a user decision to reopen.)

---

## Measured — technique #9, per-cut ms jitter (tested 2026-07-27)

The one technique in this table with first-party numbers rather than a reasoned estimate. The
proposal: jitter *every* keep-segment boundary by ±N ms, so cumulative drift makes each variant
un-alignable. Tested on `database-split-brain` (21 keep segments, 83.5s) — identical source,
identical segment order, identical encode; the only variable is the boundary jitter.
Harness + full write-up: `scratchpad/jitter_test/` (`RESULTS.md`).

**The premise is sound.** Drift does accumulate; variants are not a global time-shift:
2 ms jitter → −15.1 ms total, 50 ms → −377.7 ms.

**Video — it never changes.** Comparing decoded frames (grayscale MAE, 0–255):

| jitter | same-index MAE | nearest-frame MAE | frames re-matched | slide needed |
|--------|---------------:|------------------:|------------------:|-------------:|
| 2 ms   | 1.329 | 0.427 | 100.0% | 1 frame |
| 5 ms   | 4.025 | 0.470 | 100.0% | 2 |
| 15 ms  | 5.717 | 0.379 |  99.8% | 3 |
| 50 ms  | 11.680 | 0.637 |  99.8% | 10 |

Every jittered frame is a baseline frame that slid. This is why the folklore is persuasive —
same-index diff *does* rise (1.3 → 11.7), so a naive check "sees a change" — and why it's wrong.
Note SSCD was never needed: the **weakest possible matcher** (raw grayscale nearest-frame)
re-aligns 100%. A descriptor trained for crop/flip invariance can only do better.

**Audio — the fingerprint survives.** Landmark constellation hashes + offset voting, with controls:

| variant | hash recall | top-offset votes | offset peaks |
|---------|------------:|-----------------:|-------------:|
| **SELF (control)** | 100.0% | **21714** | 1 |
| 2 ms  | 34.2% | 5842 | 2 |
| 5 ms  | 45.2% | 5789 | 3 |
| 15 ms | 42.4% | 4525 | 2 |
| 50 ms | 36.5% | 1445 | 7 |
| **DIFFERENT (control)** | 2.0% | **6** | 48 |

`DIFFERENT` = another render, same speaker/mic/room, different words — the genuinely-different pole.

Raw hash recall *does* fall to ~34–45%, because moving a segment shifts its phase against the STFT
frame grid. That is not the decision variable. A landmark matcher declares confident identity on
*tens* of consistent landmarks; 2 ms jitter yields **5842** against a null of **6** (~970×), and
50 ms still yields 1445 (~240×). The 2–7 offset peaks are the per-segment alignment jitter creates,
which is the routine case for clip reuse and compilations, not a matcher failure.

**Why:** keep segments are sentence-length (median 3.16s). Jitter moves 21 seams and leaves 83
seconds of identical speech between them.

**The trap to remember:** 21714 → 5842 *looks* like 73% progress. The decision is thresholded, not
linear — the bar is ~tens, so it is 0% progress. No jitter value on that curve arrives, which is why
sweeping to 25× the proposal didn't help. Nor do these stack: 6 of the 8 techniques above are inside
SSCD's training augmentation set, and combining transforms a model is invariant to yields invariance.

---

## What actually moves the needle (tiered)

### Tier 0 — Free render hygiene (**implemented**; ~0 IG effect but costless)
Vary per-variant **encoder settings** (bitrate, codec/container), **trim a few frames**, and
**vary metadata**. This defeats any naive hash/perceptual-hash clustering. IG doesn't lead with
that, so treat this as cheap insurance and completeness, **not** the fix. Do it because it's free,
don't expect it to change reach.

Shipped as `output.encode_variation` (`config.yaml`, `renderer.py:_encode_variation`): per-hook CRF
(libx264) or bitrate (videotoolbox) jitter, keyframe-interval jitter, and a varying metadata tag,
all deterministically seeded by output filename so re-renders stay reproducible. Verified to produce
3/3 distinct files on both codec paths. Deliberately touches **only** the encoder — no cut-boundary
changes, so no clipped word onsets and no caption/image resync (the cost that sank #9).

### Tier 0b — Horizontal flip (**implemented** on request; ~0 IG effect)
Shipped as `output.flip` (`config.yaml`, `renderer.py` `_final_encode`, `cli.py` `_flip_plan`).
`mode` selects which hooks are mirrored (`off` / `alternate` / `all`) and `apply` decides whether a
flipped render replaces that hook's video (`in_place`) or is written beside it (`duplicate` — so
`all` + `duplicate` turns 3 hooks into 6 files).

Two things to be clear about, since this table's row #4 says never:

- **The "it mirrors the captions" objection is solved, not ignored.** The `hflip` is applied to the
  footage *before* the caption/title/image PNG sequence is composited, so on-screen text renders
  normally. `tests/test_flip_render.py` renders a real clip and asserts exactly that. What still
  mirrors is anything physically in shot — background text, a logo on clothing, gesture handedness.
- **The 0-effect verdict is unchanged.** SSCD's training augmentation includes horizontal flips, so
  a mirrored copy still matches its original. `duplicate` mode is worth having as a way to get a
  *second post* out of one hook (see Tier 1 — spacing is what earns the reach), not because the
  mirror hides it.

A duplicate does **not** cost a second render. Measured on `canva-session-revocations-s3`: segment
extraction is ~5:00 of a ~6:00 render (~80%) and depends only on the EDL, which is identical for a
hook and its mirror. `render()` therefore takes a list of `(path, flip)` outputs and shares one
extraction + concat + caption-sequence pass across all of them, repeating only `_final_encode`.
The first cut of this shipped without that and re-extracted all 26 segments for the duplicate.

### Tier 1 — Posting strategy (the durable answer — no code)
Per the research doc this is where de-clustering actually happens:
- **Space posts days apart** rather than back-to-back on the same account.
- Use **IG Trial Reels** (built to test variants against non-followers).
These outperform every render trick and cost nothing to build. This should be the default guidance
attached to every 3-hook batch.

### Tier 2 — Audio differentiation (real but capped — reopen a locked decision)
Different **prominent music bed per variant** (technique #7 done properly). Requires reopening the
"one track only" decision and adding ≥3 tracks to `assets/audio/`. Reduces audio similarity but
cannot fully clear it while the voiceover is shared. Medium value, low cost *if* tracks exist.

### Tier 3 — Body differentiation (the only true SSCD lever — expensive)
Meaningfully different **overlay / B-roll coverage across the whole runtime** per variant (heavy
version of #3), or a genuine re-edit. This is the only thing that reliably drops visual similarity
below SSCD's 0.75. It also spends exactly the efficiency the 3-from-1 pipeline exists to provide,
so it's the deferred "only if throttling persists" option.

---

## If we implement the worthwhile render-side pieces — where the code goes

Injection points (all already load per-slug config, so per-variant params are a small addition):

- **Per-variant transform dispatch:** the `render_hooks` loop (`reelcut/cli.py:161`, `for i in
  range(n)`) is where each variant is rendered. Thread a per-index transform spec from here into
  `_phase2` → `_final_encode`.
- **Visual transform point (Tier 0 / heavy Tier 3):** the single `video.filter("scale", w, h,
  force_original_aspect_ratio="disable")` line in `_final_encode` (`reelcut/renderer.py`, ~line
  269) is the one place all variants are currently identical visually. Per-variant crop/overlay
  would chain here. (Note: light crop/overlay = Tier 0-useless; only heavy per-variant overlay
  from real B-roll is worth the wiring.)
- **Encoder settings (Tier 0):** the `common` dict + `vt_kwargs` / `b:v` in `_final_encode` —
  vary bitrate/codec/container per index. Trivial.
- **Audio swap (Tier 2):** `audio.json` per slug → `_resolve_audio_tracks` (`reelcut/cli.py:842`).
  It already resolves a per-video track by name from `assets/audio/`; giving each variant a
  different `track` needs only a per-index `audio.json` (or a per-index entry) — **no renderer
  change**, just drop the tracks in and have `/produce-video` assign a different one per hook.
- **Config surface:** `config.yaml` `output.*` (resolution/fps/bitrate) and `audio.tracks.*` are
  where any new per-variant knobs would live.

---

## Do NOT build
- **#2/#6 small crop/trim, #5 speed, light #3 filters, #1/#8 re-encode-for-hash** as *IG evasion* —
  they don't move SSCD/audio-fp. (Tier 0 keeps #1/#6/#8 only as free hash hygiene, not as the fix.)
- **Audio pitch/tempo/EQ "tweaks"** — defeated by the fingerprinter.

---

## Bottom line & recommended sequence
1. **Adopt Tier 1 now** (spacing / Trial Reels) — biggest effect, zero build. Attach as standing
   guidance to every 3-hook batch.
2. **Implement Tier 0** as free insurance (per-variant encoder settings + frame trim) — small,
   harmless, defeats naive hashing.
3. **Reopen the "one track" decision → Tier 2** if you want a render-side lever: add ≥3 music beds
   and assign one per hook via `audio.json`. Real but capped by the shared voiceover.
4. **Defer Tier 3** (per-variant body/overlay differentiation) unless 1–3 prove insufficient — it's
   the only thing that truly de-clusters and it costs the pipeline's core efficiency.

The uncomfortable truth this doc is meant to make un-ignorable: with an identical body **and** an
identical voiceover, there is no cosmetic render trick that reliably de-clusters the three. The
levers are posting cadence and (expensively) making the videos genuinely different.

---

## Open decisions for the user
1. **Reopen "one audio track only"?** Tier 2 needs ≥3 distinct beds. Currently locked OFF.
2. **Is Tier 3 (real per-variant body/overlay) on the table**, or is the 3-from-1 efficiency
   non-negotiable (which caps us at Tier 0–2 and posting strategy)?
3. **Do you still want the render-side Tier 0 hygiene built** even knowing it's ~0 IG effect, purely
   as cheap insurance?
