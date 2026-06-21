---
name: prepare-video
description: Wire footage path into config, run reelcut transcription, then review EDL anomalies (bad cuts, multiple takes, silence issues) in captions.json and report findings.
tools: Read, Bash
model: sonnet
permissionMode: default
---

Runs reelcut transcription for a video slug, then reviews the resulting captions.json for anomalies and reports them for the user to fix.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Example: `/prepare-video netflix-cdn-architecture`

## Step 1 — Locate footage

The user drops their footage into `assets/<video-slug>/` before running this command.

## Step 2 — Run transcription

```bash
.venv/bin/reelcut transcribe config.yaml --slug <video-slug> --footage "assets/<video-slug>/"
```

Output goes to `assets/<slug>/`, named after the footage stem (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). The transcription step prints the actual path.

## Step 3 — Report

Summarise:
- Keep / cut duration after fixes
- Anomalies found and recommended fix for each (for the user to apply)
- Any remaining issues that need a human listen (ambiguous takes, uncertain boundaries)
- `headings.json` and `images.json` stubs were auto-created in the slug folder — optionally add a title card / image overlays later by filling them in (covered in `/produce-video`)
- Next step: `/produce-video <slug>`

