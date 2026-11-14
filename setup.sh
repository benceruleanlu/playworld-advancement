#!/usr/bin/env bash
# One-time setup on a dev or GPU box. Safe to re-run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

git submodule update --init --recursive

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -e third_party/PlayWorld
python -m pip install -q -r third_party/PlayWorld/Agent_player/SANA-WM/requirements.txt
python -m pip install -q huggingface_hub
python -m pip install -q -e .

# Full dataset (images + json). Public; HF_TOKEN optional.
if [[ ! -d data/gc/images ]]; then
  python -I -c "from huggingface_hub import snapshot_download; snapshot_download('jocelynd/playworld-bench', repo_type='dataset', local_dir='data')"
fi

[[ -f config/env.sh ]] || cp config/env.example.sh config/env.sh

echo "done. fill config/env.sh, then: source .venv/bin/activate && pwa doctor" >&2
