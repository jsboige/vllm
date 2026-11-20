#!/usr/bin/env bash
# Run against the installed vLLM release, without exposing GPUs or starting an engine.
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import pytest' 2>/dev/null || python3 -m pip install --disable-pip-version-check --no-cache-dir --retries 1 --timeout 15 'pytest>=8,<10'
python3 -c 'import importlib.metadata; print("vLLM=" + importlib.metadata.version("vllm"))'
python3 -m pytest -q -p no:cacheprovider /regression/test_step_hit_protection.py -k 'does_not_evict or degrades_to_miss'
