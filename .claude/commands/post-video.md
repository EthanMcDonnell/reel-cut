---
name: post-video
description: Publish a slug's rendered hook reels to Instagram via social-cockpit — POSTs each output/<slug>/*.mp4 local path to /api/publish/local as a trial reel, one post per hook spaced a random 3-7 minutes apart.
argument-hint: "<video-slug>"
tools: Read, Bash
model: sonnet
permissionMode: default
---

Publishes every rendered hook variant for a slug (`output/<video-slug>/*.mp4`) to Instagram
through social-cockpit's `/api/publish/local` endpoint. It hands the endpoint each mp4's local
filesystem path and social-cockpit manages the whole chain server-side (read file → upload to R2 →
presign → call Instagram → reclaim the object). Each hook is captioned from
`assets/<slug>/title.json` and posted as a trial reel (`graduation_strategy: MANUAL`). Posts are
spaced a **random 3-7 minutes apart** and each hook is posted **once** — `output/.published`
records what's gone out so re-runs never double-post.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Slugs with rendered output:
!`ls -1 output/ 2>/dev/null | grep -vE '\.(mp4|md)$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/post-video spotify-wrapped-billion-ai-stories`

## Prerequisites (set up once, outside this workflow)

- **social-cockpit** dev server running on `{COCKPIT_URL}` (`http://localhost:3000`), exposing
  `POST /api/publish/local` (`{ video_path, caption, trial_params }`). It reads the local file,
  uploads to R2, presigns, calls Instagram, and reclaims the object — no R2 credentials are needed
  on this side.

## Step 1 — Preview the plan (dry run)

Publishing to Instagram is outward-facing and hard to undo, so always show the plan first. This
uploads and posts nothing:

```bash
.venv/bin/python scrape/post_video.py <video-slug> --dry-run
```

Report the list of hooks and captions it would post (and any it will skip as already published).

## Step 2 — Confirm, then publish for real

Ask the user to confirm before posting. On confirmation:

```bash
.venv/bin/python scrape/post_video.py <video-slug>
```

The script uploads each hook to R2, POSTs it to `/api/publish`, appends it to `output/.published`,
then sleeps a random 3-7 minutes before the next. Because it sleeps between posts, the run stays
alive for several minutes per hook — let it finish. Report the published titles at the end.

Notes:
- To intentionally re-post a hook, remove its `slug/name.mp4` line from `output/.published`
  (or delete the file) before re-running.
- `COCKPIT_URL` overrides the endpoint host if the cockpit isn't on localhost.
