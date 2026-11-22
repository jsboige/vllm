#!/bin/bash
# Inkling 2 Mini SM89 feasibility window on GPU 2 (slot granted by ai-01:CoursIA-2; registry Q67 GO).
# Run under CoursIA run_guarded.py --gpu-entity myia-ai-01#gpu2 (held before, released after):
#   STOP_AT=<ISO-UTC> python D:/CoursIA/scripts/ci/run_guarded.py --limit-gib 8 --max-commit-charge-pct 90 \
#     --gpu-entity myia-ai-01#gpu2 --gpu-holder myia-ai-01:vllm --gpu-workload inkling-sm89-test \
#     --gpu-expected-end <STOP_AT> -- bash myia_vllm/_iteration_log/inkling_sm89_gpu2/test_window.sh
# Hard stop: everything ends by STOP_AT. Never GPUs 0,1. Stages, each skipped when time is short:
#   (image: docker build -t inkling-sm89-test:v1 myia_vllm/_iteration_log/inkling_sm89_gpu2/overlay)
#   1 isolation probe (abort if not exactly one device on pci 72:00.0)
#   2 upstream unit tests tests/models/inkling2 on SM89 (the PR's own suite, first SM89 execution)
#   3 boot bf16 KV -> KV pool, passage NLL, single-stream decode, GSM8K (budgeted)
#   4 boot fp8 KV (env-gated line) -> same probes; the bf16/fp8 delta is the capacity answer
set -u
cd "$(dirname "$0")/../../.." || exit 12   # repo root of THIS checkout (worktree or main)
: "${STOP_AT:?STOP_AT=<ISO-UTC> required}"
D=myia_vllm/_iteration_log/inkling_sm89_gpu2
OUT=$D/results
IMG=inkling-sm89-test:v1
mkdir -p "$OUT"
log() { echo "[$(date -u +%FT%TZ)] $*"; }
left() { echo $(( $(date -u -d "$STOP_AT" +%s) - $(date -u +%s) )); }
cleanup() { log "teardown"; docker rm -f inkling-eval inkling-ut >/dev/null 2>&1; sleep 12;
            nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; }
trap cleanup EXIT
GPU0() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0; }

log "pre: GPU state"; nvidia-smi --query-gpu=index,pci.bus_id,memory.used --format=csv,noheader
G0_BEFORE=$(GPU0)

# 1. isolation probe WITHOUT a CUDA context: which PCI bus does CUDA device 0 map to?
PROBE='import ctypes;c=ctypes.CDLL("libcuda.so.1");assert c.cuInit(0)==0;n=ctypes.c_int();c.cuDeviceGetCount(ctypes.byref(n));b=ctypes.create_string_buffer(32);c.cuDeviceGetPCIBusId(b,32,0);print(n.value,b.value.decode())'
P=$(MSYS_NO_PATHCONV=1 docker run --rm --gpus '"device=2"' -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e CUDA_VISIBLE_DEVICES=2 \
    --entrypoint python3 $IMG -c "$PROBE" 2>&1 | tail -1)
log "isolation probe: $P"
case "$P" in
  "1 "*":72:00.0"*) log "isolation OK (one device, pci 72:00.0)";;
  *) log "ISOLATION NOT PROVEN -> abort, nothing started"; exit 11;;
esac

# 2. upstream unit tests on SM89 (bounded; a hung kernel must not eat the window)
# SKIP_UT=1: a later run in the same slot (run 3, 22/11) when run 2 already recorded them.
if [ "${SKIP_UT:-0}" = "1" ]; then log "unit tests skipped (SKIP_UT=1)"; else
UT_BUDGET=900; [ "$(left)" -lt 4800 ] && UT_BUDGET=600   # capacity (stages 3-4) is the main answer
log "unit tests, budget ${UT_BUDGET}s"
MSYS_NO_PATHCONV=1 docker run -d --name inkling-ut --gpus '"device=2"' --label autoheal=False \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e CUDA_VISIBLE_DEVICES=2 -e HF_HUB_OFFLINE=1 \
  -w /opt/inkling-tests -e PYTHONPATH=/opt/inkling-tests --entrypoint sh $IMG -c \
  'touch tests/__init__.py tests/models/__init__.py && exec python3 -m pytest tests/models/inkling2 -q -rfE -p no:cacheprovider' >/dev/null
# (window 1, 22/11: dist-packages ships its own `tests/__init__.py`, which shadowed the copied
#  namespace package -> "No module named 'tests.models'". A regular package first on PYTHONPATH wins.)
for i in $(seq 1 $((UT_BUDGET / 10))); do
  [ "$(docker inspect inkling-ut --format '{{.State.Status}}' 2>/dev/null)" != "running" ] && break
  sleep 10
done
docker logs inkling-ut > "$OUT/unit_tests.log" 2>&1
log "unit tests: status=$(docker inspect inkling-ut --format '{{.State.Status}} rc={{.State.ExitCode}}')"
tail -n 6 "$OUT/unit_tests.log"
docker rm -f inkling-ut >/dev/null 2>&1
fi

# Full engine log on failure, then the first error lines (window 1, 22/11: a --tail 80 kept only
# the API server's "See root cause above" and lost the worker traceback).
boot_cause() {
  docker logs inkling-eval > "$OUT/boot_$1.full.log" 2>&1
  grep -anE 'Error|Exception|error:|assert|Traceback|raise |not supported|unsupported|requires' "$OUT/boot_$1.full.log" \
    | grep -v 'Failed core proc' | head -40 > "$OUT/boot_$1.cause.txt"
  log "full log $(wc -l < "$OUT/boot_$1.full.log") lines; first error lines:"; head -n 20 "$OUT/boot_$1.cause.txt"
}

run_mode() {  # $1 = bf16|fp8
  local kv=$1
  [ "$(left)" -lt 1500 ] && { log "skip $kv: not enough window left"; return 0; }
  log "boot KV=$kv"
  KV=$kv MSYS_NO_PATHCONV=1 bash $D/serve_inkling.sh || { log "serve $kv failed"; return 1; }
  local code=000
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:5022/health)
    [ "$code" = "200" ] && break
    st=$(docker inspect inkling-eval --format '{{.State.Status}}' 2>/dev/null)
    if [ "$st" != "running" ]; then log "engine $kv died (status=$st)"; boot_cause "$kv"; return 1; fi
    G0=$(GPU0); if [ $(( G0 - G0_BEFORE )) -gt 1500 ]; then log "GPU 0 grew by $((G0-G0_BEFORE)) MiB during boot -> abort"; exit 14; fi
    [ "$(left)" -lt 600 ] && { log "boot $kv too slow"; docker logs --tail 40 inkling-eval 2>&1; return 1; }
    sleep 10
  done
  [ "$code" = "200" ] || { log "$kv never healthy"; boot_cause "$kv"; return 1; }
  log "$kv healthy"; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
  docker logs inkling-eval 2>&1 | grep -aE 'GPU KV cache size|Maximum concurrency|Model loading took|Loading weights took|kv_cache_dtype|capability|Humming|PDL|e4m3' | tail -20 > "$OUT/boot_$kv.kv.txt"
  cat "$OUT/boot_$kv.kv.txt"
  python -X utf8 -I $D/probe_nll.py http://127.0.0.1:5022/v1 inkling-2-mini "$OUT/nll_$kv.json" "$kv" || log "nll $kv failed"
  python -X utf8 -I $D/probe_decode.py http://127.0.0.1:5022/v1 inkling-2-mini "$OUT/decode_$kv.json" "$kv" 3 512 || log "decode $kv failed"
  local gb=$(( $(left) - 900 )); [ "$kv" = "bf16" ] && gb=$(( gb / 2 - 600 )); [ "$gb" -gt 1200 ] && gb=1200
  if [ "$gb" -gt 120 ]; then
    mkdir -p "$OUT/gsm8k_$kv"; log "gsm8k $kv budget ${gb}s"
    timeout "$gb" env -u VLLM_API_KEY_MEDIUM python myia_vllm/_iteration_log/qwen38_27b_gpu2/quality_27b.py --benchmarks gsm8k --model inkling-2-mini \
      --base-url http://127.0.0.1:5022/v1 --workers 2 --output-dir "$OUT/gsm8k_$kv" > "$OUT/gsm8k_$kv/run.log" 2>&1
    log "gsm8k $kv rc=$? lines=$(wc -l < "$OUT/gsm8k_$kv/gsm8k_results.jsonl" 2>/dev/null)"
  fi
  docker logs --tail 5 inkling-eval 2>&1
  docker rm -f inkling-eval >/dev/null 2>&1; sleep 12
}
run_mode bf16
run_mode fp8
log "window done"; ls -la "$OUT"
