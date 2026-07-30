---
name: scripts
description: >
  Creates short-form video scripts. Use always when asked to write, generate, or
  create a video script, reel script, or short-form content outline.
---

# Scripts

## Voice & Tone
- **Match the creator's real delivery voice.** If `.claude/voice/voice-profile.md` exists, read it first — it is mined from the user's actual top-performing transcripts (openers like "So …", the "literally" disbelief intensifier, signature reframe-closers, real vocabulary, ~3.1 words/sec pacing). It is the cross-series delivery layer; the per-series file sets register on top of it. Refresh it with `/voice-profile`.
- Conversational, confident, opinionated — write like a friend explaining a topic in casual, flowing, everyday English. Open with natural connectors, not formal declarative statements.
- Write to the **stop-slop** skill's rules as you draft.
- **Creator presence:** write as a person talking to the viewer, not a narrator. Use "I" deliberately — one personal touch per script ("I looked this up and it's kind of wild", "this one surprised me").
- **Second-person address:** speak directly to the viewer at least once with "you" ("every time you open Spotify", "the next time you watch Netflix").
- **Emotional vocabulary:** use honest feeling words ("wild", "kind of crazy", "surprisingly simple", "this is the clever part") — neutral, technical language kills engagement. One or two beats per script, not every sentence.
- **Tangible over abstract:** concrete verbs and nouns ("ship hard drives", "deleted it"), not abstractions ("paradigm shift", "embracing chaos"). Punchy, not philosophical.

## Series Voice Profiles
The default voice above is the polished explainer. When writing for a series, **read that series' file under `series/<slug>.md`** (indexed in `SERIES.md`) and apply its voice profile — register, target length, and CTA. That file is the source of truth; do not rely on a copy here. The channel's top performer (the `ai-fundamentals` "Claude usage limits" video) won by sounding casual and native, not polished, so honour each series' register rather than defaulting to polished. If no series is given (or `series` is `misc`), use the default voice above.

**CTA (optional):** when it fits the series, close with one native line — comment-bait ("Comment X and I'll send you …") or a follow that ties to the topic. Keep it conversational, never salesy. Put it under its own **CTA** heading immediately after the **CONCLUSION** section (not folded into CONCLUSION), before **REFERENCES**.

## Audience & Scope
- **Audience:** tech-curious viewers swiping through social media. Step through concepts clearly; assume no prior knowledge.
- **One topic only:** don't cram multiple concepts. One thing, explained well.
- **Technology first:** any technology a high-school CS student wouldn't understand needs explaining.
- **Learning payoff:** the viewer must walk away able to explain the core mechanism to someone else. Don't just surprise them — teach. Use analogies to make abstract concepts concrete and sticky.
- **Word count:** use only as many words as the topic needs — never pad. Shorter wins: the channel's 100k-view performers run ~175 words. Hard cap 190. Simple concepts should land under 130; reach toward 190 only when the topic genuinely needs more steps.

## Source Integrity (non-negotiable)
- **Verify every claim against its source verbatim.** If the source says "errors", write errors, not "timeouts".
- **One source, one story.** Never merge two sources into one narrative. Two articles covering different events produce two separate stories; citing both for one script produces an inaccurate account.
- **Attribution must match the speaker.** "The document says X" is valid only if the document is the literal source of X. If a person quoted in it said X, attribute it to that person. Never let a quote from a speech become a claim of the document, or vice versa.
- **Statistics:**
  - Pull specific numbers from your sources instead of vague modifiers — counts, percentages, timings, byte sizes, locations. Never fabricate them.
  - A stat must support the exact claim it's attached to, not just relate to the topic. A number that contradicts or is irrelevant to the claim is worse than none.
  - A stat that appears in one article doesn't belong in a script about another.

## Narrative & Retention
Take the viewer on a journey of discovery, not a lecture — they should feel like they're figuring it out alongside you.

- **The arc:** pose a compelling problem → build tension and curiosity → reveal the solution with satisfaction → land a reframe that changes how they see things.
- **Incremental logic:** each sentence follows from the last — don't skip steps or jump to an abstract conclusion. Reveal each piece only when it's needed; each step earns the next.
  - Good: "Encryption needs truly random numbers. Computers are only pseudo-random, following an algorithm from an initial seed. If the seed isn't random, nothing built from it is either."
  - Bad: "Computers are deterministic by nature." (too abstract, skips the journey)
- **Narrative causality:** read the finished script as a causal chain. Does A actually cause B? Can B happen before A? Every step must follow from the previous — critical in incident post-mortems where sequence is the whole point.
- **Connect components explicitly:** when two concepts combine to create an effect, show the connection at the moment it matters — don't introduce them separately and leave the viewer to bridge the gap.
- **Rejected alternatives earn the solution:** when the source rejects an approach before landing on the real one, give the rejection its own beat with the consequence spelled out. Compressed into a subordinate clause it makes the solution look arbitrary — the viewer never feels why the obvious fix failed, so "here's the clever part" is unearned.
  - Bad: "Redis was the obvious fix, but it isn't durable and you're still babysitting a cluster." (two undefined objections in one clause)
  - Good: "Redis was the obvious fix, but Redis isn't a durable copy, so MySQL stays underneath and they'd be babysitting a cluster on top."
- **No unexplained parameters:** any number that is a design knob — window sizes, intervals, chunk sizes, thresholds — carries its reason in the same or next sentence, or gets cut. Introduce it at the beat where it does work, never earlier, and never twice. Outcome numbers ("memory dropped 87.5%") stand alone and need no justification.
  - Bad: "every gateway holds 12 hours of those in memory" (why 12?)
  - Good: "a booting pod only grabs the last 12 hours, since every cookie refreshes by then"
- **One antecedent per pronoun:** never open a sentence with It/They/This when the previous sentence introduced more than one noun. Name the thing instead.
- **Determinism vs luck:** if something is guaranteed and attacker-controlled, say so. Vague phrasing implies coincidence; make precision legible.
- **Examples need a verifiable mechanism:** any example illustrating risk must show a traceable path from cause to harm. If you can't explain it end-to-end, find a better example.
- **Be precise about claim strength:** don't imply equivalence between things of different weight. Overstatement breaks trust.

**Retention:**
- Open the first loop in the very first SCRIPT line. The 42.zip winner did it in one breath: "It's a 42 kilobyte file, that's it, or at least that's what it seems." State the mundane fact, then undercut it so the viewer has to stay.
- No dead weight — if a sentence doesn't advance the story, raise the stakes, or deepen understanding, cut it. Short sentences carry the reveal; vary length but keep the spine tight.
- Hold the loops — never close them all before the payoff. Reveal just enough to satisfy, then open the next question. If the setup hasn't built enough tension, open the loop earlier.
- The solution is a resolution, not a tutorial — frame actionable steps as the answer the viewer has been waiting for, not a how-to guide.
- Never reveal the HOW before the PAYOFF, explain the solution before building curiosity, or deliver a payoff too weak to earn the hook.

**Open-loop phrases** — drop these in throughout SETUP and PAYOFF to hold tension:
- Partial answers: answer the what, withhold the how
- "But here's the part nobody talks about…"
- "That's not even the clever part…"
- "But how do they actually do this?"
- "There's a reason this works so well…"
- "This saves them millions, but there's more…"
- "So you might be wondering…" (before the payoff)

## Script Structure
**HOOK** — comes first. Immediately follow with one sentence answering "why should I care?": who's affected, the scale of impact, or the concrete personal threat. Reveal the stakes, not the explanation.
**SETUP** — why this matters. Build curiosity, open loops, delay the HOW.
**EXTRA** — any prerequisite tech or context the viewer needs (only if required).
**PAYOFF** — reveal HOW it works. Build genuine understanding; use analogies where helpful.
- "OpenAI solves this with PostgreSQL, read replicas spread across regions, and aggressive edge caching."
- "Netflix ships hard drives to ISPs and preloads content during off-peak hours."
**CONCLUSION** — one sentence reinforcing the main message and landing the reframe.
- "They chose simplicity over complexity, then scaled it to 800 million users."
- "Sometimes the best engineering solution is shipping hard drives around the world."
- "That's how you serve a billion users without breaking."
**REFERENCES** — URLs for any statistics or data used.

## Exact Output Format
The script and the saved file must both use this exact format — bold headers, no blank lines between sections, no deviations. SETUP, EXTRA, and PAYOFF fold into the single **SCRIPT** block. `**CTA**` is optional; include it only when there is a CTA, and always between **CONCLUSION** and **REFERENCES**:
```
**HOOK**
[CONTENT]
**SCRIPT**
[CONTENT (SETUP, EXTRA, PAYOFF)]
**CONCLUSION**
[CONTENT]
**CTA**
[one CTA line — omit this header entirely if there is no CTA]
**REFERENCES:** 
[URLs]
```
This is not a documentation template — it is the literal output format. Do not substitute plain text labels, do not add blank lines between sections, do not reformat when saving to file.

## Process
- **Questions to raise:** ask the user before writing if any requirement is vague, doesn't make sense, or contradicts another.
- **Mandatory post-write review:** after writing and before saving or delivering, invoke the **stop-slop** skill on the output and fix every issue it flags. Do not skip this step.
- **Mandatory comprehension pass:** stop-slop catches prose slop, not missing logic. So also read the script back as a viewer who knows nothing about the topic and, for every noun and every number, ask "was I told why this exists?" Anything that arrives unexplained either earns a clause or gets cut — and the words come from tightening elsewhere, not from raising the cap.
