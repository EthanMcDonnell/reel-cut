#!/usr/bin/env bash
# Commit ONLY Claude's own changes inside the target dirs, line-for-line, leaving the
# user's pre-existing uncommitted edits (and anything outside the target dirs) untouched.
#
# TWO ROLES:
#   1. Committer (called WITH a subject arg, e.g. `commit-mine.sh "fix: ..."`):
#      the running session — which has full context for *why* the change was made —
#      passes the message it wrote. The script stages just Claude's lines and commits.
#   2. Stop-hook detector (called with NO arg, stdin = the Stop payload):
#      it does NOT commit blind. If Claude left changes under the target dirs, it emits
#      a `decision:block` that RE-WAKES the session, asking it to write a context-aware
#      message and re-run this script as the committer. The session's message is far
#      better than anything derivable from the diff alone — that's the whole point.
#      A static-message safety net commits anyway if the re-wake already happened once
#      (stop_hook_active) so work is never lost and the loop always terminates.
#
# How it isolates Claude's lines: the SessionStart baseline (claude-baseline) is the tree
# before Claude touched anything, so `git diff <baseline> -- <file>` is exactly Claude's
# edits. That per-file diff is applied to the INDEX with `git apply --cached`; git apply
# matches context against HEAD, so edits apart from the user's stage cleanly, while edits
# OVERLAPPING the user's fail to apply and that file is skipped (never committed mangled).
set -uo pipefail

# --- debug (remove once verified): proves whether the hook fires at all ---
DEBUG_LOG="/tmp/commit-mine.log"
echo "$(date '+%F %T') fired  arg='${1:-}'  cwd='$PWD'  CLAUDE_PROJECT_DIR='${CLAUDE_PROJECT_DIR:-}'" >> "$DEBUG_LOG"
# -------------------------------------------------------------------------

TARGETS=(reelcut tests scrape .claude config.yaml)
FALLBACK_SUBJECT="chore: auto-commit claude changes"   # safety-net only (re-wake ignored)

ARG_SUBJECT="${1:-}"

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$DIR" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
GITDIR="$(git rev-parse --git-dir)"
BASE_FILE="$GITDIR/claude-baseline"
UNTR_FILE="$GITDIR/claude-untracked-baseline"
TOUCH_FILE="$GITDIR/claude-touched-files"   # repo-relative paths Claude's tools wrote (see claude-touched.sh)

# No baseline → session started before the hook existed. Do nothing; the /commit-mine
# skill handles that case by staging hunks manually.
if [ ! -f "$BASE_FILE" ]; then
  [ -n "$ARG_SUBJECT" ] && echo "commit-mine: no session baseline; nothing committed."
  exit 0
fi
BASE="$(cat "$BASE_FILE")"
[ -f "$UNTR_FILE" ] || : > "$UNTR_FILE"

# Claude's changed + new files inside the target dirs since the baseline. (Newline-delimited
# strings + while-read loops keep this working on macOS's stock bash 3.2.)
CHANGED="$(git diff --name-only "$BASE" -- "${TARGETS[@]}")"
# Keep only files that ACTUALLY differ from HEAD. Drops files already committed but still
# flagged because the baseline went stale after a reset/amend/dropped commit, so a rewound
# history can't cause a perpetual false re-trigger.
CHANGED="$(while IFS= read -r f; do
  [ -n "$f" ] || continue
  git diff --quiet HEAD -- "$f" || printf '%s\n' "$f"
done <<< "$CHANGED")"
NEW="$(comm -13 <(sort -u "$UNTR_FILE") \
                <(git ls-files --others --exclude-standard -- "${TARGETS[@]}" | sort -u))"

# Ground-truth attribution gate: keep only files one of Claude's own tools actually wrote
# this session. A baseline diff alone can't tell a mid-session USER edit from Claude's, so
# without this a file the user edited after SessionStart would be committed under Claude's
# name. If the touch list is missing/empty (session predates the PostToolUse hook), fall
# back to baseline-only so older sessions keep working exactly as before.
filter_touched() {
  local list; list="$(cat)"; list="$(printf '%s\n' "$list" | grep -v '^[[:space:]]*$')"
  [ -n "$list" ] || return 0
  if [ -s "$TOUCH_FILE" ]; then printf '%s\n' "$list" | grep -Fxf "$TOUCH_FILE"
  else printf '%s\n' "$list"; fi
}
CHANGED="$(printf '%s\n' "$CHANGED" | filter_touched)"
NEW="$(printf '%s\n' "$NEW" | filter_touched)"

HAVE=0
[ -n "$CHANGED" ] && HAVE=1
[ -n "$NEW" ] && HAVE=1
echo "  baseline=$BASE  HAVE=$HAVE  changed=[$(echo $CHANGED)]  new=[$(echo $NEW)]" >> "$DEBUG_LOG"

# Stage Claude's lines and commit them under the given subject. Re-baselines on success.
do_commit() {
  local subject="$1" staged=0 f FILES NEWBASE
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if git diff "$BASE" -- "$f" | git apply --cached - 2>/dev/null; then
      staged=1
    else
      echo "commit-mine: could not isolate $f (edits overlap pre-existing changes) — left unstaged."
    fi
  done <<< "$CHANGED"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    git add -- "$f" && staged=1
  done <<< "$NEW"

  [ "$staged" -eq 1 ] || { echo "commit-mine: nothing of mine could be staged."; return 0; }
  git diff --cached --quiet && return 0

  FILES="$(git diff --cached --name-only | tr '\n' ' ')"
  git commit -q -m "$subject" \
    -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>" || return 0

  NEWBASE="$(git stash create 2>/dev/null || true)"
  [ -n "$NEWBASE" ] || NEWBASE="$(git rev-parse HEAD)"
  printf '%s\n' "$NEWBASE" > "$BASE_FILE"
  git ls-files --others --exclude-standard | sort -u > "$UNTR_FILE"
  : > "$TOUCH_FILE"   # committed files are no longer pending; re-populated by future edits
  echo "commit-mine: committed $(git rev-parse --short HEAD) — $FILES"
}

json_escape() {
  if command -v jq >/dev/null 2>&1; then jq -Rs .
  else sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' ' | sed -e 's/^/"/' -e 's/ *$/"/'; fi
}

# ---- Role 1: committer (session passed a message) --------------------------------------
if [ -n "$ARG_SUBJECT" ]; then
  [ "$HAVE" -eq 1 ] || { echo "commit-mine: nothing of mine to commit."; exit 0; }
  do_commit "$ARG_SUBJECT"
  exit 0
fi

# ---- Role 2: Stop-hook detector (no arg, stdin = payload) ------------------------------
PAYLOAD="$(cat 2>/dev/null || true)"
[ "$HAVE" -eq 1 ] || exit 0   # nothing of mine pending — let the turn end

case "$PAYLOAD" in
  *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) STOP_ACTIVE=1 ;;
  *) STOP_ACTIVE=0 ;;
esac

if [ "$STOP_ACTIVE" -eq 1 ]; then
  do_commit "$FALLBACK_SUBJECT"   # already re-woke once; commit anyway so work isn't lost
  exit 0
fi

# First stop with pending changes: re-wake the session to author the message in context.
FILES="$(printf '%s\n%s\n' "$CHANGED" "$NEW" | grep -v '^[[:space:]]*$' | sort -u | tr '\n' ' ')"
REASON="You changed tracked files under one of the auto-commit dirs (reelcut/ tests/ scrape/ .claude/ config.yaml) this turn ($FILES) but haven't committed it. Review your own diff for those files and commit JUST your changes (not the user's pre-existing edits) with a context-aware conventional-commits subject you write from this session — run: bash .claude/scripts/commit-mine.sh \"<subject>\". Do not describe changes you didn't make."
printf '{"decision":"block","reason":%s}\n' "$(printf '%s' "$REASON" | json_escape)"
exit 0
