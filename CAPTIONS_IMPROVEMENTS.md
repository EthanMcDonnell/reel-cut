# Caption Improvements

A deep look at how captions are rendered today, what's broken, and a ranked set of
upgrades — including motion. Read alongside [`ARCH_IMPROVEMENTS.md`](ARCH_IMPROVEMENTS.md)
(#1 there proposes the libass migration this doc re-examines).

---

## TL;DR — what's worth doing

- **Do now, regardless of anything else:** make `word_highlight` actually render (#1) and
  wire up the stroke/outline config (#2). Both are small, both fix features that exist in
  config but are silently dead, and neither depends on the renderer decision.
- **Then make one decision:** how do you want captions to *move*? That choice (the
  "renderer fork" below) gates every animation item and is the real fork in the road.
- **High-value motion once you've chosen:** active-word pop (#4) and/or karaoke wipe (#6),
  line fades (#5), per-word emphasis from the script (#8), and presets (#11).
- **Skip unless you specifically want them:** gradient fills (#9), auto-emoji (#12), shake
  (#13). They're polish with real downsides (effort, taste, or libass limitations).

The verdict column in the [ranked table](#ranked-improvements) says this per item.

---

## How captions work today

The path is `caption.py` → PNG-per-frame → `renderer.py` symlink sequence → FFmpeg overlay.

1. `render_caption_frames()` groups words into display lines (`_group_into_lines`), then
   builds a frame→`(line_words, active_idx)` map for **every frame of the video**
   (`_build_frame_cache`, ~1800 entries for a 60s/30fps reel).
2. For each frame it renders a full **1080×1920 RGBA PNG** with Pillow
   (`_render_frame` → `_draw_text_wrapped`), deduplicating via a cache key so identical
   consecutive frames reuse the same file.
3. `renderer.py:_prepare_caption_sequence` symlinks those PNGs into a **dense**
   `cap_%06d.png` sequence (filling every gap with a transparent `_blank.png`).
4. `_final_encode` overlays the PNG sequence onto the concatenated video in the final
   FFmpeg pass.

### The headline finding: `word_highlight` doesn't highlight

The config defaults to `style: word_highlight` with `highlight_color: "#FFD700"`, and the
code goes to real trouble to compute which word is active — `_active_word_at` does a
per-frame lookup, `_build_frame_cache` threads `active_idx` through, `_load_fonts` builds a
1.1× `font_highlight`, and `_render_frame` accepts both `active_idx` and `font_highlight`
as parameters.

**None of it is used.** `_render_frame` (caption.py:114) ignores `active_idx` and
`font_highlight` entirely and calls:

```python
text = _join_words(word.word for word in line_words)
_draw_text_wrapped(draw, text, font, config, w, y_pos, margin)
```

`_draw_text_wrapped` draws the **whole line** in `config.color` with one drop shadow. So:

- `highlight_color` is **never read anywhere** in the codebase.
- `font_highlight` is built, passed two layers deep, and dropped.
- `active_idx` is computed per frame and discarded.
- `word_highlight` and `full_line` render **identically**.

The single highest-value change is making the feature already in your config actually work.

### Second finding: `stroke` config is also dead

`CaptionsConfig` exposes `stroke`, `stroke_color`, `stroke_width` (and `config.yaml`
documents them). `caption.py` never references any of them. The only edge treatment is a
hardcoded `_SHADOW_OFFSET = 6` solid-black shadow. On bright/blown-out footage captions can
wash out, because the outline that would prevent that isn't wired up.

### Other current limitations

- **No motion of any kind.** Lines hard-cut in and hard-cut out after a grace period.
- **The overhead is partly self-inflicted.** The code already dedups to distinct caption
  states (step 2), but step 3 then re-expands them into a *dense* 1800-entry symlink
  sequence. Most of the "PNG overhead" the ARCH doc cites is that re-expansion, not Pillow.
- **Two constants fight the config.** `_WORDS_PER_LINE = 10` (module constant) is dead —
  `config.words_per_line` (default 7) is what's used — but it's a trap for the next reader.
- **Wrap math uses the base font only.** Once a highlight font scales the active word, the
  measured line width in `_draw_text_wrapped` is wrong and text can overflow or jitter as
  the active word moves.
- **Fixed vertical band.** `position` maps to three hardcoded fractions; captions can't
  dodge a logo/screenshot overlay that lands in the same region.

---

## The renderer fork (this gates all animation)

There is **no free lunch on motion**: per-word animation inherently means more *distinct*
frames, because during a pop/scale the line genuinely changes every frame. The only question
is *where you pay* — full pixel control in Python, or a subtitle engine that does timing for
free but constrains layout. Three honest options:

### Option A — Stay on Pillow, but stop re-expanding (the "sane frame" path)
Keep Pillow's full pixel control; fix the actual overhead by overlaying only the **distinct**
caption states with timed FFmpeg inputs (or a sparse sequence) instead of the dense symlink
expansion. Delete `_prepare_caption_sequence`'s gap-filling.
- **Best for:** per-word pop/bounce/scale — the trendy CapCut/Hormozi look. You draw exactly
  what you want, including reflow-on-scale.
- **Cost:** you hand-roll easing; more frames to composite than a static caption (but far
  fewer than 1800, and no symlinks).

### Option B — Migrate to ASS/libass
Emit one `.ass` file, burn with FFmpeg `subtitles=`. Deletes `render_caption_frames`,
`_build_frame_cache`, `_prepare_caption_sequence`, `_blank_frame`, and the symlink dance.
- **Best for:** clean styling + **karaoke wipe** + fades + line transitions. These are native
  (`\k`, `\fad`, `\t`, `\move`) and nearly free.
- **The catch (corrected from an earlier draft):** libass lays out a line **once**.
  `\t(...\fscx118...)` scales a word's glyphs but **does not re-flow the line** — neighbors
  don't move, so a popping word overlaps them or shoves the line off-center. The workaround
  (one `\pos` event per word, widths computed externally) rebuilds the layout machinery you
  were trying to delete. **Color emoji and gradient fills are also weak/broken in libass.**
  So the per-word *pop* (#4) is the one effect ASS handles *worst*.

### Option C — Keep Pillow as-is
Do only the correctness/style fixes (#1, #2, #7) and accept no motion.
- **Best for:** lowest effort, captions that are correct and readable but static.

### Recommendation
Your stated goal is "look good, animations built in." That points at per-word motion, which
is **Option A's** strength and **Option B's** weakness — so I'd lean **A** as the default,
because it doesn't cap the ceiling. Choose **B** only if, after prototyping, you decide the
**karaoke wipe** look is all you want — then B's simplification is a great trade. Either way,
**prototype the specific look you want on one clip before committing** (per the ARCH note).
Don't pick the renderer in the abstract; pick it to serve the effect.

| | A — Sane Pillow | B — ASS/libass | C — Pillow as-is |
|---|---|---|---|
| Per-word pop (#4) | ✅ natural | ⚠️ fights layout | ❌ |
| Karaoke wipe (#6) | ⚠️ hand-rolled | ✅ native `\kf` | ❌ |
| Fades/slide (#5) | ⚠️ hand-rolled | ✅ native | ❌ |
| Emoji / gradient | ✅ full control | ❌ limited | ✅ |
| Deletes machinery | partial | **most** | none |
| Effort | M | M–L | none |

---

## Ranked improvements

Verdict legend: **DO NOW** (worth it, no decision needed) · **WORTH IT** (clear value, do
after the fork) · **OPTIONAL** (good in the right niche) · **SKIP** (polish with real
downsides). Benefit ★ = visible impact on the final video.

| # | Improvement | Benefit | Effort | Verdict | Notes / depends on |
|---|---|---|---|---|---|
| 1 | **Make word highlight actually render** | ★★★★★ | S | **DO NOW** | Headline feature is dead code |
| 2 | **Wire up stroke/outline (+ glow)** | ★★★★☆ | S | **DO NOW** | Readability; one Pillow call |
| 4 | **Active-word pop (scale + settle)** | ★★★★★ | M | **WORTH IT** | The wow factor. Needs Option **A** |
| 8 | **Per-word emphasis from the script** | ★★★★☆ | M | **WORTH IT** | Directs attention; fits LLM edit step |
| 11 | **Style presets / templates** | ★★★★☆ | S | **WORTH IT** | Biggest usability win once features exist |
| 5 | **Line entrance/exit (fade/slide)** | ★★★★☆ | M | **WORTH IT** | Free on B, hand-rolled on A |
| 6 | **Karaoke wipe fill** | ★★★★☆ | M | **WORTH IT** | The reason to consider Option **B** |
| 3 | **Renderer fork (A/B/C)** | — | — | **DECIDE** | Gates #4–#6; see section above |
| 7 | **Background pill / box** | ★★★☆☆ | S | OPTIONAL | Guarantees contrast; style choice |
| 10 | **Smart vertical placement** | ★★★☆☆ | M | OPTIONAL | Fixes caption/overlay collisions |
| 9 | **Gradient / two-tone fills** | ★★★☆☆ | S | SKIP | Polish; broken in libass |
| 12 | **Auto-emoji / keyword icons** | ★★★☆☆ | M | SKIP | Polarizing; no color emoji in libass |
| 13 | **Shake / bounce on emphasis** | ★★★☆☆ | M | SKIP | Niche; easy to overdo |

---

## Detailed specs

### 1 — Make word highlight actually render · DO NOW · ★★★★★ · S

The feature is 90% built; only the draw step is missing. Pass `active_idx` through to a
word-aware draw routine that lays words out token-by-token and paints the active token in
`highlight_color`.

- Replace the single `_draw_text_wrapped(text, …)` call with a token-walking layout that
  tracks each word's x-position, so it can color one word differently.
- **First cut: color-only** (don't resize the active word) — no reflow, no jitter, ships in
  an afternoon. Defer the size bump to #4 where reflow is handled deliberately.
- This is the difference between "static subtitles" and the look people expect, and it's a
  prerequisite for most style items below.

**Verify:** render a clip; exactly one word is highlighted at any moment and it advances in
sync with speech.

### 2 — Wire up stroke/outline (+ optional glow) · DO NOW · ★★★★☆ · S

Honor `stroke`, `stroke_color`, `stroke_width`. Pillow's `draw.text(..., stroke_width=,
stroke_fill=)` does this in one call — cheaper than the manual shadow and it keeps captions
readable over bright footage. Keep the drop shadow as a separate optional layer (the best
look is usually tight outline + soft offset shadow). Optional **glow**: a blurred colored
copy underneath (`GaussianBlur`).

**Verify:** captions stay legible on a white/over-exposed background frame.

### 4 — Active-word pop · WORTH IT · ★★★★★ · M · needs Option A

When a word becomes active, scale it up fast and settle back (~1.0 → 1.18 → 1.0 over ~120ms,
ease-out), with the color change from #1. This is the signature motion of high-retention
short-form captions, and the main reason to prefer **Option A** over ASS.

- **On A (Pillow):** re-render the affected line for the ~4–6 animation frames with eased
  scale, re-flowing neighbors so the line stays centered. Each pop frame is genuinely
  distinct — that's expected and still far cheaper than a dense 1800-frame sequence.
- **On B (ASS):** awkward — `\fscx/\fscy` doesn't reflow, so the word overlaps neighbors.
  Avoid unless you absolutely-position each word, which defeats the migration's simplicity.

**Verify:** scrub across a word boundary; scale ramps smoothly and the line stays centered.

### 8 — Per-word color & emphasis from the script · WORTH IT · ★★★★☆ · M

Let the captions doc carry optional per-word styling (`emphasis: true`, `color: "#FF3B30"`)
so key words — numbers, product names, the punchline — pop differently. The pipeline already
LLM-edits `captions.json` between phases, so emphasis tagging is a natural fit there. This is
where captions stop being uniform and start *directing attention* — and it leans directly on
the "shocking numbers / dev frustration" patterns in your top-performers notes.

### 11 — Style presets / templates · WORTH IT · ★★★★☆ · S

Bundle the knobs into named presets (`captions.preset: hormozi | clean | bold-outline |
karaoke`) so a whole look is one config line instead of tuning eight fields. Cheap once the
underlying features exist, and the biggest day-to-day usability win — it's how you'll
actually pick a look per video.

### 5 — Line entrance/exit animation · WORTH IT · ★★★★☆ · M

Fade + slight upward slide on enter (~150ms), fade on exit, replacing the hard cut and the
`_CAPTION_GRACE_S` visibility window. **Native on B** (`\fad`, `\move`); hand-rolled on A.

### 6 — Karaoke wipe fill · WORTH IT · ★★★★☆ · M · the case for Option B

The highlight color sweeps across each word in time with the voice (classic karaoke fill).
**Native in ASS via `{\kf}`** — this is the single feature that most justifies Option B.
Offer as a `style` option (`word_highlight` = discrete, `karaoke` = wipe) rather than
replacing existing behavior.

### 7 — Background pill / box behind text · OPTIONAL · ★★★☆☆ · S

Semi-transparent rounded rectangle (or per-word pill) behind the caption. Guarantees
contrast on any footage. Pillow: `rounded_rectangle` before text. ASS: `BorderStyle=3`. A
style choice, not a fix — ship it inside a preset.

### 10 — Smart vertical placement · OPTIONAL · ★★★☆☆ · M

When an image/logo/screenshot overlay occupies the caption band (`images.position`), shift
captions to the opposite third automatically so they don't collide. Compute caption Y per
line from active image cues instead of a static fraction. Worth it once you use overlays
heavily; skip if captions and images rarely share screen space.

### 9 — Gradient / two-tone fills · SKIP · ★★★☆☆ · S

Gradient text fill or two-tone (white body, gold active word). Doable on A (paint text as a
mask over a gradient) but **broken in libass**, and the payoff is marginal over a solid
highlight color. Revisit only if a preset specifically calls for it.

### 12 — Auto-emoji / keyword icons · SKIP · ★★★☆☆ · M

Inline emoji/icons next to trigger words (🔥, 🤯, 📈). The repo's logo auto-detection
(`image_finder.py`) is the same keyword→asset idea. But **libass has no color-emoji
rendering**, it's taste-polarizing, and overuse reads as amateur. Skip unless your niche
clearly wants it; if so, do it on Option A.

### 13 — Shake / bounce on emphasis words · SKIP · ★★★☆☆ · M

Position wobble/overshoot on words tagged in #8. Easy to overdo and niche. Park it until
#4 and #8 are in and you have a real need.

---

## Recommended sequencing

1. **#1 highlight + #2 stroke** — small, no new deps, no decision required. Fixes the broken
   headline feature and readability *today*. **Start here.**
2. **#3 decide the fork** — prototype the look you want (pop vs wipe) on one clip. Pick
   **A** for per-word motion (recommended given your goal), **B** if the karaoke wipe is
   enough and you want the big simplification.
3. **Motion:** #4 (if A) and/or #6 (if B), then #5 line transitions.
4. **#8 per-word emphasis + #11 presets** — turn the now-rich renderer into something
   controllable per video.
5. **Optional polish** (#7, #10) per video, via presets. Leave #9/#12/#13 unless asked.

**Fastest path to "these look good":** #1 → #2 → (#4 on Option A *or* #6 on Option B). The
first two are an afternoon on existing code; the third is the wow factor and the thing the
renderer decision exists to serve.
