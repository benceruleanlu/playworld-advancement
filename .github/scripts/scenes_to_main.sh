#!/usr/bin/env bash
# scenes_to_main.sh: inside a push_results.sh snippet, copy this run's scenes manifest into the checkout of main
# ($MAIN_DIR/results/media/EXP.json) and add it to index.json. Does nothing unless the "Publish scenes" step
# uploaded every clip (it touches .published last), so the site never links to assets that are not there.
# `pwa.media to-main` reads and checks every file before writing any (no manifest without an index entry) and
# never replaces an official scored manifest with an unscored one (a later screening-judge or gen-only run).
# SCENES_DIR (default $RUNNER_TEMP/media) is where pwa media wrote EXP.json; arms.yml sets it per arm.
set -euo pipefail
src="${SCENES_DIR:-$RUNNER_TEMP/media}"
[[ -f "$src/.published" && -f "$src/$EXP.json" ]] || { echo "no published scenes for $EXP"; exit 0; }
python -m pwa.media to-main "$MAIN_DIR/results/media" "$src/$EXP.json"
