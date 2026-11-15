#!/usr/bin/env bash
# scenes_to_main.sh: inside a push_results.sh snippet, copy this run's scenes manifest into the checkout of main
# ($MAIN_DIR/results/media/EXP.json) and add it to index.json. Does nothing unless the "Publish scenes" step
# uploaded every clip (it touches .published last), so the site never links to assets that are not there.
set -euo pipefail
src="$RUNNER_TEMP/media"
[[ -f "$src/.published" && -f "$src/$EXP.json" ]] || { echo "no published scenes for $EXP"; exit 0; }
mkdir -p "$MAIN_DIR/results/media"
cp "$src/$EXP.json" "$MAIN_DIR/results/media/$EXP.json"
python -c "import json, pathlib, sys; from pwa import media; media.update_index(pathlib.Path(sys.argv[1]), json.load(open(sys.argv[2])))" \
  "$MAIN_DIR/results/media/index.json" "$src/$EXP.json"
