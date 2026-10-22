---
name: hooks
description: >
  Use always when writing, generating, evaluating video hooks, whenever hooks need to be written or improved or even if the user just says "write a hook", "make this punchier", "give me options", or asks for hooks for any tech topic. Contains rules and a quality checklist. Invoke this skill. Do NOT skip this skill if hooks are involved in any way.
---

# Hooks

The hook is the video's first line. It has about one second to make the right viewer stop, and two more to give them a reason to stay.

## What a Hook Does

1. **Names the topic in the first few words.** Viewers decide on the subject, so put the thing itself up front: a product, a company, an object they own. Never open without a subject ("Here's how to…").
2. **Sets it against what the viewer expects.** Pair something familiar with something that doesn't fit. Lead with whichever is strongest: a belief the viewer holds that's wrong, something they've seen and never questioned, a name, a number that's absurd for its context, or a reversal.
3. **Withholds the explanation.** State the surprising *what*, never the *how*. A hook that answers its own question has spent its tension.
4. **Gives a reason to stay.** Know what the viewer gets or loses by watching: a belief of theirs corrected, a mystery they've hit themselves, something they'll use, or their money, time or safety. Say "you/your" when it's theirs. Curiosity about someone else's fact is the weakest reason.
5. **Is specific.** A real name, number or time beats a vague claim ("in 4 days", not "quickly"). A number needs something riding on it, such as an absurd action, a cost, a reversal or the viewer's stake. Without that it's just a spec.

## Rules

1. **One short sentence.** Use only the words that carry the claim. No em dashes. No three-fragment staccato ("Fast. Cheap. Scalable.").
2. **Write for the ear and the screen.** It's heard once at speed and read on screen with the sound off, so it has to land both ways. Words that sound alike (megabits, megabytes) blur when spoken.
3. **Say it boldly when it's true.** "X just killed Y", not "X may be changing Y".
4. **Compression shortens the sentence, never the claim.** Keep the words that carry scope ("under load", "one of the reasons", the real count). If the source credits a whole system, don't credit one part of it. If the source rejected a design, don't describe that design. If the hook only lands with the scope wrong, pick a different angle.
5. **Promise only what the video delivers.**

## Where Patterns Come From

Which pattern wins depends on the audience, so the patterns live with the audience, not here. Read both before generating:

1. **`series/<slug>.md`** when a `SERIES` is known. Its `## Best Hooks` section is the source of truth: winning patterns, register, shipped hooks and their real numbers.
2. **`.claude/voice/proven-hooks.md`**, if it exists. These are the creator's own hooks ranked by real engagement. Refresh it with `/voice-profile`.

Use a pattern only if it fits the topic. Where a series file conflicts with this skill, follow the series file and note the conflict.

## Quality Test

Run every candidate through all six checks and rewrite any that fail:

1. **Scroll:** would a fast scroller stop? A line that reads like a blog title fails.
2. **Topic:** does the viewer know what it's about within the first few words?
3. **Gap:** is the explanation withheld, and does the viewer now need it?
4. **Reason:** can you name the viewer's reason to stay?
5. **Statement:** could it sit unchanged in the source article? Then it's a fact, not a hook.
6. **Promise:** does the video deliver exactly this?

Across a set, lead each hook with a different element so each video tests a different reason to watch. Where a series file sets its own bar for a check, its bar replaces the check.
