---
name: commit-mine
description: >
  Commit ONLY Claude's own code changes (under reelcut/ and tests/), line-for-line,
  leaving the user's pre-existing uncommitted edits untouched. Use when the user says
  "commit my changes", "commit just what you changed", "commit only the lines you
  modified", or wants a surgical commit that excludes their unrelated working-tree edits.
---

# commit-mine

Commit **only the exact lines Claude changed** in `reelcut/` and `tests/`, leaving the
user's pre-existing uncommitted edits (and anything outside those dirs) unstaged.

This is the manual entry point to the same logic the `Stop` hook runs automatically.

## How it works

The `SessionStart` hook (`.claude/scripts/claude-commit-baseline.sh`) records a snapshot
of the working tree before Claude edits anything. `git diff <baseline> -- <file>` is then
exactly Claude's edits, which are staged hunk-by-hunk with `git apply --cached`. Edits that
overlap the user's pre-existing changes can't be cleanly isolated and are skipped (never
committed mangled).

## What to do

1. Look at the changes you're about to commit (`git diff` on the files you touched in
   `reelcut/`/`tests/`) and write a concise conventional-commits subject for them.
2. Run the shared script, passing that subject as the argument:
   ```bash
   bash .claude/scripts/commit-mine.sh "feat: …your subject…"
   ```
   (The automatic `Stop` hook runs it with **no** argument. Rather than commit with a
   context-blind message, the hook then *re-wakes this session* asking you to do exactly
   the step above — write a subject from real context and re-run with it. So whether you
   reach here manually or via that re-wake, the action is the same.)
3. Report what it committed (the SHA + file list it prints), and name any file it skipped
   because Claude's edits overlapped the user's pre-existing changes.

## If it prints "no session baseline"

This session began before the hook was installed, so there's no automatic baseline. Fall
back to staging manually:

1. `git status` and `git diff` to see all working-tree changes.
2. Identify the hunks **you** (Claude) changed in `reelcut/`/`tests/`, separate from the
   user's pre-existing edits.
3. Stage only your hunks. For a file with cleanly separated changes:
   `git diff -- <file> | git apply --cached -` works only if the whole file's changes are
   yours; otherwise write a patch of just your hunks and `git apply --cached` it, or stage
   whole files that are entirely your work with `git add`.
4. Verify with `git diff --cached` that only your lines are staged, then commit with an
   auto-style message:
   ```
   chore: auto-commit claude changes
   ```
   ending with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
5. Confirm `git status` still shows the user's pre-existing edits as unstaged.
