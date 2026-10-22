---
name: motion
description: >
  Direct how a ReelCut video moves — its look, how each overlay enters, holds, hands over and
  leaves, caption and title-card motion, and the animated moves inside designed cards. Use at
  /produce-video's motion step, and whenever the user asks to animate a video, change how
  overlays come in, make a video feel punchier or calmer, or preview a move.
---

# Motion

## Where it lives

Three layers, later wins:

1. `config.yaml` `motion:` — the house look.
2. `assets/<slug>/motion.json` — this video: `{"look": "punchy", "hold": "drift"}`.
3. An `images.json` entry's `"motion"` — one overlay: `{"enter": "stamp", "tilt": -3}`. Keys: `look`, `enter`, `exit`, `hold`, `transition`, `tilt`, `spring`.

A `look` resets every field to its bundle before that layer's own fields apply. `reelcut motion --list` prints every valid name. A bad name in motion.json stops the render; one in an entry is dropped with a warning.

## Looks

| look | moves | fits |
|---|---|---|
| `editorial` | swing in, lift out, hand-held drift, 1.5° tilt, stack handover, lines pop, title rises from a slot | the house default; explainers and stories |
| `punchy` | bouncy stamp, snap out, push handover, words spring in as said, slot title | opinion, comedy, hot takes |
| `calm` | gentle rise, fade out, slow push-in hold, dissolve handover, ink title | deep dives, diagrams, serious news |
| `none` | fades only (`images.fade_duration_s`) | a deliberate plain cut |

## Vocabulary

- **enter** — `snap`, `fade`, `pop` (scales up), `rise`, `drop`, `slide` (alternates sides), `swing` (hinged at the top, alternates), `stamp` (lands from big), `slot` (rises inside its own frame), `wipe`, `iris`, `shutter` (slats open top-down).
- **exit** — `snap`, `fade`, `lift` (up and out), `sink`, `shrink`, `slot`, `wipe`, `iris`, `shutter`. Plays when nothing follows, or when an older overlay comes back from under it.
- **hold** — `still`, `drift` (slow hand-held float), `push` (slow zoom in over the hold).
- **transition** — when an overlay takes over from another: `cut`, `swap` (old goes, new plays its entrance), `push` (new shoves old off sideways), `stack` (new lands on top, old sinks back under), `dissolve`.
- **tilt** — resting angle in degrees; alternates sign overlay to overlay. Never on full-screen cards.
- **spring** — `snappy`, `bouncy`, `gentle`, `heavy`. Times every entrance, caption and card beat.
- **captions** — `none`, `pop` (each line springs in), `words` (each word springs in as it is said).
- **heading** — `none`, `slot`, `ink`. The title also pushes in slowly while up. Its first frame is then empty, so the render writes `<name>.cover.jpg` from after it settles and scheduling uses that as the cover.

Every card, animated or still, enters, holds, hands over and leaves by these moves like any overlay. Full-screen cards swap `swing` for `rise` and never drift; give them `shutter`, `iris`, `wipe` or `slot` to enter.

## Camera zooms

Slow zooms on the footage only (never the captions or overlays), anchored on the speaker's eyes so they stay where they are. The look sets their feel (`zoom` in motion.json overrides it: `{"scale": 1.06, "in": 2, "out": 2, "eyes": [0.5, 0.42]}`, or `"zoom": "off"`).

- **Set `eyes`** from one frame of the footage with a grid on it — `ffmpeg -ss 8 -i <clip> -frames:v 1 -vf "scale=270:480,drawgrid=w=iw/10:h=ih/10:c=red@0.5" <scratchpad>/eyes.png`, then Read it — the point between the eyes as fractions of width and height. A few percent off is fine.
- **Place them** in motion.json `"zooms"`, in source-clip time like images.json: `[{"start": 12.4, "end": 17.9, "source_clip": "…", "scale": 1.07}]`. In at `start`, out by `end`; `scale` is optional.
- **Where:** on the line that lands a point, a reveal, a punchline or a number; start on its first word and end on its last word or just after. Leave a few seconds between zooms, and none under a full-screen card.
- **No `zooms` key** puts them on a steady rhythm (every few seconds, each on a sentence start). `"zooms": []` means none.

## Inside cards

On top of `data-beat`, `data-hot` and `.count` (see /produce-video Step 3e):

- `data-enter="pop|drop|slide|swing|stamp|wipe"` on a beat element picks its entrance (default rises).
- `class="stagger"` — its children enter one after another, from the stagger's beat.
- `<span class="mark">` sweeps a marker under words; `.strike` draws a line through them; `.circle` rings them. Give each its own `data-beat` to draw on a later word.
- `data-focus="N"` moves a camera in on that element at beat N (`data-zoom`, default 1.6); `data-focus-out="M"` pulls back. For walking through one part of a flow or diagram while it is discussed.
- `data-swap="N" data-to="new words"` rolls the element's words over at beat N — a correction or a before → after in place.
- `<div class="bar" style="--v: 72%">label</div>` fills to `--v` on its beat. Only for proportions the script says out loud.
- Inline SVG: any stroke with `class="draw"` draws itself on — arrows, underlines, a path through a diagram.
- Custom `@keyframes` time to the video's spring with `animation: name var(--spring-s) var(--spring) var(--at) both`. A script can animate by defining `window.reelcutSeek(seconds)` and `window.reelcutDuration`; beat times are in `window.reelcutBeats`.

Check a card's motion: `.venv/bin/reelcut card <html> --beats 0,1.2,2.4 --spring snappy`, then Read the `.strip.png` beside it.

## Directing a video

1. **Take direction in this order:** what the user said, the series file's `## Motion` section, then the script's tone.
2. **Pick one look** and write it to `motion.json`. Skip the file when the house look already fits and no direction asks otherwise.
3. **Override where the moment earns it**, matching motion to meaning:
   - the proof landing (the screenshot or figure that backs the claim) → `stamp`
   - a flash gag → `pop` in, `snap` out
   - a turn ("but actually", before → after) → `push` transition
   - a diagram to study → `push` hold, `tilt: 0`
   - inside a card: a correction → `.strike` or `data-swap`, the key phrase → `.mark`, the named thing → `.circle`, a path or flow → SVG `.draw`, one step of it being explained → `data-focus`, a list said in one breath → `.stagger`, a said comparison → `.bar`
4. **Restraint.** Two or three overrides per video at most; repetition is what makes the look read as a style. Never `bouncy` on a serious or sad story.
5. **Preview every override before rendering:** `.venv/bin/reelcut motion <image> --slug <slug> --enter stamp --to <next image> --out <scratchpad>/m.png`, then Read the strip.
6. **Report** the look, and each override with the moment it marks.

## Keep it unlike a template

- Not everything scales up from zero on one wobbly spring.
- `words` captions only where the series or the user asks for them.
- No glitch or RGB-split, no typewriter code, no whoosh slide on every overlay.
- Stay inside the vocabulary: combine fields, set a per-entry tilt, give a card its own keyframes. Don't promise a move the renderer lacks.

`drift`, `push` and `words` make most frames unique and add render time; keep `still` on a long-held overlay unless the hold needs life.
