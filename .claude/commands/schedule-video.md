---
name: schedule-video
description: Schedule a slug's rendered hook reels to Instagram via social-cockpit's scheduler — books each output/<slug>/*.mp4 into a future slot spaced ≥2 days apart, as a trial reel captioned from videos.json, using the social-cockpit MCP.
argument-hint: "<video-slug> [--start <when>] [--gap <days>] [--time <HH:MM>]"
---

Books every unposted hook variant for a slug into social-cockpit's **scheduler**, rather than
posting one now. The cockpit stores each job with the mp4's local path, leaves the file on disk,
and its worker publishes at the appointed time — uploading to R2 only at that moment.

This is the scheduled counterpart to `/post-video`. Use it to lay out a slug's whole run of hooks
in one go; use `/post-video` when you want one hook to go out right now.

Arguments: `$ARGUMENTS` — expected format: `<video-slug> [--start <when>] [--gap <days>] [--time <HH:MM>]`

Slugs with rendered output:
!`ls -1 output/ 2>/dev/null | grep -vE '\.(mp4|md)$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/schedule-video spotify-wrapped-billion-ai-stories --time 18:00`

## Why the spacing matters

Every hook of a slug is the same body and the same voiceover with a different opening line.
Instagram clusters near-duplicates and throttles the later ones to almost no reach, so hooks must
be spread out. `scrape/post_video.py` enforces a **2-day minimum gap**; this command applies the
same rule, but it does not work the spacing out locally: it asks social-cockpit for free slots, so
the gap is measured against what is genuinely on the calendar — everything already published
(including posts made from the phone) and everything already booked — not just this slug.

## Prerequisites

- **social-cockpit** running on `{COCKPIT_URL}`, with its scheduler worker enabled.
- The **social-cockpit MCP server** built and configured (`.mcp.json` in this repo points at
  `{SOCIAL_COCKPIT_DIR}/mcp/dist/index.js`). If its tools aren't available, build it:
  `cd {SOCIAL_COCKPIT_DIR}/mcp && npm install && npm run build`.

## Step 1 — Confirm the scheduler will actually fire

Read the `schedule://settings` resource (or call `mcp__social-cockpit__list_scheduled_posts`,
which reports the same banner).

- `scheduler_enabled: false` → **stop.** Jobs would be stored and never published. Tell the user.
- `dry_run: true` → warn: jobs will run the pipeline but post nothing.
- Note the **timezone**. Every time you state back to the user must be in that zone.

## Step 2 — Work out what still needs posting

Hooks are `output/<slug>/*.mp4`. Exclude any already listed in **`output/.published`**.

That file answers exactly one question: **has this hook been used?** A `<slug>/<file>.mp4` key
there means the hook is spoken for and must never go out again — whether `/post-video` posted it
or this command booked it. Deleting its line is the only way to release it. Match on the key
alone; the timestamp beside it is informational.

```bash
ls -1 output/<slug>/*.mp4
cat output/.published 2>/dev/null
```

If nothing is left, say so and stop.

Caption each remaining file from `assets/<slug>/videos.json`, using the same rule as
`/post-video`: match the file's stem to its entry's stem; a mirrored duplicate that videos.json
doesn't describe falls back to the **longest stem the filename starts with**, so it inherits the
caption of the hook it mirrors.

Load `assets/<slug>/automation.json` if present. Set `key` to the slug when absent — all hooks of
a slug share **one** flow, created on the first to publish and appended to by the rest.

## Step 3 — Ask the calendar for the slots

**Do not compute slot times yourself.** Only the cockpit knows what is actually on the calendar —
what already went out (including anything posted from the phone) and what is already booked. Call:

```
mcp__social-cockpit__suggest_slots
  count:       <number of hooks from Step 2>
  gap_days:    <--gap, default 2>
  time_of_day: <--time, default "09:30">
  earliest:    <--start, omit for "now">
```

It returns one `scheduled_at` string per slot, each already clear of every published and scheduled
post by `gap_days` **on both sides** — which is the part that is easy to get wrong by hand, since a
hole two days after the last post may still sit an hour before the next booked one. Pass those
strings through to Step 5 unchanged.

If it returns fewer slots than you asked for, it says so; report that rather than inventing the
remainder.

| Argument | Default |
|---|---|
| `--gap <days>` | `2` |
| `--time <HH:MM>` | `09:30` |
| `--start <when>` | now |

## Step 4 — Show the plan and confirm

Scheduling publishes to a live account on a timer, so **always show the plan and get explicit
confirmation before booking.** Present a table in the cockpit's timezone:

```
Slot                        Hook file                          Caption
Sat 16 Aug 2026, 09:30 GMT+10   waited-longest-dropped-first.mp4   "…"
Mon 18 Aug 2026, 09:30 GMT+10   figma-fixed-outages.mp4            "…"
```

State alongside it: the gap being used, what `suggest_slots` reported fitting the plan around,
whether an automation will attach (and its key), and that each posts as a **trial reel**.

## Step 5 — Book them

On confirmation, call `mcp__social-cockpit__schedule_posts` **once** with every hook:

```json
{
  "posts": [
    {
      "scheduled_at": "2026-08-16T09:30",
      "video_path": "/absolute/path/to/output/<slug>/<hook>.mp4",
      "caption": "…",
      "trial_reel": true,
      "automation": { "key": "<slug>", "trigger_keywords": ["…"], "config": { } }
    }
  ]
}
```

Notes:
- `video_path` must be **absolute**. The cockpit reads the file at publish time, so it must stay
  where it is until then.
- `scheduled_at` without an offset is read in the cockpit's timezone — which is what you want,
  since the plan was computed in that zone.
- Entries are independent: a rejected one does not roll back the others. The result lists
  `scheduled` and `failed` separately — report both, and retry only the failures.

## Step 6 — Record what was booked

Append one line per **successfully** scheduled hook to `output/.published` — the same ledger
`/post-video` writes, in the same format:

```
<slug>/<file>.mp4<TAB><scheduled-at-iso>
```

This is what claims the hook. Once its line exists it can never be posted or scheduled again
until you delete that line, by either command.

The timestamp is the hook's slot, written as naive local time with seconds
(`2026-08-16T18:00:00`) to match every other line. It is **informational** — a note of when the
hook is due out. Nothing reads it: spacing comes from the cockpit's calendar, not from this file.

Never write a line for a hook that appears in the result's `failed` list.

Then report the final schedule, with job ids, in the cockpit's timezone.

### What this means for `/post-video`

`post_video.py` skips any hook claimed here, and runs its own gap check against the cockpit's
calendar — so a slot booked by this command will hold it off, the same way a real post would.
`--ignore-gap` overrides that when it's genuinely what you want.

## Managing what's booked

- **See the queue:** `mcp__social-cockpit__list_scheduled_posts` (filter `status: ["pending"]`).
- **Move one:** `mcp__social-cockpit__update_scheduled_post` with a new `scheduled_at` — call
  `suggest_slots` first rather than picking a time by hand. Also revives a job that failed or was
  missed. Updating the hook's timestamp in `output/.published` to match is tidy but optional;
  nothing reads it.
- **Pause / resume:** same tool, `status: "paused"` / `"pending"`.
- **Cancel:** `mcp__social-cockpit__cancel_scheduled_post`. Also remove its line from
  `output/.published`, or the hook stays claimed by a job that no longer exists.
- **Post one early:** `mcp__social-cockpit__run_scheduled_post_now` — publishes immediately and
  blocks for a few minutes. Confirm with the user first; it can't be undone.
- **Why did it fail:** `mcp__social-cockpit__get_scheduled_post` returns the job's event history.

## When a scheduled post fails

A hook is written to the ledger when it is *booked*, so a job that later fails terminally leaves a
line claiming a post that never went out. That hook will not be picked up again until the line is
removed.

Check for these before assuming a slug is fully posted:

```
mcp__social-cockpit__list_scheduled_posts  →  status: ["failed", "missed"]
```

For each one, either revive it (`update_scheduled_post` with a new `scheduled_at`, which resets
its attempts), or cancel it and delete its line so the hook is rescheduled from scratch on the
next run.
