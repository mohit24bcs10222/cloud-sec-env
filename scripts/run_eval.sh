#!/usr/bin/env bash
# Cloud Sec Env -- one-command eval.
#
# Runs N episodes of <model> against either the deployed HF Space (default)
# or a local in-process env, then prints a markdown summary table.
#
# Usage:
#   ./scripts/run_eval.sh                                  # 5 Opus episodes vs deployed Space
#   ./scripts/run_eval.sh claude-opus-4-7 10               # 10 Opus episodes
#   ./scripts/run_eval.sh claude-opus-4-7 5 local          # local in-process env
#   ./scripts/run_eval.sh Qwen/Qwen2.5-7B-Instruct 5 space # Qwen baseline vs Space
#
# Reads ANTHROPIC_API_KEY (claude-*) or HF_TOKEN (Qwen/*) from .env or shell.

set -euo pipefail

MODEL="${1:-claude-opus-4-7}"
N="${2:-5}"
TARGET="${3:-space}"   # "space" | "local"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "[run_eval] model=$MODEL n=$N target=$TARGET"

case "$TARGET" in
  space)
    python scripts/eval_against_space.py \
      --model "$MODEL" \
      --n "$N" \
      --out "trajectories/eval_summary_$(date +%Y%m%d_%H%M%S).md"
    ;;
  local)
    # Local in-process env: existing CLI handles per-episode logging + saves trajectory JSONs.
    python -m cloud_sec_env.agent.run \
      --model "$MODEL" \
      --n "$N"
    ;;
  *)
    echo "ERROR: unknown target '$TARGET'. Use 'space' or 'local'." >&2
    exit 1
    ;;
esac
