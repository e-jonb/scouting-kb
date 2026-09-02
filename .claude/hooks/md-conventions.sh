#!/usr/bin/env bash
# PostToolUse hook: enforce markdown conventions on files Claude writes.
#
# This shim is copied into each repo's .claude/hooks/. It contains no rules -
# it only LOCATES the canonical checker in the studio repo, so the rules live
# in exactly one place and every repo picks up changes automatically.
#
# Behavior:
#   - hard breaks : auto-fixed silently (structural, no meaning changes)
#   - em dashes   : reported to Claude via exit 2, so Claude fixes its own
#                   prose and leaves quoted source material alone
#
# Never blocks and never fails the turn. If the studio repo is not on this
# machine, the hook exits 0 quietly rather than nagging on every write.

input=$(cat)

file_path=$(printf '%s' "$input" | python3 -c \
  'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' \
  2>/dev/null)

# Only markdown, and only files that still exist.
case "$file_path" in
  *.md|*.markdown) ;;
  *) exit 0 ;;
esac
[ -f "$file_path" ] || exit 0

find_checker() {
  # 1. Explicit override, for non-standard layouts.
  if [ -n "$MD_CONVENTIONS_SCRIPT" ] && [ -f "$MD_CONVENTIONS_SCRIPT" ]; then
    printf '%s' "$MD_CONVENTIONS_SCRIPT"; return 0
  fi
  # 2. This repo IS the studio.
  local own="${CLAUDE_PROJECT_DIR}/scripts/md-conventions.py"
  if [ -f "$own" ]; then printf '%s' "$own"; return 0; fi
  # 3. Walk up looking for the studio as a sibling at any level. Handles both
  #    _dev/<repo> and nested checkouts like _dev/hellfireclub/kindred.
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    local cand="$dir/solution-architect-studio/scripts/md-conventions.py"
    if [ -f "$cand" ]; then printf '%s' "$cand"; return 0; fi
    dir=$(dirname "$dir")
  done
  return 1
}

checker=$(find_checker) || exit 0

# Scoping is NOT passed from here. The checker defaults to diffing a tracked
# file against HEAD, so only lines just written are reported and legacy content
# is left alone. That default deliberately lives in the checker: this shim is
# COPIED into each repo, so anything that lives here drifts. It did - two repos
# ran stale shims that scoped nothing and dumped pre-existing findings. Keep
# this file free of behavior so a years-old copy still does the right thing.
python3 "$checker" --fix --quiet "$file_path" 2>/tmp/md-conventions-hook.err
status=$?

# Exit 2 surfaces stderr to Claude as feedback it can act on. Only em dash
# findings reach here, since --fix already resolved the hard breaks.
if [ "$status" -eq 2 ]; then
  cat /tmp/md-conventions-hook.err >&2
  exit 2
fi

exit 0
