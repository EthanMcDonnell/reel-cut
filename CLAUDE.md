# CLAUDE.md

**ReelCut** — short-form video production pipeline (Instagram Reels / YouTube Shorts).

**Always use `.venv/bin/python` for all Python and pip commands.** Never system python/pip.

**To fetch article content** (e.g. verify CTA claims): `.venv/bin/python scrape/single_scrape.py <url>`

## Workflows

- `/produce-script` — Phase 0: article/URL → script + screenshots
- `/prepare-video <slug>` — Phase 1: transcribe + fix EDL
- `/produce-video <slug>` — Phase 2: assign image timings + render
- `/edit-video <slug>` — Phase 2, again: cut spans out of the tail and re-render
- `/schedule-video <slug>` — Phase 3: book every hook into a future slot
- `/post-video <slug>` — Phase 3, now: post one hook immediately


**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Fix the Automation, Not Just the Video

**A question about the output is a question about the process that produced it.**

When the user asks why something in a script, EDL, or render looks the way it does — or points out something wrong with the current video — treat it as a genuine desire to improve the underlying automation (the skills, prompts, scripts, and config that generate every video), not merely a request to patch this one output.

- Default to fixing the source: the skill, prompt rule, script, or config that will make every future video better.
- Don't silently hand-edit the current video's artifacts to paper over a systemic flaw. If a one-off manual fix is genuinely warranted, say so and explain why the automation shouldn't change.
- When a question exposes a gap, ask: "what rule or code change prevents this next time?" — then propose that.

## 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.