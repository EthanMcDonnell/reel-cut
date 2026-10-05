---
name: video-ideas
description: Generate a fresh, source-verified batch of video ideas across every series in series/, driven by live social-cockpit analytics and deduped against every existing idea bank.
tools: Read, Glob, Grep, Write, Bash, WebFetch, WebSearch
model: opus
permissionMode: default
---
Produce a new dated batch of video ideas, grounded in what is **actually performing** on the channel right now rather than in what seems interesting. Each idea is a **hook** in its series' winning pattern, plus the **angle** it has to deliver, plus (where the series requires one) a **verified source**.

This command does not write scripts. It creates a **persisted, Telegram-delivered idea batch** and also writes a dated idea bank to **`ideas/`** (Stage 7, gitignored), which is where `/produce-script` looks when a prompt names an idea rather than a URL. Keep the bank in `ideas/` and keep the `## <series-slug> — <Series Name>` headings intact: `/produce-script` reads the series straight off the heading of the entry it matches.

**Paths:** `{TOKEN}` references are machine-specific paths defined in [glossary.md](glossary.md) — resolve each before running. Repo-relative paths (`scrape/…`, `series/…`, `.claude/…`) are written inline. Run all `.venv/bin/…` commands from `{PROJECT_ROOT}`.

The user's prompt (optional) is: `$ARGUMENTS` — it may narrow the run. Honour any of:
- **a series slug** (any `series/<slug>.md` filename, excluding `series-template`) → only that series
- **a count** ("5 per series", "20 ideas") → override the defaults in Stage 5
- **a focus** ("only shareable", "lean into <series>", "no news") → weight selection accordingly

Default with no arguments: every series, at the count its file's `**Ideas per batch:**` line sets under `## Topic Selection`, or **3** when it sets none. A series may come in under its count only when its file allows it; state the shortfall plainly rather than padding.

**The series files drive this command.** In-scope series are the `series/*.md` files (not `series-template.md`). Read each one's `## Identity` and `## Topic Selection` before Stage 0: its `**Source:**` and `**Harvest (/video-ideas):**` lines say where ideas come from and how to gather them. If `SERIES.md` exists, read it too — it holds channel-wide notes.

---

## Stage 0 — Refresh scraped feeds silently

This command is the curated alternative to raw article notifications. For every in-scope series whose **Harvest** names a scraper refresh, run it now with `--no-telegram` — **never send individual article cards**. The configured sites remain the source of truth. If a refresh fails, stop and report it rather than silently building a supposedly fresh batch from old candidates.

## Stage 1 — Pull the analytics

Never generate ideas from memory of what did well. Pull it:

```bash
.venv/bin/python scrape/cockpit.py --metric engagement --limit 15
.venv/bin/python scrape/cockpit.py --metric views --limit 15
.venv/bin/python scrape/cockpit.py --metric saved --limit 12
```

Three metrics, because each surfaces a different winner: `engagement` finds the overall best, `views` finds reach winners that engagement misses, `saved` finds the explainers people keep. Each command prints a JSON array, best-first, with `metricValue`, `insights` (reach / views / likes / comments / shares / saved / watch-time), `caption`, `permalink`, `durationSec`, and the full `transcript`.

If a command errors with "could not reach cockpit", tell the user to start the social-cockpit server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`, serving `{COCKPIT_URL}`) and **stop**. Do not fabricate a batch from remembered performance — the whole point of this command is that selection is driven by live numbers.

## Stage 2 — Derive what is winning (re-derive; do not assume)

Read the pulled data and answer three questions in writing. These drive every selection downstream, so be concrete and quantified.

1. **Which series is over-performing, and by how much?** Map each top performer to a series from its caption and transcript, using each series file's `## Identity`. A series carrying an outlier deserves disproportionate ideas even in an even-spread run.
2. **Which shape drives which action?** Compare `shares` against `saved` per video. They are different intents — breakages, price hikes, and "this affects you" news get *shared*; mechanism explainers get *saved*. Tag each idea you later write with `[share]` or `[save]` where its shape clearly favours one.
3. **What is the weak tail telling you?** Look at the bottom of the ranking, not just the top. The lowest performers usually share a shape, and that shape is the thing to stop making.

Treat any calibration notes in `SERIES.md` as priors to check against fresh numbers, never as conclusions to restate.

## Stage 3 — Build the dedup set

An idea that repeats something shipped, queued, or already proposed is worthless. Before generating anything, assemble the full exclusion list:

- **Shipped / produced:** `ls assets/archive/` and `ls output/` — every slug there is done.
- **Existing idea banks:** read every `VIDEO_IDEAS*.md` and `*_VIDEO_IDEA*.md` in `ideas/` (`Glob` for `ideas/*VIDEO_IDEA*.md` — the set grows each time this command runs). This includes `ideas/VIDEO_IDEAS_BACKLOG.md`, a large standing backlog of unproduced ideas — much of what looks "missing" from a series is really already queued there.
- **Series files:** read `series/<slug>.md` for each in-scope series — the **Queued** and **Best Hooks** sections list both what is planned and what already shipped.
- **Scripted but not yet shot:** `assets/*/script.md` — a slug with a script is already written.
- **Rejected topics:** `.venv/bin/python scrape/query.py rejected --series <series>` — topics previously ruled out. Do not re-propose them.
- **Persisted ideas:** `.venv/bin/python scrape/ideas.py list --status all` — these are the durable record of prior proposals, their approval state, and their sources. Do not repeat their semantic topic, slug, or supporting article as a new idea.

Record the exclusion set. Every idea in the final file must clear it.

## Stage 4 — Harvest source material per series

Each series has its own sourcing rules — follow its file's `**Source:**` and `**Harvest (/video-ideas):**` lines, don't apply one standard to all. Rules that hold whichever series:

- **Scrape every shortlisted article in full** before using it: `.venv/bin/python scrape/single_scrape.py "<url>"`. A feed blurb is not the article.
- **A series sourced from a scraped table** (`scrape/query.py articles <table> --status new`): skim titles first, shortlist the ones with a real story, then scrape. Skip announcements, vague "we improved X" posts and marketing — feeds are full of them.
- **A series with no source DB** (concept picks): no citation is expected, so dedup is the whole job — most "obvious" picks are already in the backlog or a prior bank.
- **A series sourced from the user's own opinions or experience:** never invent one. Mine their transcripts (pulled in Stage 1) and the series' **Queued** list, quote where each came from, and present every idea as a candidate for them to confirm, edit, or reject.

## Stage 5 — Generate and select

For each in-scope series, generate **wide then cut** — do not write the target count and keep all of it. Aim for ~2× the target, then drop everything that fails the checks below. The default target is each series' `**Ideas per batch:**` (3 when unset), adjusted only by an explicit count in `$ARGUMENTS`.

Write each idea in the series' own winning hook pattern, taken from `series/<slug>.md` **Best Hooks** and `.claude/voice/proven-hooks.md` — not a generic phrasing. Each idea needs:

- **The hook**, bolded, in the series' pattern.
- **`[share]` / `[save]` tag** where the shape clearly favours one (from Stage 2).
- **The angle** — what the video actually has to deliver. Concrete: the mechanism, the numbers, the reversal. Quote real figures from the scraped article, never remembered ones.
- **The source**, linked, with publication and date — for every series whose ideas come from articles or events.
- **A "why" line** tying it to a specific top performer from Stage 1, where the link is real.
- **Notes** for anything the user must know: adjacency to an existing idea, a company already used, a handling sensitivity, a figure that needs re-checking at produce time.

**The mechanism test.** Before keeping an idea, write its core as one sentence: the mechanism — how or why the thing works — that the video explains. If that sentence contains no mechanism — only *what happened* and *to whom* — the idea has nothing to fill 60 seconds with and it fails, however striking the outcome. Compare:

- *"The SMTP connect timeout compiled to zero, aborting after ~3ms, and 3 millilightseconds is 558 miles"* — a mechanism. The whole video is the explanation.
- *"Someone typed the wrong username into a records request"* — not a mechanism. It's an outcome. The explanation ends with the hook.

A shocking outcome is what earns the click; the mechanism is what the viewer stays for. An idea needs both, and this test is the one that catches ideas carrying only the first.

Drop an idea if any of these fail:

- It collides with the Stage 3 exclusion set.
- Its source doesn't actually support the hook's claim (see Stage 6).
- **It fails the mechanism test above** — a news event, court case, or political story with nothing of the channel's subject under it. The subject merely *appearing* in a story is not the same as the story being *about* it.
- It's a company-origins story, or any other shape the Stage 2 weak tail flagged.
- It's a reworded version of another idea in the same batch.

This is a judgement call, not a keyword ban. Politics, crime, and law are fine subjects when the video is genuinely about the channel's subject — e.g. for a tech channel, a court ruling on how a system works or a breach with a real root cause. What doesn't belong is a story the channel would be covering purely because it's in the news. When an idea is borderline, keep it and say plainly in its **Notes** why it's borderline, so the user makes the call.

## Stage 6 — The verification gate

This is the stage that makes the output trustworthy. Apply it before writing the file.

1. **Full text, not the blurb.** Every fact from an article must come from the scraped article body. An RSS `description` is not verification — it is frequently a marketing summary that contradicts the post.
2. **Every number is quoted, not recalled.** If you cannot point at the sentence in the scraped content, the number does not go in the file.
3. **Attribute correctly.** A claim inside a quote block belongs to the person quoted, not the publication. A fact from source B is not from source A.
4. **Say so when you couldn't verify.** If an idea is worth keeping but a figure went unconfirmed, keep it and **mark it explicitly** (`**Verify before producing:** …`). Never quietly present an unverified claim as verified, and never drop a good idea silently to keep the batch looking clean.
5. **Flag decay.** Anything news-pegged — and any live pricing, valuation, or "first company to" figure anywhere — gets a re-check-at-produce-time note.

## Stage 7 — Write the file

Write to `ideas/VIDEO_IDEAS_<YYYY-MM-DD>.md` (today's date). **Never overwrite an existing bank** — each run is a new dated file, so prior batches stay readable and the Stage 3 glob keeps picking them all up. If a bank already exists for today, add a numeric suffix such as `ideas/VIDEO_IDEAS_<YYYY-MM-DD>_2.md`.

Structure:

1. **Header** — how it was generated (metrics and limits used, DB tables queried, date), and the explicit dedup list from Stage 3.
2. **"What the analytics actually say"** — the top-performer table (views / engagement / saved / comments / shares) and the three Stage 2 findings. This is why the batch looks the way it does; a reader must be able to check the reasoning.
3. **One section per series** — heading `## <series-slug> — <Series Name> (<count>)`, its pattern restated in one italic line, then the numbered ideas. Each idea is a bolded hook, a paragraph of angle and detail, and a `- **Source:** [title](url)` line where the series requires one. `/produce-script` resolves against exactly this shape — it reads the series off the heading and the source off that line — so keep the slug in the heading and the format steady.
4. **Recommended production order** — the top ~5 across all series, ranked, each with a one-line reason. Freshness-sensitive ideas rank higher; the best idea in the weakest series does not.
5. **Footer** — total count, and a plain statement of which sections are source-verified, which are concept picks, and which individual ideas carry an unverified flag.

## Stage 8 — Persist and deliver the batch

After writing the Markdown bank, create a temporary JSON payload and persist it before reporting success. Every final idea must have one object; use an empty `sources` list only for a genuine concept or user-authored hot take. `slug` is a stable, lowercase, hyphen-separated description of the underlying topic — not a reworded hook — because it is the cross-run dedupe key.

```json
{
  "batch_id": "ideas-<YYYY-MM-DD[-N]>",
  "generated_at": "<UTC ISO-8601 timestamp>",
  "bank_path": "ideas/VIDEO_IDEAS_<YYYY-MM-DD>.md",
  "ideas": [
    {
      "series": "<series-slug>",
      "slug": "stable-topic-slug",
      "hook": "The exact hook from the Markdown bank",
      "angle": "What the video has to explain",
      "why": "Why this fits a real top performer",
      "intent": "share",
      "notes": "Optional production caveat",
      "sources": [
        {
          "title": "Verified article title",
          "url": "https://…",
          "publication": "Publication or company",
          "published_date": "YYYY-MM-DD",
          "article_id": "optional scraped DB ID"
        }
      ]
    }
  ]
}
```

Use the bank filename's date and optional numeric suffix in `batch_id`: for example, `VIDEO_IDEAS_2026-08-24_2.md` uses `ideas-2026-08-24-2`. Write the payload to a temporary JSON file, then run:

```bash
.venv/bin/python scrape/ideas.py import /tmp/video-ideas-<YYYY-MM-DD>.json --send
```

This sends one grouped digest, then an individual **Keep/Delete** approval card for every new idea, then one supporting-article link per unique source URL. Keep marks the idea `viewed` and, when it came from a scraped table, marks its matching source article viewed too; Delete marks the idea `rejected` and adds its topic to the permanent reject set. The command is retry-safe: rerunning the same payload sends only messages that were not successfully delivered.

## Final Output

Report to the user:

- Metrics and limits pulled, and how many posts fed the analysis
- The three Stage 2 findings, in 2–3 lines — the winning series, the share/save split, the weak tail
- File written, and the idea count per series
- The recommended top ~5, with one line each
- **Every flag, stated plainly:** unverified figures, ideas that overlap an existing bank entry (and which one to drop), companies already used recently, handling sensitivities, and anything that will decay before it ships
- Whether anything was deliberately excluded and why (rejected topics, vault collisions)
- SQLite and Telegram delivery results: batch ID, ideas newly persisted, digest/card/source-link counts, and any failed delivery that needs a retry
