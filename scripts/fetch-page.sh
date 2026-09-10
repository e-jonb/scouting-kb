#!/usr/bin/env bash
# Locator shim for fetch-page.sh. CONTAINS NO BEHAVIOR ON PURPOSE.
#
# The real script lives in the Solution Architect Studio at
# scripts/fetch-page.sh. This file only finds it and hands over. Everything
# that could need changing - the User-Agent string, the text extraction, the
# --check diagnostic - lives there, so a fix reaches every repo at once.
#
# This is copied per repo, and a file that is copied by design must not carry
# behavior: anything that lands here drifts silently and the comment claiming
# it is centralized keeps being believed. That happened once already, to the
# markdown hook, where diff-scoping was added to the shim and two repos ran
# stale copies for weeks.
#
# Unlike the markdown hook's shim, this one FAILS LOUDLY when it cannot find
# the canonical script. A linter that quietly does nothing is survivable. A
# fetch tool that quietly does nothing gets read as "the site is down."
#
# Usage: scripts/fetch-page.sh <url> [--html|--json|--check]
#   --check first, before recording any source as unavailable.

set -uo pipefail

find_canonical() {
  # 1. Explicit override, for non-standard layouts.
  if [ -n "${FETCH_PAGE_SCRIPT:-}" ] && [ -f "$FETCH_PAGE_SCRIPT" ]; then
    printf '%s' "$FETCH_PAGE_SCRIPT"; return 0
  fi
  # 2. Walk up looking for the studio as a sibling at any level. Handles both
  #    _dev/<repo> and nested checkouts like _dev/hellfireclub/<repo>.
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    local cand="$dir/solution-architect-studio/scripts/fetch-page.sh"
    if [ -f "$cand" ]; then printf '%s' "$cand"; return 0; fi
    dir="$(dirname "$dir")"
  done
  return 1
}

if ! canonical="$(find_canonical)"; then
  cat >&2 <<'EOF'
fetch-page: cannot find the canonical script.

It lives in the Solution Architect Studio at scripts/fetch-page.sh, and this
shim looks for a `solution-architect-studio` directory in any parent of this
repo. Either that repo is not on this machine, or it sits somewhere this
search does not reach.

Fix one of:
  - clone the studio alongside this repo
  - export FETCH_PAGE_SCRIPT=/path/to/solution-architect-studio/scripts/fetch-page.sh

This is failing loudly rather than falling back to a plain curl on purpose.
A silent fallback would return the very 403 or 404 this script exists to get
past, and that reads as "the source is unavailable" - which is a claim that
sticks and stops anyone retrying.
EOF
  exit 127
fi

exec bash "$canonical" "$@"
