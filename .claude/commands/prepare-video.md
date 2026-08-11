---
name: prepare-video
description: Wire footage path into config, run reelcut transcription, then review EDL anomalies (bad cuts, multiple takes, silence issues) in captions.json and report findings.
argument-hint: "<video-slug>"
tools: Read, Bash
model: sonnet
permissionMode: default
---

Runs reelcut transcription for a video slug, then reviews the resulting captions.json for anomalies and reports them for the user to fix.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/prepare-video netflix-cdn-architecture`

## Step 1 — Locate footage

The user drops their footage into `assets/<video-slug>/` before running this command.

## Step 2 — Run transcription

```bash
.venv/bin/reelcut transcribe config.yaml --slug <video-slug> --footage "assets/<video-slug>/"
```

Output goes to `assets/<slug>/`, named after the footage stem (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). The transcription step prints the actual path.

**This is a full reset.** Transcription first wipes everything derived from any prior run — the old `captions.json`, debug reports, and the overlay files `images.json` / `headings.json` / `audio.json` / `title.json` — then re-scaffolds them as fresh stubs. So re-running this command on a slug that already went through `/produce-video` discards those image timings, title cards, and Instagram titles (they'd otherwise drift against the new transcript). Source inputs are untouched: the footage, `manifest.json`, and the produce-script screenshots all carry over.

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

**Hook takes are intentional.** The user deliberately records several alternate openers back-to-back at the top of the clip (often fully reworded, e.g. "Reddit moved a petabyte…" then "Reddit swapped Kafka onto Kubernetes…"). The retake detector won't cut these because they share little verbatim wording. Do **not** flag them as anomalies or bad cuts — just list the alternate hooks. Only a *truncated false start* (a cut-off opener like "…brokers to re…" immediately followed by its clean completion) is a real anomaly worth flagging as such.

Summarise:
- Manifest reconciliation results (if run): contexts re-aligned, and any orphaned screenshots / unsupported claims for the user to action
- Keep / cut duration after fixes
- Anomalies found and recommended fix for each (for the user to apply)
- Any remaining issues that need a human listen (ambiguous takes, uncertain boundaries)
- `headings.json`, `images.json`, and `title.json` stubs were auto-created in the slug folder — optionally add a title card / image overlays / Instagram title later by filling them in (covered in `/produce-video`)

## Step 4 — Auto-fix the certain anomalies, then log

Take the Step 3 anomalies and split them into **CERTAIN-FIX** vs **REPORT-ONLY**. Only the certain ones get applied here; everything else stays reported for the human.

**The only file you edit to apply a fix is `captions.json`, and only its `edl` and `words` arrays.** The `edl` is a flat list of contiguous `{source_clip, start, end, keep, reason}` spans. An `edl` fix is a **surgical in-place edit to one span** — flip its `keep` flag. A `words` fix edits **only the `word` text** of one entry — never its `start`/`end`/`source_clip`, never insert or delete entries (the render and the `edl` are timed off these). Leave `source_clips` byte-for-byte untouched. Never alter the `start`/`end` of a kept-speech span. Do **not** re-run `transcribe` to "refresh" anything — that recomputes the whole `edl` and discards these fixes.

Auto-fix **only** these (if a fix needs guessing which take the user wants, or a boundary you can't read straight off word timings, do **not** touch it):

| Anomaly | Fix |
|---|---|
| Truncated false-start opener (a cut-off opener immediately followed by its clean completion) | flip the truncated span → `keep: false` |
| Clear over-cut: a `keep: false` span (`reason` silence/noise) that actually contains real words present in `words` | flip → `keep: true` |
| Micro keep-segment that is a bare fragment (no full word) | flip → `keep: false` |
| Missed cut sitting *inside* a keep span, where the digest names the exact dead words | split that one span into three at the surrounding word boundaries (from `words`), middle sub-span → `keep: false` |
| Misheard word, where the surrounding sentence makes the intended word unambiguous (e.g. "never miss is **riding** commit messages" → `writing`; "**AR** whips up a commit message" → `AI`) | rewrite that `words[i].word` text |
| Mid-sentence full stop or spurious capital that splits/mangles a caption line | rewrite that `words[i].word` text |

**Never auto-fix** (report only): alternate hook takes (user picks one), low-confidence survivors that are the *correct* word, word swaps where you'd be guessing what was actually said or the swap changes the claim, large kept gaps / ambiguous boundaries that need a human listen, and hard-cap hits.

After editing, recompute keep/cut totals from the edited `edl`, then write the fix log to `assets/<slug>/<clip-stem>.debug.7.fixlog.txt` (same `<clip-stem>` as the other `.debug.*` files; `7` sorts it last). Format:

```
FIX LOG — <slug>
run: <ISO timestamp>   clip: <stem>
keep/cut duration:  before <k>s / <c>s  →  after <k>s / <c>s   (Δ <±>s kept)

FIXES APPLIED (n)
  [1] <mm:ss>  <category>   edl[<i>] keep <old>→<new>   |   words[<i>] '<old>' → '<new>'
      <one-line reason>. (digest line <n>)

LEFT FOR HUMAN (n)
  - <mm:ss>  <category> — <why not auto-fixed>
```

If there were no certain fixes, write the file with `FIXES APPLIED (0)` and change nothing in `edl` or `words`.

In the chat summary, state: N auto-fixed + N left for human, and that `.debug.7.fixlog.txt` holds the record (each applied line carries `edl[i]` / `words[i]` before→after so it's trivial to revert).

- Next step: `/produce-video <slug>`

