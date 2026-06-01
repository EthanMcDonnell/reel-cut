---
name: scripts
description: >
  Creates short-form video scripts. Use always when asked to write, generate, or
  create a video script, reel script, or short-form content outline.
---

# Scripts

## Voice & Tone
- Conversational, confident, opinionated
- Sound like a friend explaining a topic.
- Use CASUAL, flowing everyday english.

### Questions to Raise
Raise a question to user if at any point:
- something about what is required doesnt make sense or is too vague
- there is contradicting requirements
---

## Target Audience
Tech-curious viewers swiping through social media. Step through concepts clearly and don't assume prior knowledge.

## Non-Negotiable Rules
**Technology First:** Any technology that a high school software engineering student wouldnt understand needs to be explained.
**One topic only:** Don't cram multiple concepts. One thing, explained well.
**Word count:** Use only as many words as the topic needs — never pad to fill length. Hard cap is 225 words. Simple concepts should be fine under 150. Only reach toward 225 when the topic genuinely requires more steps to build understanding.
**Learning payoff:** The viewer must walk away able to explain the core mechanism to someone else. Don't just surprise — genuinely teach. Use analogies to make abstract concepts concrete and sticky.
**Source integrity:** Verify every claim against its source verbatim. If the source says "errors", write errors — not "timeouts". If a stat appears in article B, it doesn't belong in a script about article A.
**One source, one story:** Never merge two sources into one narrative. If two articles cover different events or time periods, they produce two separate stories. Citing both as references for one script will produce an inaccurate account.
**Attribution must match the actual speaker:** "The document says X" is only valid if the document is the literal source of X. If a person quoted in the document said X, attribute it to that person. If the encyclical says one thing and a speaker at the same event says another, they are different claims and must be kept separate. Never let a quote from a speech become a claim of the document, or vice versa.

## Voice and Tone
**Use conversational tone** — Start with natural connectors rather than formal declarative statements. Write like you're talking to a friend.
Apply all rules from the **stop-slop** skill to all script output.
**Creator presence:** Write as a person talking to the viewer, not as a narrator. Use "I" sparingly but deliberately — one personal touch per script is enough. Examples: "I looked this up and it's kind of wild", "this one surprised me", "I've actually used this."
**Emotional vocabulary:** Use feeling words where they're honest — "wild", "kind of crazy", "surprisingly simple", "this is the clever part". Neutral and technical language kills engagement. Don't overdo it — one or two emotional beats per script, not every sentence.
**Second-person address:** Speak directly to the viewer at least once. Use "you" — "every time you open Spotify", "the next time you watch Netflix", "if you've ever wondered why". Makes the content feel personal, not like a lecture.
**Use tangible language over abstract concepts** — Prefer concrete actions and objects. Keep it punchy, not philosophical:
- Good: Concrete verbs and nouns ("buy lava lamps," "ship hard drives," "deleted it")
- Bad: Abstract concepts ("physics vs algorithms," "embracing chaos," "paradigm shift")

## Additional Requirements
**Personal stakes:** Every script must answer "why should I care?" in the SETUP.
## Take the Viewer on a Journey
Structure each script as a journey of discovery — not a lecture. The viewer should feel like they're figuring something as you speak, not being told the answer.
**The arc:** Pose a compelling problem → build tension and curiosity → reveal the solution with satisfaction → land a reframe that changes how they see the world.
**Quantify where possible** — When your sources provide specific numbers, use them instead of vague modifiers. Never fabricate statistics (see Research rule), but prioritize concrete details when they're available:
- Good: Specific counts, percentages, timings, byte sizes, geographic locations (when stated in sources)
- Bad: "many," "massive," "complex," "chaotic," "significant" (vague descriptors)
**Stats must support the claim they're attached to:** Before using a statistic, verify it actually proves the point you're making — not just that it's related to the topic. A number that contradicts or is irrelevant to the claim is worse than no number at all.
**Narrative causality:** Before finalising, read the script as a causal chain. Does A actually cause B? Can B happen before A has occurred? Every step must logically follow from the previous — especially in incident post-mortems where sequence is the whole point.
**Connect components explicitly:** When two separate concepts combine to create an effect, show the connection at the moment it matters — don't introduce them independently and leave the viewer to bridge the gap.
**Determinism vs luck:** If something is guaranteed and attacker-controlled, say so. Vague phrasing implies coincidence. Make precision legible.
**Incremental logic building** — Each sentence should follow logically from the previous. Don't skip steps or jump to abstract conclusions:
- Good: "Encryption needs truly random numbers. Computers are only pseudo-random and follow mathematical algorithms based on an initial seed. If the seed isn't random, nothing generated from it is truly random either."
- Bad: "Computers are deterministic by nature" (too abstract, skips the journey)
**Step-through explanation** — Walk the viewer through the concept as if they're experiencing it in real time. Reveal each piece only when it's needed. The viewer should feel like they're figuring it out alongside you — not being briefed. Each step earns the next.

## Examples & Claims
**Examples must have a verifiable mechanism** — Any example used to illustrate risk must show a clear, traceable path from cause to harm. If you cannot explain how the harm occurred end-to-end, find a better example.
**The solution should feel like a resolution, not a tutorial** — Actionable steps are the payoff to the tension built. Frame them as the answer the viewer has been waiting for, not a how-to guide.
**Avoid redundant qualifiers** — Review phrasing before finalising. If two terms mean the same thing, pick one.
**Be precise about the strength of claims** — Don't imply equivalence between things that differ in weight. Overstatement breaks trust.
**Prime the viewer for the solution** — Before writing the solution section, check whether the setup has built enough tension for the viewer to be pulling toward it. If not, set up the open loop earlier in the script.

## Retention Rules
No sentence should be dead weight. If a sentence doesn't advance the story, raise the stakes, or deepen understanding, cut it.
Never close all loops before the payoff. Reveal just enough to satisfy, then open the next question.
**Retention killers — never do these:**
- Reveal the HOW before the PAYOFF section
- Explain the solution before building curiosity
- Deliver a weak payoff that doesn't earn the hook
- Answer everything upfront
     
## Script Structure
**HOOK**
Hook is first. Immediately follow with one sentence that answers "why should I care?" — state who is affected, quantify the impact, or make the personal threat concrete. Do not reveal the explanation, just the stakes.
**SETUP**
Why this matters. Build curiosity. Open loops. Why is this important/worth watching. Delay the HOW.
**EXTRA**
Explain if required any prerequisite tech/information the viewer may need.
**PAYOFF**
Reveal HOW it works or discuss main content. Build genuine understanding — use analogies where helpful.
**REFERENCES**
URLs for any statistics or data used.

## Exact Output Format
The script and the saved file must both use this exact format — bold headers, no blank lines between sections, no deviations:
```
**SCRIPT**
[CONTENT]
**REFERENCES:** 
[URLs]
```
This is not a documentation template — it is the literal output format. Do not substitute plain text labels, do not add blank lines between sections, do not reformat when saving to file.

## Mandatory Post-Write Review
After writing the script and before saving or delivering it, invoke the `stop-slop` skill on the output. Fix every issue it flags. Do not skip this step.

