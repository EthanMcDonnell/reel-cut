---
name: produce-reel
description: Orchestrate the whole ReelCut pipeline for one slug — spawns a Sonnet reel-step subagent per command (prepare → produce → publish) and relays each subagent's questions to you via AskUserQuestion.
argument-hint: "<video-slug> [--through prepare|produce|schedule|post]"
---

Runs the pipeline end to end for one asset folder, one subagent per command. **You stay in the main
conversation** and do not do the pipeline work yourself — you dispatch, relay questions, and report.

Arguments: `$ARGUMENTS` — `<video-slug> [--through <stage>]`

Available slugs in `assets/`:
!`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If no slug is given, ask which of the above to use. `--through` sets where to stop; default is
`produce` (render, don't publish). Publishing stages only run if asked for explicitly.

## Why this is a command and not an agent

Subagents have **no `AskUserQuestion` tool** — a spawned orchestrator could not reach the user
either. Only the main conversation can. That is the whole reason this runs here: you own the
question channel, and the workers borrow it through you.

## The chain

| Stage | Command | Notes |
|---|---|---|
| `prepare` | `/prepare-video <slug>` | full reset — wipes images.json/videos.json from any prior run |
| `produce` | `/produce-video <slug>` | asks about title cards + captions |
| `schedule` | `/schedule-video <slug>` | live calendar — confirms before booking |
| `post` | `/post-video <slug>` | live account, posts now — confirms before publishing |

`schedule` and `post` are alternatives, not a sequence: run whichever the user named. Phase 0
(`/produce-script`) is out of scope — it *creates* the asset folder this command consumes. If the
slug folder has no footage, say so and stop rather than starting the chain.

## Per stage

1. **Dispatch.** Spawn one `reel-step` subagent (`subagent_type: "reel-step"`), one per stage,
   never reusing a previous stage's agent. Prompt it with just the command and the slug, e.g.
   *"Run the `produce-video` command for slug `netflix-cdn-architecture`."* Plus any decisions the
   user already made in this session that the step would otherwise ask about. Keep its agent id.

2. **Relay.** If it returns `NEEDS_DECISION`, put the question to the user with
   **AskUserQuestion**, using its `options` verbatim as the choices, its `recommend` first with
   `(Recommended)` appended, and its `context` shown so the user is deciding on the real content —
   the proposed cards, the slot table — not on a summary of it. Then resume that same agent with
   **SendMessage** to its id: `DECISION: <the user's choice>` plus any free-text notes they added.
   Repeat until it returns `DONE` or `FAILED`.

3. **Report, then continue.** Relay its `result` and `flags` to the user in a couple of lines
   (subagent output is not shown to them). On `DONE`, move to the next stage. On `FAILED`, stop the
   chain and report — do not attempt the next stage, and do not fix the step yourself unless the
   user asks.

Stop after the `--through` stage and say what the next command would be.

## Rules

- **Never answer a subagent's question on the user's behalf.** Every `NEEDS_DECISION` goes to the
  human. Being confident about the right answer is not a reason to skip the ask — the questions
  that survive to this layer are the ones the command deliberately reserved for a person.
- **Never collapse the publish gates.** `schedule` and `post` touch a live account; their internal
  confirmations reach the user through you, unchanged.
- Run stages strictly in order, one at a time. No parallel stages — each reads what the last wrote.
- Carry forward `flags` from earlier stages into the summary at the end, so left-for-human anomalies
  from `prepare` don't get buried behind a successful render.
