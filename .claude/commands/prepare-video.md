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

**This is a full reset.** Transcription first wipes everything derived from any prior run — the old `captions.json`, debug reports, and the overlay files `images.json` / `headings.json` / `audio.json` — then re-scaffolds them as fresh stubs. So re-running this command on a slug that already went through `/produce-video` discards those image timings and title cards (they'd otherwise drift against the new transcript). Source inputs are untouched: the footage, `manifest.json`, and the produce-script screenshots all carry over.

## Step 2.5 — Reconcile screenshot manifest (only if one exists)

If `assets/<video-slug>/manifest.json` is present (screenshots were produced by `/produce-script`), the script has almost certainly moved since the manifest was written, so its `script_context` lines — which `/produce-video` uses to place each screenshot — must be re-aligned to what was actually said:

```bash
.venv/bin/python scrape/reconcile_manifest.py --slug <video-slug>
```

This auto-rewrites each screenshot's `script_context` to the closest verbatim line in the new transcript and prints a JSON report with three buckets:

- `context_fixed` — contexts that were re-aligned (applied automatically).
- `orphaned` — screenshots whose supported line no longer exists in the script (left untouched). **Report each**: its claim has no on-screen evidence — either re-shoot against the new line or drop it from the manifest.
- `unsupported_claims` — claim-bearing script sentences (numbers, %, $) that no screenshot covers. **Report each** as a candidate for a new screenshot.

If no `manifest.json` exists, skip this step.

## Step 3 — Report

**Hook takes are intentional.** The user deliberately records several alternate openers back-to-back at the top of the clip (often fully reworded, e.g. "Reddit moved a petabyte…" then "Reddit swapped Kafka onto Kubernetes…"). The retake detector won't cut these because they share little verbatim wording. Do **not** flag them as anomalies or bad cuts — just list the alternate hooks as a quick "pick one" so the user can flip the others to `keep: false`. Only a *truncated false start* (a cut-off opener like "…brokers to re…" immediately followed by its clean completion) is a real anomaly worth flagging as such.

Summarise:
- Manifest reconciliation results (if run): contexts re-aligned, and any orphaned screenshots / unsupported claims for the user to action
- Keep / cut duration after fixes
- Alternate hook takes at the cold open — list them for the user to pick one (not an anomaly)
- Anomalies found and recommended fix for each (for the user to apply)
- Any remaining issues that need a human listen (ambiguous takes, uncertain boundaries)
- `headings.json` and `images.json` stubs were auto-created in the slug folder — optionally add a title card / image overlays later by filling them in (covered in `/produce-video`)
- Next step: `/produce-video <slug>`

