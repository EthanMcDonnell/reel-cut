---
name: produce-reel
description: Orchestrate the whole ReelCut pipeline for one slug — spawns a reel-step subagent per command (prepare → produce → publish), verifies each subagent's proposals against the script, transcript and source, and puts what's left to you via AskUserQuestion.
argument-hint: "<video-slug> [--through prepare|produce|schedule] [--auto]"
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
| `prepare` | `/prepare-video <slug>` | `sonnet` | re-transcribes; keeps videos.json card wording but clears its hook windows, and drops images.json |
| `produce` | `/produce-video <slug>` | **`opus`** | asks about title cards + captions |
| `schedule` | `/schedule-video <slug>` | `sonnet` | live calendar — confirms before booking |

Phase 0 (`/produce-script`) is out of scope — it *creates* the asset folder this command consumes. If the slug folder has no footage, say so and stop rather than starting the chain.

## Direct-recording intake

A phone upload may have `.reelcut-intake.json` in its asset folder. Read it before dispatching any stage.

- `kind: "scripted"` means this is an isolated returned take. Its copied `script.md` remains authoritative exactly as for a normal script-created asset.
- `kind: "direct"` with `hook_policy: "single"` means the absent `script.md` is intentional. This is one finished hook plus body, so it has **exactly one hook**. Do not infer alternate hooks, ask the user to select one, or stop merely because no script exists.
- For a direct recording, transcript wording is the authority for cards and captions. There is no source article, manifest, screenshot reconciliation, or script-based proper-noun correction. Still stop for malformed intake metadata, missing footage, unusable transcription, or a real failure outside the declared single-hook contract.
- Include the intake kind, series, and hook policy in every dispatched step prompt. This overrides the later non-script caveat for a declared direct single-hook receipt.

An asset with neither `script.md` nor a receipt is the manual-folder case — the user made the directory and dropped a clip in. That is **not** a blocker. Hook count is not carried by either file: it is read off the timeline by `produce-video` Step 3c, receipt or no receipt. Dispatch the chain as normal, tell the worker there is no script and no receipt, and report the hook count it arrived at. Only the transcript can make hook count genuinely ambiguous — see *Verifying*.

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
| hook count and where each hook ends | `assets/<slug>/script.md` — the `**HOOK**` section is one line per hook | the timeline alone, where alternate takes and false starts read as extra hooks — but with no script it is all you have, and that is fine (below) |
| whether a title card or caption contradicts the video | `words` in `assets/<slug>/*.captions.json` — what actually shipped | `script.md`, which is what was *meant*; the speaker rewords freely and ad-libs are normal |
| a garbled or oddly-cased proper noun | `script.md`, which keeps real casing (`ChatGPT`, `PGKeeper`) | the transcript, where casing is Whisper guessing |
| whether the underlying claim is true | the source article (`.venv/bin/python scrape/single_scrape.py <url>`) | `script.md`, which can faithfully carry a claim it inherited wrong |

**`script.md` may not exist**, and neither may a receipt. Only slugs from `/produce-script` have a script; only phone uploads have a receipt. Neither absence stops the chain. Hook count comes from the timeline — hooks are the punchy openers before the speaker shifts into explaining, and one opener means one hook. Take the worker's count, check it against the timeline yourself, and report it.

Hook count is only genuinely ambiguous when **the transcript** makes it so: several consecutive sentences at the top that each read as a complete opener — alternate takes recorded back to back. That, and not a missing file, is what goes to the user. Being wrong costs one re-render, before anything is published, so bias toward proceeding.

What you may decide alone: anything with a determinate answer in those files — a card that contradicts the transcript, a miscounted hook, a proper noun cased wrong, a claim the source does not support. Reject the worker's proposal on those grounds and tell it what to fix.

What you may **not** decide alone, however confident you are: which wording is better. There is no ground truth for that in any file, and you and the worker share enough training to be wrong the same way — that is one check, not two. `tellcheck` and `stop-slop` exist in this repo precisely because model-drafted prose needs a human filter.

Stop after the `--through` stage and say what the next command would be.

## `--auto`

Unattended render. Verification in step 2 still runs in full — `--auto` changes only what happens to a question that survives it: instead of going to the user, you accept the worker's proposal and log it. Then:

- **Hard stop after `produce`**, whatever `--through` says. `--auto` never runs `schedule`. If the user asked for both, run the render stages, then stop and report that the renders are ready and publishing needs them.
- **Stop and ask anyway** if verification fails and the worker cannot fix it, if a stage returns `FAILED`, or if the transcript shows several consecutive openers at the top of the clip so hook count is genuinely ambiguous. A missing `script.md` or receipt is *not* that — see *Verifying* — and is never on its own a reason to stop. `--auto` means "don't ask me about taste", not "don't ever stop".
- **List every auto-accepted decision** in the final report, each with the card or caption text as rendered, so the user can review what they would otherwise have been asked. Burned-in text is fixable only by re-rendering — cheap now, expensive after posting.

## Rules

- **Never collapse the publish gates.** `schedule` touch a live account, publicly and on a timer. Their confirmations reach the user unchanged, in every mode including `--auto`. This is not a confidence threshold — verification changes how often you are wrong, never what happens when you are, and these are the two places being wrong is not recoverable.
- **Never auto-decide a taste question**, and never let `--auto` reach a live account.
- Run stages strictly in order, one at a time. No parallel stages — each reads what the last wrote.
- Carry forward `flags` from earlier stages into the summary at the end, so left-for-human anomalies from `prepare` don't get buried behind a successful render.
