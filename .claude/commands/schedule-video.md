---
name: schedule-video
description: Schedule a slug's rendered hook reels to Instagram via social-cockpit's scheduler — books each output/<slug>/*.mp4 into its own slot recommended by the MCP, never inside the next 15 minutes, as a trial reel captioned from videos.json.
argument-hint: "<video-slug> [--start <when>] [--time <HH:MM>]"
---

Books every unposted hook variant for a slug into social-cockpit's **scheduler**, rather than
posting one now. The cockpit stores each job with the mp4's local path, leaves the file on disk,
and its worker publishes at the appointed time — uploading to R2 only at that moment.

This is the scheduled counterpart to `/post-video`. Use it to lay out a slug's whole run of hooks
in one go; use `/post-video` when you want one hook to go out right now.

Arguments: `$ARGUMENTS` — expected format: `<video-slug> [--start <when>] [--time <HH:MM>]`

Slugs with rendered output:
!`ls -1 output/ 2>/dev/null | grep -vE '\.(mp4|md)$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/schedule-video spotify-wrapped-billion-ai-stories --time 18:00`

## Why the spacing matters

Every hook of a slug is the same body and the same voiceover with a different opening line.
Instagram clusters near-duplicates and throttles the later ones to almost no reach, so hooks must
be spread out. The rule is **per video**: two hooks of one video stay `min_same_video_days` apart,
while two different videos may happily share a day.

**Nothing in social-cockpit enforces that rule.** `suggest_slots` honours `max_posts_per_day` and
offers `suggested_times` — that is all it does, and it never asks which video is calling, so with a
2-a-day policy it will return two same-day slots without hesitation. The same-video gap exists only in the callers: `scrape/post_video.py` checks the
calendar before posting, and Step 3 here walks the slot requests forward one gap at a time. If you
short-circuit that walk into a single `count: N` call, the spacing silently disappears and the later
hooks get throttled — which is the whole failure this command was written to avoid.

There is no `--gap` argument, on purpose. The number lives in the cockpit's settings so this command
and `/post-video` read the same one. Change it there, not per run.

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
- Note **`min_same_video_days`** — Step 3 needs it. Absent means 2.

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

### The automation

`assets/<slug>/automation.json` is the only source of the comment automation. `/produce-script`
writes it at Step 3.6.5 for comment-bait series, carrying the CTA's keyword and the lead magnet
URL; it is the same file `/post-video` reads. Nothing here reads the vault note, and nothing here
invents an automation that file doesn't describe.

- **File present** → attach it to every hook, with `key` forced to the **slug** (default it when the
  file omits it, and override a `key` that is anything else). All hooks of a slug share **one**
  flow: the first to publish creates it, every later one appends. A per-hook key would create a
  flow per hook, which is the failure this rule exists to prevent.
- **File absent** → schedule with no `automation` field at all. That is the correct result for
  `follow`, `disagreement` and `misc` series, which have no keyword to trigger on. Say so in
  Step 4 rather than treating it as a problem.

## Step 3 — Ask the cockpit for the slots

**Do not compute slot times yourself, and do not adjust the ones you get back.** The cockpit is the
only thing that knows what is actually on the calendar — what already went out (including posts made
from the phone), what is already booked, and which times this account posts at. The returned times
are the recommendation; this command's job is to hand them straight to Step 5.

First, see the shape of the fortnight:

```
mcp__social-cockpit__get_calendar   days: 14
```

Read it before booking. It is what you show the user in Step 4 and what tells you whether the
suggestions landed somewhere sane. If the coming days are already dense with this slug's hooks,
that is worth saying out loud — but it is not a reason to hand-pick different times.

Then ask for the slots. `suggest_slots` takes exactly three arguments — `count`, `earliest`,
`times` — and knows nothing about which video is asking:

| Setting | What `suggest_slots` does with it |
|---|---|
| `max_posts_per_day` | Hard ceiling per day, enforced. Not overridable: the booking route rejects a breach with `409 day_full`, so asking for more only produces slots that fail. |
| `suggested_times` | The times slots are offered at. More than one entry is how a day holds more than one post. `--time` overrides these for this run only. |

Those two are the **entire** policy. There is no collision buffer and no cadence rule of any kind:
a day under its cap will offer every one of its configured times.

`--time` maps to `times`. Omit it unless the user asked for a specific time. `--start` maps to
`earliest`, but only ever pushes it later — see the floor below.

### Ask once per hook, not once for all of them

**`suggest_slots` has no same-video rule.** It will happily return two slots on the same day when
the policy allows two posts a day — which is precisely the case that gets a video's second hook
throttled. `count: <all hooks>` in one call is therefore wrong, however convenient it looks.

Instead, walk the hooks and make **one call per hook**, each starting after the last one landed:

1. Read `min_same_video_days` from the settings banner in Step 1. If the cockpit doesn't supply it,
   use **2** — the same fallback `scrape/post_video.py` uses (`FALLBACK_MIN_GAP_DAYS`), so the two
   commands can't drift on the one number that decides whether a hook gets throttled.
2. First hook: `suggest_slots  count: 1  earliest: <now + 15 minutes, or --start if later>`.
3. Each hook after: `suggest_slots  count: 1  earliest: <previous slot + min_same_video_days>`.

Every time still comes from the cockpit — it picks the time of day, skips full days, and dodges
collisions. The loop only decides which window to ask about, which is the one thing the tool cannot
work out for itself. Booking is still a **single** `schedule_posts` call at Step 5; it is only the
asking that iterates.

A call that returns no slot means the calendar is full from that point on — stop there and report
the hooks left over rather than tightening the gap to make them fit.

### The 15-minute floor

**Never book anything inside the next 15 minutes.** A job whose slot is minutes away gives no room
to cancel a mistake, and one that lands during this conversation can fire mid-plan. So:

- Compute `earliest` as **now + 15 minutes** in the cockpit's timezone and pass it explicitly.
  Take the later of that and `--start` when the user gave one; a `--start` in the past or inside the
  floor loses to the floor.
- When the suggestions come back, **check the first one is still more than 15 minutes out.** If it
  is not, drop it, ask for one more, and say what you dropped.

### Before moving on

Each hook is its own post at its own time. Pair hooks to slots in order, then check the collected
slots as a set: no two on the same **day**, and every consecutive pair at least
`min_same_video_days` apart. If that doesn't hold, the loop above was short-circuited — redo it
rather than nudging a time by hand.

Pass the returned `scheduled_at` strings through to Step 5 unchanged. If a call reports days skipped
at the daily limit, that is worth repeating to the user, but it is not a problem — it is the policy
working.

If the output warns that the cockpit returned no policy, it is running a build without these
settings — report that instead of silently using fallbacks.

### Posting more than once a day

Change it **in social-cockpit**, not here — one place, and it applies to `/schedule-video`,
`/post-video` and the scheduler alike:

```bash
curl -X PUT {COCKPIT_URL}/api/schedule/settings -H 'Content-Type: application/json' \
  -d '{"suggested_times":["09:30","18:00"],"max_posts_per_day":2}'
```

Two posts in one day is for **two different videos** — a second video takes the 18:00 slot on a day
the first holds 09:30. Two hooks of *one* video on the same day is the thing to avoid, and since
`suggest_slots` won't stop you, Step 3's one-call-per-hook walk is what keeps them apart. Raising
`max_posts_per_day` makes that walk more necessary, not less.

`min_same_video_days` lives in the same settings object and is read by `/post-video` and Step 3
here. The cockpit stores it; nothing in the cockpit acts on it.

## Step 4 — Show the plan and confirm

Scheduling publishes to a live account on a timer, so **always show the plan and get explicit
confirmation before booking.** Present a table in the cockpit's timezone:

```
Slot                        Hook file                          Caption
Sat 16 Aug 2026, 09:30 GMT+10   waited-longest-dropped-first.mp4   "…"
Mon 18 Aug 2026, 09:30 GMT+10   figma-fixed-outages.mp4            "…"
```

State alongside it: that every time came from `suggest_slots` and what it reported fitting the plan
around, the `min_same_video_days` gap in force and whether it came from the cockpit or the
fallback, the first `earliest` you passed and why (the 15-minute floor, or `--start`), whether an automation
will attach — with its key and trigger keywords, or that there is no `automation.json` so these post
without one — and that each posts as a **trial reel**.

If any hook went unslotted because `suggest_slots` returned fewer slots than hooks, name it here.
It stays unscheduled and unclaimed, and the next run picks it up.

## Step 5 — Book them

On confirmation, call `mcp__social-cockpit__schedule_posts` **once** with every hook:

```json
{
  "posts": [
    {
      "scheduled_at": "2026-08-16T09:30",
      "video_path": "/absolute/path/to/output/<slug>/<hook>.mp4",
      "video": "<slug>",
      "caption": "…",
      "trial_reel": true,
      "automation": { "key": "<slug>", "trigger_keywords": ["…"], "config": { } }
    }
  ]
}
```

Notes:
- **`video` must be the slug on every hook.** It is what marks these posts as variants of one
  video, and so what makes the same-video spacing work on the next run. It is stored on the job and
  never sent to Instagram. Omitting it silently disables the throttle protection.
- `video_path` must be **absolute**. The cockpit reads the file at publish time, so it must stay
  where it is until then.
- `scheduled_at` is the string `suggest_slots` returned, **verbatim**. Without an offset it is read
  in the cockpit's timezone, which is the zone the suggestion was made in.
- One entry per hook, every entry a different `scheduled_at`, all in **one** call — the tool creates
  them in order and reports each independently.
- `automation.key` is the **slug** on every entry, or the whole `automation` field is absent on
  every entry. Never a mix, and never a per-hook key.
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
