---
name: schedule-video
description: Schedule a slug's rendered hook reels to Instagram via social-cockpit's scheduler — books each output/<slug>/*.mp4 into its own slot recommended by the MCP, never inside the next 15 minutes, as a trial reel captioned from videos.json, then books a YouTube Short a day after the last hook that cross-posts whichever hook earned the most views.
argument-hint: "<video-slug> [--start <when>] [--time <HH:MM>] [--no-youtube]"
---

Books every unposted hook variant for a slug into social-cockpit's **scheduler**, rather than posting one now. The cockpit stores each job with the mp4's local path, leaves the file on disk, and its worker publishes at the appointed time — uploading to R2 only at that moment.

This is the scheduled counterpart to `/post-video`. Use it to lay out a slug's whole run of hooks in one go; use `/post-video` when you want one hook to go out right now.

Arguments: `$ARGUMENTS` — expected format: `<video-slug> [--start <when>] [--time <HH:MM>] [--no-youtube]`

Slugs with rendered output: !`ls -1 output/ 2>/dev/null | grep -vE '\.(mp4|md)$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/schedule-video spotify-wrapped-billion-ai-stories --time 18:00`

## Why the spacing matters

Every hook of a slug is the same body and the same voiceover with a different opening line. Instagram clusters near-duplicates and throttles the later ones to almost no reach, so hooks must be spread out. The rule is **per video**: two hooks of one video stay `min_same_video_days` apart, while two different videos may happily share a day.

**Nothing in social-cockpit enforces that rule.** `suggest_slots` honours `max_posts_per_day` and offers `suggested_times` — that is all it does, and it never asks which video is calling, so with a 2-a-day policy it will return two same-day slots without hesitation. The same-video gap exists only in the callers: `scrape/post_video.py` checks the calendar before posting, and Step 3 here walks the slot requests forward one gap at a time. If you short-circuit that walk into a single `count: N` call, the spacing silently disappears and the later hooks get throttled — which is the whole failure this command was written to avoid.

There is no `--gap` argument, on purpose. The number is meant to live in the cockpit's settings so this command and `/post-video` read the same one — but social-cockpit dropped `min_same_video_days` from `/api/schedule/settings` (its b96b23d), so today the real number is `FALLBACK_MIN_GAP_DAYS` in `scrape/post_video.py`. Change it there until the cockpit brings the setting back.

## The YouTube cross-post

Every hook is booked with the slug set, which does two things in social-cockpit: it groups the hooks in the calendar, and — the new part — **publishing a hook enrols its file in that slug's content pool** (see `docs/slug-scheduling.md` in social-cockpit). One extra job is then booked at the end: a **YouTube Short with no file of its own**, pointed at the pool. The cockpit picks the member with the most views when the slot arrives.

Why it works out that way:

- **A day after the last hook.** The pick ranks on real Instagram numbers, and a hook that hasn't published yet has none. Every hook has been live for at least a day by then, so "most successful" means something. `most_views` is the ranking, matching the cockpit's own `default_selection`.
- **A candidate already posted to a platform is never picked for that platform again.** Pools drain per platform, so the Instagram run leaves the YouTube pool untouched — and a second YouTube slot on the same slug would draw the *next* best hook, never repeat the first.
- **No automation.** The cockpit attaches comment automations to Instagram posts only, and drops one on a YouTube job.
- **The title comes from `videos.json`**, not from the hook: the pick happens hours later, so there is no per-hook title to send. `schedule_video.py` flattens the primary entry's `title` (the burned-in card, minus its line breaks). Without an explicit title YouTube would get the mp4's filename.
- **`--no-youtube` skips it.** The cross-post is on by default; leave it off only when the user asks.

`/post-video` enrols too, so a hook posted immediately is still a candidate later.

## Prerequisites

- **social-cockpit** running on `{COCKPIT_URL}`, with its scheduler worker enabled.
- The **social-cockpit MCP server** built and configured (`.mcp.json` in this repo points at `{SOCIAL_COCKPIT_DIR}/mcp/dist/index.js`). If its tools aren't available, build it: `cd {SOCIAL_COCKPIT_DIR}/mcp && npm install && npm run build`.

## Step 1 — Confirm the scheduler will actually fire

Read the `schedule://settings` resource (or call `mcp__social-cockpit__list_scheduled_posts`, which reports the same banner).

- `scheduler_enabled: false` → **stop.** Jobs would be stored and never published. Tell the user.
- `dry_run: true` → warn: jobs will run the pipeline but post nothing.
- Note the **timezone**. Every time you state back to the user must be in that zone.
- Note **`min_same_video_days`** — Step 3 needs it. Absent (the norm now — social-cockpit removed the setting) means `FALLBACK_MIN_GAP_DAYS` from `scrape/post_video.py` (currently 1.5 days / 36 hours).

## Step 2 — Work out what still needs posting

Hooks are `output/<slug>/*.mp4`. Exclude any already listed in **`output/.published`**.

That file answers exactly one question: **has this hook been used?** A `<slug>/<file>.mp4` key there means the hook is spoken for and must never go out again — whether `/post-video` posted it or this command booked it. Deleting its line is the only way to release it. Match on the key alone; the timestamp beside it is informational.

A `<slug>/@youtube` key is not a hook — it claims the cross-post (Step 6). Ignore it here; the script checks it itself.

```bash
ls -1 output/<slug>/*.mp4
cat output/.published 2>/dev/null
```

If nothing is left, say so and stop.

Caption each remaining file from `assets/<slug>/videos.json`, using the same rule as `/post-video`: match the file's stem to its entry's stem; a mirrored duplicate that videos.json doesn't describe falls back to the **longest stem the filename starts with**, so it inherits the caption of the hook it mirrors.

### The automation

`assets/<slug>/automation.json` is the only source of the comment automation. `/produce-script` writes it at Step 3.6.5 for comment-bait series, carrying the CTA's keyword and the reward; it is the same file `/post-video` reads. Nothing here reads the vault note, and nothing here invents an automation that file doesn't describe.

**You never compose the `automation` block by hand.** `scrape/schedule_video.py` (Step 5) builds it itself, from `scrape/automation_spec.py` — the same code `/post-video` already trusts for this — so there is nothing per-hook to retype into a tool call. An earlier version of this workflow had the agent read `validate_automation.py --spec`'s printed JSON and hand-type it into `schedule_posts`; that step once dropped `template_type` on a live video's automation, silently downgrading a comment→follow→DM flow to a comment→DM flow with the wrong config shape, which meant it could never actually send a DM. Don't reintroduce a hand-typed `automation` block.

Still run this before Step 3 — it's the only check that the reply function and DM pack still exist under those names in social-cockpit; a renamed one isn't rejected at booking time, it just sends an empty message days later on a live post:

```bash
.venv/bin/python scrape/validate_automation.py <slug>
```

- **Exit 0** → an automation will attach; say so in Step 4 with its keywords.
- **Exit 1** → fix what it reports before Step 3.
- **File absent** → hooks schedule with no automation. That is the correct result for `follow`, `disagreement` and `misc` series, which have no keyword to trigger on. Say so in Step 4 rather than treating it as a problem.

## Step 3 — Ask the cockpit for the slots

**Do not compute slot times yourself, and do not adjust the ones you get back.** The cockpit is the only thing that knows what is actually on the calendar — what already went out (including posts made from the phone), what is already booked, and which times this account posts at. The returned times are the recommendation; this command's job is to hand them straight to Step 5.

First, see the shape of the fortnight:

```
mcp__social-cockpit__get_calendar   days: 14
```

Read it before booking. It is what you show the user in Step 4 and what tells you whether the suggestions landed somewhere sane. If the coming days are already dense with this slug's hooks, that is worth saying out loud — but it is not a reason to hand-pick different times.

Then ask for the slots. `suggest_slots` takes exactly three arguments — `count`, `earliest`, `times` — and knows nothing about which video is asking:

| Setting | What `suggest_slots` does with it |
|---|---|
| `max_posts_per_day` | Hard ceiling per day, enforced. Not overridable: the booking route rejects a breach with `409 day_full`, so asking for more only produces slots that fail. |
| `suggested_times` | The times slots are offered at. More than one entry is how a day holds more than one post. `--time` overrides these for this run only. |

Those two are the **entire** policy. There is no collision buffer and no cadence rule of any kind: a day under its cap will offer every one of its configured times.

`--time` maps to `times`. Omit it unless the user asked for a specific time. `--start` maps to `earliest`, but only ever pushes it later — see the floor below.

### Ask once per hook, not once for all of them

**`suggest_slots` has no same-video rule.** It will happily return two slots on the same day when the policy allows two posts a day — which is precisely the case that gets a video's second hook throttled. `count: <all hooks>` in one call is therefore wrong, however convenient it looks.

Instead, walk the hooks and make **one call per hook**, each starting after the last one landed:

1. Read `min_same_video_days` from the settings banner in Step 1. The cockpit doesn't supply it today (removed there), so use **`FALLBACK_MIN_GAP_DAYS`** from `scrape/post_video.py` — currently 1.5 days (36 hours) — so the two commands can't drift on the one number that decides whether a hook gets throttled.
2. First hook: `suggest_slots  count: 1  earliest: <now + 15 minutes, or --start if later>`.
3. Each hook after: `suggest_slots  count: 1  earliest: <previous slot + min_same_video_days>`.

Every time still comes from the cockpit — it picks the time of day, skips full days, and dodges collisions. The loop only decides which window to ask about, which is the one thing the tool cannot work out for itself. Booking is still a **single** `schedule_video.py` run at Step 5; it is only the asking that iterates.

A call that returns no slot means the calendar is full from that point on — stop there and report the hooks left over rather than tightening the gap to make them fit.

### The 15-minute floor

**Never book anything inside the next 15 minutes.** A job whose slot is minutes away gives no room to cancel a mistake, and one that lands during this conversation can fire mid-plan. So:

- Compute `earliest` as **now + 15 minutes** in the cockpit's timezone and pass it explicitly. Take the later of that and `--start` when the user gave one; a `--start` in the past or inside the floor loses to the floor.
- When the suggestions come back, **check the first one is still more than 15 minutes out.** If it is not, drop it, ask for one more, and say what you dropped.

### Then one more slot, for YouTube

Unless `--no-youtube` was passed, ask for one final slot **a day after the last hook**:

```
suggest_slots  count: 1  earliest: <last hook's slot + 1 day>
```

Same rule as every other slot: the time comes back from the cockpit, you don't pick it. The one-day offset is only which window you ask about — it is what gives the last hook a day on Instagram before its numbers decide the pick.

This slot has no same-video problem to avoid: it is a different platform, and it draws a hook that has already run its course on Instagram. If the call returns nothing, report that the cross-post could not be slotted and carry on with the Instagram hooks — it is not a reason to abandon the run.

Before Step 4, confirm the pool will actually have something to give it:

```
mcp__social-cockpit__get_slug_pool   slug: <slug>   platform: "yt"
```

For a brand-new slug this reads `0 video(s)` and that is **correct** — the pool fills as each hook publishes, all of which is still in the future. What you are checking for is the opposite case: a slug whose hooks have already gone out, where `eligible` for `yt` being 0 means every one has been cross-posted already and this job would fail with `no_candidate`. Say which of the two you are looking at in Step 4.

### Before moving on

Each hook is its own post at its own time. Pair hooks to slots in order, then check the collected slots as a set: no two on the same **day**, and every consecutive pair at least `min_same_video_days` apart. If that doesn't hold, the loop above was short-circuited — redo it rather than nudging a time by hand.

Pass the returned `scheduled_at` strings through to Step 5 unchanged. If a call reports days skipped at the daily limit, that is worth repeating to the user, but it is not a problem — it is the policy working.

The cockpit reporting no `min_same_video_days` policy is expected now (social-cockpit removed it), not a build anomaly — use `FALLBACK_MIN_GAP_DAYS` without flagging it each run.

### Posting more than once a day

Change it **in social-cockpit**, not here — one place, and it applies to `/schedule-video`, `/post-video` and the scheduler alike:

```bash
curl -X PUT {COCKPIT_URL}/api/schedule/settings -H 'Content-Type: application/json' \
  -d '{"suggested_times":["09:30","18:00"],"max_posts_per_day":2}'
```

Two posts in one day is for **two different videos** — a second video takes the 18:00 slot on a day the first holds 09:30. Two hooks of *one* video on the same day is the thing to avoid, and since `suggest_slots` won't stop you, Step 3's one-call-per-hook walk is what keeps them apart. Raising `max_posts_per_day` makes that walk more necessary, not less.

`min_same_video_days` used to live in the same settings object; social-cockpit removed it, so `FALLBACK_MIN_GAP_DAYS` in `scrape/post_video.py` is what `/post-video` and Step 3 here actually read. Nothing in the cockpit acts on it either way.

## Step 4 — Show the plan and confirm

Scheduling publishes to a live account on a timer, so **always show the plan and get explicit confirmation before booking.** Present a table in the cockpit's timezone:

```
Slot                            Hook file                          Caption
Sat 16 Aug 2026, 09:30 GMT+10   waited-longest-dropped-first.mp4   "…"
Mon 18 Aug 2026, 09:30 GMT+10   figma-fixed-outages.mp4            "…"
Tue 19 Aug 2026, 09:30 GMT+10   YouTube — picked from the pool     "Figma's Fix For Outages"
```

State alongside it: that every time came from `suggest_slots` and what it reported fitting the plan around, the `min_same_video_days` gap in force and whether it came from the cockpit or the fallback, the first `earliest` you passed and why (the 15-minute floor, or `--start`), whether an automation will attach — with its key and trigger keywords, or that there is no `automation.json` so these post without one — and that each Instagram post goes out as a **trial reel**.

For the YouTube row, say plainly that **no file is being chosen now**: it books the slug's pool, and the cockpit picks whichever hook has the most views at that moment. Give the title it will carry (from `videos.json`) and what `get_slug_pool` reported — an empty pool that is about to fill, or an exhausted one that will fail.

If any hook went unslotted because `suggest_slots` returned fewer slots than hooks, name it here. It stays unscheduled and unclaimed, and the next run picks it up.

## Step 5 — Book them

On confirmation, book every hook in **one** run of `scrape/schedule_video.py` — it builds the caption and the automation block itself (see above), POSTs each hook to social-cockpit's `/api/schedule` directly, and claims each success in `output/.published` as it goes:

```bash
.venv/bin/python scrape/schedule_video.py <slug> \
  "<hook1>.mp4=<scheduled-at-iso-1>" \
  "<hook2>.mp4=<scheduled-at-iso-2>" \
  --youtube "<youtube-scheduled-at-iso>"
```

Notes:
- One `<hook>.mp4=<scheduled-at-iso>` pair per hook, in the order agreed in Step 4. `<hook>.mp4` is the filename only (the script resolves it under `output/<slug>/`); `<scheduled-at-iso>` is the string `suggest_slots` returned, **verbatim** — without an offset it's read in the cockpit's timezone, the zone the suggestion was made in.
- `--youtube` takes the extra slot from Step 3, the same way and just as verbatim. Omit the flag entirely for `--no-youtube`, or when Step 3 could not slot it.
- Entries are independent: one failing (e.g. a `day_full` conflict) doesn't roll back the others. The script prints `✓`/`✗` per hook and a `Booked N, failed N` summary — report both, and retry only the failures. The YouTube job is booked last and still goes ahead when some hooks failed: the pool only needs one candidate.
- The `video` field marking these as one video's hooks, the `slug` that enrols each published hook in the pool, the `automation.key` shared across them, the YouTube title, `selection_method`, and every `output/.published` ledger line are all written by the script — nothing left for you to compose or append by hand.

## Step 6 — Report what was booked

`output/.published` is already updated for every hook the script booked — that's what claims it; nothing more to write. Report the final schedule, with job ids, in the cockpit's timezone. For any hook the script reported `failed`, no ledger line was written, so it stays eligible for the next run once you've addressed why it failed.

The cross-post gets a ledger line too, keyed **`<slug>/@youtube`** rather than an mp4 — a slug job claims the pool, not a file, but without a claim a second run of this command would book a second YouTube post for the same slug. Removing that line is what allows another one.

### What this means for `/post-video`

`post_video.py` skips any hook claimed here, and runs its own gap check against the cockpit's calendar — so a slot booked by this command will hold it off, the same way a real post would. `--ignore-gap` overrides that when it's genuinely what you want.

## Managing what's booked

- **See the queue:** `mcp__social-cockpit__list_scheduled_posts` (filter `status: ["pending"]`).
- **Move one:** `mcp__social-cockpit__update_scheduled_post` with a new `scheduled_at` — call `suggest_slots` first rather than picking a time by hand. Also revives a job that failed or was missed. Updating the hook's timestamp in `output/.published` to match is tidy but optional; nothing reads it.
- **Pause / resume:** same tool, `status: "paused"` / `"pending"`.
- **Cancel:** `mcp__social-cockpit__cancel_scheduled_post`. Also remove its line from `output/.published`, or the hook stays claimed by a job that no longer exists.
- **Post one early:** `mcp__social-cockpit__run_scheduled_post_now` — publishes immediately and blocks for a few minutes. Confirm with the user first; it can't be undone.
- **Why did it fail:** `mcp__social-cockpit__get_scheduled_post` returns the job's event history.

## When a scheduled post fails

A hook is written to the ledger when it is *booked*, so a job that later fails terminally leaves a line claiming a post that never went out. That hook will not be picked up again until the line is removed.

Check for these before assuming a slug is fully posted:

```
mcp__social-cockpit__list_scheduled_posts  →  status: ["failed", "missed"]
```

For each one, either revive it (`update_scheduled_post` with a new `scheduled_at`, which resets its attempts), or cancel it and delete its line so the hook is rescheduled from scratch on the next run.

### When the cross-post fails

A YouTube slug job has one failure the hooks don't: **`error_kind: "no_candidate"`**, which is not retryable — moving it to a later slot changes nothing. `get_scheduled_post` names which of the four it hit, and `get_slug_pool  slug: <slug>  platform: "yt"` shows the same thing against the pool:

- **Empty pool** — no hook ever published, so nothing enrolled. Find out why the Instagram jobs failed first.
- **Exhausted** — every candidate has already been cross-posted to YouTube. Working as intended; delete the `@youtube` ledger line only if you have added new hooks.
- **Missing from disk** — a rendered mp4 was moved or deleted after it published. The pool holds a reference, never a copy.
- **All spoken for** — another slot on the same slug is publishing right now. Rare, and it clears itself.
