#!/usr/bin/env bash
# judge_specs.sh JUDGE_MODEL: normalise the judge_model input of experiment.yml and arms.yml.
# Prints the screening judge specs, space-separated (each one `pwa score|report --judge-model` value), or nothing
# for the official judge (Gemini 3.1 Pro, upstream settings). Exit 2 on a bad value.
#   ""        -> official judge (the behaviour before Luna became the workflow default)
#   "gemini"  -> official judge, the same as "" (any case, surrounding spaces ignored); not allowed inside a list
#   otherwise -> comma-separated [openai:|gemini:]MODEL[:minimal|low|medium|high]
# The workflow default is openai:gpt-6-luna, a PROXY judge (user decision Nov 15: Gemini AI Studio credits ran out).
set -euo pipefail
in="${1-}"
in="${in// /}"
[[ "$in" =~ ^[A-Za-z0-9._:,-]*$ ]] || { echo "judge_model must match [A-Za-z0-9._:,-]*" >&2; exit 2; }
# Only the "gemini" checks ignore case; the thinking-level regex and the duplicate check stay case-sensitive,
# like Judge.parse (pwa/score.py), so openai:x:HIGH is refused here, not after generation.
[[ -z "$in" || "${in,,}" == gemini ]] && exit 0
specs=()
IFS=',' read -ra items <<< "$in"
for raw in "${items[@]}"; do
  [[ "${raw,,}" != gemini ]] || { echo "judge_model 'gemini' (official judge) cannot be combined with screening judges" >&2; exit 2; }
  m="$raw"
  [[ "$m" =~ :(minimal|low|medium|high)$ ]] && m="${m%:*}"
  m="${m#openai:}"; m="${m#gemini:}"
  [[ "$m" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "judge_model entry '$raw' must be [openai:]MODEL[:minimal|low|medium|high] with MODEL in [A-Za-z0-9._-]" >&2; exit 2; }
  [[ " ${specs[*]-} " != *" $raw "* ]] || { echo "judge_model lists '$raw' twice" >&2; exit 2; }
  specs+=("$raw")
done
(( ${#specs[@]} > 0 )) || { echo "judge_model has no entries" >&2; exit 2; }
echo "${specs[*]}"
