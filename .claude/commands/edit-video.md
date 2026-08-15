---
name: edit-video
description: Cut spans out of an already-rendered video from a plain-English request ("drop the bit at the end", "lose the false start"), then re-render. Trims only — never re-transcribes.
argument-hint: "<video-slug> [what to cut]"
---

Trims spans out of a video that has already been through `/prepare-video` and `/produce-video`,
then re-renders it. The user says what they want gone in plain English; you locate it in the
transcript, confirm the exact span, cut it, and re-render.

**Paths:** `{TOKEN}` references are machine-specific absolute paths defined in
[glossary.md](glossary.md) — resolve each before running.

Arguments: `$ARGUMENTS` — expected format: `<video-slug> [what to cut]`

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If `$ARGUMENTS` is empty, ask the user which slug and what they want cut.

Example: `/edit-video ht-ghd-better-gitcli drop the sign-off at the end`

## What this command can and cannot change

**The only thing you edit is `edl[i].keep`, via the script below.** Word timings, `source_clips`
and the `words` array are load-bearing — the render and the EDL are both timed off them. Do not
hand-edit `captions.json`, and never re-run `transcribe` to "refresh" anything: that recomputes
the whole EDL and discards every fix `/prepare-video` applied.

**Captions follow the EDL — you never edit them.** `_remap_kept_words` drops any word sitting in a
`keep: false` span, so cutting a span removes its burned-in captions along with its audio. There is
no separate caption edit to make, and making one by hand would desync the two.

**Cuts must start after the last hook window.** `videos.json` hook `start`/`end` are
*output-timeline* seconds, so removing anything earlier shifts every later word forward and slides
the burned-in title cards onto the wrong words — silently, and burned-in means re-render-only to
undo. The script enforces this and refuses earlier cuts. If the user genuinely wants an earlier
cut, tell them it needs `/produce-video <slug>` re-run afterwards to re-time the cards, and let
them decide.

## Step 1 — Gate and read the transcript

```bash
.venv/bin/python scrape/edit_video.py --slug <video-slug>
```

This fails loudly if `/prepare-video` or `/produce-video` hasn't run. On success it prints:

- `keep_s` / `cut_s` — current durations
- `earliest_cuttable_source_s` — the tail guard boundary
- `words[]` — every word with its `source_s`, its `output_s`, and a `cuttable` flag

**Times you pass to `--cut` are `source_s`** (source-clip seconds, the units of `words` and `edl`).
`output_s` is only for telling the user where something lands in the finished video.

## Step 2 — Locate what the user asked for

Match their description against the `words[]` list. Common requests and what they mean:

| They say | Look for |
|---|---|
| "the filler at the end" / "the waffle" | trailing words after the last substantive point |
| "the false start" / "where I trail off" | an abandoned clause — `I just...`, `and the—`, a sentence with no verb that is not resumed |
| "the sign-off" | `let me know what you think`, `drop a comment`, `follow for more` |
| "the bit about X" | the sentence(s) containing X |

Choose span boundaries at **sentence** edges, not word edges, unless the user asked for something
narrower. Start at the first word of the doomed sentence; end at or past the last word's `end_s`
(overshooting the final word is fine and cleaner — it takes the trailing silence with it).

If the request is ambiguous — two candidate spans, or you can't tell where they want the cut to
begin — do **not** guess. Show the candidates and ask.

## Step 3 — Confirm with the user

Always dry-run first and show the result:

```bash
.venv/bin/python scrape/edit_video.py --slug <video-slug> --cut <start>-<end> --dry-run
```

`--cut` is repeatable — pass one per span to remove several at once.

Report to the user, then get explicit confirmation before Step 4:
- the **verbatim text** each cut removes (the `text` field) — this is the thing they actually care
  about, so quote it
- keep duration before → after
- any `snapped` boundaries (a mid-word boundary was widened to take the whole word)
- any `absorbed_slivers` — a cut boundary landed a few ms inside a keep span and the remnant was
  too short to render, so it went with the cut. Mention it, but it needs no decision: these are
  sub-100ms fragments of silence, never words.
- any `orphaned_images` — **flag these prominently**. An overlay inside a cut span silently
  vanishes from the render. If the cut is meant to keep that screenshot, the span is wrong.

## Step 4 — Apply

Same command without `--dry-run`. It writes `captions.json` and appends to
`assets/<slug>/<clip-stem>.debug.8.editlog.txt` (every cut with its verbatim text and the
before→after durations, so a revert is legible).

## Step 5 — Re-render

```bash
.venv/bin/reelcut render-hooks config.yaml "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

This overwrites `output/<video-slug>/*.mp4` in place — the previous renders are gone. Say so
before running it if the user might still want the old files.

Report the output paths.

## Step 6 — Tell the user what to do about anything already posted

Do **not** repost or reschedule anything on your own. Report the state and let them choose:

- If the slug appears in `output/.notified`, the new files will **not** re-post to Telegram until
  those lines are removed. Offer to remove them and re-run `/produce-video` Step 7, or leave it.
- If the video is already live on Instagram, replacing it is a manual decision — say the render is
  updated and stop there. `/post-video <slug>` posts it as a **new** post; it does not replace one.

## When a trim is the wrong fix

Per CLAUDE.md rule 4, ask what produced the thing being cut before treating the cut as the answer:

- **An abandoned clause or false start that survived** (`I just...`) is a
  `retake_detector` / `gap_detector` miss — every future video will have the same class of filler.
  Trim it here, but also propose a Gap writeup in `TODO.md`.
- **A sign-off or a rambling ending the user never wants** is a scripting rule, not an edit. Propose
  a rule in the `scripts` skill so it stops being written in the first place.
- **A wrong or misheard word** is not this command's job at all — that is a `words[]` fix under
  `/prepare-video` Step 4.

Raise these once, take the user's answer, and move on.
