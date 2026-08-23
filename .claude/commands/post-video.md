---
name: post-video
description: Publish a slug's rendered hook reels to Instagram via social-cockpit — POSTs each output/<slug>/*.mp4 local path to /api/publish/local as a trial reel, one post per hook spaced a random 3-7 minutes apart.
argument-hint: "<video-slug>"
tools: Read, Bash
model: sonnet
permissionMode: default
---

Publishes every rendered hook variant for a slug (`output/<video-slug>/*.mp4`) to Instagram through social-cockpit's `/api/publish/local` endpoint. It hands the endpoint each mp4's local filesystem path and social-cockpit manages the whole chain server-side (read file → upload to R2 → presign → call Instagram → reclaim the object). Each hook is captioned from `assets/<slug>/videos.json` and posted as a trial reel (`graduation_strategy: MANUAL`). A mirrored duplicate (`output.flip.apply: duplicate`) has its own entry there when `/produce-video` Step 4b wrote one, so it posts under its own caption; without one it inherits the caption of the hook it mirrors. Posts are spaced a **random 3-7 minutes apart** and each hook is posted **once** — `output/.published` records what's gone out so re-runs never double-post.

Two separate questions, two separate authorities:

- **Has this hook been used?** — `output/.published`, shared with `/schedule-video`. A key there means the hook is spoken for, whether it was posted or booked into a future slot, and deleting its line is the only way to release it. The timestamp beside it is informational.
- **Is now a good time to post?** — social-cockpit's calendar. The gap check asks the cockpit what is within `--min-gap-days` of now, counting both what actually went out and what is booked, so a slot booked by `/schedule-video` holds this off the same way a real post would. `--ignore-gap` overrides it.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Slugs with rendered output: !`ls -1 output/ 2>/dev/null | grep -vE '\.(mp4|md)$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/post-video spotify-wrapped-billion-ai-stories`

## Optional: attach a comment automation

If `assets/<slug>/automation.json` exists, each hook is also wired into a single comment automation server-side (comment keyword → auto DM/reply). All hooks of the slug share **one** flow: `automation.key` defaults to the slug, so the cockpit creates the flow on the first hook and appends every later hook to it — no duplicate flows, and re-posting is idempotent. No file = posts with no automation (unchanged behaviour). The dry run reports whether an automation will attach.

`/produce-script` writes this file at Step 3.6.5 for comment-bait series, from the CTA's keyword and lead magnet. Series with no keyword get no file, and post without an automation.

`assets/<slug>/automation.json` holds only what differs between videos:

```json
{
  "trigger_keywords": ["GUIDE"],
  "follower_message": "Here you go:\n\n<labelled resource list>"
}
```

`scrape/automation_spec.py` fills in the rest — the `comment_to_follow_dm` template, the `casual_replies` reply function, the `casual` DM pack, `DONE`, and `resources` — which is identical for every video and so lives in one place rather than in each file. `social-cockpit/docs/publish-with-automation.md` covers the publish-time behaviour.

Before posting, confirm it validates. This is also the only check that the packs still exist under those names in social-cockpit — a renamed one is not rejected at post time, it just sends an empty message:

```bash
.venv/bin/python scrape/validate_automation.py <video-slug>
```

## Prerequisites (set up once, outside this workflow)

- **social-cockpit** dev server running on `{COCKPIT_URL}` (`http://localhost:3000`), exposing `POST /api/publish/local` (`{ video_path, caption, trial_params }`). It reads the local file, uploads to R2, presigns, calls Instagram, and reclaims the object — no R2 credentials are needed on this side.

## Step 1 — Preview the plan (dry run)

Publishing to Instagram is outward-facing and hard to undo, so always show the plan first. This uploads and posts nothing:

```bash
.venv/bin/python scrape/post_video.py <video-slug> --dry-run
```

Report the list of hooks and captions it would post (and any it will skip as already published).

## Step 2 — Confirm, then publish for real

Ask the user to confirm before posting. On confirmation:

```bash
.venv/bin/python scrape/post_video.py <video-slug>
```

The script uploads each hook to R2, POSTs it to `/api/publish`, appends it to `output/.published`, then sleeps a random 3-7 minutes before the next. Because it sleeps between posts, the run stays alive for several minutes per hook — let it finish. Report the published titles at the end.

Notes:
- To intentionally re-post a hook, remove its `slug/name.mp4` line from `output/.published` (or delete the file) before re-running.
- `COCKPIT_URL` overrides the endpoint host if the cockpit isn't on localhost.
