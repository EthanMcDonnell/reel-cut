---
name: voice-profile
description: Mine your top-performing reels from social-cockpit into two reusable reference artifacts — proven-hooks.md (real hooks ranked by real engagement) and voice-profile.md (your actual speaking style). The scripts pipeline reads both.
tools: Read, Write, Bash
model: opus
permissionMode: default
---
Regenerate the voice/hook reference artifacts from your **actual** top-performing
Instagram reels. These are the ground truth the `produce-script` command and the
`hooks`/`scripts` skills lean on so generated content matches what already wins
and sounds like you — not generic AI.

Run this whenever you've posted new winners (or on demand). It overwrites the two
artifacts in `.claude/voice/`.

**Paths:** `{TOKEN}` references below are machine-specific paths/endpoints defined in [glossary.md](glossary.md) — resolve each to its value before running. Repo-relative paths (`.claude/…`, `series/…`, `scrape/…`) are written inline as-is.

The user's prompt (optional) is: `$ARGUMENTS` — it may name a metric
(`engagement`, `views`, `saved`, `shares`, `reach`, `comments`, …) or a limit.
Default to `--metric engagement --limit 12`.

## Stage 1 — Pull the data

Fetch top performers (full transcripts + insights) from social-cockpit:

```bash
.venv/bin/python scrape/cockpit.py --metric engagement --limit 12
```

Also pull a second ranking so the analysis isn't single-metric biased — `views`
surfaces reach-winners that engagement misses:

```bash
.venv/bin/python scrape/cockpit.py --metric views --limit 12
```

Each command prints a JSON array, best-first, with `metricValue`, `insights`
(reach/views/likes/comments/shares/saved/watch-time), `caption`, `permalink`,
`durationSec`, and the full `transcript`.

If the script errors with "could not reach cockpit", tell the user to start the
social-cockpit server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`, serves
`{COCKPIT_URL}`) and stop — do not fabricate artifacts from memory.

## Stage 2 — Synthesize `proven-hooks.md` (cross-channel only)

The hook is the **first spoken line** of each transcript. Extract each verbatim and
analyze what made it work — but `proven-hooks.md` holds only the **channel-wide
synthesis**, not a per-video table. The individual hooks belong in their series
files (Stage 3.5), so don't duplicate them here. Write `.claude/voice/proven-hooks.md`:

- A scope note: this file is the cross-series lessons; per-video hooks live in
  `series/*.md` Best Hooks.
- A **"What's winning"** synthesis across *all* series: which patterns dominate,
  which lead elements recur (specific numbers? named tools in the first 4 words?
  second-person threat?), the repeatable templates (e.g. `"What is X and why was it
  so dangerous?"`, `"So [Company] literally [absurd action]"`), and typical hook
  length in words. Be concrete and quantified — "a named tech leads all 12 top
  hooks", not "names tend to work".
- The **biggest engagement lever** observed (e.g. comment-bait CTA driving the #1
  video's comment count).
- A short **channel-wide exemplars** list (top ~3 hooks overall) for `misc` scripts
  that have no series file.
- Keep it tight and skimmable — it is read as priors before writing new hooks.

## Stage 3 — Synthesize `voice-profile.md`

From the **full transcripts** (not just hooks), profile how the user actually
talks. Write `.claude/voice/voice-profile.md` covering:

- **Openers** — how sentence 1 typically starts (connectors, declaratives,
  questions). Quote 2–3 real examples.
- **Sentence rhythm** — short vs long, fragments, where they vary pace. Note the
  rough pacing in words/second (transcript word count ÷ `durationSec`).
- **Vocabulary & emotion** — the actual feeling words and casual markers they use
  ("wild", "kind of crazy", lowercase asides). List real ones; don't invent.
- **Address** — how often and how they use "you" and "I".
- **Reveals & transitions** — the phrases they use to open/close loops and pivot
  to the payoff.
- **CTA style** — how they actually end videos (comment-bait wording, follow
  lines, or nothing).
- **Tics to reuse** — recurring phrasings worth keeping.
- **Never-do list** — AI-isms absent from their real speech, so generation avoids
  them (cross-check against the `stop-slop` skill).

Ground every claim in the transcripts — quote real fragments. This file is read
before script-writing to match the user's register.

## Stage 3.5 — Push per-video hooks into series files

The `series/<slug>.md` files (indexed in `SERIES.md`) are the source of truth the
pipeline reads, and each has a **Best Hooks** section. The individual proven hooks
live here (per-audience), not in `proven-hooks.md`. Push real top-performer hooks
into the matching series file — but **do this only with the user's confirmation**,
because the cockpit data is not tagged by series and these files are hand-curated.

1. **Infer a series for each top performer** from its caption + transcript, using
   the canonical slugs: `tbbt` (how big tech solved an engineering problem),
   `updates` (timely news/price/release), `tech-in-one-breathe` (one tool, ~30s),
   `interesting-tech` (mystery artifact / "what is X"), `ai-fundamentals`
   (practical AI concept the viewer is confused about today), `hot-takes`
   (first-person contested opinion, no source article).
2. **Show the user the inferred mapping** (hook → series → metric) and ask them to
   confirm or correct it before writing anything.
3. On confirmation, for each affected `series/<slug>.md`, **add or refresh a single
   bolded block under its Best Hooks section**, exactly in this format and nowhere
   else in the file:

   ```
   **Top performers (analytics, auto — refresh via `/voice-profile`):**
   - "<verbatim hook>" — <N> engagement, <N>k views (<pattern; brief note>)
   ```

   Replace the block's bullets wholesale on each run (it's regenerated, not
   appended). Do **not** touch the user's curated "Shipped"/"Example" lists or any
   other section.

If the user declines, skip this stage; the cross-channel synthesis still covers it.

## Stage 4 — Report

Tell the user: which metrics/limits were used, how many posts fed the analysis,
the files written (`proven-hooks.md`, `voice-profile.md`, and any `series/*.md`
updated in Stage 3.5), and a 2–3 line summary of the dominant winning pattern and
the single most distinctive voice trait you found.
