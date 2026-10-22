# Trim variants: plan

Render hook variants with different optional body lines removed, so each hook's video has a
different duration, audio sequence and frame sequence. This is built on the existing
per-hook render and the flip lever.

## 1. The model: one planner, a list of videos

A slug renders a list of videos today: one per hook, plus any flipped duplicates. Each video
becomes a tuple:

```
(hook, copy, flip, trims)    e.g.  (2, 1, flip, {1,2})
```

**Levers are configured independently and assigned jointly.** Config says *which* levers are
on and how many videos each hook gets. One planner then fills in the tuple for every video,
so the levers never collide. Its guarantees:

1. **The core video is untouched.** Hook 1, copy 1: full script, unflipped.
2. **No two videos are the same.** Every `(hook, flip, trims)` is unique.
3. **Copies of one hook differ in their trims** where there are enough trim units, and in
   flip otherwise.
4. **Trims spread before they repeat.** The order is `all`, then each single unit `{1}`,
   `{2}`…, then pairs. "One line cut, all lines cut" falls out of this order.
5. **It's deterministic.** The same inputs always give the same plan.

**The plan is written into `videos.json`, not recomputed at every render.** `/produce-video`
runs the planner once and records `flip` and `trim` on each entry. `render-hooks` renders
exactly what the file says. Three reasons:
- **Stability.** Editing `trims.json` or the config after posting can't silently change
  what an already-posted filename contains.
- **Visibility.** One file shows what every output is.
- **Per-video override.** Hand-edit an entry's `trim` and nothing else moves.

Entries with no `flip`/`trim` fields (every existing slug) fall back to computing the plan
from config at render time, so old slugs re-render unchanged.

## 2. Config

This replaces `output.flip`:

```yaml
output:
  variants:
    copies: 1            # videos per hook. 1 = each hook's one video carries the variation
                         #   (today's in_place). 2 = every hook also gets a second video
                         #   (today's duplicate); each copy needs its own videos.json entry.
    flip: alternate      # off | alternate | copies | all
                         #   alternate = every second video in the planned list
                         #   copies    = only the extra copies (today's apply: duplicate)
                         #   all       = every video except the core video
    trim: rotate         # off | rotate — give videos different trim subsets (section 1).
                         #   Silently off for a slug with no trims.json units.
```

Mapping from today's settings:

| today | new |
|---|---|
| `mode: alternate, apply: in_place` | `copies: 1, flip: alternate` |
| `mode: all, apply: duplicate` | `copies: 2, flip: copies` |
| `mode: off` | `flip: off` |

The `suffix` option goes away. An undescribed copy falls back to `<stem>-2.mp4`, but
`/produce-video` always writes an entry per copy, so the fallback should never be used.

**Render cost.** A copy that differs only by flip still shares overlay frames and segment
extraction, and repeats only the encode. A copy with a different trim set is a full render
because its EDL differs. So `copies: 2` with `trim: rotate` roughly doubles render time.

### Example plans

3 hooks, 2 trim units, `copies: 1, flip: alternate, trim: rotate`:

| video | hook | flip | trims |
|---|---|---|---|
| core | 1 | – | – |
| 2 | 2 | ✓ | 1, 2 |
| 3 | 3 | – | 1 |

3 hooks, 2 units, `copies: 2, flip: copies, trim: rotate`: 6 videos, subsets
`– / {1,2} / {1} / {2} / {1,2} / {1}`. Each hook's two copies have different trims, and every
second copy is flipped.

## 3. Marking lines: script time (`scripts` skill and `/produce-script` Stage 3)

**The writer marks lines because only the writer can make a line removable.** Whether a line
can go depends on whether anything later leans on it.

**Syntax.** Prefix a whole `**SCRIPT**` body sentence with `[cut-N]`:

```
[cut-1] That's about three times what the old cluster cost.
```

- `N` is the removal priority. 1 is the least needed.
- Lines that share a number are one unit and are always cut together. Use this for a pair
  that only works as a pair.
- Write 0–3 units. Never pad the script to have something to mark: no qualifying line means
  no marks, and the slug simply gets no trim variety.

**A line qualifies only if all of these hold:**

1. It's in `**SCRIPT**`. It is not the first body line (the stakes line or the hook-to-body
   handoff), the crux, the payoff, the turn, or the diagram walk-through passage. Nothing in
   `**CONCLUSION**` or `**CTA**` qualifies.
2. Nothing after it refers back to it: no "that", "this", "it", "the second one", no number
   or name first introduced there.
3. Read the body aloud without it: the line before lands as a finished thought, and the
   line after opens cleanly.
4. It ends with `.`, `!` or `?`, and so does the line before it. A comma-joined clause is
   never a unit.

**Limits, enforced by `lint_script.py`:**
- The full script still fits the series word cap.
- Marked words total at most 25% of the body.
- Units are numbered from 1 with no gaps.
- Markers appear only in `**SCRIPT**`.

`format_script.py` already splits after `.`/`!`/`?`, so a leading marker stays on its own
sentence's line. A test should confirm this.

**Filming.** Record every line as normal. No special delivery is needed: the pipeline already
cuts at 96% of body sentence breaks (section 4).

`/prepare-video` strips the markers before it scores script coverage
(`debug_report._script_body_lines`).

## 4. Finding exact cut points (new code, `/produce-video` Step 3d)

**`reelcut trims <captions>` writes `assets/<slug>/trims.json`:**

```json
[{"unit": 1, "text": "...", "source_clip": "...", "start": 67.19, "end": 73.21,
  "seconds": 6.02, "also_removes": "", "status": "ok", "reason": "",
  "vanishes": ["screenshot snippet-03.png"]}]
```

**The rule: a trim only ever runs from one existing EDL cut to another.** Never from a word
timestamp. The pipeline already places a silence cut between sentences: from the previous
word's measured speech end to the next word's onset minus `speech_pad_ms`. A trim covering
exactly the keep spans between two of those cuts merges with them, so the new join is
"last word before, straight into first word after", built from the same measured edges as
every other join in the video.

For each marked line (built: `reelcut/trims.py`):

1. **Find the words.** Use the script-coverage fuzzy matcher (`_best_window`) over the *kept*
   body words: output time after the last hook window, the same guard as `/edit-video`.
   Then a word-level alignment pins the first and last words. Hyphens split tokens, because
   Whisper writes "UTF-32" as "UTF -32".
   - Whisper's punctuation is **not** used to find sentences. It writes commas at real
     sentence breaks ("alphabet, | 130" has a 660 ms pause and a cut). The script decides
     what a sentence is; the EDL decides where a cut can go.
2. **Merge a unit's lines** delivered back to back (up to 2 ad-libbed words between them).
3. **Snap out to the nearest cut** on each side (or a clip edge). The trim may take up to 2
   extra words with it, e.g. an ad-libbed "See," or a trailing "really.". These are reported
   as `also_removes`. Rejections:
   - more than 2 extra words, or a sentence end inside them: `no cut before/after "…"`;
   - a lowercase connective (and, but, so, which…) right across an edge: `delivered joined to
     its neighbour`;
   - in the hooks, the last line of the video, or spanning two clips.
4. **Set the trim** to `[end of the cut before, start of the cut after]`. Retake cuts inside
   the line don't matter; they're inside the trim. Both new join points are edges the gap
   detector already measured, so no separate audio check is needed.
5. **Check overlays** (images.json and motion.json zooms):
   - Starts inside the trim: it vanishes from that variant, since the render drops overlays
     by start time. This is reported as `vanishes`.
   - Already on screen when the trim starts: rejected, because it would be cut off at the
     join mid-move. The fix is to end it at the trim start.

**Stress test** (every body line of the 3 slugs with scripts and hook windows, each treated
as its own unit): 23 ok, 11 rejected, and every rejection was real:
- 8 are in a 20-second stretch of github-casefold with no cuts at all;
- the rest were delivered joined to their neighbour ("…a second, which isn't…").

**Measured on all 15 existing slugs, 178 of 186 body sentence breaks (96%) already have an
EDL cut**, so steps 2 and 3 almost always succeed. Of the 8 misses:
- 1 is a real run-on (120 ms gap).
- 2 are false sentence breaks: a capitalised word after a pause, mid-sentence.
- 5 are real pauses of 300–900 ms that weren't cut, probably because of low-confidence
  words or noise in the gap.

**No fallback cut.** A rejected line gets `status: "rejected"` with the
reason. It is left out of the plan, and a unit with any rejected line is unusable. A cut where you ran two sentences together carries the pitch of one into the
other, and it audibly sounds like an edit. `/produce-video` reports rejected units, and the
Gap writeup notes where a marked line had no pause.

## 5. Render (`render-hooks`)

- Read `flip` and `trim` from each `videos.json` entry, or compute the plan for old slugs.
- Before rendering, check that each trim's edges still sit on EDL cuts and that every unit
  the plan names has `status: "ok"`. Re-running `/prepare-video` rebuilds the EDL and makes
  `trims.json` stale. If it's stale, fail loudly with "re-run `reelcut trims`".
- After `build_hook_edl`, set the entry's trim spans to `keep: false` (reason `trim`) and
  add them to `drop_intervals`. That covers words and images. Placed sfx and zooms that
  start in a cut are already dropped by `_phase2` and `_camera_zooms`.
- Hook windows, title cards and `hold_after_hook_s` are untouched, because every trim sits
  after the body starts.
- Group entries that share `(hook, trims)` so flip-only copies keep sharing overlay frames.
- `_hook_caption_survival`: a trimmed variant isn't owed its trimmed words.
- Add `--plan`: print the table from section 2 with each video's length, then stop.

## 6. Skill changes

| skill | change |
|---|---|
| `scripts` | Marking rules from section 3. Add "mark, don't cut" to the trim pass only for lines that pass all four tests. |
| `/produce-script` | Stage 3: write the markers. Stage 3.5: linter checks. |
| `lint_script.py` | Parse markers, enforce the limits, report full vs. all-trimmed word counts. |
| `/prepare-video` | Strip markers before the coverage check. |
| `/produce-video` | New Step 3d after hook windows: run `reelcut trims`, fix overlays that straddle a trim, report rejected units. Step 4b: run the planner, write `flip`/`trim` on every entry, write one entry per copy (own title and caption, as mirror entries work now). Step 5: `render-hooks --plan` first, then render. |
| `video_spec.py` | `flip: bool`, `trim: list[int]` on entries. `of` becomes "another copy of this hook" instead of "the mirror of". |
| `/schedule-video` | Never book two copies of the same hook in adjacent slots. |

## 7. Build order (each step leaves the pipeline working)

1. **Resolver and `trims.json`**: done.
2. **Render from `videos.json` `flip`/`trim`**, plus caption-survival and `--plan`.
   Verify: render one slug with a hand-written trim, and check every cut in the trim's
   `.debug` report.
3. **Planner and `output.variants`** (replaces `output.flip`), with tests for every
   guarantee in section 1, and an old slug re-rendering to the same files.
4. **Skills and linter** (section 6).

## Open questions

- Rejections should be about 4% of breaks. If they turn out to matter, look into the 300–900 ms
  pauses that weren't cut. Those are gap-detector misses that would hurt the normal edit
  too, not something specific to trims.
- `copies: 2` doubles output per slug. That depends on whether the scheduler has slots for
  it, so the multi-take spacing rule needs to cover copies.
