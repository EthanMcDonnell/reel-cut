---
name: motion
description: >
  Direct how a ReelCut video moves: pick its look, then choose how every overlay enters,
  holds, hands over and leaves from that look's palette, place the camera zooms, and build
  the moves inside designed cards. Use at /produce-video's motion step, and whenever the user
  asks to animate a video, change how overlays come in, make a video punchier or calmer, or
  preview a move.
---

# Motion

You direct every overlay. The look gives a palette; you pick from it per overlay, by what the overlay shows and what the line under it is doing. The look's default move is the fallback when nothing in the palette fits better.

## Where it goes

- `assets/<slug>/motion.json` — the video: `{"look": "editorial", "zoom": {"eyes": [0.58, 0.49]}, "zooms": [...]}`.
- Each `images.json` entry — its moves: `"motion": {"enter": "slot", "exit": "wipe", "hold": "still", "transition": "push"}`. Set only what differs from the look's default. `"tilt"` and `"spring"` work too.
- `config.yaml` `motion:` is the house default. `.venv/bin/reelcut motion --list` prints every look, default and palette.

## 1. Pick the look

Take direction in this order: what the user said, the series file's `## Motion` section, the script's tone.

| look | default | feel |
|---|---|---|
| `editorial` | swing in, lift out, drift, stack | pasted clippings, slight tilt; explainers and stories |
| `punchy` | stamp in, snap out, still, push | hard and fast; opinion, comedy |
| `calm` | rise in, fade out, slow push, dissolve | unhurried; deep dives, serious news |
| `none` | fade only | a deliberately plain cut |

## 2. Choose each overlay's moves

Go through images.json in order, and for each entry decide each of these fields:

- **enter** — when it appears from nothing.
- **transition** — when it replaces the overlay before it with no gap, or lands on top of one still showing.
- **exit** — only plays when nothing follows it, or an older overlay comes back from under it.
- **hold** — what it does while it's up.

### What each move reads as

| move | reads as | fits |
|---|---|---|
| `swing` | hung on a pin, settles from a tilt | a person, a concept photo, a logo |
| `slot` | rises up inside its own frame | a screenshot or page being shown; a figure |
| `drop` | falls in from above | something arriving: a launch, a new product, a name |
| `stamp` | lands from big, with weight | the proof, a number, a verdict, a punchline |
| `wipe` | drawn on left to right | a line of text, a chart, a timeline |
| `pop` | springs up from smaller | a quick gag, an emoji-like aside |
| `slide` | comes in from the side (alternates) | one of a series, a list of examples |
| `shutter` | slats open top-down | a full-screen card, a scene change |
| `rise` | floats up softly | anything, quietly |
| `iris` | opens from the centre | a reveal, the thing being zoomed into |
| `fade` | appears | when motion would distract |
| `snap` | is just there | a hard cut, a beat that should feel abrupt |

| transition | reads as | fits |
|---|---|---|
| `stack` | lands on top, the old one sinks under | building up evidence, one thing after another |
| `push` | shoves the old one off sideways | a turn: but, instead, before → after, us vs them |
| `swap` | old goes, new plays its entrance | an unrelated next point |
| `dissolve` | crossfade | a continuation of the same thought |
| `cut` | hard switch | rapid-fire beats |

| hold | fits |
|---|---|
| `drift` | photos and logos held a few seconds; keeps them alive |
| `push` | something to study: a diagram, a chart, a long screenshot |
| `still` | anything that must be read precisely; anything under ~1.5s |

Exits: `lift` (up and out), `sink`, `shrink`, `wipe`, `slot`, `iris`, `shutter`, `fade`, `snap`. An exit mirrors the entrance it answers best: `slot` out after `slot` in, `wipe` after `wipe`.

### Choosing

- **Stay in the palette.** The render warns on a move outside it. Leave a field unset when the default is right.
- **Vary with meaning.** Neighbouring overlays shouldn't all enter the same way unless they are parts of one list. Repeat a move only when the content repeats.
- **Short overlays (under ~0.8s)** get quick moves: `pop`, `stamp` or `snap` in, `snap` out, `still`.
- **Full-screen cards** never tilt or drift and swap `swing` for `rise`. Give them `shutter`, `iris`, `wipe` or `slot`.
- **Video clips** don't take these moves. Animated and still cards do.
- `"tilt": 0` for anything that must read straight (dense screenshots, diagrams); `"tilt": -3` to exaggerate a gag.

## 3. Place the camera zooms

Slow zooms on the footage only, anchored on the speaker's eyes.

- **Eyes:** extract a gridded frame — `ffmpeg -ss 8 -i <clip> -frames:v 1 -vf "scale=270:480,drawgrid=w=iw/10:h=ih/10:c=red@0.5" <scratchpad>/eyes.png` — Read it, and set `zoom.eyes` to the point between the eyes as fractions of width and height.
- **Zooms:** `"zooms": [{"start": 12.4, "end": 17.9, "source_clip": "…", "scale": 1.07}]`, in source-clip seconds from the words, like images.json. In at `start`, out by `end`.
- **Where:** the line that lands a point, a reveal, a punchline, a number; start on its first word, end on its last. Use the series file's `**Zooms:**` line when there is one. Leave a few seconds between zooms; none under a full-screen card. `"zooms": []` means none; leaving the key out lets them fall on a steady rhythm.

## 4. Build the cards

A card's parts animate on beats (see /produce-video Step 3e for `data-beat`, `data-hot` and `.count`). On top of those:

- `data-enter="pop|drop|slide|swing|stamp|wipe"` on a beat element picks its entrance.
- `class="stagger"` — its children enter one after another, from the stagger's beat.
- `.mark` sweeps a marker under words; `.strike` draws a line through them; `.circle` rings them. Give each its own `data-beat` to draw on a later word.
- `data-swap="N" data-to="new words"` rolls the words over at beat N — a correction, a before → after.
- `data-focus="N"` moves a camera in on that element at beat N (`data-zoom`, default 1.6); `data-focus-out="M"` pulls back. For walking through one part of a flow or diagram.
- `<div class="bar" style="--v: 72%">label</div>` fills on its beat — only for proportions the script says.
- Inline SVG strokes with `class="draw"` draw themselves on: arrows, underlines, paths through a diagram.
- Custom `@keyframes` time to the video's spring: `animation: name var(--spring-s) var(--spring) var(--at) both`.

## 5. Preview

- An overlay's moves: `.venv/bin/reelcut motion <image> --slug <slug> --enter slot --exit wipe --to <next image> --transition push --out <scratchpad>/m.png`, then Read the strip.
- A card: `.venv/bin/reelcut card <html> --beats 0,1.2,2.4`, then Read the `.strip.png` beside it.

Preview every overlay whose moves aren't the look's default, and every animated card.

## 6. Report

A table: each overlay (time, what it shows) → enter / transition / exit / hold, with a few words on why. Then the look, the eye point and each zoom with its line.

## Keep it unlike a template

- No glitch or RGB-split, no typewriter code, no whoosh on every overlay.
- `words` captions only where the series or the user asks for them.
- Stay inside the vocabulary. Don't promise a move the renderer lacks.
