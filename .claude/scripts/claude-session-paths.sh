#!/usr/bin/env bash
# Sourced by claude-commit-baseline.sh, claude-touched.sh and commit-mine.sh to resolve
# the per-session marker paths.
#
# Why: these markers used to be three fixed files (.git/claude-baseline,
# claude-untracked-baseline, claude-touched-files) — one set per REPO, not per session.
# They only *behaved* per-session because SessionStart rewrote them. So a second session
# starting, resuming, or clearing in the same checkout overwrote a RUNNING session's
# baseline mid-turn: edits it had already made got folded into the new "before Claude
# touched anything" snapshot and were silently reclassified as the user's, while the
# touched-files reset erased the attribution fallback. Keying by session id keeps
# concurrent sessions independent.
#
# Expects GITDIR set. Reads $PAYLOAD (may be empty/unset) when the caller is a hook.
# Sets: SID, SESSION_DIR, BASE_FILE, UNTR_FILE, TOUCH_FILE.

# Session id: hook payloads carry it on stdin. The committer role of commit-mine.sh is run
# from Bash by the session itself with no stdin, so it falls back to the env var Claude
# Code exports there.
SID=""
if [ -n "${PAYLOAD:-}" ]; then
  if command -v jq >/dev/null 2>&1; then
    SID="$(printf '%s' "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)"
  else
    SID="$(printf '%s' "$PAYLOAD" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)"
  fi
fi
[ -n "$SID" ] || SID="${CLAUDE_CODE_SESSION_ID:-}"
[ -n "$SID" ] || SID="shared"   # last resort: no id available, old repo-wide behaviour
SID="$(printf '%s' "$SID" | tr -c 'A-Za-z0-9._-' '_')"   # path-safe

SESSION_DIR="$GITDIR/claude-sessions/$SID"
BASE_FILE="$SESSION_DIR/baseline"
UNTR_FILE="$SESSION_DIR/untracked-baseline"
TOUCH_FILE="$SESSION_DIR/touched-files"
mkdir -p "$SESSION_DIR" 2>/dev/null

# Adoption for a session that was already in flight when this change landed: its state is
# in the old repo-wide files, so inherit it once instead of losing the turn's work. A new
# session's SessionStart overwrites this immediately with its own snapshot.
if [ ! -f "$BASE_FILE" ] && [ -f "$GITDIR/claude-baseline" ]; then
  cp "$GITDIR/claude-baseline" "$BASE_FILE" 2>/dev/null
  [ -f "$GITDIR/claude-untracked-baseline" ] && cp "$GITDIR/claude-untracked-baseline" "$UNTR_FILE" 2>/dev/null
  [ -f "$GITDIR/claude-touched-files" ] && cp "$GITDIR/claude-touched-files" "$TOUCH_FILE" 2>/dev/null
fi
