#!/usr/bin/env bash
set -euo pipefail

REMOTE="upstream"
BRANCH="main"
REMOTE_URL="https://github.com/NousResearch/hermes-agent.git"
AUTOSTASH=1

usage() {
  cat <<'EOF'
Usage: scripts/sync_upstream_main.sh [options]

Fetch upstream/main and merge it into the current branch without discarding
local commits. If the upstream remote is missing, the script adds the canonical
NousResearch remote.

Options:
  --remote NAME       Remote to fetch from (default: upstream)
  --branch NAME       Branch to merge from that remote (default: main)
  --remote-url URL    URL to use if the remote is missing
  --no-autostash      Refuse to run with local tracked changes instead of using git merge --autostash
  -h, --help          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)
      REMOTE="${2:?missing value for --remote}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?missing value for --branch}"
      shift 2
      ;;
    --remote-url)
      REMOTE_URL="${2:?missing value for --remote-url}"
      shift 2
      ;;
    --no-autostash)
      AUTOSTASH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

git rev-parse --is-inside-work-tree >/dev/null

current_branch="$(git branch --show-current)"
if [[ -z "$current_branch" ]]; then
  echo "Refusing to merge while HEAD is detached." >&2
  exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Adding missing remote '$REMOTE': $REMOTE_URL"
  git remote add "$REMOTE" "$REMOTE_URL"
fi

if [[ "$REMOTE" == "upstream" ]]; then
  git remote set-url --push "$REMOTE" DISABLED
fi

echo "Fetching $REMOTE/$BRANCH..."
git fetch "$REMOTE" "$BRANCH"

if [[ "$AUTOSTASH" -eq 0 ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to merge with local changes. Commit/stash them, or rerun without --no-autostash." >&2
  git status --short >&2
  exit 1
fi

echo "Merging $REMOTE/$BRANCH into $current_branch..."
if [[ "$AUTOSTASH" -eq 1 ]]; then
  git merge --autostash "$REMOTE/$BRANCH"
else
  git merge "$REMOTE/$BRANCH"
fi

echo
echo "Sync complete."
git status --short
