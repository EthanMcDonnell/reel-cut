#!/usr/bin/env bash
# SessionStart hook — snapshot the working tree as it is RIGHT NOW so that
# commit-mine.sh can later tell Claude's own edits apart from the user's
# pre-existing uncommitted changes. Writes two markers under .git/:
#   claude-baseline            — a commit SHA capturing the current tracked tree
#   claude-untracked-baseline  — the list of currently-untracked files
# Nothing on disk is modified. Safe to no-op outside a git repo.
set -uo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$DIR" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
GITDIR="$(git rev-parse --git-dir)"

# `git stash create` snapshots tracked (modified + staged) content into a
# throwaway commit object without touching the working tree or the stash list.
# It prints nothing when the tree is clean — fall back to HEAD in that case.
BASE="$(git stash create 2>/dev/null || true)"
[ -n "$BASE" ] || BASE="$(git rev-parse HEAD 2>/dev/null || true)"
[ -n "$BASE" ] || exit 0

printf '%s\n' "$BASE" > "$GITDIR/claude-baseline"
git ls-files --others --exclude-standard | sort -u > "$GITDIR/claude-untracked-baseline"
exit 0
