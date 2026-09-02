#!/usr/bin/env bash

# Session-start sync: pull recursively, then report stale submodule pins.
#
# Run this instead of a bare `git pull`.
#
# `git pull` reporting "Already up to date" is NOT evidence that the working
# tree is current. There are two separate failures and the obvious fix only
# addresses one of them:
#
#   A. The working tree is behind the parent's pin. A plain pull moves the
#      parent's gitlink but leaves the submodule checkout where it was.
#      Fixed by recursing, which this script always does explicitly rather
#      than relying on a `submodule.recurse` setting that may not be present
#      on whichever machine or clone you are sitting at.
#
#   B. The parent's pin is behind the submodule's own origin. Someone pushed
#      upstream and never bumped the pointer here. Recursion does NOT fix
#      this – it faithfully checks out whatever the parent pins, so a stale
#      pin is checked out stale, accurately, forever.
#
# Only an explicit pin-versus-origin comparison catches B, which is what the
# second half of this script does. B is the one that bites in practice: a
# shared knowledge-base submodule can sit months behind its own origin while
# every repo consuming it reports a clean, successful pull, so consumers keep
# serving content whose upstream was corrected long ago.
#
# This script REPORTS. It never bumps a pointer. Bumping is a content change
# to the parent repo, and if that parent deploys anything, it is a change to
# what users see. It belongs to a human who has looked at what the missing
# commits actually contain.
#
# A pin that is behind is not automatically wrong. It may be deliberate. The
# commit subjects are printed so a reader can judge rather than guess.
#
# SYNC_SKIP_PULL=1 runs the drift report on its own without touching the
# working tree – useful to see what a pull would bring in before running it,
# and to exercise the drift half against a known-stale pin, since a check
# whose passing result is "nothing found" is worth little until it has been
# watched to fail.
#
# This script is safe to ship in a repo with no submodules: the pull is then
# the whole job, and it stays correct if the repo later gains one.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${SYNC_SKIP_PULL:-0}" = "1" ]; then
  echo "SYNC_SKIP_PULL=1 – skipping pull, reporting drift only."
else
  echo "Pulling $(basename "$ROOT") (recursing into submodules)..."
  echo

  if ! git pull --recurse-submodules; then
    echo
    echo "sync: git pull failed. Resolve the above, then re-run." >&2
    exit 1
  fi
fi

# No submodules? Then the pull was the whole job.
if [ ! -f .gitmodules ]; then
  echo
  echo "No submodules. Up to date."
  exit 0
fi

echo
echo "Checking each submodule pin against its own origin..."
echo

drift_found=0

# Read name/path pairs from .gitmodules. A while-read loop rather than an
# unquoted variable: zsh does not word-split unquoted expansions, so the
# usual `for x in $LIST` idiom silently breaks under zsh.
while IFS= read -r line; do
  [ -n "$line" ] || continue

  key="${line%% *}"                 # submodule.<name>.path
  path="${line#* }"
  name="${key#submodule.}"
  name="${name%.path}"

  if [ ! -e "$path/.git" ]; then
    echo "  $path – not initialized, skipping (run: git submodule update --init)"
    continue
  fi

  # The commit this repo pins, read from the gitlink in HEAD's tree rather
  # than from the submodule's checkout, which may have been moved by hand.
  pinned="$(git rev-parse "HEAD:$path" 2>/dev/null)"
  if [ -z "$pinned" ]; then
    echo "  $path – could not read pinned commit, skipping" >&2
    continue
  fi

  (
    cd "$path" || exit 0
    git fetch origin --quiet 2>/dev/null || {
      echo "  $path – could not fetch origin, skipping"
      exit 0
    }

    # Which upstream branch to compare against: an explicit .gitmodules
    # branch, else origin/HEAD, else main, else master.
    target=""
    branch="$(git config -f "$ROOT/.gitmodules" --get "submodule.$name.branch" 2>/dev/null || true)"
    if [ -n "$branch" ] && git show-ref --quiet --verify "refs/remotes/origin/$branch"; then
      target="origin/$branch"
    elif git symbolic-ref --quiet refs/remotes/origin/HEAD >/dev/null 2>&1; then
      target="$(git symbolic-ref --short refs/remotes/origin/HEAD)"
    else
      for b in main master; do
        if git show-ref --quiet --verify "refs/remotes/origin/$b"; then
          target="origin/$b"
          break
        fi
      done
    fi

    if [ -z "$target" ]; then
      echo "  $path – no origin branch found to compare against, skipping"
      exit 0
    fi

    behind="$(git rev-list --count "$pinned..$target" 2>/dev/null || echo 0)"

    if [ "$behind" -eq 0 ]; then
      echo "  $path – current with $target"
      exit 0
    fi

    echo
    echo "  $path – PIN IS $behind COMMIT(S) BEHIND $target"
    echo "    pinned here: $(git log -1 --format='%h %ad %s' --date=short "$pinned" 2>/dev/null)"
    echo "    $target is at: $(git log -1 --format='%h %ad %s' --date=short "$target" 2>/dev/null)"
    echo
    echo "    Not picked up by this repo:"
    git log --reverse --format='      %h %ad  %s' --date=short "$pinned..$target" 2>/dev/null
    echo
    exit 42
  )
  [ $? -eq 42 ] && drift_found=1

done < <(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null)

echo

if [ "$drift_found" -eq 0 ]; then
  echo "All submodule pins are current."
  exit 0
fi

cat <<'EOF'
One or more submodule pins are behind their origin.

Read the subjects above before deciding. A pin that is behind may be
deliberate – a submodule rebuilt on a fixed cadence can be weeks old and
entirely correct. But a rebuild cadence governs when new content is
GENERATED, not how current the pin has to be: correctness fixes get taken
immediately.

If the missing commits should be taken, bump deliberately and verify the
content, not just the pointer:

  git -C <path> checkout main && git -C <path> pull
  # then actually read a file the fix was supposed to repair
  git add <path>
  git commit -m "fix(deps): bump <name> to <sha> – <why>"

If the pin is deliberate, record why next to it. "Intentionally pinned" and
"drifted and nobody noticed" look identical from the outside, and that
ambiguity is exactly what lets a stale dependency sit unnoticed for months.
EOF

exit 0
