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
- Write to the **tellcheck** skill's rules as you draft.
- **Creator presence:** write as a person talking to the viewer, not a narrator. Use "I" deliberately — one personal touch per script ("I looked this up and it's kind of wild", "this one surprised me").
- **Second-person address:** speak directly to the viewer at least once with "you" ("every time you open Spotify", "the next time you watch Netflix").
- **Emotional vocabulary:** use honest feeling words ("wild", "kind of crazy", "surprisingly simple", "this is the clever part") — neutral, technical language kills engagement. One or two beats per script, not every sentence.
- **Tangible over abstract:** concrete verbs and nouns ("ship hard drives", "deleted it"), not abstractions ("paradigm shift", "embracing chaos"). Punchy, not philosophical.

## Series Voice Profiles
The default voice above is the polished explainer. When writing for a series, **read that series' file under `series/<slug>.md`** (indexed in `SERIES.md`) and apply its voice profile — register and target length. That file is the source of truth; do not rely on a copy here. The channel's top performer (the `ai-fundamentals` "Claude usage limits" video) won by sounding casual and native, not polished, so honour each series' register rather than defaulting to polished. If no series is given (or `series` is `misc`), use the default voice above.

**CTA:** the series file's `## CTA & Resources` section owns this — it names the CTA type (comment-bait, follow, or disagreement) and what may be offered. Close with one native line in that shape; keep it conversational, never salesy. Put it under its own **CTA** heading immediately after the **CONCLUSION** section (not folded into CONCLUSION), before **REFERENCES**. Omit the heading only for `misc`, which has no series file and needs no CTA.

## Audience & Scope
- **Audience: the series file's `## Audience` section owns this — read it before writing.** It names who is watching, what they already know, and what has to be explained. That varies more than anything else across the channel: the six run from "anyone curious, may not be a developer" to "practicing engineers who already know the basics" to an audience that resents being explained to at all. Any default written here would be wrong for most of them. Step through concepts clearly and in order whoever is watching; *how much* to explain is the series' call. Only `misc`, which has no series file, falls back to a tech-curious viewer with no prior knowledge.
- **One topic only:** don't cram multiple concepts. One thing, explained well.
- **Technology first:** a term needs explaining when the series' `## Audience` doesn't already list it as known — that section sets the bar, and it is the only thing that does. **Say it in plain words first, then the real term in brackets**: "Canva's front door (the gateway)"; "one running value (an accumulator)". Plain first so the viewer understands the thing before they meet the label. Also make the bracket read as a natural aside — the script is spoken aloud, so it has to sound right said out loud.
  - **This rule outranks the word count.** An unexplained term is never what you cut to fit the cap. If you can't afford to explain a term, the script has too many mechanisms — cut a mechanism, not the explanation. If every remaining mechanism is load-bearing for a hook, that's the signal to split it into two scripts, one per hook.
- **Payoff: the viewer walks away with something, and what that something is depends on the video.** When the video explains a mechanism, the bar is that they could re-explain it to someone else — don't just surprise them, teach, and use analogies to make abstract concepts concrete and sticky. When the video argues a position, the takeaway is the reason to believe it, and teaching is the wrong instinct: explaining a tool to people who use it daily is condescension, not payoff. When it reports news, the takeaway is what changed and what it costs them. Work out which of the three this video is before deciding what the viewer leaves with.
- **Word count: the series file's `**Target length:**` is the cap, not a number written here.** The six series run from under 120 words to 230, so a single figure is wrong for five of them. Read `series/<slug>.md` and write to its range; the linter enforces that same number via `--series`. Reach it by cutting a long draft down, not by budgeting as you write — see **Draft for meaning, then cut** under `## Process`. Only `misc`, which has no series file, falls back to a default of 190. Within the range, use only as many words as the topic needs — never pad. Shorter wins: the channel's 100k-view performers run ~175 words, so reach for the top of a series' range only when the topic genuinely needs the extra steps.

## Source Integrity (non-negotiable)
- **Verify every claim against its source verbatim.** If the source says "errors", write errors, not "timeouts".
- **One source, one story.** Never merge two sources into one narrative. Two articles covering different events produce two separate stories; citing both for one script produces an inaccurate account.
- **Attribution must match the speaker.** "The document says X" is valid only if the document is the literal source of X. If a person quoted in it said X, attribute it to that person. Never let a quote from a speech become a claim of the document, or vice versa.
- **Statistics:**
  - Pull specific numbers from your sources instead of vague modifiers — counts, percentages, timings, byte sizes, locations. Never fabricate them.
  - A stat must support the exact claim it's attached to, not just relate to the topic. A number that contradicts or is irrelevant to the claim is worse than none.
  - A stat that appears in one article doesn't belong in a script about another.
  - **Credit the whole cause, not the nearest one.** When the source attributes an outcome to a system, a rollout, or a set of changes, the script may not pin it on whichever single component the video happens to be about. *"PGKeeper prevented more than 20 incidents"* covers admission control, connection rate limiting, pool warming and fair sharing; "the unfair queue stopped 20 outages" is a narrower, unsourced claim. Either name the real cause, or keep the component and restore the scope with the qualifier that makes it true — "one of the reasons", "part of why", "among other things".
  - **Scope qualifiers outrank the word count.** The words that keep a claim honest — "among other things", "under heavy load", "one of four" — are never what you cut to fit the cap, any more than an unexplained term is. They cost two or three words and they are the difference between true and false. If the sentence won't fit with them, the stat comes out instead, or the words come from tightening elsewhere. Before saving, check every outcome number: does the source credit it to the same thing this sentence credits it to?

## Narrative & Retention
Take the viewer on a journey of discovery, not a lecture — they should feel like they're figuring it out alongside you.

- **The arc:** pose a compelling problem → build tension and curiosity → reveal the solution with satisfaction → land a reframe that changes how they see things. **This is the shape for a video that explains something, which is most of them but not all.** A video that argues a position is shaped by its argument, and a news video by what changed; forcing either into problem→tension→reveal invents a problem the material doesn't have and makes the video sound engineered. Everything below this bullet — incremental logic, causality, one antecedent per pronoun, earning transitions — applies whatever the shape.
- **Incremental logic:** each sentence follows from the last — don't skip steps or jump to an abstract conclusion. Reveal each piece only when it's needed; each step earns the next.
  - Good: "Encryption needs truly random numbers. Computers are only pseudo-random, following an algorithm from an initial seed. If the seed isn't random, nothing built from it is either."
  - Bad: "Computers are deterministic by nature." (too abstract, skips the journey)
- **Narrative causality:** read the finished script as a causal chain. Does A actually cause B? Can B happen before A? Every step must follow from the previous — critical in incident post-mortems where sequence is the whole point.
- **Connect components explicitly:** when two concepts combine to create an effect, show the connection at the moment it matters — don't introduce them separately and leave the viewer to bridge the gap.
- **Rejected alternatives earn the solution:** when the source rejects an approach before landing on the real one, give the rejection its own beat with the consequence spelled out. Compressed into a subordinate clause it makes the solution look arbitrary — the viewer never feels why the obvious fix failed, so "here's the clever part" is unearned.
  - Bad: "Redis was the obvious fix, but it isn't durable and you're still babysitting a cluster." (two undefined objections in one clause)
  - Good: "Redis was the obvious fix, but Redis isn't a durable copy, so MySQL stays underneath and they'd be babysitting a cluster on top."
- **No unexplained parameters:** any number that is a design knob — window sizes, intervals, chunk sizes, thresholds — carries its reason in the same or next sentence, or gets cut. Introduce it at the beat where it does work, never earlier, and never twice.
  - Bad: "every gateway holds 12 hours of those in memory" (why 12?)
  - Good: "a booting pod only grabs the last 12 hours, since every cookie refreshes by then"
- **Every tease names its object.** Calling something "a weird limit", "one strange rule", or "a problem nobody expects" promises a specific thing, and the script owes the viewer that thing by name and number. Explaining the mechanism around it does not discharge the promise — "every connection spawns a separate process, so connections are expensive and capped" says why the limit exists without ever saying what it is, and the loop the tease opened never closes. Name it in the same or next sentence, with the source's own figure, or don't tease it.
  - Bad: "Postgres has a weird limit. Every connection spawns a whole separate program with its own memory. Connections are expensive and capped."
  - Good: "…with its own memory. Connections are so expensive that each database machine only takes about a hundred at a time."
  - The figure has to come from *this* video's source. Reaching into a second article for a number because the primary one wasn't read closely enough is the same failure wearing a disguise, and it breaks "a stat that appears in one article doesn't belong in a script about another" above.
- **Every relative stat names its baseline:** outcome numbers need no design reason — nobody chose 87.5% — but a percentage, a fraction, or a multiple is meaningless without the thing it's measured against. "87.5% smaller", "3x faster", "cut in half" all answer *compared to what?* in the same sentence, or they're just a number that sounds impressive. The source almost always states the baseline; dropping it is a comprehension bug, not a trim.
  - Bad: "That packing cut the cache's memory by 87.5%." (87.5% smaller than what?)
  - Good: "Before, each revocation was several Java objects, and every object carries its own overhead. Packed flat, the cache got 8 times smaller."
  - Prefer the plainer form when the source gives both — "8 times smaller" lands in speech where "87.5%" makes the viewer do arithmetic.
  - The baseline is a *mechanism*, not just a prior value. "Smaller than the old version" restates the stat; "several Java objects, each with its own overhead" tells the viewer why the new number is possible. Take the source's reason, not just its comparison.
- **Never narrate the script's own structure.** Writing to a fixed shape (a series `## Structure`, or the SETUP/PAYOFF arc) makes it tempting to speak the section labels: "here's where X wins" before the turn, "that's what this is about" after the opening, "which brings me to". The viewer isn't reading the outline and doesn't need signposts — the content carries the turn, or the turn hasn't been written. This is the loudest AI tell in a spoken script, because nobody talking to a friend announces their next paragraph.
- **One antecedent per pronoun:** never open a sentence with It/They/This when the previous sentence introduced more than one noun. Name the thing instead.
- **Transitions carry weight:** "then", "so", "and now" only earn their place when the previous sentence set up what follows. A bare "Then X started happening" after a present-tense standing fact has no moment to follow from — the connective fakes a causal link the script never made. Supply the hinge that makes the turn inevitable before you turn.
  - Bad: "…a deny-list every gateway keeps in memory. Then deploys started hurting."
  - Good: "…a deny-list every gateway keeps in memory. And memory starts empty. So every deploy…"
- **Watch the tense seam:** setup runs in present tense (how the system works today), the problem runs in past (what went wrong). Crossing between them without a bridge is where flow breaks most often — that's the same seam the example above repairs.
- **Determinism vs luck:** if something is guaranteed and attacker-controlled, say so. Vague phrasing implies coincidence; make precision legible.
- **Examples need a verifiable mechanism:** any example illustrating risk must show a traceable path from cause to harm. If you can't explain it end-to-end, find a better example.
- **Be precise about claim strength:** don't imply equivalence between things of different weight. Overstatement breaks trust.

**Retention:**
- Open the first loop in the very first SCRIPT line. The 42.zip winner did it in one breath: "It's a 42 kilobyte file, that's it, or at least that's what it seems." State the mundane fact, then undercut it so the viewer has to stay.
- No dead weight — if a sentence doesn't advance the story, raise the stakes, or deepen understanding, cut it. Short sentences carry the reveal; vary length but keep the spine tight.
- Hold the loops — never close them all before the payoff. Reveal just enough to satisfy, then open the next question. If the setup hasn't built enough tension, open the loop earlier.
- The solution is a resolution, not a tutorial — frame actionable steps as the answer the viewer has been waiting for, not a how-to guide.
- Never reveal the HOW before the PAYOFF, explain the solution before building curiosity, or deliver a payoff too weak to earn the hook.

**Open-loop phrases** — for videos built on a reveal, where tension between the question and the answer is what holds the viewer. They are not a checklist to sprinkle through every script: in a first-person argument they read as stalling (there is no reveal being withheld, so the phrase promises something that never arrives), and under ~120 words there is no room to open a loop and still close it. Use one where the script genuinely has something withheld, and none where it doesn't. A canned phrase over a script with nothing to reveal is the loudest slop in this file.
- Partial answers: answer the what, withhold the how
- "But here's the part nobody talks about…"
- "That's not even the clever part…"
- "But how do they actually do this?"
- "There's a reason this works so well…"
- "This saves them millions, but there's more…"
- "So you might be wondering…" (before the payoff)

## Script Structure
**VIDEO TYPE** — the series slug, one line, first thing in the file. It's the only record of which series the saved script belongs to once it's sitting in `assets/`, so it has to be right.
**HOOK** — comes first. **If the hook leaves "why should I care?" unanswered, the next sentence answers it** — who's affected, the scale of impact, or the concrete personal threat. Reveal the stakes, not the explanation. Check the hook first rather than writing this line by reflex: a hook that already names the stakes ("if you install this month's Windows update, it is likely bricking your PC") or that stakes a claim the viewer holds an opinion about has done this job, and a stakes sentence after it is a sentence about nothing. That is what "you push, pull and merge every single day, and that's what this is about" was — restating the hook's premise as if it were new. When the hook has covered it, open on the content instead.
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
**VIDEO TYPE**
[series slug, or misc]
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

The one exception is line breaks inside the spoken body: once saved, `format_script.py` re-flows `**SCRIPT**` and `**CONCLUSION**` to one sentence per line so the script is readable off a phone while filming. Those breaks are correct — never collapse the body back into a paragraph when editing a saved script.

## Process
- **Questions to raise:** ask the user before writing if any requirement is vague, doesn't make sense, or contradicts another.
- **Draft for meaning, then cut:** write the first draft to explain the thing properly and ignore the word cap while doing it. Budgeting from the first sentence is what stops an explanation being written at all, and an explanation never written leaves nothing behind to notice — unlike one you cut, which you had to look at first. Bringing it down to the series cap is a separate pass afterwards, and that pass cuts **mechanisms, never explanations**: if it still won't fit, the script has too many moving parts, so drop one and keep what survives fully explained.
- **Mandatory post-write review:** after writing and before saving or delivering, invoke the **tellcheck** skill on the output and fix every issue it flags. Do not skip this step. Two findings recur on every script and are not defects: `bold_overuse` fires on the mandated `**HOOK**` / `**SCRIPT**` / `**CONCLUSION**` headers, because the no-blank-lines format makes the whole file one paragraph, and `magic_adverbs` fires on "literally" wherever a hook uses the channel's proven `So [X] literally [absurd action]` template. Leave both, and never write a `tellcheck-disable-line` comment into a script to silence them — the file is parsed by `lint_script.py` and by produce-video, and a stray line breaks the format.
- **Mandatory comprehension pass:** tellcheck catches prose slop, not missing logic. So also read the script back as a viewer who knows nothing about the topic and, for every noun and every number, ask "was I told why this exists?" — for every percentage, fraction, or multiple, also ask "was I told what it's measured against?" — for every thing the script calls weird, surprising, clever, or strange, ask "was I ever told what it actually is?" — for every gloss, ask "does this assume something the viewer was never told?", because explaining a term's consequence while presupposing its mechanism ("a wrong guess stalls the CPU" takes for granted that the CPU guesses at all) explains nothing — and for the fix at the centre of the video, ask "was I told what it costs?", because a change shown with only its upside reads as magic instead of a trade. Anything that arrives unexplained either earns a clause or gets cut — and the words come from tightening elsewhere, not from raising the cap.
- **Mandatory jargon sweep:** as part of that pass, list out every technical term and proper noun in the draft — infrastructure words ("gateway", "pod", "cluster"), storage and protocol names ("S3", "MySQL", "Redis"), and complexity or systems vocabulary ("O(N squared)", "durable", "idempotent"). Go term by term against the series' `## Audience`: a term that section lists as known stays bare, and everything else gets the **Technology first** treatment at first mention, or gets cut. Listing them explicitly is the point — jargon reads as normal prose to whoever wrote it, so it only surfaces when you enumerate it. **Write the list out in your reply, one line per term with its verdict, before saving.** A sweep done in your head is not a sweep: you reread your own prose, it all looks obvious because you wrote it, and nothing surfaces.
