---
name: produce-reel
description: Orchestrate the whole ReelCut pipeline for one slug — spawns a reel-step subagent per command (prepare → produce → publish), verifies each subagent's proposals against the script, transcript and source, and puts what's left to you via AskUserQuestion.
argument-hint: "<video-slug> [--through prepare|produce|schedule|post] [--auto]"
---

Runs the pipeline end to end for one asset folder, one subagent per command. **You stay in the main conversation** and do not do the pipeline work yourself — you dispatch, check the workers' output, and put the decisions that need a person to the user.

Arguments: `$ARGUMENTS` — `<video-slug> [--through <stage>] [--auto]`

Available slugs in `assets/`: !`ls -1 assets/ | grep -vE '^audio$|\.json$'`

If no slug is given, ask which of the above to use. `--through` sets where to stop; default is `produce` (render, don't publish). Publishing stages only run if asked for explicitly.

## Why this is a command and not an agent

Subagents have **no `AskUserQuestion` tool** — a spawned orchestrator could not reach the user either. Only the main conversation can. That is the whole reason this runs here: you own the question channel, and the workers borrow it through you.

## The chain

| Stage | Command | Model | Notes |
|---|---|---|---|
| `prepare` | `/prepare-video <slug>` | `sonnet` | full reset — wipes images.json/videos.json from any prior run |
| `produce` | `/produce-video <slug>` | **`opus`** | asks about title cards + captions |
| `schedule` | `/schedule-video <slug>` | `sonnet` | live calendar — confirms before booking |
| `post` | `/post-video <slug>` | `sonnet` | live account, posts now — confirms before publishing |

`schedule` and `post` are alternatives, not a sequence: run whichever the user named. Phase 0 (`/produce-script`) is out of scope — it *creates* the asset folder this command consumes. If the slug folder has no footage, say so and stop rather than starting the chain.

## Per stage

1. **Dispatch.** Spawn one `reel-step` subagent (`subagent_type: "reel-step"`), one per stage, never reusing a previous stage's agent. Prompt it with just the command and the slug, e.g. *"Run the `produce-video` command for slug `netflix-cdn-architecture`."* Plus any decisions the user already made in this session that the step would otherwise ask about. Keep its agent id.

   **Pass `model` explicitly on every dispatch**, per the table above — the agent definition defaults to `sonnet` and the `model` parameter overrides it. `produce` gets `model: "opus"` because its output is generative rather than mechanical: the literal-noun gag pass (`produce-video:73`), hook detection done by intuition (`:123`), and the title cards and captions themselves (`:228`), whose register is the one a weaker model flattens into "how X did Y". Those are also the parts *no* later check catches — the verify step below is barred from touching wording, so under `--auto` whatever this worker writes is what gets burned into the video.

2. **Verify.** On `NEEDS_DECISION`, do not take the worker's framing at face value — re-derive the checkable part yourself, from the files, before doing anything with it. See *Verifying* below.

3. **Route.** Determinate questions you resolved in step 2: decide, and record the reasoning to report later. Everything else goes to the user with **AskUserQuestion** — its `options` verbatim as the choices, its `recommend` first with `(Recommended)` appended, and its `context` shown so they are deciding on the real content (the proposed cards, the slot table) and not a summary of it. Append what your verification found, including any correction to the worker's proposal. Then resume that same agent with **SendMessage** to its id: `DECISION: <choice>` plus any notes the user added. Repeat until it returns `DONE` or `FAILED`.

4. **Report, then continue.** Relay its `result` and `flags` to the user in a couple of lines (subagent output is not shown to them), along with anything you auto-decided in step 3. On `DONE`, move to the next stage. On `FAILED`, stop the chain and report — do not attempt the next stage, and do not fix the step yourself unless the user asks.

## Verifying

Three sources, each authoritative for a different thing. Using the wrong one is the failure mode:

| To check | Read | Not |
|---|---|---|
| hook count and where each hook ends | `assets/<slug>/script.md` — the `**HOOK**` section is one line per hook | the timeline alone, where alternate takes and false starts read as extra hooks |
| whether a title card or caption contradicts the video | `words` in `assets/<slug>/*.captions.json` — what actually shipped | `script.md`, which is what was *meant*; the speaker rewords freely and ad-libs are normal |
| a garbled or oddly-cased proper noun | `script.md`, which keeps real casing (`ChatGPT`, `PGKeeper`) | the transcript, where casing is Whisper guessing |
| whether the underlying claim is true | the source article (`.venv/bin/python scrape/single_scrape.py <url>`) | `script.md`, which can faithfully carry a claim it inherited wrong |

**`script.md` may not exist.** Only slugs produced by `/produce-script` have one. Without it, hook count stops being determinate — put it to the user rather than guessing, and say why you're asking.

What you may decide alone: anything with a determinate answer in those files — a card that contradicts the transcript, a miscounted hook, a proper noun cased wrong, a claim the source does not support. Reject the worker's proposal on those grounds and tell it what to fix.

What you may **not** decide alone, however confident you are: which wording is better. There is no ground truth for that in any file, and you and the worker share enough training to be wrong the same way — that is one check, not two. `tellcheck` and `stop-slop` exist in this repo precisely because model-drafted prose needs a human filter.

Stop after the `--through` stage and say what the next command would be.

## `--auto`

Unattended render. Verification in step 2 still runs in full — `--auto` changes only what happens to a question that survives it: instead of going to the user, you accept the worker's proposal and log it. Then:

- **Hard stop after `produce`**, whatever `--through` says. `--auto` never runs `schedule` or `post`. If the user asked for both, run the render stages, then stop and report that the renders are ready and publishing needs them.
- **Stop and ask anyway** if verification fails and the worker cannot fix it, if a stage returns `FAILED`, or if `script.md` is missing and hook count is genuinely ambiguous. `--auto` means "don't ask me about taste", not "don't ever stop".
- **List every auto-accepted decision** in the final report, each with the card or caption text as rendered, so the user can review what they would otherwise have been asked. Burned-in text is fixable only by re-rendering — cheap now, expensive after posting.

## Rules

- **Never collapse the publish gates.** `schedule` and `post` touch a live account, publicly and on a timer. Their confirmations reach the user unchanged, in every mode including `--auto`. This is not a confidence threshold — verification changes how often you are wrong, never what happens when you are, and these are the two places being wrong is not recoverable.
- **Never auto-decide a taste question**, and never let `--auto` reach a live account.
- Run stages strictly in order, one at a time. No parallel stages — each reads what the last wrote.
- Carry forward `flags` from earlier stages into the summary at the end, so left-for-human anomalies from `prepare` don't get buried behind a successful render.
