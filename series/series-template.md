# Series File Template

Copy this to `series/<slug>.md` to add a series. The slug is the filename and is canonical everywhere — the `topic_package`, `lint_script.py --series`, and `assets/` all key off it.

**This file is not a series.** Every other `series/*.md` file is one — the set of files *is* the list of series (`lint_script.py`, `scrape/db.py series_slugs()` and every command read it that way), and this file is excluded by name. `series/` is gitignored except for this template: your series are yours.

**Optional `SERIES.md`** at the repo root (also gitignored) holds channel-wide notes — calibration from past analytics, naming history. `/video-ideas` reads it if present.

Seven headings are required and every series has them. Three are optional and most series omit them. Order below is the order the files use.

| Heading | Required | Read by |
|---|---|---|
| `## Identity` | yes | `produce-script` Stage 0 (series routing), `/video-ideas` |
| `## Audience` | yes | `scripts` skill (jargon bar), `produce-script` Stage 3 |
| `## Topic Selection` | yes | `/video-ideas`, `produce-script` Stage 0 |
| `## Voice Profile` | yes | `scripts` skill, **`lint_script.py --series`** |
| `## Title Card` | yes | `/produce-video` Step 4b |
| `## Structure` | no | `produce-script` Stage 0.5 — replaces spine selection |
| `## CTA & Resources` | yes | `produce-script` Stage 3.6 |
| `## Sourcing` | no | `produce-script` Stage 3 |
| `## Best Hooks` | yes | `hooks` skill, `produce-script` Stage 1 |
| `## Production` | no | **`scripts/upload_server.py`** |

**Two fields are parsed by code.** `**Target length:**` under `## Voice Profile` is read by `lint_script.py` to set the word cap. It understands three shapes — `hard cap 230`, `150–230 words`, `under 120 words` — and an explicit hard cap wins over a range on the same line. Anything else falls back to the default of 190, so keep one of those three shapes. `**Uploads:** individual` under `## Production` is read by the upload server; see that section.

**Three sections override the shared layer outright** rather than adding to it: `## Audience`, `## Structure`, and `## CTA & Resources`. Where they contradict the `scripts` skill or `produce-script` defaults, the series file wins.

---

# <slug> — <Series Name>

## Identity
One or two sentences: what these videos are and what makes the series distinct. No audience here, that is the next section.

## Audience
**Who:** who is watching, in one line. Be specific about their level — this is the single biggest difference between series.
**Assume known:** the vocabulary and background they already own. Naming these matters as much as the next field: glossing a term this audience knows reads as condescension and spends words the script needs elsewhere.
**Explain:** what has to be glossed, replaced with plain language, or cut. This is the jargon bar, and it is the only thing that sets it — there is no channel-wide default.

## Topic Selection
**Source:** where topics come from — a table in `scrape/db/influencer.db` with the query to run, or "no DB" plus how they are chosen.
**Dedup against:** *(optional)* any notes folder outside the repo that lists videos already planned or made.
**Good topic:** what makes a topic work here. Ground it in what has actually performed, not in theory.
**Avoid:** the failure modes, each with the evidence. A bullet that names a real underperformer ("0 comments on 2.7k views") stops that mistake repeating; a bare "avoid X" does not.
**Queued:** *(optional)* topics lined up but not yet produced.
**Harvest (/video-ideas):** how `/video-ideas` gathers candidates for this series — a scraper refresh and `scrape/query.py` call, a `WebSearch` brief, concept picks, or mining the user's own opinions — plus what to prefer and skip.
**Ideas per batch:** *(optional)* how many ideas `/video-ideas` writes per run. Default 3.

## Voice Profile
- **Register:** how it sounds out loud — polished, casual, brisk, first person. This is where the series diverges from the default explainer voice.
- **Target length:** `A–B words` with a short reason. Parsed by `lint_script.py`, so use `A–B words`, `under N words`, or `hard cap N`.

## Title Card
**Style:** the framing the burned-in title card should hit for this series, then the shared clause every series ends on: **name the concrete thing, hold back the resolution.** The card is slightly mysterious by design — specific enough to be worth stopping for, incomplete enough that the viewer has to stay. Keep it distinct from a plain restatement of the hook (`/produce-video` writes one card per hook, never the hook's verbatim wording).
**Subtitle:** the fixed branding line under the title, identical across every card in the series. Include `{n:<slug>}` where an episode counter belongs.

## Structure
*(Optional — most series omit this and let `produce-script` Stage 0.5 choose a spine.)*
Only add this when the series genuinely has one fixed body shape and you can say which measured problem it fixes. A beat list here becomes the spine and Stage 0.5 skips shape selection, so it is a strong constraint: the risk is that a script written to a numbered template starts narrating the template out loud.

## CTA & Resources
**CTA type:** `comment-bait`, `follow`, or `disagreement` — these are the three Stage 3.6 handles, and each runs a different subset of its steps.
**Resources (N max):** what kind of link fits this audience, and why. Use `**Resources:** none` for a series that ships no links.
**Keyword:** the comment-bait keyword pattern, or `none`.

## Sourcing
*(Optional — only needed when the series' sourcing differs from the default "verify everything against the article".)*
State what still needs a source when the usual article isn't there.

## Best Hooks
**Winning pattern for this audience:** the pattern that wins here, described concretely. The `hooks` skill holds no pattern library, so this is where patterns live.
**Shipped / top performer:** hooks that have actually shipped, with real numbers. Write "none yet" if the series is new rather than inventing one.
**Top performers (analytics, auto — refresh via `/voice-profile`):** maintained by `/voice-profile` from real engagement data. Leave the heading; the command fills it.
**Example hooks (pattern templates):** two or three templates showing the shape. Mark them clearly as templates when none have shipped yet.

## Production
*(Optional — omit it and a script's link takes one upload, recorded with every hook and split per hook in production.)*
**Uploads:** `individual` — every upload from a script's link becomes its own full video (one hook plus body) in a fresh `assets/<slug>-<timestamp>/`, any number of times, and production ignores `script.md` in favour of the take's transcript. Use it for series short enough to record whole per hook. Anything after the word is commentary; only `individual` is recognised.
