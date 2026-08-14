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
same rule when laying out slots, and the gap is measured against *everything already committed* —
posts already published and posts already scheduled — not just against this slug.

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

Hooks are `output/<slug>/*.mp4`. Exclude any already listed in **`output/.published`** —
the single ledger both this command and `/post-video` read and write. A hook appears there once
it is *committed to going out*, whether that means posted just now or booked for a future slot,
so neither command can ever pick up a hook the other has claimed.

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

## Step 3 — Lay out the slots

Find the anchor — the latest time already committed. That is the newest timestamp in
`output/.published`, which now covers both past posts and future booked slots.

Cross-check it against the latest `scheduled_at` among live jobs from
`mcp__social-cockpit__list_scheduled_posts` (statuses `pending`, `paused`, `finalizing`) and take
whichever is later. The two should agree; a job in the cockpit that is missing from the ledger
means something was booked outside this command, and ignoring it would double-book that slot.

The first new slot is `anchor + gap`; each hook after it is another `gap` later. Defaults, all
overridable by the arguments:

| Argument | Default |
|---|---|
| `--gap <days>` | `2` |
| `--time <HH:MM>` | the time of day of the anchor post, or `09:30` if there's nothing to anchor to |
| `--start <when>` | `anchor + gap`; an explicit value overrides the anchor entirely |

Every slot must be in the future — if the computed first slot has already passed, move it forward
by whole gaps until it hasn't.

## Step 4 — Show the plan and confirm

Scheduling publishes to a live account on a timer, so **always show the plan and get explicit
confirmation before booking.** Present a table in the cockpit's timezone:

```
Slot                        Hook file                          Caption
Sat 16 Aug 2026, 09:30 GMT+10   waited-longest-dropped-first.mp4   "…"
Mon 18 Aug 2026, 09:30 GMT+10   figma-fixed-outages.mp4            "…"
```

State alongside it: the gap being used, the anchor it was measured from, whether an automation
will attach (and its key), and that each posts as a **trial reel**.

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

The timestamp is the hook's **slot**, not the moment you booked it — the ledger records when a
post goes out, and for a scheduled hook that is in the future.

Write it as **naive local time with seconds** (`2028-12-16T18:00:00`) — no `Z`, no offset — to
match every other line in the file. `scrape/post_video.py` will convert an offset-aware stamp to
local rather than choke on it, but only naive stamps read correctly at a glance.

Never write a line for a hook that appears in the result's `failed` list.

Then report the final schedule, with job ids, in the cockpit's timezone.

### What this means for `/post-video`

`post_video.py` takes the newest timestamp in the ledger as its gap anchor, so once slots are
booked it will hold off until the last one has passed plus the gap, reporting the booked date as
the last post. That is the intended, conservative behaviour: the queue is already spoken for, and
posting another hook by hand into the middle of it is what breaks the spacing. `--ignore-gap`
overrides it when that is genuinely what you want.

## Managing what's booked

- **See the queue:** `mcp__social-cockpit__list_scheduled_posts` (filter `status: ["pending"]`).
- **Move one:** `mcp__social-cockpit__update_scheduled_post` with a new `scheduled_at`. Also
  revives a job that failed or was missed.
- **Pause / resume:** same tool, `status: "paused"` / `"pending"`.
- **Cancel:** `mcp__social-cockpit__cancel_scheduled_post`. Also remove its line from
  `output/.published` so the hook becomes eligible again — otherwise it stays claimed by a job
  that no longer exists.
- **Move one:** rescheduling changes when it goes out, so update that hook's timestamp in
  `output/.published` to match, or the gap anchor will be wrong on the next run.
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
its attempts) and correct the timestamp in `output/.published`, or cancel it and delete its line
so the hook is rescheduled from scratch on the next run.
