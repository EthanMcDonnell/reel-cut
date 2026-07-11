#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit) hook — record the repo-relative path of every file
# Claude's OWN tools write this session, into .git/claude-touched-files.
#
# Why: commit-mine.sh used to decide "is this Claude's change?" purely from a git snapshot
# (the SessionStart baseline). But a point-in-time snapshot cannot tell a user's edit that
# lands AFTER SessionStart from one of Claude's — git has no working-tree attribution. This
# list is the ground truth git can't infer, so commit-mine can gate on "a tool of mine
# actually touched this file" instead of guessing. Append-only; deduped/cleared elsewhere.
set -uo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$DIR" || exit 0
GITDIR="$(git rev-parse --git-dir 2>/dev/null)" || exit 0
TOP="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

PAYLOAD="$(cat 2>/dev/null || true)"
if command -v jq >/dev/null 2>&1; then
  FP="$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"
else
  FP="$(printf '%s' "$PAYLOAD" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)"
fi
[ -n "$FP" ] || exit 0

# Normalize to a repo-relative path so it compares equal to `git diff --name-only` output.
case "$FP" in /*) ABS="$FP" ;; *) ABS="$DIR/$FP" ;; esac
REL="${ABS#"$TOP"/}"
printf '%s\n' "$REL" >> "$GITDIR/claude-touched-files"
exit 0
