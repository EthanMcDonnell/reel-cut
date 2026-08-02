---
name: hooks
description: >
  Use always when writing, generating, evaluating video hooks, whenever hooks need to be written or improved or even if the user just says "write a hook", "make this punchier", "give me options", or asks for hooks for any tech topic. Contains rules and a quality checklist. Invoke this skill. Do NOT skip this skill if hooks are involved in any way.
---

# Hooks

## What Makes a Hook Work

You have 1.3–3 seconds to stop the scroll. A strong hook does two things simultaneously:

- **Reveals the WHAT** — the surprising fact, reversal, or counterintuitive truth
- **Withholds the HOW** — the explanation the viewer now needs

The WHAT creates the stop. The missing HOW creates the stay.

**Weak vs. strong:** a hook that announces the subject and its explanation together has spent its tension before the viewer has stopped ("Today I'll explain how *X* works"). A hook that states the surprising thing and leaves the reason unsaid keeps it. Same subject either way — the difference is only which half you withhold.

A surprising fact stops the scroll. An unresolved implication or personal threat makes them *stay*. Ask yourself: after hearing this hook, does the viewer *need* to know what comes next?

## Rules

1. **Single fluent sentence.** One short concise sentence as the hook.
2. **No em dashes (—). Ever.** Not even once. If you feel the urge to write "X — Y", rewrite it as a subordinate clause: "X because/while/until/but Y".
3. **No triplet staccato.** Don't write three short punchy fragments in a row ("Fast. Cheap. Scalable.").
4. **Promise exactly what you deliver.** The video must give the viewer what the hook implied — no bait-and-switch.
5. **Cut every unnecessary word.** Shorter = more confident = more scroll-stopping.
6. **Trigger one emotion or open one loop.** Curiosity, threat, awe, identity challenge. If a hook does none of these, rewrite it.
7. **Lead with the most compelling raw element.** Before writing, identify the strongest hook element in the topic: a name, a number, a stat, a reversal. Make sure it survives into the final hook. Do not abstract it away.
8. **Make the threat personal when it applies to the viewer.** "Your data" beats a statistic about companies. Use "you/your" when the viewer is the one at risk.
9. **Make bold declarative claims when the facts support it.** "X just killed Y" beats "X may be changing Y." If the claim is true, say it directly. Keep it short.

## Where Patterns Come From

This skill is the craft. **Which pattern wins belongs to the audience, so it lives with that audience** — no pattern library here, and none carried from memory. Read both sources below before generating, every time:

1. **The series file.** When a `SERIES` is known, read `series/<slug>.md` — every slug is indexed in `SERIES.md`. Its `## Best Hooks` section is the source of truth for that series: which patterns win, the register the hook has to be spoken in, the hooks that have actually shipped, and their real numbers.
2. **`.claude/voice/proven-hooks.md`**, if it exists — the creator's own shipped hooks across every series, ranked by real engagement, with the recurring templates distilled. Refresh it with `/voice-profile`.

Use a pattern only if it fits the topic and the content of the video. Don't force one that doesn't.

**The series file outranks this skill.** These rules describe what usually works; a series file describes what has measurably worked for its audience. Where the two conflict, follow the series file and note the conflict rather than splitting the difference.

## Hook Quality Test

Before finalizing, run these three checks:

1. **Scroll test** — Would someone scrolling fast pause here? (If it sounds like a blog post title, the answer is no.)
2. **HOW test** — Does the hook withhold something the viewer now needs to know?
3. **Promise test** — Does the video actually deliver what the hook implies?

If any check fails, rewrite. Where a series file sets its own bar for one of these, that bar replaces the check — a series whose hooks are required to state the claim outright is not failing the HOW test, it is running a different one.

