---
name: produce-video
description: Assign screenshot and person image timings to images.json, then render one video per hook via reelcut.
argument-hint: "<video-slug>"
tools: Read, Edit, Bash
permissionMode: default
---

Populates image overlays in images.json and renders one video per hook (each hook + the shared body).

**Paths:** `{TOKEN}` references below are machine-specific absolute paths/endpoints defined in [glossary.md](glossary.md) — resolve each to its value before running. Repo-relative paths (`assets/…`, `output/…`, `config.yaml`, `tests/…`) are written inline as-is.

Arguments: `$ARGUMENTS` — expected format: `<video-slug>`

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If `$ARGUMENTS` is empty, ask the user which of the slugs above to use.

Example: `/produce-video netflix-cdn-architecture`

## Step 1 — Locate captions file and generate output timeline

List `assets/<video-slug>/` to find the `.captions.json` file — it may be named after the footage stem, not the slug (e.g. `Teleprompter-2026-01-06_20-59-13.captions.json`). Use whatever file is present; there will be exactly one.

```bash
.venv/bin/reelcut timeline "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

Use this to understand what is spoken when in the final video. **Do not use these times in image entries** — they are for orientation only.

## Step 2 — Check for manifest

Check whether `assets/<video-slug>/manifest.json` exists (it is only present when screenshots were produced by `/produce-script`). Also check whether `assets/<video-slug>/figures.json` exists (present when charts/diagrams were selected by `/produce-script` Stage 4b) — if so, handle it in **Step 3d**.

**If neither `manifest.json` nor `figures.json` exists → skip Steps 3 and 4. Go straight to Step 5 (render).**

If `manifest.json` exists, read both:

1. **Screenshot manifest**: `assets/<video-slug>/manifest.json`
2. **captions.json**: `assets/<video-slug>/<actual-captions-filename>.captions.json` (the file found in Step 1)

The manifest maps each `snippet-NN.png` to these fields:
- `article_snippet` — the verbatim source text captured from the article
- `script_context` — the script line it supports (written at produce-script time, re-aligned to the transcript by `prepare-video`)
- `trigger_show_word` / `trigger_go_away_word` — optional verbatim anchors from within `script_context` marking where the screenshot should appear and disappear (may be empty)

Use `script_context` as the primary guide when locating the timestamp — it directly names the script line being visualised. Fall back to matching words from `article_snippet` against the `words` array if `script_context` is absent.

## Step 3 — Assign image timings

Image timings are stored in **source-clip time** (same as `words` and `edl`). The renderer remaps them to output-timeline at render time.

**Hook vs body coverage (matters because of `render-hooks`).** Step 5 renders one video per hook — each is *that hook + the shared body*, with the other hooks cut out. So an overlay whose source-clip time falls inside a **hook** appears **only in that hook's video**; an overlay in the **body** appears in **all** of them. Before placing images, identify where the hooks end and the body begins (the shift from punchy hook statements into explaining/narrating — the same boundary as Step 3c, but note its source-clip time here). Screenshots and figures usually land on body lines already. For **concept** and **person** overlays you're free to position, prefer anchoring them to **body** words so every rendered video gets them — only pin one to a specific hook when the gag depends on that hook's exact wording.

Work through every screenshot in the manifest (skip `body.png`). **Skip any screenshot whose `script_context` or `article_snippet` cannot be matched to words in the `words` array — do not invent a placement.**

1. Use the `script_context` field to identify the moment the screenshot supports. If `script_context` is absent, match words from `article_snippet` against the `words` array
2. Find the words covering that moment in the `words` array of captions.json — use their `start`, `end`, and `source_clip` values
3. **Bound the on-screen window:**
   - **If `trigger_show_word` and `trigger_go_away_word` are both present and non-empty**, locate them in the `words` run for this line (search within the `script_context` span so they can't match a duplicate elsewhere): the screenshot's `start` = the matched `trigger_show_word`'s `start`, and its `end` = the matched `trigger_go_away_word`'s `end`.
   - **If a trigger anchor is empty or can't be found**, fall back to spanning the full sentence: `start` of the first matched word to `end` of the last matched word. If even the sentence boundaries can't be determined, use ~5 seconds centred on the anchor moment.
4. Set `type: "screenshot"`, `source_clip` to the `source_clip` from the anchor words, and `path` to the absolute path: `{PROJECT_ROOT}/assets/<video-slug>/<file>` where `<file>` is the `file` field from the manifest (may include a subdirectory)

Then scan the `words` array for person names (consecutive capitalised words that form a full name, e.g. "Reed Hastings", "Sam Altman"). For each name found:
- Use the source-clip timestamps from those words
- Add a `type: "person"` entry with `name: "<Full Name>"`, `source_clip` from the anchor word, and `path: ""` — the renderer resolves Wikipedia headshots automatically

Build the complete images list — one entry per screenshot, plus any person entries, plus an optional concept image (Step 3b).

## Step 3b — Concept image (optional, at most three per video)

A few quirky Wikipedia image can add a fun extra dimension — drop a literal photo of an unexpected *thing* onto a punchline. The gag lands when an abstract phrase is rendered as the real object behind it: "spaghetti code" → a bowl of spaghetti, "rubber-duck debugging" → a rubber duck, "the cops showed up" → a police car. Resolved exactly like a `person`, but the **name** is any Wikipedia subject, not a person.

- **Do a deliberate pass for these — don't wait for one to jump out.** A 60–90s reel that runs 15+ seconds with no visual overlay at all feels flat, so scan the **body** transcript for literal-noun gags: a concrete, photographable thing hiding inside an abstract phrase or a brand name (the kind of pun in the examples above). Aim for a visual beat of *some* kind (screenshot, figure, person, or concept) roughly every 10–15s of body — where the screenshots already cover that stretch you need no concept; where there's a gap, reach for one.
- Cap concepts at **at most three** per video. If a beat has no concrete noun that genuinely fits, skip it — restraint beats clutter. But don't let the cap or the restraint rule talk you out of the *first* good gag: a long overlay-free stretch is its own failure.
- The **name** must be the Wikipedia title of a **concrete, photographable object** whose page shows a **real photo** of that thing. This is the whole trick — and it's also where it breaks:
  - ✅ `Spaghetti code` (its page literally shows a bowl of spaghetti), `Rubber duck debugging`, `Police car`, `Trojan Horse` — concrete nouns with a real photo.
  - ❌ Abstract terms with **no photo**: `Technical debt`, `Scalability`, `Latency` — these resolve to nothing and silently vanish.
  - ❌ Terms whose page art is a **diagram/schematic, not a photo**: e.g. `Race condition` (an SVG diagram). A chart is not a gag.
  - When in doubt, picture the literal noun and use *that* title (e.g. `Rubber duck`, not "debugging"). If you can't name an object you're confident has a real photo on Wikipedia, omit it.
- **Keep it a flash, not a hold.** These are meant to appear and vanish in under a second — a quick visual joke, not a prolonged overlay. Aim for 0.5–1.0s of screen time. A ladybug flickering on "a new bug crept into the codebase" lands; the same image lingering for 3 seconds kills the pace.
- Place it on the *meaning*, even when the exact word isn't spoken. Anchor to the words in captions.json: `start` = the anchor word's `start`, `end` = the `end` of the line it punctuates, `source_clip` from the anchor word.
- Add `{ "type": "concept", "name": "<Wikipedia subject>", "start": ..., "end": ..., "source_clip": "...", "path": "" }`.

## Step 3d — Assign figure timings (from figures.json)

If `assets/<video-slug>/figures.json` exists, add one `type:"figure"` entry to the images list
for each figure in it (charts/diagrams harvested from the article). Timing works exactly like
screenshots:

1. Use the figure's `script_context` to find the moment it supports in the `words` array.
2. **Bound the on-screen window** with `trigger_show_word` / `trigger_go_away_word` (search within
   the `script_context` span so they can't match a duplicate elsewhere): `start` = the matched
   `trigger_show_word`'s `start`, `end` = the matched `trigger_go_away_word`'s `end`. If a trigger
   is empty or not found, span the full matched sentence; if even that fails, use ~5s centred on
   the anchor moment. **Skip any figure whose `script_context` can't be matched — don't invent a
   placement.**
3. Emit `type: "figure"`, `kind` copied from the figures.json entry, `source_clip` from the anchor
   words, `name: ""`, and `path` = the absolute path `{PROJECT_ROOT}/assets/<video-slug>/<file>`
   where `<file>` is the entry's `file` (e.g. `figures/figure-01.png`).

**Figures are held, not flashed.** A figure renders on a padded card (sized by
`figure_overlay_size_pct`) and has to be *read*, so after step 2 enforce a minimum on-screen hold:
- **`diagram`: at least 5s** (target 5–8s). A diagram has to be *studied*. If the speaker keeps
  discussing the same system past `trigger_go_away_word`, extend `end` forward to the last word of
  that explanation — hold the diagram across the whole walk-through instead of cutting it at the
  single line.
- **`chart`: at least 3s.** A chart proves one number, so it can leave sooner — but never a flash.

Widen the window by pushing `end` later (and only if needed, nudging `start` a touch earlier) to
reach the floor, staying inside the same `source_clip` and not overrunning the next hard cut.

Example entry (added to the same images list written in Step 4):
```json
{ "type": "figure", "kind": "diagram", "start": 21.4, "end": 26.8, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "{PROJECT_ROOT}/assets/slug/figures/figure-01.png" }
```

## Step 3c — Detect hook count and output-timeline boundaries

**Purpose:** establish how many heading cards Step 4b should generate and what output-timeline windows they occupy.

**1. Identify hooks from the output timeline.**

Use the `reelcut timeline` output from Step 1. Read the first several lines of the output and use intuition: hooks are the short, punchy statements at the very start of the video — questions, shocking facts, provocative claims — that grab attention before the body explanation begins. The body starts when the speaker shifts into explaining or narrating (e.g. "Picture a...", "So how does...", "It works by...").

Each distinct hook sentence is one hook. Count them and note the output-timeline start of each. The script file at `{VAULT_VIDEOS_TODO}<slug>.md` can help confirm what the HOOK section contains, but the timeline is the ground truth for timing.

**2. Locate each hook's boundaries in the output timeline.**

For each hook, record its `start` (first word) and the start of the next hook (or body) as its `end`. Record `hook_start[N]` = the output-timeline start of the first word of hook N.

**3. Compute hook windows.**

- For hooks 1 through N-1: `end = hook_start[N+1]`
- For hook N (last): `end` = the output-timeline start of the first word **after** the last hook — i.e. the first word that belongs to the body. If the body start can't be determined, use `hook_start[N] + 3.0`

Store `hook_windows: list[(start, end)]`. This drives heading card generation in Step 4b.

## Step 4 — Write images.json

Write the images list into `assets/<video-slug>/images.json` (a JSON list — a `[]` stub is auto-created by `prepare-video`, so use the Edit tool to fill it in). It is separate from captions.json; do not modify `edl` or `words` in captions.json.

Example `images.json`:
```json
[
  { "type": "screenshot", "start": 12.935, "end": 16.402, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "{PROJECT_ROOT}/assets/slug/snippet-01.png" },
  { "type": "person", "start": 4.205, "end": 7.444, "source_clip": "assets/slug/clip.MP4", "name": "Reed Hastings", "path": "" },
  { "type": "concept", "start": 31.2, "end": 34.1, "source_clip": "assets/slug/clip.MP4", "name": "Rubber duck debugging", "path": "" },
  { "type": "figure", "kind": "diagram", "start": 21.4, "end": 26.8, "source_clip": "assets/slug/clip.MP4", "name": "", "path": "{PROJECT_ROOT}/assets/slug/figures/figure-01.png" }
]
```

All `start`/`end` values are **source-clip seconds** taken from the `words` array in captions.json (the renderer remaps them to the output timeline).

## Step 4b — Headings (one distinct on-screen title card per hook)

Read `assets/<video-slug>/headings.json`. If the first entry has a non-empty `title`, it's already filled in — skip to Step 4c.

If the title is empty (the stub state from `prepare-video`), generate the heading cards.

**Each hook video gets its OWN on-screen title card, derived from that hook's angle — do NOT stamp one shared title across all cards.** This is deliberate. The three hook videos (`render-hooks` → `output/<slug>/*.mp4`) share an identical body and voiceover, so the burned-in title card in the opening seconds is the one visual element we can cheaply make distinct per variant. A single reused title stamps a byte-identical overlay onto the exact region Instagram scans hardest for near-duplicates; a per-hook title removes that shared signal and keeps each card matching the hook the viewer just heard. (This alone does **not** de-cluster the videos — the shared body + voiceover cap that; see `INSTAGRAM_DEDUP_EVASION_PLAN.md`. It is cheap, on-strategy hygiene, not a silver bullet.)

**Inputs to draw from:**
- `hook_windows` from Step 3c — one window per hook, each with its output-timeline `(start, end)` — **plus that hook's spoken text** (from the Step 1 timeline). The title for card N is derived from hook N's angle.
- The video slug and topic; the manifest `topic` / `hook` fields if present
- The series (from the manifest or inferred from the slug — check SERIES.md for the tone of each series)

**Generate one title per hook** — each punchy, tailored to *that hook's* angle, and in the series tone (a stylized 2–3-second card, not the hook's verbatim wording):
- *tbbt*: punchy question or shocking statement about the architecture
- *updates*: news-style headline
- *interesting-tech / Interesting Tech*: the "impossible thing" framing ("Can a prime number be illegal?")
- *AI Fundamentals*: first-principles question the viewer is already asking

Use `\n` in `title` for line breaks (2 lines usually reads better on mobile). Keep each title short enough to read in 2–3 seconds.

**A card may compress the claim but never contradict it.** The card is burned in, so an error here can only be fixed by re-rendering and re-uploading. Before proposing, check each card against the spoken body from the Step 1 timeline and against the source article: every number, count, and singular/plural in the card has to survive that check. If the body says "chunks", the card may not say "one file". The failure mode to watch for is a card that states the approach the source *rejected* — it will read as the most striking option precisely because it's wrong. See rule 10 in the `hooks` skill.

**The subtitle stays constant across all cards** — it carries the series branding, so keep it identical for every hook (varying the big gold title is what makes the cards visually distinct; the subtitle keeps the brand recognisable):
- *tbbt*: `Tech Behind Big Tech Day {n:tbbt}` (the literal words "Tech Behind Big Tech Day" followed by the episode number — not `#`, and never just `Day {n:tbbt}` on its own)
- *updates*: `Tech & AI Updates #{n:updates}` (the series name followed by the episode number)
- *interesting-tech / Interesting Tech*: subtitle can include the series day count
- *AI Fundamentals*: a short tagline

**Use AskUserQuestion** to present the full set of proposed per-hook titles at once — one option to accept all, plus "Enter my own" — the same pattern as Step 4c. Pair each proposed title with the hook it was derived from so the mapping is clear.

Once approved, write `headings.json` with **one card per hook window** from `hook_windows` — each card carries its OWN `title`, all sharing the same `subtitle`:

```json
[
  { "title": "What Are\nAI Tokens?", "subtitle": "Tech Behind Big Tech Day {n:tbbt}", "start": 0.0, "end": 3.1, "scrim": true },
  { "title": "Why ChatGPT\nBills Per Word", "subtitle": "Tech Behind Big Tech Day {n:tbbt}", "start": 3.1, "end": 6.4, "scrim": true },
  { "title": "You Pay\nBy The Syllable", "subtitle": "Tech Behind Big Tech Day {n:tbbt}", "start": 6.4, "end": 9.8, "scrim": true }
]
```

Field reference:
- `title` — use `\n` for line breaks; `{n:<series>}` is auto-replaced with this video's episode number at render time (series slug from SERIES.md)
- `alt_title` — the card the **mirrored duplicate** of this hook gets (see below); omit when flip duplicates are off
- `subtitle` — optional smaller italic line; also supports `{n:<series>}`
- `start`/`end` — **output-timeline seconds** from `hook_windows` (Step 3c), not source-clip time
- `scrim` — `true` darkens footage behind the text; omit to use the config default

**Mirrored duplicates need their own card.** Check `output.flip` in `config.yaml`: when `apply: duplicate` and `mode` is not `off`, every (or every second) hook is rendered *twice*, and without an `alt_title` the mirror carries a byte-identical card — exactly the shared signal the per-hook titles above exist to remove. So for each hook that gets a duplicate, write a **second** title for the same hook's angle (a different phrasing of the same claim — it must pass the same accuracy check, since both cards sit over the same spoken words):

```json
{ "title": "What Are\nAI Tokens?", "alt_title": "The Hidden\nCost Of A Word", "subtitle": "Tech Behind Big Tech Day {n:tbbt}", "start": 0.0, "end": 3.1, "scrim": true }
```

Include the alt titles in the same AskUserQuestion set. Omitting `alt_title` is a valid choice — the mirror then reuses the hook's card, and it renders faster (the duplicate shares the hook's overlay frames and segment extraction; its own card means its own full render pass).

**Logo resets:** each card's start/end is a logo-reset boundary. A brand re-mentioned after any card edge re-fires its logo in that section — no extra configuration needed.

## Step 4c — Instagram titles (one per hook)

The **on-screen** title card (Step 4b) is a different artifact from the **Instagram/Telegram** title written here. This step names each rendered file and captions the post — it is not burned into the video. `render-hooks` reads `title.json` and writes `output/<video-slug>/<title-slug>.mp4` (one file per hook, grouped in a per-slug folder).

Read `assets/<video-slug>/title.json`. If the first entry has a non-empty `title`, it's already filled in — skip to Step 5. If it's the empty stub (`[]`), generate one title **per hook** — each tailored to *that hook's* angle (the openings differ; the body is shared).

**Style (all titles):**
- **all lowercase**
- **at most one emoji, only if it earns its place.** No default emoji — most titles are stronger without one. Reach for a single emoji only when it actually lands the joke (e.g. the conspiratorial `🤫`); a tacked-on one is worse than none. Never more than one.
- **short & sharp** — roughly 4–8 words
- **no em dashes.** `->`, `w/`, `&`, `/` are fine — that quirky shorthand register is the point
- **quirky and scroll-stopping over informative.** Lead with attitude, understatement, meme energy, or a sneaky reframe — a title that makes someone stop mid-scroll beats one that neatly summarises. It does **not** have to explain (or even literally describe) the video; intrigue is the job. Avoid the flat "how X did Y" / "why X did Y" template unless it's carrying a genuine twist.
- **never assert what the video denies.** The bullet above frees the title from *describing* the video; it does not license contradicting it. Those are different axes, and this rule only bites on the second. A title carrying no factual claim (`the cloud? never heard of it`) has nothing to check — that's the register working as intended. But the moment a title asserts something (a number, a count, a singular/plural, a mechanism), that assertion has to hold against the spoken script and the source article. The trap is a title stating the approach the source *rejected*, since it reads as the punchiest option for exactly the reason it's false. Same check as the Step 4b cards and rule 10 in the `hooks` skill.

Examples of the register: `the cloud? never heard of it` · `dropbox unsubscribed from amazon` · `big tech hates this one weird trick: owning your servers 🤫` · `turns out the cloud was just amazon's computers ☁️`

**Use AskUserQuestion** to present the full set of proposed per-hook titles (one option to accept all, plus "Enter my own"). Once approved, write `title.json` with **one entry per hook** (same order as the hook windows / `headings.json` cards):

```json
[
  { "title": "reddit & kafka -> kubernetes w/ no 🧑❓", "slug": "reddit-kafka-to-kubernetes" },
  { "title": "why reddit ditched kafka 😵", "slug": "why-reddit-ditched-kafka" }
]
```

Field reference:
- `title` — the pretty caption (emoji + lowercase), used verbatim in the Telegram/Instagram post (Step 7)
- `slug` — a filesystem-safe stem for the `.mp4` filename: lowercase, hyphen-separated, no emoji/punctuation. The renderer re-sanitizes it defensively; if you leave it empty it's derived from `title`, and if nothing usable survives the file falls back to `hook{i}.mp4`.
- `alt_title` / `alt_slug` — the caption and filename for this hook's **mirrored duplicate** (see below)

**Mirrored duplicates need their own caption too.** Same trigger as Step 4b: if `output.flip` is `apply: duplicate` with `mode` not `off`, each duplicated hook needs a second Instagram title, written to the same entry as `alt_title` (+ `alt_slug`). It follows every style rule above and stays true to the same spoken body — it's a different angle on the same hook, not a different video:

```json
{ "title": "why reddit ditched kafka 😵", "slug": "why-reddit-ditched-kafka",
  "alt_title": "kafka? we hardly knew her", "alt_slug": "kafka-we-hardly-knew-her" }
```

With `alt_slug` set, that copy is written as `output/<video-slug>/kafka-we-hardly-knew-her.mp4` instead of `<slug><flip-suffix>.mp4`, and `/post-video` captions it from `alt_title`. Leave both out and the mirror keeps the hook's caption and the suffixed filename (today's behaviour).

## Step 5 — Render (one video per hook)

```bash
.venv/bin/reelcut render-hooks config.yaml "assets/<video-slug>/<actual-captions-filename>.captions.json"
```

`render-hooks` reads the hook cards in `headings.json` (one per hook, from Step 4b) and
renders **one video per hook** — each is `hook_i + body`, with the other hooks cut out. The
outputs are grouped in a per-slug folder and named by their Instagram title (Step 4c):
`output/<video-slug>/<title-slug>.mp4`, one per hook (falling back to `hook{i}.mp4` if
`title.json` is empty). Music, captions, and the title card behave exactly as in a normal
render; there is no concatenation.

**More files than hooks?** That is `output.flip` in `config.yaml`. With `apply: duplicate` a
flipped hook is written *twice* — `<title-slug>.mp4` plus `<title-slug><suffix>.mp4` (default
suffix `-flipped`) — so `mode: all` turns 3 hooks into 6 files; with `apply: in_place` the count
is unchanged and the selected hooks are simply mirrored. The mirror is applied to the footage
only, never to the captions or title card. `/post-video` picks the extra files up automatically.

A duplicate with no alt text (Steps 4b/4c) is cheap — it shares the hook's overlay frames and
segment extraction (~80% of a render), repeats only the encode, and posts with the hook's
caption. Give it an `alt_title` card and it becomes its own render pass; give it an
`alt_slug`/`alt_title` in `title.json` and it takes that filename and that caption instead of
the suffixed clone of its hook's.

Report all output paths when done.

*(To render the old single combined video instead — all hooks in sequence — use
`reelcut render config.yaml <captions.json>`, which writes `output/<video-slug>.mp4`.)*

## Step 6 — Lock in a regression fixture

Capture this clip's full word list as a committed real-clip test fixture, so its retake
detection and sentence segmentation are pinned against future regressions (this is how the
"retake cut swallowed the whole body" class of bug gets caught — a synthetic unit test
can't, only a real full-length clip can). Cheap: the data already exists in the transcription
debug report.

```bash
grep -E "→.*conf=" assets/<video-slug>/*.debug.4.post-vad.txt > tests/fixtures/retake/<video-slug>.txt
.venv/bin/python -m pytest tests/test_real_clips.py -q
```

The generic invariants in `tests/test_real_clips.py` (no runaway retake cut; sane sentence
count) pick up the new fixture automatically via glob — no test edit needed, and they must
pass. If the clip has a distinctive line spoken exactly once that you want pinned as
"must survive", copy `test_billion_laughs_unique_content_survives` for the new slug with its
own survivor words. Note: this fixture exercises the *detector/segmenter* on real words; it
does NOT re-run Whisper, so it can't catch transcription-side regressions — those still
require an actual transcribe run to verify.

Commit the fixture alongside the video's other artifacts.

## Step 7 — Publish to Tailscale & notify Telegram

Make every rendered `output/<video-slug>/*.mp4` reachable over Tailscale, then post a
link for each **not-yet-notified** hook video **of this slug** to the Telegram `file-exchange`
topic. The loop is scoped to the current slug's folder so other videos' hooks are never
touched; a `.notified` log additionally dedupes across renders, so re-running only posts newly
rendered hooks. The Telegram caption uses the pretty Instagram title from `title.json`.

**Prerequisites** (set up once, outside this workflow):
- Tailscale installed and this machine joined to the tailnet (`tailscale up`).
- **Operator rights granted**, so `tailscale serve` runs without root:
  `sudo tailscale set --operator=$USER`. Without this, step 1 below fails with
  `401 Unauthorized: must be root` on *every* render and the serve config silently goes stale.
- The local Telegram bot API server running on `{TELEGRAM_API}` (same server used by
  `scrape/telegram.py`).

```bash
# 1. Serve the output directory over Tailscale (idempotent — safe to re-run every render).
#    Abort on failure: a broken serve config must not be papered over by notifying anyway.
tailscale serve --bg --set-path /reels "{PROJECT_ROOT}/output" \
  || { echo "tailscale serve failed — see Prerequisites (operator rights)"; exit 1; }

# 2. Base tailnet URL — read from the SERVE CONFIG, not just .Self.DNSName. Renaming this
#    machine leaves the serve handler keyed to the OLD vhost while .Self.DNSName reports the
#    new one, so links built from .Self.DNSName point at a host the serve config never answers.
TS_HOST=$(tailscale serve status --json | jq -r '.Web | keys[0]' | sed 's/:443$//')
DNS_NAME=$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')
[ -n "$TS_HOST" ] && [ "$TS_HOST" = "$DNS_NAME" ] || {
  echo "serve vhost '$TS_HOST' != device name '$DNS_NAME' — re-run step 1 with operator rights"
  exit 1; }
# This shell may not use the MagicDNS resolver even when the tailnet is healthy, so the
# reachability check below pins the hostname to the tailnet IP. Without this it fails with
# "Could not resolve host" and skips videos whose links are perfectly fine.
TS_IP=$(tailscale ip -4)

# 3. Post one link per hook video to the local Telegram bot API — the file-exchange topic.
#    Scoped to THIS video's slug folder only, never other slugs' videos.
#    The .notified log additionally guards against re-sending on repeat renders (keyed on the
#    slug-relative path so two videos sharing a title-slug can't collide).
SLUG="<video-slug>"
TITLES="{PROJECT_ROOT}/assets/${SLUG}/title.json"
SENT_LOG="{PROJECT_ROOT}/output/.notified"
touch "$SENT_LOG"
for f in "{PROJECT_ROOT}"/output/"${SLUG}"/*.mp4; do
  name=$(basename "$f")
  key="${SLUG}/${name}"
  grep -qxF "$key" "$SENT_LOG" && continue   # already notified — skip
  # Pretty caption: the title.json entry whose slug matches this file's stem; else the filename.
  caption=$(jq -r --arg s "${name%.mp4}" '(map(select(.slug == $s)) | .[0].title) // $s' "$TITLES" 2>/dev/null || echo "$name")
  url="https://${TS_HOST}/reels/${SLUG}/${name}"
  # Never post a link the serve config doesn't actually answer — an unreachable URL must not
  # be logged as notified. --resolve pins DNS to the tailnet IP (see TS_IP note above).
  curl -sfI --max-time 15 --resolve "${TS_HOST}:443:${TS_IP}" "$url" >/dev/null \
    || { echo "UNREACHABLE, not notifying: $url"; continue; }
  PAYLOAD=$(jq -n --arg c "🎬 ${caption} is ready: ${url}" '{content: $c, topic: "file-exchange"}')
  curl -sf {TELEGRAM_API}/telegram/send -H 'Content-Type: application/json' -d "$PAYLOAD" \
    && echo "$key" >> "$SENT_LOG"
done
```

Notes:
- `--set-path /reels` serves privately **within your tailnet** — the link resolves only on
  your own devices. Swap `tailscale serve` → `tailscale funnel` if the link must work
  off-tailnet (public internet).
- `topic` is a **name** the broker resolves to a Telegram thread id via its `config.yaml`
  `projects:` list — `file-exchange` is the configured video topic. A raw numeric id in this
  field fails with `unknown topic name`.
- `output/.notified` records the basename of every hook video already posted. To re-send a
  link, delete its line (or the whole file). `curl -sf` only logs a video as notified when
  the POST returns 2xx, so a failed send is retried on the next run.
- **Renaming this Mac breaks `/reels`.** The serve handler stays keyed to the old
  `<name>.<tailnet>.ts.net:443` vhost, which MagicDNS stops resolving (NXDOMAIN), so every
  link 404s while `tailscale status` still reports a healthy node. Step 2's vhost-vs-DNSName
  check catches this; the fix is re-running step 1 (needs operator rights). If the stale key
  lingers, `tailscale serve reset` then re-run step 1.
