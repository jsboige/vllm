#!/bin/bash
# Test runner for overlay_v0340_fsadmit. Runs INSIDE a throwaway CPU-only
# container (no --gpus): never against the production container.
#
#   run_tests.sh admission           # tests/test_fs_admission.py
#   run_tests.sh regression          # tierpin race regression (whole file, 3 tests)
#   run_tests.sh upstream <label>    # upstream v0.34.0 tests/v1/kv_offload
#
# Host-side driver (Git Bash: MSYS_NO_PATHCONV=1 keeps container paths intact):
#   O=<repo>/myia_vllm/configs/docker/overlay_v0340_fsadmit
#   MSYS_NO_PATHCONV=1 docker run --rm --entrypoint bash -e CUDA_VISIBLE_DEVICES= \
#     -v "$O:/work:ro" -v <scratch>/upstream_tests:/upstream:ro -v <scratch>/out:/out \
#     [-e MYIA_FS_ADMIT_MIN_HITS=0] \
#     vllm-openai-v0340-fsadmit:v1 /work/tests/run_tests.sh upstream fsadmit-default
#
# <scratch>/upstream_tests is extracted from the fork tag the port reads:
#   git archive 0c57b4195da4a6b69a7725908e428053e51e51b8 tests/v1/kv_offload | tar -x -C <scratch>/upstream_tests
#   git show 0c57b419…:tests/__init__.py    > <scratch>/upstream_tests/tests/__init__.py
#   git show 0c57b419…:tests/v1/__init__.py > <scratch>/upstream_tests/tests/v1/__init__.py
# (tests/conftest.py is deliberately NOT extracted: the kv_offload tests only
# need tests/v1/kv_offload/conftest.py, and the top-level one pulls the whole
# model-test stack.)
#
# Baseline for the regression verdict: run the same `upstream` suite on
# vllm-openai-v0340-tierpin:v1 (production) and compare the failure sets.
set -u
SUITE="${1:?suite: admission|regression|upstream}"
LABEL="${2:-run}"
export CUDA_VISIBLE_DEVICES=""
python3 -c "import pytest" 2>/dev/null || pip install -q pytest >/dev/null 2>&1
echo "=== suite=$SUITE label=$LABEL MYIA_FS_ADMIT_MIN_HITS=${MYIA_FS_ADMIT_MIN_HITS:-<unset, default 2>}"
case "$SUITE" in
  admission)
    cd /work/tests || exit 2
    python3 -m pytest -q -p no:cacheprovider -rfE test_fs_admission.py
    ;;
  regression)
    cd /work/tests || exit 2
    # Whole file (3 tests). overlay_v0340_tierpin/regression.sh selects only
    # the two discriminating ones (-k 'does_not_evict or degrades_to_miss');
    # the third (protection released at schedule end) is a liveness check.
    python3 -m pytest -q -p no:cacheprovider -rfE test_step_hit_protection.py
    ;;
  upstream)
    cd /upstream || exit 2
    python3 -m pytest -q -p no:cacheprovider -rfE tests/v1/kv_offload \
      --junitxml="/out/$LABEL.xml"
    ;;
  *)
    echo "unknown suite $SUITE" >&2
    exit 2
    ;;
esac
