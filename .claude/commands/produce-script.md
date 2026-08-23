---
name: produce-script
description: Produce a single video script from a user-supplied prompt (URL, phrase, idea-bank reference, or a bare contested claim)
---
Produces a complete, validated video script from a user-supplied prompt. The prompt may be a URL (engineering blog post, article), a phrase or topic idea, a reference to an idea in a repo-root idea bank (`*VIDEO_IDEA*.md`, written by `/video-ideas`, or the standing backlog in `VIDEO_IDEAS_BACKLOG.md`), or a bare contested claim (a `hot-takes` opinion with no source).

**Everything lives in the repo.** `/video-ideas` writes its banks at the root, Stage 0 resolves against them, and Stage 3.5 saves the script to `assets/<video-slug>/script.md` — next to that slug's screenshots, where `/prepare-video` reads it as ground truth for the transcript.

**Paths:** `{TOKEN}` references below are machine-specific absolute paths defined in [glossary.md](glossary.md) — resolve each to its value before running. Repo-relative paths (`scrape/…`, `assets/…`, `.claude/…`) are written inline as-is. Run everything from the project root (`{PROJECT_ROOT}`).

## Stage 0 — Resolve Prompt

The user's prompt is: `$ARGUMENTS`

Determine the prompt type and resolve it to **source URLs** (branches 1–2) or to no source at all (branch 3). Try each check in order; branches 1–2 both end at the shared fetch step below.

### 1. If the prompt looks like a URL

The URL is the source. Note it and go to the fetch step.

### 2. If the prompt references a video idea (a hook, a topic, an idea-bank entry, or a note title)

Idea banks live at the **repo root** — that is where `/video-ideas` writes them and where this command looks.

**First, the dated idea banks.** `Glob` `VIDEO_IDEAS_*.md` / `*_VIDEO_IDEA*.md` at the repo root and read the matches (the set grows every time `/video-ideas` runs, so search them all, newest first). A dated bank groups ideas under `## <series-slug> — <Series Name>` headings, and each idea is a numbered entry: a bolded hook, a paragraph of angle and detail, and a `- **Source:** [title](url)` line. Match the prompt against the hooks and topics, and when one entry fits:

- `SERIES` is the **enclosing heading's slug**, when the file uses them — take it from there rather than inferring. Some older one-topic banks have no series headings and instead name the series in prose; use what the file says. Judge it yourself only when nothing in the file states it.
- The entry's paragraph is the angle; carry it into `KEY_DISCUSSION_POINTS`.
- The URL on its `**Source:**` line is the source. An entry with no source line resolves to no source, and the source gate below handles it.

**Otherwise, the backlog bank.** `VIDEO_IDEAS_BACKLOG.md` at the root is an older, undated list of one-idea-per-entry notes. Match the prompt against its entries and read the one that fits. Extract topic and angle; the first URL it lists, if any, is the source (most of these entries have none, which is normal). These entries carry **no series heading**, so work out which series the idea belongs to from its subject, judging against the series identities rather than defaulting. Fall back to `misc` only when it genuinely fits no series.

### 3. If the prompt is a bare claim (an opinion with no source)

A prompt that states a contested position about how to build software — "GitHub Desktop is better than the git CLI", "long Claude skills are worse than no skill" — is a **hot take**, not a topic to research. Set `SERIES` to `hot-takes` and read `series/hot-takes.md` before going further.

There is no article to fetch, so the material has to come from the user:

1. **Ask for the mechanism.** The body of a hot take is *why the user believes it, from real use*. You cannot supply this — inventing lived experience for a first-person video is the one thing this branch must never do. Ask the user directly: what happened when they did it, what broke, what they tried instead. Keep asking until there is a concrete mechanism rather than a preference.
2. **Ask for the strongest counter-argument** and where they concede it wins. This is the user's opinion to give, not yours.

Build the `topic_package` with `SOURCE_URLS: none` and `FULL_CONTENT: none`, putting the user's own reasoning in `HOW_IT_WAS_SOLVED` and the claim in `MOST_SURPRISING_FACT`. There is nothing to fetch, so skip the fetch step below.

If the take rests on a specific fact, number, or attribution, research **that** and only that (`WebSearch` / `single_scrape.py`), and add what you verify to `FULL_CONTENT` so Stage 3 can trace it.

### Fetch the sources (branches 1–2)

Fetch each resolved URL with the Bash tool:

```bash
.venv/bin/python scrape/single_scrape.py --json "<url>"
```

This picks the right fetch method (rss/scrape/playwright/reddit) from the source config.

**Reddit — linked article fetch.** After fetching a Reddit source, scan `content` and `description` for external URLs and fetch each one the same way. Append the results to `FULL_CONTENT`. If any fetch fails or returns empty content, abort: "Failed to fetch linked article: `<url>`."

**Source access check.** If a source returned an error or empty content, stop: "⚠️ Couldn't fetch `<url>` directly — research is from search snippets only. Paste the article text to continue, or type 'proceed' to write from secondary sources."

### Mine the material (branches 1–2)

We then want to collate all information as well as provide some summarisation and insight for future steps: what are the key points across sources that could be used. Mine two kinds of raw material, because a video needs both a reason to stop and a reason to stay:

- **Problem side** — the single most surprising or counterintuitive fact across the sources, and the assumption a viewer probably holds that this fact overturns.
- **Solution side** — *how* it was actually done: the specific methods, the core mechanism, the tradeoff, and any reversal or irony in the approach (e.g. the fix reused the very thing that caused the problem). This is what the video pays off with, and it is what the spine stage below draws its payoff from. Do not stop at the surprising fact; the interesting part is usually in the solution.

### Story gate

Before continuing, judge whether there is a video here at all. The bar depends on where the material came from:

- **With sources:** the material must hold a non-obvious mechanism, a surprising cause or reversal, and a concrete outcome. Thin looks like an announcement, or a plain "we improved X by N%" with no mechanism or twist.
- **Without sources:** the claim must be genuinely contested — would a competent engineer argue the other side? Thin looks like a recommendation nobody opposes, which this channel's data says draws no comments.

Either way, say so plainly and record `STORY_STRENGTH: thin` with the reason. Do not manufacture drama the material doesn't support. A thin gate isn't an automatic stop: surface it and let the user decide whether to proceed, pick a different source, or reframe.

Build the following `topic_package` once resolved:

```
SERIES: <tbbt | updates | tech-in-one-breathe | interesting-tech | ai-fundamentals | hot-takes | misc>
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

### Source gate

`SOURCE_URLS` decides which of the later stages run at all. Three of them exist only to mine an article — **Stage 0.4** (harvest figures), **Stage 4** (screenshots), and **Stage 4b** (match figures). With `SOURCE_URLS: none` there is nothing for them to read: record `FIGURES_AVAILABLE: none`, skip all three, and say in the Final Output that the video ships without on-screen evidence. This is one rule for every source-free video, not a carve-out for one series.

### Load the series profile

Once `SERIES` is resolved (and it is not `misc`), **read `series/<SERIES>.md`** — that file is the source of truth for this series, and it outranks the defaults written into this command. It drives Stage 0.5 (spine), Stage 1 (hooks), Stage 3 (voice), and Stage 3.6 (CTA and resources). The canonical slugs are `tbbt`, `updates`, `tech-in-one-breathe`, `interesting-tech`, `ai-fundamentals`, `hot-takes`; `misc` has no file and uses the `scripts` skill's default voice, no CTA, and no resources.

Three of its sections replace the defaults written into this command and the `scripts` skill outright, rather than adding to them:

- **`## Audience`** (always present) — the series owns who is watching, what they already know, and what needs explaining. This sets the jargon bar for Stage 3; there is no channel-wide default, and the six audiences differ enough that assuming one is the main way a script ends up pitched at the wrong viewer.
- **`## Structure`** (when present) — the series has a fixed body shape, so it *is* the spine; Stage 0.5 fills in its beats instead of choosing a shape.
- **`## CTA & Resources`** (always present) — the series owns its CTA type, how many resources ship, and what kind. Stage 3.6 does what it says.

### Fix the video slug

Choose the `<video-slug>` **now**: kebab-case, describing the topic (e.g. `canva-session-revocations-s3`). Everything downstream uses it — the figures and screenshots in `assets/<video-slug>/`, and the script filename in Stage 3.5. Pick it once here rather than letting the script filename decide it later, because Stage 0.4 needs somewhere to write before the script exists.

## Stage 0.4 — Harvest Source Figures

Figures are explanatory images the article already contains — **charts** and **diagrams** — reused as on-screen overlays. A chart is the visual proof of a shocking number; a diagram shows how a system works.

**This runs before the script is written, and that ordering is the point.** A diagram has to stay on screen for 5–8 seconds and the narration has to still be about that system the whole time. A script written blind to the available figures usually has no passage that long, so the figure gets retrofitted onto one short line and flashed. Knowing what diagrams exist *before* Stage 3 lets the body be written with somewhere for them to live. Selection and anchoring still happen later, at Stage 4b, once there's a script to match against.

### Step 0.4.1: Harvest candidates

For each source URL, run:

```bash
.venv/bin/python scrape/figure_finder.py --url "<source_url>" --output-dir "assets/<video-slug>/"
```

It writes candidate images to `assets/<video-slug>/figures/` and metadata to `assets/<video-slug>/figure_candidates.json` (each entry: `file`, `figcaption`, `alt`, `heading`, `surrounding_text`, `format`, `width`/`height`, `score`). The deterministic prefilter has already dropped icons/avatars/logos/ads/banners/hero images; what remains is worth a look. If `candidates` is empty, record `FIGURES_AVAILABLE: none` and skip Stage 4b entirely.

### Step 0.4.2: Look at each candidate and judge it

**Use the Read tool on each `figures/figure-NN.*` image** and judge it, grounded by its `figcaption`/`alt`/`surrounding_text` from the candidates JSON:

- **`is_usable`** — an informative chart or diagram, not a photo/headshot/decorative/logo. Drop anything that isn't.
- **`kind`** — `chart` (bars/curves/comparisons of numbers) or `diagram` (architecture / flow / sequence / how-it-works). v1 uses only these two; drop tables, UI screenshots, and photos.
- **`legibility`** — **would it read on a 9:16 phone screen?** A dense diagram with tiny text or a busy multi-panel chart is a drop — an unreadable figure hurts more than none. Aspect ratio matters as much as resolution: a 2.7:1 panorama shrinks to nothing in a vertical frame however many pixels it has.

If reading the images fails or the user asks you not to, say so plainly and judge from `figcaption`/`alt`/`surrounding_text` and the dimensions instead — then flag in the Final Output that legibility was inferred, not seen.

Carry the survivors forward as `FIGURES_AVAILABLE` — for each, its `file`, `kind`, and a one-line description of what it shows. Stage 0.5 and Stage 3 both read this.

## Stage 0.5 — Script Spine

The **spine** is what the video is actually about: the crux mechanism it explains and the reframe it lands at the end. It is the single biggest driver of whether the video works, because it decides what the viewer *stays* for. It is not the hook and not a framing — it is the story the body tells. Build it from the `topic_package`, drawing the payoff from `HOW_IT_WAS_SOLVED`, not just the surprising fact.

**The `topic_package` has to be the real thing before a spine is built on it.** For every URL in `SOURCE_URLS`, `FULL_CONTENT` must hold the actual fetched article body — not the URL, not its title, not a search snippet, and not recollection of having read it before. If a URL resolved but its content never made it into `FULL_CONTENT`, go back and fetch it before doing anything here: a spine drawn from a headline is a guess about what the article says, and every later stage inherits that guess. With `SOURCE_URLS: none` the `topic_package` holds the user's own account from Stage 0 branch 3, and the same bar applies — use what they actually said, and never fill a gap with invented experience.

**If the series file has a `## Structure` section, that structure is the spine.** The series has already fixed the body shape and usually says which measured problem it fixes, so there is nothing to select: name the crux, payoff, and turn *in its beats*, and skip the shape-choice below. Do not reshape the material to fit deep-dive / key-problem / walkthrough — those are defaults for series that leave the shape open.

1. **Find the strongest spine.** Identify the best video the `topic_package` supports. A spine takes one of three shapes — pick the one it best supports, then don't force it into a different shape:
   - **Deep-dive** — one mechanism, explained in depth. Crux = that mechanism.
   - **Key problem solved** — one hard problem and the clever fix. Crux = the problem and its solution; lean on any reversal or irony in *how* it was solved.
   - **Walkthrough** — a multi-stage system where no single mechanism is the whole story. Crux = the pipeline itself; the individual mechanisms are ordered *beats* of the body, not separate spines. This is the shape to reach for when the user wants to understand how the whole thing works.

   Whichever shape, state it as three parts:
   - **Crux** — what the video explains: a mechanism, a problem+fix, or a pipeline, per the shape above.
   - **Payoff** — how it actually works: the methods, the tradeoff, the *how they solved it*. Ground this in `HOW_IT_WAS_SOLVED` so the body has a real payoff, not a problem-then-fix summary.
   - **Turn** — the reframe that recasts the whole thing at the end.
2. **Default to one spine; apply the merge test before forking.** Most topics have one clearly-best spine — when they do, proceed with it and just tell the user what it is; do not force a choice. Before presenting a fork, try to *merge* the candidates into one walkthrough: if they merge cleanly (they are stages of the same build), it is **one** spine — present the walkthrough, do not fork. Only fork when merging would force a candidate to lose its payoff — i.e. they are genuinely two videos that cannot share one body: a different crux, a different payoff, and a different turn, not reworded framings of the same story.
3. **Select only when real forks exist.** If two or more genuinely distinct spines survive the merge test, present them and ask the user to choose; each option states its shape, crux, payoff, and turn (the flow of the video) so the choice is made on the story, not a label. If one spine dominates, skip the question and continue.

The chosen `SPINE` drives Stage 1 (hooks) and Stage 3 (script). If the story gate recorded `STORY_STRENGTH: thin`, restate that here — the spine can only be as strong as the `topic_package` allows, so flag the weakness rather than overselling it.

## Stage 1 — Hook Generation

Invoke the `hooks` skill and apply its rules, patterns, and quality test. Better hooks come from breadth then ruthless selection, not from writing three and hoping one lands.

0. **Ground in proven hooks.** Pass the resolved `SERIES` to the `hooks` skill — it reads the series file's **Best Hooks** and `.claude/voice/proven-hooks.md` (the user's top hooks ranked by real engagement) and biases toward what wins on this channel. Your job here is just to give it the slug; bias generation toward those proven patterns while still generating wide.

1. **Generate wide.** Write 8–10 candidate hooks that captivate and funnel into the crux of the chosen `SPINE`. The hook is the on-ramp, not a summary of the body: it is *free* to lead with a different, stronger element (a name, a number, a reversal) than the crux itself. Use that freedom rather than relaxing into it — each hook must stop the scroll on its own single strongest element, not merely introduce the topic. Span at least 3 of the skill's distinct patterns — do not return rewordings of a single idea. For each, note its `PATTERN` and the single raw element it leads with (the name, number, stat, or reversal, seeded from `MOST_SURPRISING_FACT`).
2. **Score each.** Run the skill's 3-check quality test (scroll / HOW / promise) on every candidate and judge the strength of its lead element. Drop any that fail a check or lead with a weak element.
3. **Critique and rewrite.** Take the ~5 strongest survivors. For each, name its single weakest element (buried lead, soft claim, too long, no open loop) and rewrite it once to fix exactly that. Keep the stronger version.
4. **Shortlist distinct winners.** Select the top **N hooks (default 3)**, each using a *different pattern or lead element* so the resulting videos test genuinely different strategies, not phrasings. Store them ordered best-first as `HOOK_1 … HOOK_N`, each with a `PATTERN` and `TEXT` field.

## Stage 2 — Hook Approval

Present the shortlist: for each hook show its `TEXT`, its `PATTERN`, and one line on why it stops the scroll. Ask the user to confirm the set, swap in a runner-up, edit wording, or change N. The confirmed, ordered set (best first) is the `HOOK_SET` recorded into the script in Stage 3 — you are keeping **all** of them, not picking one.

## Stage 3 — Script Writing

Invoke the `scripts` skill and `tellcheck` skill, use the full `topic_package`, the chosen `SPINE`, and the confirmed `HOOK_SET` to create a captivating short form content script for platforms like Instagram Reels. Write the body to the `SPINE`: explain its crux, deliver the payoff (the *how*, drawn from `HOW_IT_WAS_SOLVED`), and land its turn. A body that only states the problem and names the fix has failed the spine — the payoff is the video. Pass the resolved `SERIES` to the `scripts` skill — it applies the series file's voice profile (register, target length) and layers the user's delivery voice from `.claude/voice/voice-profile.md` on top; for `misc` it uses its default voice. The CTA is not written here: Stage 3.6 appends it once the series' policy has been read.

**Write every hook from `HOOK_SET` into the script.** You record all of them in one take and split them into separate videos later, so the `**HOOK**` section holds the full set, numbered and ordered best-first, one hook per line. Lead the file with a `**VIDEO TYPE**` section holding the resolved `SERIES` slug — it's the only record of which series the saved file belongs to:

```
**VIDEO TYPE**
<SERIES>
**HOOK**
HOOK 1: <HOOK_1 text>
HOOK 2: <HOOK_2 text>
HOOK 3: <HOOK_3 text>
**SCRIPT**
...
```

Each hook must independently lead into the **same** body, so any split (hook N + the body) stands alone as a complete video. If the body needs a "why should I care" stakes sentence (the `scripts` skill decides — a hook that already carries the stakes doesn't get one), it goes at the **start of `**SCRIPT**`**, not attached to any single hook, so it is shared across every variant. Judge it against the weakest hook in the set, since the body has to stand up behind all of them. No blank lines.

**If `FIGURES_AVAILABLE` contains a `diagram`, the body must give it somewhere to live.** Write **one sustained walk-through passage** — several consecutive sentences, **25+ words**, staying on that one system the whole way — describing what the diagram shows. This is not a request to narrate the picture: never write "as you can see in this diagram" or otherwise point at it. The viewer should just be hearing the system explained for long enough that a diagram can sit on screen and be read while they listen. Absent this, Stage 4b has nothing to anchor to and the diagram gets dropped.

This runs *with* the series voice, not against it. Punchy one-line delivery is still correct everywhere else in the body — spend the length in one place, on the mechanism the diagram illustrates, and keep the rest tight. If the spine's crux genuinely doesn't warrant a sustained passage, don't manufacture one to justify a figure: drop the figure instead. The script serves the video, not the assets.

For every claim, stat, or quote that will appear in the script:

1. **Locate it verbatim** in `FULL_CONTENT`. Drop any quote that doesn't appear there.
2. **Confirm the correct subject.** Ask: who said this — the document, a person quoted in it, or a secondary source? A quote from someone's speech is not the document's claim. A fact from source B is not from source A. Never collapse two sources into one sentence.
3. **Check the attribution in the script matches the actual speaker/document.** If the encyclical says X and a speaker says Y, they must be attributed separately. "The document points out..." is only valid if the document is the actual source of that sentence.
4. **Articles often contain third-party quotes.** A blog post may include testimonials, customer quotes, or researcher statements. A claim inside a quoted block belongs to the quoted person — not the publication. Do not write "[Company] says X" if X came from a quoted third party inside their article.

Any claim that cannot be traced to a specific sentence in `FULL_CONTENT` is cut, not paraphrased from memory.

**With `SOURCE_URLS: none`, the user is the source.** The opinion and the user's own account of their experience trace to *them*, not to `FULL_CONTENT` — use them as given and never embellish them into specifics they didn't say. Every **factual claim, number, or attribution** in the script still meets the bar above against whatever was verified into `FULL_CONTENT` in Stage 0. An unverifiable stat is cut and the mechanism argued without it.

## Stage 3.5 — Save & QC Gate
After the script is written, save it:

1. Save to `assets/<video-slug>/script.md` — the slug already fixed in Stage 0, so it sits beside that slug's screenshots and figures. Create the folder if Stage 0.4 didn't
2. No empty lines in the saved file
3. **`/prepare-video` reads this file as the ground truth for what was said**, so the body must be the spoken words exactly as scripted — same `**VIDEO TYPE**` / `**HOOK**` / `**SCRIPT**` / `**CONCLUSION**` / `**CTA**` / `**REFERENCES:**` / `**VIEWER RESOURCES:**` headings, same one-line-per-hook shape. Keep proper nouns in their real casing (`ChatGPT`, `PgBouncer`, `PGKeeper`) — that casing is what the transcript gets checked against
4. **Re-flow the body to one sentence per line.** The `**SCRIPT**` and `**CONCLUSION**` sections are written as one paragraph, which is hard to read off a phone while filming. This rewrites the line breaks only, never the wording, and every other section is left alone:

   ```bash
   .venv/bin/python .claude/skills/scripts/scripts/format_script.py "<saved_file_path>"
   ```

   Run it after every save of this file, including any re-save made to fix a linter error. Re-running is safe.
5. **Run the deterministic QC linter and block on it.** It catches mechanical defects (em dashes, banned throat-clearing openers, missing apostrophes, format and blank-line violations) that self-review keeps missing:

   ```bash
   .venv/bin/python .claude/skills/scripts/scripts/lint_script.py "<saved_file_path>" --series <SERIES>
   ```

   **Always pass `--series`** (omit it only for `misc`, which has no series file). The word cap comes from that series' own `**Target length:**` line, so without the flag the linter falls back to a series-agnostic default that is too loose for the short series and too tight for `tbbt`.

   If it exits non-zero, fix every reported blocking error, re-save, and re-run until it passes. Warnings are advisory — review them, but they don't block. The word-count warning already excludes the `**HOOK**` and `**CTA**` blocks, so it is measuring the shared body against the series' real ceiling. Do not continue to Stage 4 until the linter passes.

Wait for the saved file path before continuing.

Leave the idea banks alone — they are a record of what was proposed, and `/video-ideas` dedups against the scripts saved under `assets/`, so a produced idea drops out on its own without editing the bank.

## Stage 3.6 — CTA & Viewer Resources

**Read the series file's `## CTA & Resources` section before doing anything here.** It names the CTA type, how many resources ship, and which kinds fit this audience. It decides which of the steps below run:

| CTA type | What this stage does |
|---|---|
| `comment-bait` | All four steps. The keyword ask is the CTA and a resource has to be worth commenting for. |
| `follow` | Steps 3.6.1, 3.6.2, 3.6.4. The CTA is the series' follow line, so there is no lead magnet and no keyword — resources still ship in the file for reference, they are just not promised out loud. |
| `disagreement` | Step 3.6.4 only, and only its CTA half. Write the CTA the series describes, name the counter-position, and ask the people who hold it to argue. No resources, no keyword. |
| *(none — `misc`)* | Skip the whole stage. No `**CTA**` heading, no resources block. |

The goal behind comment-bait: give the viewer a reason to **comment**, and a payoff worth commenting for. Comments are the strongest algorithmic signal on Reels/Shorts, and "comment a keyword and I'll send the link" only works if the thing you're sending is genuinely worth getting.

### Step 3.6.1 — Brainstorm topic-specific resource ideas

Think about what *this specific audience* (developers/builders watching a `SERIES` video on `TOPIC`) would actually want to do *next* after the video lands the `SPINE`. **Start from the kinds the series file asks for** — it already knows what its audience takes. Then **anchor on what the article itself names**: the specific technology, system, or company it's about, the source's own deeper write-ups, talks, or repos, or the source article itself.

**Hard gate — every resource must be about a technology, system, paper, or company the article actually names.** Check the resource's subject against `FULL_CONTENT` the same way you check a claim: if the article says "a column-oriented key-value database" but never names Bigtable, you may **not** add a Bigtable paper — the article didn't cite it, so the tie is fabricated. Either find a resource for something the article *does* name (in this example the article does name "Direct Preference Optimization" and "LLM as a judge", so those are fair game), or generalise the resource so it doesn't claim a specific product the source never mentioned. A resource for tech the article doesn't name is not a go-deeper, it's an invented association. Reach for a generic third-party tool only when nothing article-named fits, and never in violation of this gate.

Generate **3–4 candidate resources**, pulling from different categories so they diverge — don't return four of the same kind. Only the series' allowance ships (Step 3.6.4), so the spread exists to give you a real choice, not to fill a list. The categories below are the menu; the series file says which of them belong in *its* videos:

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

*Comment-bait series only. For `follow`, write the series' follow line as the CTA and go to Step 3.6.4. For `disagreement`, write the CTA the series describes and go to Step 3.6.4.*

From the verified candidates, select the **single best lead magnet**: the one with the strongest "I want that" pull *and* the tightest tie to the article's actual topic (a steal-this asset, the source's own deeper material, or the article itself). Then write a comment-bait CTA:

- A short, memorable, topic-tied **keyword** (one word, uppercase, e.g. `CACHE`, `SCALE`, `RAFT`).
- A one-line CTA the creator can pin or say: `<Who made it> <has/have> a guide to <doing this yourself>. Comment "<KEYWORD>" and I'll send it over.`

**State the resource as a fact, then ask for the comment.** The CTA is the last thing the viewer hears, so it has to sound like the creator mentioning something in passing, not a pitch. Never open it with `Want`, `Wanna`, `Want to know`, `Do you want`, `Ever wondered`, or any other question about what the viewer desires — that is the shape of an ad, and it breaks the video's voice on the final line. Name who made the resource and what it does, in the same plain register as the body, then make the ask.

Good: `AWS have their own guide to setting up S3 this same way. Comment "S3" and I'll send it over.`

Bad: `Want the AWS guide to running this same multi writer trick on S3 yourself? Comment "S3" and I'll send it over.` — the question opener sells instead of tells, and `trick` hypes a resource that can speak for itself.

### Step 3.6.4 — Append to the saved script file

Write the CTA and the resources in **two** places, **no blank lines anywhere** (the linter blocks on them):

1. Insert a `**CTA**` heading and the CTA line immediately **after** the `**CONCLUSION**` section and **before** `**REFERENCES:**`. This line is spoken, so it is prose-checked — keep it free of em dashes. Its shape follows the series' CTA type:

```
**CTA**
<one line, in the shape below>
```

- **comment-bait:** `<Who made it> <has/have> a guide to <doing this yourself>. Comment "<KEYWORD>" and I'll send it over.`
- **follow:** the series' own follow line.
- **disagreement:** name the counter-position and ask the people who hold it to make their case.

2. Append the resources block to the **end** of the file, **after** the `**REFERENCES:**` section. One resource per pair of lines: a short label on the first line, the bare URL on the second. No blank lines anywhere (the linter still blocks on them):

```
**VIEWER RESOURCES:**
<name> resource:
<url>
<name> resource:
<url>
Video reference article:
<url>
```

**The series file sets the resource cap** — two, one, or none. The source article link(s) always go last and never count against the cap. One resource followed by the article is a finished list; add a second only when it covers ground the first doesn't, because a second link that overlaps the first is worse than no second link. Everything else you verified stays out.

If the script drew on more than one source article, use `Video reference articles:` and list each URL under it, one per line. With `SOURCE_URLS: none` there is no reference line and, on a series that ships no resources, no `**VIEWER RESOURCES:**` block at all — end the file at `**REFERENCES:**` rather than writing an empty heading.

**The resource the CTA promises goes first.** That position is the only marker it needs, so nothing in the file says `Lead Magnet` — that is your word for it, not the viewer's, and the viewer is the one reading this block.

**Label rules — a label is a name, not a pitch:**

- Name the thing, then `resource:`. **Six words or fewer** including that word, and no em dashes.
- No parenthetical explanation of why the viewer wants it. The URL is one line down; they can look.
- No category names (`Lead Magnet`, `Go Deeper`, `Hands-on`, `Go-deeper canonical`, `The real source`). Those are your sorting buckets from Step 3.6.1, not words a viewer needs.
- No hype or endorsement adjectives: `exact`, `actual`, `complete`, `ultimate`, `definitive`, `deep dive`, `everything you need`.

Good: `S3 conditional writes resource:` / `ZooKeeper leader election resource:` / `GLM-5.2 open weights resource:`

Bad: `Lead Magnet (AWS Storage Blog, building multi writer applications on S3 with conditional writes, the exact If-Match pattern Canva used, with code):` — it is three labels stapled together, it argues for the link, and nobody reads that far.

### Step 3.6.5 — Write the automation spec

*Comment-bait series only.* The keyword and the resources are the whole content of the comment automation, so write them down now, while you still hold them — `/post-video` and `/schedule-video` both read this file and neither of them can see the vault note.

Every automation this project produces is the same funnel — comment the keyword, get asked to follow, reply DONE, receive the resources. Only the **keyword** and the **reward** differ between videos, so those two are the only things you write. The rest is fixed in `scrape/automation_spec.py` and filled in at post time; do not restate it here and do not invent a variation of it.

Write `assets/<video-slug>/automation.json` — exactly these two fields, nothing else:

```json
{
  "trigger_keywords": ["<KEYWORD>"],
  "follower_message": "<the resources block from Step 3.6.4, verbatim>"
}
```

- `trigger_keywords` is the keyword from Step 3.6.3, exactly as the CTA says it, and it must be **one word**. The worker matches it as a substring of any comment of ten words or fewer, so a keyword that turns up inside ordinary words fires on people who weren't asking.
- `follower_message` is the **reward** — the `**VIEWER RESOURCES:**` block you just wrote into the note, copied **character-for-character**, except insert one blank line between entries (the script file's no-blank-line rule is for the linter and doesn't apply to this DM). Every entry, including the `Video reference article:` line, in the same order, with the same labels. Do not reword a label, do not merge two entries into a sentence, and do not send only the lead magnet — this is what the follower actually receives, and an empty one means they are sent nothing at all.
- **Check the count before moving on:** the reward must contain exactly as many URLs as the block in the note. Dropping the go-deeper resource or the reference article is the way this goes wrong.

For `follow`, `disagreement` and `misc` there is no keyword and nothing to send, so write no file. A missing `automation.json` means the hooks post with no automation, which is the correct result.

Then check it, and fix anything it reports before moving on:

```bash
.venv/bin/python scrape/validate_automation.py <video-slug>
```

It checks both halves: the two fields you wrote, and that the reply function and DM pack named in `automation_spec.py` still exist in social-cockpit. Nothing rejects a renamed pack at post time — the flow is created, fires, and sends an empty message — so this is the only place it gets caught.

Then re-run the linter and confirm it still passes:

```bash
.venv/bin/python .claude/skills/scripts/scripts/lint_script.py "<saved_file_path>" --series <SERIES>
```

If it reports a blank-line error, the resources block introduced an empty line — remove it and re-run until clean.

## Stage 4 — Source Screenshots for Video

*Skipped entirely when `SOURCE_URLS: none` — there is no page to screenshot.*

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

Where `<video-slug>` is the slug fixed in Stage 0 (the same one Stage 0.4 harvested figures into).

If a source URL is a Reddit post, use the linked article URL instead (already fetched in Stage 0).

### Step 4.3: Check what was actually captured

The JSON result includes a `snippets` array — one entry per requested snippet with `found`, `match_type` (`exact` | `fuzzy` | `none`), `confidence`, `highlight` (`range` | `fuzzy_range` | `whole_block`), and (on a miss) `reason`. The same misses are also recorded under `missed` in `manifest.json`.

- **Report every snippet with `found: false`** and its `reason`. That claim will have **no on-screen evidence** in the video — either revise the `article_snippet` to match the article's wording verbatim and re-run for that URL, or call the claim out as unsupported.
- **Flag any `match_type: "fuzzy"` match with `confidence` below 0.8** — find located an approximate block rather than the exact phrase, so it's worth an eyeball before relying on it.
- **Flag any `highlight: "whole_block"`** — the exact phrase couldn't be pinpointed so the whole paragraph was coloured; the screenshot shows a wall of highlight rather than the specific proof. Worth eyeballing, and often fixed by trimming the `article_snippet` to a span that matches the live page verbatim and re-running.
- If `skipped` is non-null, the whole page failed to load — report that reason; no screenshots were captured for that URL.

## Stage 4b — Match Figures to Script Beats

The usable charts and diagrams were already harvested and judged in Stage 0.4 and carried forward as `FIGURES_AVAILABLE`. If it is `none`, skip to Final Output. This stage does the half that needed a finished script: anchoring each figure to the beat it supports.

### Step 4b.1: Match to a script beat

Match by kind:

- **`chart` → the stat beat** whose exact number the chart visualises (highest priority — it proves the "shocking number" a hook makes).
- **`diagram` → the sustained walk-through passage** Stage 3 wrote for it. Anchor it to the *whole* passage, not one clause.

### Step 4b.2: Apply the span gate

`script_context` is a ceiling, not a hint: produce-video can only hold a figure inside the span you give it, so a short span means a flashed figure or one stretched over narration that has moved on. Measure the span you're about to write — `trigger_show_word` through `trigger_go_away_word` — and check it against its kind:

- **`diagram`: the anchored span must be 25+ words** (roughly 8s of speech) and stay on that one system throughout. Multi-sentence is normal and expected here.
- **`chart`: 10+ words.** A chart proves one number, so it can leave sooner — but never a flash.

If a diagram's span falls short, in this order: **widen** it to take in the neighbouring sentences, provided they're still about the same system; if they aren't, **drop the figure**. Do not pad the span with adjacent narration just to clear the number — a diagram held over words about something else is worse than no diagram. Report every figure dropped this way in the Final Output, since it usually means Stage 3 didn't write the passage the diagram needed.

**One overlay on screen at a time.** Never plan a figure and a screenshot to be visible together. The viewer can only read one thing while you narrate one thing, and the script never describes two at once. The renderer does displace an overlapping screenshot to a corner rather than dropping it (`_assign_slots` in `reelcut/image_overlay.py`), but that is a safety net for accidental pile-ups, not a layout to design for.

So when a screenshot from Stage 4 falls inside a figure's passage, **the figure keeps the span and the screenshot is removed** — delete that entry from `manifest.json`. Do not resolve it the other way by shortening the figure: truncating a diagram to dodge a screenshot is the main way it ends up flashed on one sentence, which is what this gate exists to prevent. Losing the text crop costs little, since a diagram covering that passage usually shows the same number the screenshot proved. List every screenshot removed this way in the Final Output.

### Step 4b.3: Select

**Cap at ≤3 figures per video**, and drop redundant ones (two figures of the same system → keep the more legible / higher-resolution). Figures hold longer and take more screen space than a text pop, so fewer-and-stronger wins.

### Step 4b.4: Write `figures.json`

Write the selected figures to `assets/<video-slug>/figures.json` (a JSON list). This is the figure equivalent of the screenshot manifest — it records the *selection* and *anchors*; `produce-video` computes the actual timings later. Each entry:

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

- `script_context` — copy the supported script line **verbatim** from the script. For a `diagram`, copy the **whole walk-through passage** (the several sentences that explain the system), not one line, so `trigger_go_away_word` can sit at the end of the walk-through and clear the span gate.
- `trigger_show_word` / `trigger_go_away_word` — short verbatim anchors from **inside** `script_context`, marking where the figure appears and disappears. Same rules as screenshot triggers; leave `""` if no clean anchor and produce-video spans the whole line.

## Step 5 — Send the script and upload links to Telegram

Post the slug's script link and footage-upload link to the `file-exchange` topic, so you can read the script off your phone and send the take straight back from the same thread.

```bash
.venv/bin/python scripts/send_script.py <video-slug>
```

Best-effort: if it fails (upload server down, tailnet unreachable, broker off), say so in the final report and carry on — the script is already written to disk.

The helper sends **one** message holding both links. The script body is not pasted into the thread: `scripts/upload_server.py` serves `assets/<slug>/script.md` at `http://<tailnet-ip>:8770/script/<slug>`, reading it on every request, so any edit made after this step is live on the phone at the next refresh. That is also why a later fix to the script needs no re-send — the link already points at the current file.

## Final Output

Report to the user:

- Prompt resolved as: [URL / file reference / phrase / bare claim] → [TOPIC] ([SERIES])
- Script saved to: [file path]
- CTA & resources: the CTA type the series called for and the line you wrote, plus the shipped links appended to the file. Note any verified candidate you cut, in case the user wants a different lead magnet
- Automation: the keyword, the template and the resources the reward carries, written to `assets/<slug>/automation.json` and validated clean — or that none was written and why (the series' CTA type has no keyword)
- **If `SOURCE_URLS: none`:** say the source gate skipped Stages 0.4, 4, and 4b, so the video ships with no screenshots and no figures. Skip the four items below
- Screenshots saved to: `assets/<slug>/`
- Screenshot results: how many captured (with the exact/fuzzy breakdown), and explicitly list any snippets that were **not found** so the user knows which claims lack on-screen evidence
- Figures: how many charts/diagrams were selected (with `kind` and the beat each supports), the count of candidates harvested vs. kept, and where they were saved (`assets/<slug>/figures/`, `figures.json`). Call out each figure **dropped by the span gate** and the span it fell short by — that means the body never got the sustained passage the diagram needed, and is worth a script edit. Say so if legibility was judged from metadata rather than from reading the images
- Unsupported claims: any checkable claim you dropped at selection time because the source didn't state it verbatim (Step 4.1.2) — the user may want to re-source or soften it
- Telegram: the `http://<tailnet-ip>:8770/script/<slug>` and `/upload/<slug>` links sent to `file-exchange` — or that nothing was sent, and why (upload server down, tailnet unreachable, broker off)
- Any warnings (near-tie runner-up available, low-confidence fuzzy matches, skipped screenshots, etc.)
