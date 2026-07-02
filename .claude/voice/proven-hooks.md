# Proven Hooks — what's winning channel-wide

Cross-series synthesis of the user's own top-performing reels, from real
engagement data (social-cockpit `/api/scripts/top`). Regenerate with
`/voice-profile`.

**Scope:** this file holds the *channel-wide* lessons only. The actual
per-video hooks live in each series' file under **Best Hooks** (`series/*.md`,
indexed in `SERIES.md`) — that's the per-audience source of truth. Read this for
the meta-patterns; read the series file for the hooks that won in that series.

## What's winning (across all series)

- **A named technology lands in the first ~4 words of every top hook** — Claude,
  42.zip, Windows, GitHub, Netflix, ChatGPT, Cloudflare, Salesforce/Kubernetes,
  Kafka, Anthropic, React. The viewer self-qualifies on the name instantly. Never
  genericize it (hook-skill rule 7, confirmed by the data).
- **A specific number is the next-strongest lead element** — 42(kb), 900%, 800
  million, 47%, "a billion". The two engagement monsters pair a name with either a
  number or a frustration.
- **Two templates carry the top ranks, reusable verbatim:**
  - `"What is [X] and why was it so dangerous?"` — won for 42.zip *and* the billion
    laughs attack. Reliable for any mystery artifact / named exploit.
  - `"So [Company] literally [absurd-sounding action]."` — won for Netflix
    (ships servers) and Cloudflare (uses lava lamps). "literally" sells the disbelief.
- **`[Company] just [did X]`** (Recent Update) carries the news items — keep the
  action short and let the number/juxtaposition shock.
- **Second-person threat is rare but disproportionately strong** — only the
  rank-1 and rank-3 hooks use "you/your", and they outrank their reach. When the
  topic touches the viewer's own work, make the threat personal.
- **Typical hook length is 9–14 words.** Below ~6 or above ~16 underperforms for
  the topic's reach.

## The biggest engagement lever: comment-bait CTA

The #1 video by engagement carries **3037 comments vs <300 on every other video** —
its lead is almost entirely comments, driven by its `Comment "Claude" and I'll send
you [the script]` CTA. The hook earns the watch; the **comment-bait CTA spikes the
engagement metric**. This is why `produce-script` Stage 3.6 builds a real lead
magnet + keyword CTA. Pair a strong hook with a genuinely-wanted lead magnet
whenever the topic allows — it is the single biggest lever in the data.

## Channel-wide exemplars (for `misc` scripts with no series)

The three best-performing hooks overall, as reference when there's no series file:
- "Everyone tells you to use Claude but no one explains how the token limits actually work." (Hidden Knowledge)
- "What is 42.zip and why was it so dangerous?" (What Is X)
- "GitHub just raised the price of Copilot by 900%." (Recent Update)
