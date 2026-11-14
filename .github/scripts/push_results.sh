#!/usr/bin/env bash
# push_results.sh MESSAGE SNIPPET
# Run SNIPPET (bash) against a fresh checkout of main at $MAIN_DIR, then commit and push whatever it
# changed under results/. Only results/ is staged, so no branch code reaches main. Retries on push races.
set -euo pipefail
msg="$1"
snippet="$2"
export MAIN_DIR="$RUNNER_TEMP/main"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
if [[ ! -d "$MAIN_DIR" ]]; then
  git worktree add -q --detach "$MAIN_DIR" HEAD  # contents are replaced by the reset below
fi
for i in 1 2 3 4 5; do
  # a transient fetch error uses up an attempt instead of aborting the script
  if ! git -C "$MAIN_DIR" fetch -q --depth 50 origin main; then
    sleep $((i * 3))
    continue
  fi
  git -C "$MAIN_DIR" reset -q --hard FETCH_HEAD
  git -C "$MAIN_DIR" clean -qfd results
  bash -euo pipefail -c "$snippet"
  git -C "$MAIN_DIR" add results
  git -C "$MAIN_DIR" diff --cached --quiet && exit 0
  git -C "$MAIN_DIR" commit -q -m "$msg"
  git -C "$MAIN_DIR" push -q origin HEAD:main && exit 0
  sleep $((i * 3))
done
echo "could not push results to main after 5 attempts" >&2
exit 1
