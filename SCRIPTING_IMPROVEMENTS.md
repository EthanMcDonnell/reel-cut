# Scripting Improvements — Outstanding

## Blocked (needs sign-off)

### #8 — Run creative stages on Opus
**Change:** `model: sonnet` → `model: opus` in `.claude/commands/produce-script.md` frontmatter.
**Why:** Trivial one-line change; real ceiling-raise on angle and script quality. Blocked by auto-mode permission classifier — needs explicit user sign-off.

---

## Deferred

### #2 — Annotated exemplar library
**Change:** Add `.claude/skills/scripts/references/exemplars.md` with 3–4 annotated top-performer scripts (`claude-1m-context-window-trap`, `github-copilot-metered-billing`, `claude-usage-limit-timing-trick` for the casual register), each annotated with *why it works*. Point the skill at it: "read these before writing."
**Why:** Few-shot exemplars are the most reliable lever for subjective quality and voice. Simultaneously raises prose quality and teaches the winning register that the current rules suppress.

### #3 — Performance patterns + pre-save self-scoring rubric
**Change:** (a) Move top-performer patterns ("shocking number / dev-frustration / mystery-artifact") into `scripts/SKILL.md` as a "what wins on this channel" section. (b) Add a short self-eval before Stage 3.5: score the draft on hook strength, open-loop retention, payoff, one surprising fact, and register fit — revise if weak.
**Why:** Turns a one-shot generator into a system that learns from what worked. Compounding.

---

## Low priority

### #6 — Trim rule-overload
**Change:** Dedupe remaining overlaps with `stop-slop`, convert imperatives to reasoned guidance, push detail into references so the body stays lean.
**Why:** Largely moot — `scripts/SKILL.md` was already rewritten/deduped. Marginal gain.
