#!/bin/bash
# DaisyRose GPU 2 quality window, 20/11 (slot 06:00Z-08:00Z granted by ai-01:CoursIA-2).
# Run under CoursIA run_guarded.py --gpu-entity myia-ai-01#gpu2 (held before, released after).
# Hard stop: everything ends by STOP_AT so the device is back at 08:00Z.
set -u
cd /d/vllm
STOP_AT="2026-11-20T07:52:00Z"
OUT=myia_vllm/_iteration_log/daisyrose_eval/results
mkdir -p "$OUT/daisyrose" "$OUT/swift-ref"
log() { echo "[$(date -u +%FT%TZ)] $*"; }
left() { echo $(( $(date -u -d "$STOP_AT" +%s) - $(date -u +%s) )); }
cleanup() { log "teardown: docker rm -f daisyrose-eval"; docker rm -f daisyrose-eval >/dev/null 2>&1; sleep 12;
            nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; }
trap cleanup EXIT

log "pre: GPU state"; nvidia-smi --query-gpu=index,pci.bus_id,memory.used --format=csv,noheader
G0_BEFORE=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0)

# 1. isolation probe WITHOUT a CUDA context: which PCI bus does CUDA device 0 map to?
PROBE='import ctypes;c=ctypes.CDLL("libcuda.so.1");assert c.cuInit(0)==0;n=ctypes.c_int();c.cuDeviceGetCount(ctypes.byref(n));b=ctypes.create_string_buffer(32);c.cuDeviceGetPCIBusId(b,32,0);print(n.value,b.value.decode())'
P=$(MSYS_NO_PATHCONV=1 docker run --rm --gpus '"device=2"' -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e CUDA_VISIBLE_DEVICES=2 \
    --entrypoint python3 vllm-openai-v0340-tierpin:v1 -c "$PROBE" 2>&1 | tail -1)
log "isolation probe: $P"
case "$P" in
  "1 "*":72:00.0"*) log "isolation OK (one device, pci 72:00.0)";;
  *) log "ISOLATION NOT PROVEN -> abort, nothing started"; exit 11;;
esac

# 2. serve
MSYS_NO_PATHCONV=1 bash myia_vllm/_iteration_log/daisyrose_eval/serve_daisyrose.sh || { log "serve failed"; exit 12; }
for i in $(seq 1 180); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:5022/health)
  [ "$code" = "200" ] && break
  st=$(docker inspect daisyrose-eval --format '{{.State.Status}}' 2>/dev/null)
  if [ "$st" != "running" ]; then log "engine died (status=$st)"; docker logs --tail 60 daisyrose-eval 2>&1; exit 13; fi
  G0=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0)
  if [ $(( G0 - G0_BEFORE )) -gt 1500 ]; then log "GPU 0 grew by $((G0-G0_BEFORE)) MiB during boot -> abort"; exit 14; fi
  [ "$(left)" -lt 900 ] && { log "boot too slow, not enough window left"; docker logs --tail 40 daisyrose-eval 2>&1; exit 15; }
  sleep 10
done
[ "$code" = "200" ] || { log "never healthy"; docker logs --tail 60 daisyrose-eval 2>&1; exit 16; }
log "DaisyRose healthy"; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
MSYS_NO_PATHCONV=1 docker exec daisyrose-eval du -sb /models/daisyrose
docker logs daisyrose-eval 2>&1 | grep -aE 'GPU KV cache size|Maximum concurrency|warp_quant|Loading weights took|Model loading took' | tail -8

# 3. paired quality, same window, bounded
BUDGET=$(( $(left) - 60 ))
log "bench budget ${BUDGET}s"
export VLLM_API_KEY_MEDIUM=$(grep -m1 '^VLLM_API_KEY_MEDIUM=' myia_vllm/.env | cut -d= -f2-)
# quality_27b.py parses --max-samples-* but never applies them: one process per bench so
# GSM8K and IFEval both progress; items are submitted in index order, so both models
# complete overlapping prefixes and the pairs intersect.
PIDS=""
for b in gsm8k ifeval; do
  ( timeout "$BUDGET" env -u VLLM_API_KEY_MEDIUM python myia_vllm/_iteration_log/qwen38_27b_gpu2/quality_27b.py       --benchmarks $b --model daisyrose-27b --base-url http://127.0.0.1:5022/v1 --workers 4       --output-dir "$OUT/daisyrose" > "$OUT/daisyrose/run-$b.log" 2>&1; echo "rc=$?" >> "$OUT/daisyrose/run-$b.log" ) &
  PIDS="$PIDS $!"
  ( timeout "$BUDGET" python myia_vllm/_iteration_log/qwen38_27b_gpu2/quality_27b.py       --benchmarks $b --model swift-1.5-27b --base-url http://localhost:5002/v1 --workers 2       --output-dir "$OUT/swift-ref" > "$OUT/swift-ref/run-$b.log" 2>&1; echo "rc=$?" >> "$OUT/swift-ref/run-$b.log" ) &
  PIDS="$PIDS $!"
done
wait $PIDS
log "benches done"; tail -n 2 "$OUT"/*/run-*.log
docker logs --tail 3 daisyrose-eval 2>&1
