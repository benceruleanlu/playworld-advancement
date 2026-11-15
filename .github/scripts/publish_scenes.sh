#!/usr/bin/env bash
# publish_scenes.sh: the "Publish scenes" step. Encodes every rollout of $EXP (pwa media), uploads the clips to the
# GitHub Release run-EXP, and touches $RUNNER_TEMP/media/.published last, so the commit steps publish the manifest
# only when every upload succeeded. An unscored run (gen-only, capped smoke, screening judge) never replaces the
# official scenes of the same EXP already on main: it publishes nothing, so the release and its notes stay as they were.
# Env: EXP, GITHUB_REPOSITORY(_OWNER), GITHUB_SHA, RUNNER_TEMP, GITHUB_STEP_SUMMARY, STAGE, JUDGE_IN, JUDGE_SLUG,
# RUNNER_IN, ACTION_SOURCE; GH_TOKEN for gh.
set -euo pipefail
tag="run-$EXP"
repo="https://github.com/$GITHUB_REPOSITORY"
site="https://${GITHUB_REPOSITORY_OWNER}.github.io/${GITHUB_REPOSITORY#*/}/"
out="$RUNNER_TEMP/media"
[[ -d "runs/$EXP" ]] || { echo "no rollouts on this runner"; exit 0; }
report_name="$EXP.md"; screening=()
if [[ -n "${JUDGE_IN:-}" && "$STAGE" != "gen-only" ]]; then
  report_name="$EXP.${JUDGE_SLUG:-screening}.md"; screening=(--screening "$JUDGE_IN")
fi
pwa media "$EXP" --out "$out" --base-url "$repo/releases/download/$tag/" --release-url "$repo/releases/tag/$tag" \
  --report-name "$report_name" --site-url "$site" "${screening[@]}"
shopt -s nullglob
files=("$out"/*.mp4 "$out"/*.jpg)
# pipeline tests and runs without rollouts publish nothing (pwa media writes no clips for them)
if (( ${#files[@]} == 0 )); then echo "no rollouts to publish"; rm -f "$out/$EXP.json"; exit 0; fi
# Keep official scenes. An unscored run publishes only when main's manifest for EXP is known not to be an official
# scored one. If main cannot be fetched the state is unknown and counts as official, so nothing is overwritten.
if ! python -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("scored", True) else 1)' "$out/$EXP.json"; then
  main_man="$RUNNER_TEMP/main-scenes-$EXP.json"
  if git fetch -q --depth 1 origin main; then
    git show "FETCH_HEAD:results/media/$EXP.json" > "$main_man" 2>/dev/null || : > "$main_man"
  else
    echo '{"scored": true}' > "$main_man"
  fi
  if python -m pwa.media keeps-official "$main_man" "$out/$EXP.json"; then
    echo "::notice title=scenes kept::main has official scored scenes for $EXP (or main could not be read); this unscored run publishes none"
    rm -f "$out/$EXP.json"
    exit 0
  fi
fi
if gh release view "$tag" >/dev/null 2>&1; then
  gh release upload "$tag" "${files[@]}" --clobber
  gh release edit "$tag" --notes-file "$out/RELEASE_NOTES.md"
else
  gh release create "$tag" "${files[@]}" --target "$GITHUB_SHA" --title "Scenes: $EXP" \
    --notes-file "$out/RELEASE_NOTES.md" --latest=false
fi
# reached only if every upload above succeeded (set -e); the commit steps publish the manifest only then
touch "$out/.published"
# every task with a play link, in the step summary and in the results/reports/ entry committed below
if [[ "$STAGE" == "gen-only" ]]; then
  { echo "## $EXP (generated, not scored)"; echo
    echo "runner \`$RUNNER_IN\` | action source \`$ACTION_SOURCE\` | stage gen-only"; echo; } > "$RUNNER_TEMP/report.md"
fi
{ echo; cat "$out/SCENES.md"; } | tee -a "$RUNNER_TEMP/report.md" >> "$GITHUB_STEP_SUMMARY"
