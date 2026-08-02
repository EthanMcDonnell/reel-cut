---
name: video-ideas
description: Generate a fresh, source-verified batch of video ideas across the six series, driven by live social-cockpit analytics and deduped against every existing idea bank.
tools: Read, Glob, Grep, Write, Bash, WebFetch, WebSearch
model: opus
permissionMode: default
---
Produce a new dated batch of video ideas, grounded in what is **actually performing** on the
channel right now rather than in what seems interesting. Each idea is a **hook** in its series'
winning pattern, plus the **angle** it has to deliver, plus (where the series requires one) a
**verified source**.

This command does not write scripts. Its output is a dated idea bank at the **repo root** (Stage 7), which is where `/produce-script` looks when a prompt names an idea rather than a URL. Keep the bank at the root and keep the `## <series-slug> — <Series Name>` headings intact: `/produce-script` reads the series straight off the heading of the entry it matches.

**Paths:** `{TOKEN}` references are machine-specific paths defined in [glossary.md](glossary.md) —
resolve each before running. Repo-relative paths (`scrape/…`, `series/…`, `.claude/…`) are
written inline. Run all `.venv/bin/…` commands from `{PROJECT_ROOT}`.

The user's prompt (optional) is: `$ARGUMENTS` — it may narrow the run. Honour any of:
- **a series slug** (`tbbt`, `updates`, `tech-in-one-breathe`, `interesting-tech`, `ai-fundamentals`, `hot-takes`) → only that series
- **a count** ("5 per series", "20 ideas") → override the defaults in Stage 5
- **a focus** ("only shareable", "lean into ai-fundamentals", "no news") → weight selection accordingly
Default with no arguments: **all six series, ~5–6 ideas each**.

---

## Stage 1 — Pull the analytics

Never generate ideas from memory of what did well. Pull it:

```bash
.venv/bin/python scrape/cockpit.py --metric engagement --limit 15
.venv/bin/python scrape/cockpit.py --metric views --limit 15
.venv/bin/python scrape/cockpit.py --metric saved --limit 12
```

Three metrics, because each surfaces a different winner: `engagement` finds the overall best,
`views` finds reach winners that engagement misses, `saved` finds the explainers people keep.
Each command prints a JSON array, best-first, with `metricValue`, `insights` (reach / views /
likes / comments / shares / saved / watch-time), `caption`, `permalink`, `durationSec`, and the
full `transcript`.

If a command errors with "could not reach cockpit", tell the user to start the social-cockpit
server (`npm run dev` in `{SOCIAL_COCKPIT_DIR}`, serving `{COCKPIT_URL}`) and **stop**. Do not
fabricate a batch from remembered performance — the whole point of this command is that
selection is driven by live numbers.

## Stage 2 — Derive what is winning (re-derive; do not assume)

Read the pulled data and answer three questions in writing. These drive every selection
downstream, so be concrete and quantified.

1. **Which series is over-performing, and by how much?** Map each top performer to a series
   (`tbbt`, `updates`, `tech-in-one-breathe`, `interesting-tech`, `ai-fundamentals`, `hot-takes`)
   from its caption and transcript. A series carrying an outlier deserves disproportionate ideas even in
   an even-spread run.
2. **Which shape drives which action?** Compare `shares` against `saved` per video. They are
   different intents — breakages, price hikes, and "this affects you" news get *shared*;
   mechanism explainers get *saved*. Tag each idea you later write with `[share]` or `[save]`
   where its shape clearly favours one.
3. **What is the weak tail telling you?** Look at the bottom of the ranking, not just the top.
   The lowest performers usually share a shape, and that shape is the thing to stop making.

**Calibration note (2026-07-30 — re-derive, don't copy):** on that pull, `ai-fundamentals`
carried a large outlier (Claude usage limits: 122k views, ~7× the saves and ~10× the comments of
anything else); shares split cleanly from saves (Copilot price hike 2461 shares vs. 222 saves);
and the weak tail was entirely company-*origins* content (React origins 5k, lava lamps 7k) —
a company doing something absurd or expensive *now* beat a company's backstory. Treat this as a
prior to check against fresh numbers, never as a conclusion to restate.

## Stage 3 — Build the dedup set

An idea that repeats something shipped, queued, or already proposed is worthless. Before
generating anything, assemble the full exclusion list:

- **Shipped / produced:** `ls assets/archive/` and `ls output/` — every slug there is done.
- **Existing idea banks:** read every `VIDEO_IDEAS*.md` and `*_VIDEO_IDEA*.md` at the repo root
  (`Glob` for `*VIDEO_IDEA*.md` — the set grows each time this command runs).
- **Series files:** read `series/<slug>.md` for each in-scope series — the **Queued** and
  **Best Hooks** sections list both what is planned and what already shipped.
- **Obsidian vault:** `Glob` `{VAULT_VIDEO_IDEAS}` and `{VAULT_VIDEOS_TODO}` for `*.md`. The
  vault holds a large unproduced backlog — much of what looks "missing" from a series is really
  already queued there.
- **Rejected topics:** `.venv/bin/python scrape/query.py rejected --series <series>` — topics
  previously ruled out. Do not re-propose them.

Record the exclusion set. Every idea in the final file must clear it.

## Stage 4 — Harvest source material per series

The six series have different sourcing rules — follow each series file, don't apply one
standard to all.

### tbbt and updates — the article DB

These two have a real feed. Pull unread candidates:

```bash
.venv/bin/python scrape/query.py articles tbbt --status new --limit 200
.venv/bin/python scrape/query.py articles updates --status new --limit 200
```

Skim titles first (`jq -r '.[] | "\(.published_date[0:10]) | \(.company) | \(.title)"'` keeps it
readable), shortlist the ones with a real story, then **scrape each shortlisted article in full**:

```bash
.venv/bin/python scrape/single_scrape.py "<url>"
```

Prefer, in this order: a **surprising mechanism or reversal**, a **shocking concrete number**, a
**visible breakage or incident report**, a **counter-intuitive engineering decision**. Skip
product announcements, "we improved X by N%" with no mechanism, and marketing posts — a large
share of the feed is these.

`updates` also decays fast, so supplement the DB with `WebSearch` for anything breaking in the
last 1–2 weeks that the feed missed.

### interesting-tech — verified incidents, and mind the rut

No DB. The bar is a **real, concrete, named artifact or incident** that survives a thumbnail —
never an abstract concept. Verify each with `WebSearch` and, where possible, a primary source.

Check the existing banks before generating: this series drifts hard toward malware/exploits.
If the existing pool is already malware-heavy, deliberately branch — aviation, finance, space
hardware, infrastructure, legal, cryptography, detective stories with no attacker at all.

### tech-in-one-breathe and ai-fundamentals — concept picks

No source DB **by design** (per their series files) — these are concepts, not news, so no
citation is expected. Two rules instead:

- Dedup hard. Both series have long queued backlogs in the vault and in prior banks; most
  "obvious" picks are already taken.
- Prefer concepts that are the **mechanism behind a `tbbt` idea in the same batch** — they
  double as companion pieces and cost nothing extra to find.

For `ai-fundamentals` specifically: the series file allows a "confused right now" flavour, and
that is where the channel's top performer came from. Pegging an idea to something published in
the last two weeks is unusual for this series and worth doing when the peg is real.

### hot-takes — mined from the user, never invented

No DB and no research: the material is the user's own opinions, and **you cannot generate those
for them**. Do not write a take the user has not expressed — a first-person video asserting a
belief they don't hold is the one failure mode this series cannot absorb.

Mine candidates instead, from two places, and label where each came from:

- **Their own transcripts** (already pulled in Stage 1). Opinions get voiced in passing inside
  other videos and buried there — e.g. "I spend days on some skills only to find out using no
  skill at all provided better outputs", said as tip #1 in a listicle. A take the user has
  already stated on camera is proven to be theirs; quote it back verbatim as the candidate.
- **The `Queued` list** in `series/hot-takes.md`.

Present every hot-takes idea as a **candidate for the user to confirm, edit, or reject**, with
the quote or queue entry it came from — not as a finished idea. Flag any where you can see the
opposing case is weak: per the series file, an uncontested take is a recommendation and draws no
comments.

## Stage 5 — Generate and select

For each in-scope series, generate **wide then cut** — do not write five ideas and keep five.
Aim for ~2× the target, then drop everything that fails the checks below. Default target is
**5–6 ideas per series**, adjusted by `$ARGUMENTS`.

Write each idea in the series' own winning hook pattern, taken from `series/<slug>.md` **Best
Hooks** and `.claude/voice/proven-hooks.md` — not a generic phrasing. Each idea needs:

- **The hook**, bolded, in the series' pattern.
- **`[share]` / `[save]` tag** where the shape clearly favours one (from Stage 2).
- **The angle** — what the video actually has to deliver. Concrete: the mechanism, the numbers,
  the reversal. Quote real figures from the scraped article, never remembered ones.
- **The source**, linked, with publication and date — for `tbbt`, `updates`, and
  `interesting-tech`.
- **A "why" line** tying it to a specific top performer from Stage 1, where the link is real.
- **Notes** for anything the user must know: adjacency to an existing idea, a company already
  used, a handling sensitivity, a figure that needs re-checking at produce time.

Drop an idea if any of these fail:

- It collides with the Stage 3 exclusion set.
- Its source doesn't actually support the hook's claim (see Stage 6).
- It's a company-origins story, or any other shape the Stage 2 weak tail flagged.
- It's a reworded version of another idea in the same batch.

## Stage 6 — The verification gate

This is the stage that makes the output trustworthy. Apply it before writing the file.

1. **Full text, not the blurb.** Every `tbbt`/`updates` fact must come from the scraped article
   body. An RSS `description` is not verification — it is frequently a marketing summary that
   contradicts the post.
2. **Every number is quoted, not recalled.** If you cannot point at the sentence in the scraped
   content, the number does not go in the file.
3. **Attribute correctly.** A claim inside a quote block belongs to the person quoted, not the
   publication. A fact from source B is not from source A.
4. **Say so when you couldn't verify.** If an idea is worth keeping but a figure went
   unconfirmed, keep it and **mark it explicitly** (`**Verify before producing:** …`). Never
   quietly present an unverified claim as verified, and never drop a good idea silently to keep
   the batch looking clean.
5. **Flag decay.** Anything in `updates` — and any live pricing, valuation, or "first company
   to" figure anywhere — gets a re-check-at-produce-time note.

## Stage 7 — Write the file

Write to `VIDEO_IDEAS_<YYYY-MM-DD>.md` at the repo root (today's date). **Never overwrite an
existing bank** — each run is a new dated file, so prior batches stay readable and the Stage 3
glob keeps picking them all up.

Structure:

1. **Header** — how it was generated (metrics and limits used, DB tables queried, date), and the
   explicit dedup list from Stage 3.
2. **"What the analytics actually say"** — the top-performer table (views / engagement / saved /
   comments / shares) and the three Stage 2 findings. This is why the batch looks the way it
   does; a reader must be able to check the reasoning.
3. **One section per series** — heading `## <series-slug> — <Series Name> (<count>)`, its pattern
   restated in one italic line, then the numbered ideas. Each idea is a bolded hook, a paragraph
   of angle and detail, and a `- **Source:** [title](url)` line where the series requires one.
   `/produce-script` resolves against exactly this shape — it reads the series off the heading
   and the source off that line — so keep the slug in the heading and the format steady.
4. **Recommended production order** — the top ~5 across all series, ranked, each with a
   one-line reason. Freshness-sensitive ideas rank higher; the best idea in the weakest series
   does not.
5. **Footer** — total count, and a plain statement of which sections are source-verified, which
   are concept picks, and which individual ideas carry an unverified flag.

## Final Output

Report to the user:

- Metrics and limits pulled, and how many posts fed the analysis
- The three Stage 2 findings, in 2–3 lines — the winning series, the share/save split, the weak tail
- File written, and the idea count per series
- The recommended top ~5, with one line each
- **Every flag, stated plainly:** unverified figures, ideas that overlap an existing bank entry
  (and which one to drop), companies already used recently, handling sensitivities, and anything
  that will decay before it ships
- Whether anything was deliberately excluded and why (rejected topics, vault collisions)
