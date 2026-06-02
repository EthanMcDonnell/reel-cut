# CLAUDE.md

**ReelCut** — short-form video production pipeline (Instagram Reels / YouTube Shorts).

**Always use `.venv/bin/python` for all Python and pip commands.** Never system python/pip.

## Key paths

- `assets/<slug>/` — per-video working files (captions.json, debug.txt, screenshots, manifest.json)
- `output/<slug>.mp4` — final rendered videos
- `scrape/db/influencer.db` — SQLite content discovery DB (gitignored)
- Scripts → Obsidian `Videos/Videos To Do/<slug>.md`

## Workflows

- `/produce-script` — Phase 0: article/URL → script + screenshots
- `/prepare-video <slug>` — Phase 1: transcribe + fix EDL
- `/produce-video <slug>` — Phase 2: assign image timings + render
