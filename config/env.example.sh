# Copy to config/env.sh (git-ignored) and fill in. `pwa` sources it automatically.

# Agent Player (closed-loop action selection). Paper uses Claude Haiku 4.5.
# The harness calls POST {PLAYER_API_URL}/chat/completions. Our adapters set
# auth headers by provider: openai | anthropic | upstream.
export PLAYER_API_PROVIDER="openai"
export PLAYER_API_URL="https://api.openai.com/v1"
export PLAYER_API_KEY=""
export PLAYER_MODEL="gpt-4.1-mini"   # non-reasoning; reasoning models can return empty at 128 tokens
# Request settings (adapters/common/agent_api.py); defaults shown. Remote (Modal) runs: pass the runner args
# --player-max-completion-tokens / --player-reasoning-effort / --player-empty-retries instead.
# export PLAYER_MAX_COMPLETION_TOKENS=4096
# export PLAYER_REASONING_EFFORT=low     # openai default; empty or "off" omits it
# export PLAYER_EMPTY_RETRIES=2
# Paper-matching alternative:
# export PLAYER_API_PROVIDER="anthropic"
# export PLAYER_API_URL="https://api.anthropic.com/v1"
# export PLAYER_MODEL="claude-haiku-4-5-20251001"

# Rubric Verifier (scoring). Must be Gemini 3.1 Pro to match the leaderboard.
export GEMINI_API_KEY=""
export GEMINI_MODEL="gemini-3.1-pro-preview"
# Same judge on Google Cloud billing instead of AI Studio: Gemini Enterprise Agent Platform (formerly Vertex AI).
# A Google Cloud API key for it (express mode; project with the Agent Platform API, aiplatform.googleapis.com,
# enabled). Set = `pwa score` calls the global endpoint with it and GEMINI_API_KEY is unused by the judge.
# export GCP_GEMINI_API_KEY=""
# Or Application Default Credentials (gcloud auth application-default login), no key:
# export PWA_JUDGE_BACKEND="gcp"   # aistudio|gcp; default: gcp iff GCP_GEMINI_API_KEY is set
# export GOOGLE_CLOUD_PROJECT=""
# export GOOGLE_CLOUD_LOCATION="global"  # Gemini 3.1 Pro preview is served from global only
# Screening judge on an OpenAI-compatible API (`--judge-model openai:MODEL`, dev loops only).
# Empty = use PLAYER_API_KEY / PLAYER_API_URL.
# export JUDGE_API_KEY=""
# export JUDGE_API_URL="https://api.openai.com/v1"

# Hugging Face (dataset is public; token only raises rate limits).
export HF_TOKEN=""

# World model checkpoints. Fill the one(s) you run.
export SANA_ROOT=""            # local clone of NVlabs/Sana with SANA-WM inference
export SANA_CONFIG=""          # optional
export SANA_CHECKPOINT=""      # optional
export MG3_ROOT=""             # local clone of Matrix-Game 3.0 inference code
export MG3_CHECKPOINT=""       # Matrix-Game 3.0 weights dir

# Point SANA runner defaults away from the authors' internal paths.
export WORLDMODEL_BENCHMARK_DIR="$PWD/third_party/PlayWorld"
