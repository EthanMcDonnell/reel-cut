#!/usr/bin/env bash
# SessionStart hook — snapshot the working tree as it is RIGHT NOW so that
# commit-mine.sh can later tell Claude's own edits apart from the user's
# pre-existing uncommitted changes. Writes three markers under
# .git/claude-sessions/<session-id>/ (per session, so starting or resuming a second
# session in this checkout can't clobber a running one — see claude-session-paths.sh):
#   baseline            — a commit SHA capturing the current tracked tree
#   untracked-baseline  — the list of currently-untracked files
#   touched-files       — reset here, re-populated by claude-touched.sh
# Nothing on disk is modified. Safe to no-op outside a git repo.
set -uo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$DIR" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
GITDIR="$(git rev-parse --git-dir)"

PAYLOAD="$(cat 2>/dev/null || true)"   # carries session_id
. "$(dirname "$0")/claude-session-paths.sh"

# `git stash create` snapshots tracked (modified + staged) content into a
# throwaway commit object without touching the working tree or the stash list.
# It prints nothing when the tree is clean — fall back to HEAD in that case.
BASE="$(git stash create 2>/dev/null || true)"
[ -n "$BASE" ] || BASE="$(git rev-parse HEAD 2>/dev/null || true)"
[ -n "$BASE" ] || exit 0

printf '%s\n' "$BASE" > "$BASE_FILE"
git ls-files --others --exclude-standard | sort -u > "$UNTR_FILE"
: > "$TOUCH_FILE"   # reset per session; claude-touched.sh re-populates as Claude edits

# Keep .git tidy: drop marker dirs from sessions untouched for a fortnight.
find "$GITDIR/claude-sessions" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null
exit 0
