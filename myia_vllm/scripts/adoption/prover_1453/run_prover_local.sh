#!/usr/bin/env bash
# Bounded prover pass on the local MoE (CoursIA #1453), from the dedicated clone only.
# Every role is pinned to the local provider: with --provider local alone, the coordinator
# and tactic agents still default to openrouter. Record: _iteration_log/prover_1453/NOTES.md
# usage: run_prover_local.sh <demo_id> <max_iter> <workflow_timeout_s> [extra args]
set -o pipefail
DEMO=$1; ITER=$2; TMO=$3; shift 3
A=/d/dev/CoursIA-prover/MyIA.AI.Notebooks/SymbolicAI/Lean/agent_tests
PY=/c/Users/MYIA/miniconda3/envs/coursia-ml-training/python.exe
KEY=$(grep -E '^VLLM_API_KEY_MEDIUM=' /d/vllm/myia_vllm/.env | head -1 | cut -d= -f2- | tr -d '\r"')
[ -n "$KEY" ] || { echo "no MEDIUM key in .env" >&2; exit 9; }
export LOCAL_LLM_BASE_URL=http://localhost:5002/v1 LOCAL_LLM_API_KEY="$KEY" LOCAL_LLM_MODEL_ID=qwen3.6-35b-a3b PYTHONIOENCODING=utf-8
cd "$A" && exec "$PY" -u run_prover_bg.py "$DEMO" --provider local --local-provider local \
  --coordinator-provider local --tactic-provider local --search-provider local --critic-provider local \
  --max-iter "$ITER" --workflow-timeout "$TMO" "$@"
