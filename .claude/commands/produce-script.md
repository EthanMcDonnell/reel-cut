---
name: produce-script
description: Produce a single video script from a user-supplied prompt (URL, phrase, DB article ID/title, or Obsidian video idea reference)
tools: Read, Glob, Edit, Bash, WebFetch, WebSearch, Agent
model: opus
permissionMode: default
---
Produces a complete, validated video script from a user-supplied prompt. The prompt may be a URL (engineering blog post, article), a phrase or topic idea, a reference to an article in `scrape/db/`, or a reference to an existing file in the Obsidian Video Ideas folder (`{VAULT_VIDEO_IDEAS}`).

**Paths:** `{TOKEN}` references below are machine-specific absolute paths defined in [glossary.md](glossary.md) — resolve each to its value before running. Repo-relative paths (`scrape/…`, `assets/…`, `.claude/…`) are written inline as-is.

## DB Access

Articles and rejected topics are stored in `scrape/db/influencer.db` (SQLite). Use the query CLI via Bash:

- List tbbt articles: `.venv/bin/python scrape/query.py articles tbbt --limit 10 --tier passing --status viewed`
- List updates articles: `.venv/bin/python scrape/query.py articles updates --limit 5 --status viewed`
- Search by keyword: `.venv/bin/python scrape/query.py articles tbbt --search "keyword"`
- Mark as viewed: `.venv/bin/python scrape/query.py mark-viewed <series> <url>`
- Mark as done: `.venv/bin/python scrape/query.py mark-done <series> <url>`
- Check rejected topics: `.venv/bin/python scrape/query.py rejected --series <series>`

All commands output JSON. Run from the project root (`{PROJECT_ROOT}`).

## Stage 0 — Resolve Prompt

The user's prompt is: `$ARGUMENTS`

Determine the prompt type and resolve it to a `topic_package`. Try each check in order:

### 1. If the prompt looks like a URL

- Fetch the article content using the Bash tool:

  ```bash
  .venv/bin/python scrape/single_scrape.py --json "<URL>"
  ```
- This uses the correct fetch method (rss/scrape/playwright/reddit) based on the source config.1

### 2. If the prompt looks like a DB reference (article ID, title fragment, or `db:<keyword>`)

- Search both series tables using the Bash tool:
  - `.venv/bin/python scrape/query.py articles tbbt --search "<keyword>"`
  - `.venv/bin/python scrape/query.py articles updates --search "<keyword>"`
- Match against `id` (exact) or `title` (case-insensitive substring) across both results.
- If multiple matches, pick the one with the highest `relevance_score`. If scores are tied, prefer the most recent `published_date`.
- Use the matched article's `url`, `title`, `description`, and `company` to build the research base.
- Fetch the article URL for full content using the Bash tool:

  ```bash
  .venv/bin/python scrape/single_scrape.py --json "<matched_url>"
  ```

- **Mark as read:** `.venv/bin/python scrape/query.py mark-done <series> "<url>"`

### 3. If the prompt references a file (path, filename, or Obsidian note title)

- Search for a matching `.md` file in `{VAULT_VIDEO_IDEAS}` using Glob.
- Read the matched file. Extract topic, angle, and any URLs listed in the file.
- If URLs are present, fetch the first one for additional research.
- Set `series` to `misc`.


### Reddit — Linked Article Fetch

After fetching a Reddit article, scan `content` and `description` for external URLs and fetch each one via `single_scrape.py --json`. Append results to `FULL_CONTENT`. If any fetch fails or returns empty content, abort: "Failed to fetch linked article: `<url>`."

### Source Access Check

If the primary source returned an error or empty content, stop: "⚠️ Couldn't fetch `<url>` directly — research is from search snippets only. Paste the article text to continue, or type 'proceed' to write from secondary sources."

We then want to collate all information as well as provide some summarisation and insight for future steps: what are the key points across sources that could be used. Mine two kinds of raw material, because a video needs both a reason to stop and a reason to stay:

- **Problem side** — the single most surprising or counterintuitive fact across the sources, and the assumption a viewer probably holds that this fact overturns.
- **Solution side** — *how* it was actually done: the specific methods, the core mechanism, the tradeoff, and any reversal or irony in the approach (e.g. the fix reused the very thing that caused the problem). This is what the video pays off with, and it is what the spine stage below draws its payoff from. Do not stop at the surprising fact; the interesting part is usually in the solution.

**Story gate.** Before continuing, judge whether the sources actually contain a video-worthy story: a non-obvious mechanism, a surprising cause or reversal, and a concrete outcome. If the material is thin (an announcement, or a plain "we improved X by N%" with no mechanism or twist), say so plainly and record `STORY_STRENGTH: thin` with the reason — do not manufacture drama the sources don't support. A thin gate isn't an automatic stop: surface it and let the user decide whether to proceed, pick a different source, or reframe.

Build the following `topic_package` once resolved:

```
SERIES: <tbbt | updates | tech-in-one-breathe | interesting-tech | ai-fundamentals | misc>
MOST_SURPRISING_FACT: <the single most counterintuitive fact across the sources, and the assumption the viewer probably holds that it overturns>
HOW_IT_WAS_SOLVED: <the solution-side material — the methods, the core mechanism, the tradeoff, and any reversal/irony in how it was done>
STORY_STRENGTH: <strong | thin — the story-gate judgement in one line, and why>

(one block per source)
TOPIC: <concise topic title>
SOURCE_URLS: <comma-separated list of source URLs, or "none">
FULL_CONTENT: <complete raw article content>
KEY_DISCUSSION_POINTS: <summarise/provide key talking points>
```

If no usable content can be resolved from the prompt, abort with: "Could not resolve prompt to a scriptable topic — please provide a URL or more specific phrase."

### Load the series profile

Once `SERIES` is resolved (and it is not `misc`), **read `series/<SERIES>.md`** — that file is the source of truth for this series' identity, voice profile (register, target length, CTA), and best hooks. It drives Stage 0.5 (spine), Stage 1 (hooks), and Stage 3 (voice). The canonical slugs are `tbbt`, `updates`, `tech-in-one-breathe`, `interesting-tech`, `ai-fundamentals`; `misc` has no file and uses the `scripts` skill's default voice.

## Stage 0.5 — Script Spine

The **spine** is what the video is actually about: the crux mechanism it explains and the reframe it lands at the end. It is the single biggest driver of whether the video works, because it decides what the viewer *stays* for. It is not the hook and not a framing — it is the story the body tells. Build it from the `topic_package`, drawing the payoff from `HOW_IT_WAS_SOLVED`, not just the surprising fact.

1. **Find the strongest spine.** Identify the best video the sources support, as three parts:
   - **Crux** — the one mechanism worth explaining.
   - **Payoff** — how it actually works: the methods, the tradeoff, the *how they solved it*. Ground this in `HOW_IT_WAS_SOLVED` so the body has a real payoff, not a problem-then-fix summary.
   - **Turn** — the reframe that recasts the whole thing at the end.
2. **Only fork when the story genuinely diverges.** Most articles have one clearly-best spine — when they do, proceed with it and just tell the user what it is; do not force a choice. Generate alternate spines **only** where the sources support genuinely distinct videos: a different crux, a different payoff, and a different turn — not reworded framings of the same story.
3. **Select only when real forks exist.** If two or more genuinely distinct spines exist, present them and ask the user to choose; each option states its crux, payoff, and turn (the flow of the video) so the choice is made on the story, not a label. If one spine dominates, skip the question and continue.

The chosen `SPINE` drives Stage 1 (hooks) and Stage 3 (script). If the story gate recorded `STORY_STRENGTH: thin`, restate that here — the spine can only be as strong as the sources allow, so flag the weakness rather than overselling it.

## Stage 1 — Hook Generation

Invoke the `hooks` skill and apply its rules, patterns, and quality test. Better hooks come from breadth then ruthless selection, not from writing three and hoping one lands.

0. **Ground in proven hooks.** Pass the resolved `SERIES` to the `hooks` skill — it reads the series file's **Best Hooks** and `.claude/voice/proven-hooks.md` (the user's top hooks ranked by real engagement) and biases toward what wins on this channel. Your job here is just to give it the slug; bias generation toward those proven patterns while still generating wide.

1. **Generate wide.** Write 8–10 candidate hooks that captivate and funnel into the crux of the chosen `SPINE`. The hook is the on-ramp, not the definition of the video: it grabs attention and links into the story the body pays off, so it does not have to carry the whole video by itself. Span at least 3 of the skill's distinct patterns — do not return rewordings of a single idea. For each, note its `PATTERN` and the single raw element it leads with (the name, number, stat, or reversal, seeded from `MOST_SURPRISING_FACT`).
2. **Score each.** Run the skill's 3-check quality test (scroll / HOW / promise) on every candidate and judge the strength of its lead element. Drop any that fail a check or lead with a weak element.
3. **Critique and rewrite.** Take the ~5 strongest survivors. For each, name its single weakest element (buried lead, soft claim, too long, no open loop) and rewrite it once to fix exactly that. Keep the stronger version.
4. **Shortlist distinct winners.** Select the top **N hooks (default 3)**, each using a *different pattern or lead element* so the resulting videos test genuinely different strategies, not phrasings. Store them ordered best-first as `HOOK_1 … HOOK_N`, each with a `PATTERN` and `TEXT` field.

## Stage 2 — Hook Approval

Present the shortlist: for each hook show its `TEXT`, its `PATTERN`, and one line on why it stops the scroll. Ask the user to confirm the set, swap in a runner-up, edit wording, or change N. The confirmed, ordered set (best first) is the `HOOK_SET` recorded into the script in Stage 3 — you are keeping **all** of them, not picking one.

## Stage 3 — Script Writing

Invoke the `scripts` skill and `stop-slop` skill, use the full `topic_package`, the chosen `SPINE`, and the confirmed `HOOK_SET` to create a captivating short form content script for platforms like Instagram Reels. Write the body to the `SPINE`: explain its crux, deliver the payoff (the *how*, drawn from `HOW_IT_WAS_SOLVED`), and land its turn. A body that only states the problem and names the fix has failed the spine — the payoff is the video. Pass the resolved `SERIES` to the `scripts` skill — it applies the series file's voice profile (register, target length, CTA) and layers the user's delivery voice from `.claude/voice/voice-profile.md` on top; for `misc` it uses its default voice.

**Write every hook from `HOOK_SET` into the script.** You record all of them in one take and split them into separate videos later, so the `**HOOK**` section holds the full set, numbered and ordered best-first, one hook per line:

```
**HOOK**
HOOK 1: <HOOK_1 text>
HOOK 2: <HOOK_2 text>
HOOK 3: <HOOK_3 text>
**SCRIPT**
...
```

Each hook must independently lead into the **same** body, so any split (hook N + the body) stands alone as a complete video. Keep the "why should I care" stakes sentence at the **start of `**SCRIPT**`**, not attached to any single hook, so it is shared across every variant. No blank lines.

For every claim, stat, or quote that will appear in the script:

1. **Locate it verbatim** in `FULL_CONTENT`. Drop any quote that doesn't appear there.
2. **Confirm the correct subject.** Ask: who said this — the document, a person quoted in it, or a secondary source? A quote from someone's speech is not the document's claim. A fact from source B is not from source A. Never collapse two sources into one sentence.
3. **Check the attribution in the script matches the actual speaker/document.** If the encyclical says X and a speaker says Y, they must be attributed separately. "The document points out..." is only valid if the document is the actual source of that sentence.
4. **Articles often contain third-party quotes.** A blog post may include testimonials, customer quotes, or researcher statements. A claim inside a quoted block belongs to the quoted person — not the publication. Do not write "[Company] says X" if X came from a quoted third party inside their article.

Any claim that cannot be traced to a specific sentence in `FULL_CONTENT` is cut, not paraphrased from memory.

## Stage 3.5 — Save & QC Gate
After the script is written, save it:

1. Save to `{VAULT_VIDEOS_TODO}`
2. Use kebab-case filename describing the topic (e.g. `netflix-cdn-architecture.md`)
3. No empty lines in the saved file
4. Ignore any other existing `.md` files in the `Videos/` folder — do not read, reference, or modify them
5. **Run the deterministic QC linter and block on it.** It catches mechanical defects (em dashes, banned throat-clearing openers, missing apostrophes, format and blank-line violations) that self-review keeps missing:

   ```bash
   .venv/bin/python .claude/skills/scripts/scripts/lint_script.py "<saved_file_path>"
   ```

   If it exits non-zero, fix every reported blocking error, re-save, and re-run until it passes. Warnings are advisory — review them, but they don't block. The word-count warning may fire because the extra hooks count toward content length; that is expected here (the hooks get split across separate videos), so judge the body's length on its own. Do not continue to Stage 4 until the linter passes.

Wait for the saved file path before continuing.

**Mark the videos ideas `status:` frontmatter field:** update it from `new` to `done` using the Edit tool.

## Stage 3.6 — Viewer Resources & Comment CTA

The goal: give the viewer a reason to **comment**, and a payoff worth commenting for. Comments are the strongest algorithmic signal on Reels/Shorts, and the standard "comment a keyword and I'll send the link" mechanic only works if the thing you're sending is genuinely worth getting.

### Step 3.6.1 — Brainstorm topic-specific resource ideas

Think about what *this specific audience* (developers/builders watching a `SERIES` video on `TOPIC`) would actually want to do *next* after the video lands the `SPINE`. **Anchor on what the article itself names** — the specific technology, system, or company it's about, the source's own deeper write-ups, talks, or repos, or the source article itself. Reach for a generic third-party tool only when nothing article-specific fits; a random tool with no direct tie to what the video explained is the weakest option. Generate **4–6 candidate resources**, pulling from different categories so they diverge — don't return six of the same kind:

- **Steal-this asset** — a free template, cheatsheet, boilerplate, config, checklist, or diagram the viewer can copy and use today. Highest comment-bait pull ("I want that").
- **Hands-on / try-it-yourself** — a playground, sandbox, interactive demo, or online tool that lets them *experience* the concept from the video themselves.
- **The real source code** — the open-source repo, the actual implementation, or the file that does the thing discussed. Developers love seeing the real code.
- **Go-deeper canonical** — the seminal paper, RFC, official docs, design doc, or conference talk that goes far past the article's depth.
- **Build-it tutorial** — a concrete step-by-step guide to recreate what the video showed.
- **Adjacent tool / alternative** — a tool the viewer can adopt to solve their own version of this problem now. Use sparingly, and only when it's tied to the article's topic.

For each candidate, name the category, a one-line "why a viewer wants this," and the URL.

### Step 3.6.2 — Verify every link is real

**Do not invent or guess URLs.** For each candidate, find the real resource with `WebSearch`, then confirm the URL resolves with `WebFetch` (or `single_scrape.py --json`). Drop any candidate whose URL can't be verified. A fabricated link is worse than one fewer resource — it breaks trust the moment a viewer clicks.

### Step 3.6.3 — Pick the lead magnet and write the CTA

From the verified candidates, select the **single best lead magnet**: the one with the strongest "I want that" pull *and* the tightest tie to the article's actual topic (a steal-this asset, the source's own deeper material, or the article itself). Then write a comment-bait CTA:

- A short, memorable, topic-tied **keyword** (one word, uppercase, e.g. `CACHE`, `SCALE`, `RAFT`).
- A one-line CTA the creator can pin or say: `Comment "<KEYWORD>" and I'll send you <what the resource is>.`

### Step 3.6.4 — Append to the saved script file

Write the CTA and the resources in **two** places, **no blank lines anywhere** (the linter blocks on them):

1. Insert a `**CTA**` heading and the CTA line immediately **after** the `**CONCLUSION**` section and **before** `**REFERENCES:**`. This line is spoken, so it is prose-checked — keep it free of em dashes:

```
**CTA**
Comment "<KEYWORD>" and I'll send you <resource>.
```

2. Append the resources block to the **end** of the file, **after** the `**REFERENCES:**` section (lines after that header are exempt from the linter's prose checks, so the ` — ` separators are fine there):

```
**VIEWER RESOURCES:**
LEAD MAGNET: <category> — <name> — <url>
<category> — <name> — <url>
<category> — <name> — <url>
<category> — <name> — <url>
```

Then re-run the linter and confirm it still passes:

```bash
.venv/bin/python .claude/skills/scripts/scripts/lint_script.py "<saved_file_path>"
```

If it reports a blank-line error, the resources block introduced an empty line — remove it and re-run until clean.

## Stage 4 — Source Screenshots for Video
### Step 4.1: Choose what to back with on-screen evidence

Screenshots exist to kill doubt: when the script makes a claim a viewer can't quite believe, a highlighted source line on screen proves you didn't invent it. So **start from the claims, not from the article** — don't go hunting for quotable phrases, work backwards from what the viewer disbelieves.

**1. List the script's checkable claims.** Read the delivered script and note every line a skeptical viewer would stop on: the surprising statistic, the bold assertion, the "that can't be real" number, the direct quote, the dollar / date / percentage figure. Ignore setup, transitions, opinion, and anything unfalsifiable — those need no proof.

**2. Rank, then cap.** Order those claims by **how much the viewer doubts it × how central it is to the video**. Keep the strongest from the top down — **up to 6 per URL, and fewer is better than padding with weak ones**. Drop a claim when either: it's only mildly doubted or peripheral to the story, or the source doesn't actually state it. A claim with no verbatim backing in `FULL_CONTENT` gets **no screenshot** — flag it as unsupported (Step 4.3 / Final Output) rather than forcing a loose match.

**3. For each kept claim, grab the tightest proof.** Find the phrase in the article that **contains the proof itself** — the number, the name, the figure — plus only enough surrounding words to read as a clause. Prefer the **smallest verbatim span that still proves the claim** over the surrounding topic sentence: a tight highlight on `reclaimed millions from 47% idle capacity` beats a wide highlight on a three-clause sentence that merely mentions it. Tighter spans read as stronger evidence and crop cleaner on screen.

For each kept claim, write **four fields**:

- **`article_snippet`** — the proof phrase, **verbatim** from `FULL_CONTENT` (copy it, don't paraphrase, or it won't be found). Roughly **40–200 characters**: long enough to read as a standalone clause, short enough to stay centred on the proof token. Maps to exactly one script sentence.
- **`script_context`** — the **exact verbatim script line** this screenshot supports, copied word-for-word from the script. This is the line the screenshot is shown under in the video.
- **`trigger_show_word`** — a short verbatim anchor (one word or a 2–4 word phrase) **from inside `script_context`** marking where in the spoken line the screenshot should *appear*. Pick the word at the moment the claim starts landing — usually the first word of the clause that states the claim.
- **`trigger_go_away_word`** — a short verbatim anchor from inside `script_context` marking where the screenshot should *disappear* — usually the last word of the claim, before the script moves on. Choose anchors that are unique within the line so they can't match the wrong spot.

The trigger anchors let produce-video bound the on-screen window precisely instead of guessing the sentence span. They're optional refinements — if a clean anchor isn't obvious, leave them as `""` and produce-video falls back to spanning the whole line.

### Step 4.2: Run the screenshot tool

For each source URL, run:

```bash
.venv/bin/python scrape/screenshot.py \
  --url "<source_url>" \
  --output-dir "assets/<video-slug>/" \
  --snippets '[{"article_snippet": "verbatim phrase 1", "script_context": "exact script line", "trigger_show_word": "anchor in", "trigger_go_away_word": "the line"}, {"article_snippet": "verbatim phrase 2", "script_context": "...", "trigger_show_word": "...", "trigger_go_away_word": "..."}, ...]'
```

Where `<video-slug>` matches the saved script filename (without `.md`).

If a source URL is a Reddit post, use the linked article URL instead (already fetched in Stage 0).

### Step 4.3: Check what was actually captured

The JSON result includes a `snippets` array — one entry per requested snippet with `found`, `match_type` (`exact` | `fuzzy` | `none`), `confidence`, `highlight` (`range` | `fuzzy_range` | `whole_block`), and (on a miss) `reason`. The same misses are also recorded under `missed` in `manifest.json`.

- **Report every snippet with `found: false`** and its `reason`. That claim will have **no on-screen evidence** in the video — either revise the `article_snippet` to match the article's wording verbatim and re-run for that URL, or call the claim out as unsupported.
- **Flag any `match_type: "fuzzy"` match with `confidence` below 0.8** — find located an approximate block rather than the exact phrase, so it's worth an eyeball before relying on it.
- **Flag any `highlight: "whole_block"`** — the exact phrase couldn't be pinpointed so the whole paragraph was coloured; the screenshot shows a wall of highlight rather than the specific proof. Worth eyeballing, and often fixed by trimming the `article_snippet` to a span that matches the live page verbatim and re-running.
- If `skipped` is non-null, the whole page failed to load — report that reason; no screenshots were captured for that URL.

## Stage 4b — Source Figures (article charts & diagrams)

Separate from text screenshots (which crop article *prose* to prove a claim), figures are
explanatory images the article already contains — **charts** and **diagrams** — reused as
on-screen overlays. A chart is the visual proof of a shocking number; a diagram shows how a
system works. This stage is deterministic-harvest-then-you-look: `figure_finder.py` finds and
filters candidates; **you** read the images and pick the good ones.

### Step 4b.1: Harvest candidates

For each source URL, run:

```bash
.venv/bin/python scrape/figure_finder.py --url "<source_url>" --output-dir "assets/<video-slug>/"
```

It writes candidate images to `assets/<video-slug>/figures/` and metadata to
`assets/<video-slug>/figure_candidates.json` (each entry: `file`, `figcaption`, `alt`,
`heading`, `surrounding_text`, `format`, `width`/`height`, `score`). The deterministic prefilter
has already dropped icons/avatars/logos/ads/banners/hero images; what remains is worth a look.
If `candidates` is empty, there were no usable figures — skip to Final Output.

### Step 4b.2: Look at each candidate and judge it

**Use the Read tool on each `figures/figure-NN.*` image** and judge it, grounded by its
`figcaption`/`alt`/`surrounding_text` from the candidates JSON:

- **`is_usable`** — an informative chart or diagram, not a photo/headshot/decorative/logo. Drop
  anything that isn't.
- **`kind`** — `chart` (bars/curves/comparisons of numbers) or `diagram` (architecture / flow /
  sequence / how-it-works). v1 uses only these two; drop tables, UI screenshots, and photos.
- **`legibility`** — **would it read on a 9:16 phone screen?** A dense diagram with tiny text or
  a busy multi-panel chart is a drop — an unreadable figure hurts more than none.

### Step 4b.3: Match to a script beat and select

Keep the ones that support a specific beat, matched by kind:

- **`chart` → the stat beat** whose exact number the chart visualises (highest priority — it
  proves the "shocking number" a hook makes).
- **`diagram` → the "here's how it works" line** describing that system/flow.

**Cap at ≤3 figures per video**, and drop redundant ones (two figures of the same system → keep
the more legible / higher-resolution). Figures hold longer and take more screen space than a
text pop, so fewer-and-stronger wins.

### Step 4b.4: Write `figures.json`

Write the selected figures to `assets/<video-slug>/figures.json` (a JSON list). This is the
figure equivalent of the screenshot manifest — it records the *selection* and *anchors*;
`produce-video` computes the actual timings later. Each entry:

```json
[
  {
    "file": "figures/figure-01.png",
    "kind": "diagram",
    "caption": "one line: what the figure shows",
    "script_context": "the exact verbatim script line this figure is shown under",
    "trigger_show_word": "anchor word in that line where it appears",
    "trigger_go_away_word": "anchor word where it disappears",
    "source_url": "<source_url>"
  }
]
```

- `script_context` — copy the supported script line **verbatim** from the script.
- `trigger_show_word` / `trigger_go_away_word` — short verbatim anchors from **inside**
  `script_context`, marking where the figure appears and disappears. Same rules as screenshot
  triggers; leave `""` if no clean anchor and produce-video spans the whole line.

## Final Output

Report to the user:

- Prompt resolved as: [URL / file reference / phrase] → [TOPIC] ([SERIES])
- Script saved to: [file path]
- Viewer resources: the comment CTA line (keyword + lead magnet), and the full verified resource list appended to the script file
- Screenshots saved to: `assets/<slug>/`
- Screenshot results: how many captured (with the exact/fuzzy breakdown), and explicitly list any snippets that were **not found** so the user knows which claims lack on-screen evidence
- Figures: how many charts/diagrams were selected (with `kind` and the beat each supports), the count of candidates harvested vs. kept, and where they were saved (`assets/<slug>/figures/`, `figures.json`)
- Unsupported claims: any checkable claim you dropped at selection time because the source didn't state it verbatim (Step 4.1.2) — the user may want to re-source or soften it
- Any warnings (near-tie runner-up available, low-confidence fuzzy matches, skipped screenshots, etc.)
