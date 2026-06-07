---
name: produce-script
description: Produce a single video script from a user-supplied prompt (URL, phrase, DB article ID/title, or Obsidian video idea reference)
tools: Read, Glob, Edit, Bash, WebFetch, WebSearch, Agent
model: sonnet
permissionMode: default
---
Produces a complete, validated video script from a user-supplied prompt. The prompt may be a URL (engineering blog post, article), a phrase or topic idea, a reference to an article in `scrape/db/`, or a reference to an existing file in the Obsidian Video Ideas folder (`Vault/Videos/Video Ideas/`).

## DB Access

Articles and rejected topics are stored in `scrape/db/influencer.db` (SQLite). Use the query CLI via Bash:

- List tbbt articles: `.venv/bin/python scrape/query.py articles tbbt --limit 10 --tier passing --status viewed`
- List updates articles: `.venv/bin/python scrape/query.py articles updates --limit 5 --status viewed`
- Search by keyword: `.venv/bin/python scrape/query.py articles tbbt --search "keyword"`
- Mark as viewed: `.venv/bin/python scrape/query.py mark-viewed <series> <url>`
- Mark as done: `.venv/bin/python scrape/query.py mark-done <series> <url>`
- Check rejected topics: `.venv/bin/python scrape/query.py rejected --series <series>`

All commands output JSON. Run from the project root (`/Users/ethanmcdonnell/Documents/reel-cut`).

## Stage 0 — Resolve Prompt

The user's prompt is: `$ARGUMENTS`

Determine the prompt type and resolve it to a `topic_package`. Try each check in order:

### 1. If the prompt looks like a URL

- Fetch the article content using the Bash tool:

  ```bash
  .venv/bin/python scrape/single_scrape.py --json "<URL>"
  ```

  This uses the correct fetch method (rss/scrape/playwright/reddit) based on the source config. Use the returned `title`, `content`, `company`, and `series` fields as the research base.
- If `single_scrape.py` returns an error or empty content, fall back to WebFetch as a last resort.
- Set `series` from the returned `series` field if present; otherwise infer from content (tbbt for eng blog posts, updates for Claude/AI tooling).
- **Mark as read:** if the article's URL matches an entry in the tbbt or updates table, run: `.venv/bin/python scrape/query.py mark-done <series> "<url>"`

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

- Set `series` to the matched article's series (`tbbt` or `updates`).
- **Mark as read:** `.venv/bin/python scrape/query.py mark-done <series> "<url>"`

### 3. If the prompt references a file (path, filename, or Obsidian note title)

- Search for a matching `.md` file in `/Users/ethanmcdonnell/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/Videos/Video Ideas/` using Glob.
- Read the matched file. Extract topic, angle, and any URLs listed in the file.
- If URLs are present, fetch the first one for additional research.
- Set `series` to `misc`.

### 4. If the prompt is a plain phrase or topic idea

- Search both series tables for unread articles matching keywords from the prompt:
  - `.venv/bin/python scrape/query.py articles tbbt --unread --search "<keyword>"`
  - `.venv/bin/python scrape/query.py articles updates --unread --search "<keyword>"`
  If a strong match exists, treat it as a DB reference (case 2 above).
- Otherwise, use WebSearch to find 1–2 authoritative sources (official eng blog, release notes, or reputable article).
- Extract the core insight, surprising stat or benchmark, and angle from the search results.
- Set `series` to whichever fits best (tbbt / updates / misc).

### Reddit — Linked Article Fetch

After fetching a Reddit article, scan `content` and `description` for external URLs and fetch each one via `single_scrape.py --json`. Append results to `FULL_CONTENT`. If any fetch fails or returns empty content, abort: "Failed to fetch linked article: `<url>`."

### Source Access Check

If the primary source returned an error or empty content, stop: "⚠️ Couldn't fetch `<url>` directly — research is from search snippets only. Paste the article text to continue, or type 'proceed' to write from secondary sources."

We then want to collate all information as well as provide some summarisation and insight for future steps what are key points across sources that could be used.

Build the following `topic_package` once resolved:

```
TOPIC: <concise topic title>
SOURCE_URLS: <comma-separated list of source URLs, or "none">
FULL_CONTENT: <complete raw article content>
KEY_DISCUSSION_POINTS: <summarise/provide key talking points>

(if multiple sources, create multiple)
TOPIC: <concise topic title>
SOURCE_URLS: <comma-separated list of source URLs, or "none">
FULL_CONTENT: <complete raw article content>
KEY_DISCUSSION_POINTS: <summarise/provide key talking points>

```

If no usable content can be resolved from the prompt, abort with: "Could not resolve prompt to a scriptable topic — please provide a URL or more specific phrase."

## Stage 1 — Hook Generation

Invoke the `hooks` skill. Use the rules and patterns it returns to write 3 hooks for the `topic_package`. Store them as `HOOK_1` through `HOOK_3`, each with a `PATTERN` and `TEXT` field.

## Stage 2 — Hook Approval

Ask the user which hook they prefer
Use confirmed hook in Stage 3.

## Stage 3 — Script Writing

Invoke the `scripts` skill and `stop-slop` skill, use the full `topic_package` and confirmed hook (PATTERN + TEXT) to create a captivating short form content script for platforms like Instagram Reels. 

For every claim, stat, or quote that will appear in the script:

1. **Locate it verbatim** in `FULL_CONTENT`. Drop any quote that doesn't appear there.
2. **Confirm the correct subject.** Ask: who said this — the document, a person quoted in it, or a secondary source? A quote from someone's speech is not the document's claim. A fact from source B is not from source A. Never collapse two sources into one sentence.
3. **Check the attribution in the script matches the actual speaker/document.** If the encyclical says X and a speaker says Y, they must be attributed separately. "The document points out..." is only valid if the document is the actual source of that sentence.
4. **Articles often contain third-party quotes.** A blog post may include testimonials, customer quotes, or researcher statements. A claim inside a quoted block belongs to the quoted person — not the publication. Do not write "[Company] says X" if X came from a quoted third party inside their article.

Any claim that cannot be traced to a specific sentence in `FULL_CONTENT` is cut, not paraphrased from memory.

## Stage 3.5 — Script Writing
After the script is written, save it:

1. Save to `/Users/ethanmcdonnell/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault/Videos/Videos To Do/`
2. Use kebab-case filename describing the topic (e.g. `netflix-cdn-architecture.md`)
3. No empty lines in the saved file
4. Ignore any other existing `.md` files in the `Videos/` folder — do not read, reference, or modify them

Wait for the saved file path before continuing.

**Mark the videos ideas `status:` frontmatter field:** update it from `new` to `done` using the Edit tool.

## Stage 4 — Source Screenshots for Video
### Step 4.1: Extract verbatim snippets with context

For each source URL used in the script, identify up to 6 verbatim phrases that are able to support sections of the script users may be   
questioning whther the claim is true or where the information was sourced from. So core claims of the script, key statistic claims etc that were quoted, paraphrased, or used as factual support in the script. For each snippet, also write a `context` (the **exact verbatim script line**) that the image will be shown in video with snippet highlighted. Think about what would support the output video to confirm to audience the validity of what I am saying.
Each snippet must:
- Appear **verbatim** in `FULL_CONTENT` and be explicitly referenced or used as supporting content for a specific script line
- Be **40–200 characters** — include enough surrounding words that the snippet is readable in isolation as evidence
- Be the **specific phrase that directly maps to the script sentence**. 

**Good snippet candidates:**
- The source's version of the script's big claims — sentences in the article that directly back up the bold assertions in the script. These are the screenshots that give the video credibility.
- Direct quotes from named people
- Specific named claims with dollar figures, dates, or numbers
- Ask yourself what does the viewer need to believe for the rest of the video to land?

**Skip:** generic setup sentences, supporting detail that isn't itself a strong claim, navigation text, or phrases so short they carry no standalone meaning.

The `context` field must be the **exact verbatim script line** this screenshot supports — copy it word-for-word from the script.

### Step 4.2: Run the screenshot tool

For each source URL, run:

```bash
.venv/bin/python scrape/screenshot.py \
  --url "<source_url>" \
  --output-dir "assets/<video-slug>/" \
  --snippets '[{"text": "verbatim phrase 1", "context": "Script line: ..."}, {"text": "verbatim phrase 2", "context": "Script line: ..."}, ...]'
```

Where `<video-slug>` matches the saved script filename (without `.md`).

If a source URL is a Reddit post, use the linked article URL instead (already fetched in Stage 0).

If `skipped` is non-null in the JSON result, report the reason so the user knows which screenshots are missing.

## Final Output

Report to the user:

- Prompt resolved as: [URL / file reference / phrase] → [TOPIC] ([SERIES])
- Script saved to: [file path]
- Screenshots saved to: `assets/<slug>/`
- Any warnings (near-tie runner-up available, skipped screenshots, etc.)
