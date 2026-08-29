---
name: prepare-video
description: Wire footage path into config, run reelcut transcription, then review captions.json for EDL anomalies (bad cuts, multiple takes, silence issues) and caption errors — auto-fixing the unambiguous ones and reporting the rest.
argument-hint: "<video-slug> [--fresh]"
---

Runs reelcut transcription for a video slug, then reviews the resulting captions.json for anomalies: the unambiguous ones you fix here (Step 4), everything else you report for the user to decide.

Arguments: `$ARGUMENTS` — expected format: `<video-slug> [--fresh]`. `--fresh` also wipes `videos.json` and `audio.json` (see Step 2).

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/prepare-video netflix-cdn-architecture`

## Step 1 — Locate footage

The user drops their footage into `assets/<video-slug>/` before running this command.

## Step 2 — Run transcription

```bash
.venv/bin/reelcut transcribe config.yaml --slug <video-slug> --footage "assets/<video-slug>/"
# add --fresh only if the user passed it
```

Output goes to `assets/<slug>/`, named after the footage stem (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). The transcription step prints the actual path.

**This resets the transcript.** `captions.json`, the debug reports, `retranscribe-clips/` and `images.json` are always regenerated. `videos.json` keeps its card wording (title, subtitle, caption, filename) but has its `start`/`end` hook windows cleared, because those are output-timeline values the new EDL moves — `/produce-video` Step 3c recomputes them. `audio.json` is kept whole. Add `--fresh` to wipe all three back to stubs. Source inputs are untouched either way: footage, `script.md`, `manifest.json` and the produce-script screenshots.

**Any hand-edits to `captions.json` from a previous run are lost** — the `edl` keep-flips and word fixes from Step 4 live only in that file. If a take was rescued by flipping a cut, it will be re-cut and needs fixing again.

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

## Step 3 — Assess

Work out the anomalies here, apply the certain ones in Step 4, then report — so the numbers you quote are post-fix.

**Read `assets/<video-slug>/script.md` first — it is what the speaker was reading.** `/produce-script` writes it and it survives the Step 2 reset. It is ground truth for **wording**, never for timing or for which take to keep. Align the surviving transcript against it; it settles three things the confidence digest cannot see, because Whisper is regularly confident *and* wrong:

- **Misheard words** — a transcript token differing from the script's word at the aligned position (`Chachabit` → **ChatGPT**, `unsee` → **un-issue**, `pgKeeper` → **PGKeeper**). Certain fix in Step 4, including casing.
- **Dropped script sentences** — a script sentence with no surviving transcript span. Usually a cut that reached too far; report it naming the `edl` span that swallowed it.
- **Inserted tokens** — a transcript word with no script counterpart (a stray `well.` or `it.`).

**Ad-libs are normal and are not anomalies.** The delivery rewords freely ("Before" → "Previously", an added "See," or "usually"), and hooks are often reworded on the fly. Only flag a difference that changes a word's identity, a name's spelling or casing, or a claim. If the slug has no `script.md` (footage predating it, a slug that never went through `/produce-script`, or a direct recording — see below), say so once and assess from the transcript alone. Skip the script-anchored fixes in Step 4; the rest still apply.

**Check `assets/<video-slug>/.reelcut-intake.json` before assessing hooks** (a dotfile — `cat` it, a listing won't show it). With `kind: "direct"` and `hook_policy: "single"` the missing `script.md` is contractual, not a degraded case: the clip is one hook plus body, so the next paragraph does not apply — do not read a second emphatic sentence as an alternate take.

**Hook takes are intentional.** The user deliberately records several alternate openers back-to-back at the top of the clip (often fully reworded, e.g. "Reddit moved a petabyte…" then "Reddit swapped Kafka onto Kubernetes…"). The retake detector won't cut these because they share little verbatim wording. Do **not** flag them as anomalies or bad cuts — just list the alternate hooks. Only a *truncated false start* (a cut-off opener like "…brokers to re…" immediately followed by its clean completion) is a real anomaly worth flagging as such.

Summarise (after Step 4 has run):
- Manifest reconciliation results (if run): contexts re-aligned, and any orphaned screenshots / unsupported claims for the user to action
- Keep / cut duration after fixes
- Anomalies found, split into those auto-fixed in Step 4 and those left for the user to apply (with the recommended fix for each)
- Any remaining issues that need a human listen (ambiguous takes, uncertain boundaries)
- What Step 2 left in `videos.json`: a fresh stub, or a prior run's cards with their hook windows cleared. Either way `/produce-video` fills in the windows, and the image overlays in `images.json`.

## Step 4 — Apply the certain fixes, then log

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
| Transcript word contradicted by `script.md` at the aligned position — including a proper noun's casing (`Chachabit` → `ChatGPT`, `pgKeeper` → `PGKeeper`) | rewrite that `words[i].word` text to the script's word |
| Mid-sentence full stop or spurious capital that splits/mangles a caption line | rewrite that `words[i].word` text |

**Never auto-fix** (report only): alternate hook takes (user picks one), low-confidence survivors that are the *correct* word, word swaps where you'd be guessing what was actually said or the swap changes the claim, large kept gaps / ambiguous boundaries that need a human listen, and hard-cap hits. The script's **dropped sentences and inserted tokens** are report-only too — fixing either means moving a boundary or adding/removing a `words` entry, which this step never does.

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

