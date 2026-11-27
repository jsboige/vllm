#!/usr/bin/env bash
# Runs INSIDE the ephemeral test container (no --gpus). Usage:
#   bash /stage/run_tests.sh <patched|base|none> <logname> <pytest args...>
# Overlays /stage/<variant>/vllm/** onto the image's installed vllm package
# (pure Python only; compiled .so stay the image's), copies the staged test tree
# to /tmp/wt and runs pytest there. Everything -> /logs/<logname>.log.
set -uo pipefail
VARIANT="$1"; shift
LOGNAME="$1"; shift
LOG="/logs/$LOGNAME.log"
: > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }

SP=$(python3 -c "import vllm,os;print(os.path.dirname(vllm.__file__))")
say "== $(date -u +%Y-%m-%dT%H:%M:%SZ) variant=$VARIANT"
python3 -c "import vllm,sys;print('== vllm', vllm.__version__, '| python', sys.version.split()[0], '|', vllm.__file__)" | tee -a "$LOG"

if [ "$VARIANT" != "none" ]; then
  SP_PARENT=$(dirname "$SP")
  n=0
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    # $f is repo-relative and starts with "vllm/" -> land it at
    # <dist-packages>/vllm/... (NOT <dist-packages>/vllm/vllm/...).
    install -D -m 644 "/stage/$VARIANT/$f" "$SP_PARENT/$f" && n=$((n+1))
  done < /stage/files.txt
  say "== overlaid $n files from /stage/$VARIANT (list: /stage/files.txt)"
fi
say "== installed tiering/manager.py: _lookup_hits occurrences = $(grep -c '_lookup_hits' "$SP/v1/kv_offload/tiering/manager.py")"
say "== installed tiering/manager.py sha256 = $(sha256sum "$SP/v1/kv_offload/tiering/manager.py" | cut -d' ' -f1)"
say "== staged   tiering/manager.py sha256 = $(sha256sum "/stage/$VARIANT/vllm/v1/kv_offload/tiering/manager.py" | cut -d' ' -f1)"
say "== nested stray dir present? $(test -d "$SP/vllm" && echo YES-BAD || echo no)"

mkdir -p /tmp/wt
cp -r /stage/tests/. /tmp/wt/
cat > /tmp/wt/pytest.ini <<'EOF'
[pytest]
markers =
    slow_test
    skip_global_cleanup
    core_model
    hybrid_model
    cpu_model
    cpu_test: mark test as CPU-only test
    split
    distributed
    optional
EOF
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/tmp/wt
say "== cmd: python3 -m pytest -p no:cacheprovider --rootdir=/tmp/wt -c /tmp/wt/pytest.ini $* -q -rfEs"
python3 -m pytest -p no:cacheprovider --rootdir=/tmp/wt -c /tmp/wt/pytest.ini "$@" -q -rfEs >> "$LOG" 2>&1
rc=$?
say "== pytest exit code: $rc"
tail -n 40 "$LOG"
exit $rc
