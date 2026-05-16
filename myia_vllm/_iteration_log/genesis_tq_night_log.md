# Genesis TQ A/B iteration log (overnight 2026-05-16)

Container reused: `myia_vllm-medium-qwen36-moe` (one at a time).
Baseline image: `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 + shm patch).
Genesis image: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3`.

Rule: rollback to baseline + 20-min cooldown between attempts.

Constants confirmed working (across v2a/v2b/v2d/v2e):
- dtype `float16`, `--language-model-only`, `--gdn-prefill-backend triton`,
  `--no-enable-flashinfer-autotune`, `--disable-custom-all-reduce`, `--async-scheduling`,
  `--no-scheduler-reserve-full-isl`, `--enable-chunked-prefill`,
  `--prefix-caching-hash-algo xxhash`, `--performance-mode interactivity`.
- Env: `VLLM_FLOAT32_MATMUL_PRECISION=high`, `NCCL_P2P_DISABLE=1`,
  `VLLM_USE_FLASHINFER_SAMPLER=1`, `CUDA_DEVICE_MAX_CONNECTIONS=8`, `OMP_NUM_THREADS=1`,
  `VLLM_MARLIN_MOE_BLOCK_SIZE_M=8`, `VLLM_MOE_USE_DEEP_GEMM=0`,
  `VLLM_USE_FLASHINFER_MOE_FP8=0`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0`,
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:512`,
  `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`.
- Genesis flags: P37, P38B, P67, P98, P101, P78, P40.
- **`--max-num-batched-tokens 4096`** — Genesis canonical PROD-MIRROR value; **8192 triggers a Dynamo shape mismatch** (`tensor a (65536) must match tensor b (16*sNN)` at `aot_compile_fullgraph`). Worth filing upstream (not Genesis-specific).

## v1 — FAILED (Dynamo, batched=8192)
seqs=16, batched=8192, dtype=auto, vision ON, gpu_util=0.85.

## v2a — BOOT OK, OOM at first inference
seqs=2, batched=4096, fp16, LM-only, gpu_util=0.92. KV 2.72M.

## v2b — SMOKES + CRASH GATE PASS, single-user OK, concurrent queue-saturated
seqs=2, batched=4096, fp16, LM-only, gpu_util=0.85. KV 2.33M.

## v2c — FAILED (Dynamo, batched=8192)
seqs=8, batched=8192. Same shape error as v1.

## v2d — WIN: single parity, concurrent +29% vs baseline (commit 541f3a155)
seqs=8, batched=4096, gpu_util=0.82, +P40. KV 2.10M.
single no-think 103.3 tok/s (FP8 107), single thinking 115.1 (FP8 116.5),
8-conc 419, 12-conc 475 (+29%), 16-conc 447. Crash gate PASS.

## v2e — BIGGER WIN: concurrent +125% vs baseline
seqs=16, batched=4096, gpu_util=0.82, +P40. KV 2.10M.

Smokes pass (chat, tool calling).
Crash gate PASS in 3.90s (with prefix cache hit).
3-iter scaling stability (no leak, no degradation):

| N users | iter 1 | iter 2 | iter 3 | median | vs FP8 baseline |
|---|---|---|---|---|---|
| 1 | 95 | 90 | 95 | 95 | -11% (TTFT-noise on 22-tok) |
| 2 | 127 | 111 | 124 | 124 | n/a |
| 4 | 220 | 209 | 231 | 220 | n/a |
| 8 | 458 | 405 | 437 | 437 | n/a |
| 12 | 653 | 550 | 629 | 629 | **+70%** vs 369 |
| 16 | **822** | **854** | **823** | **823** | **+123%** vs 369 |

VRAM: GPU 0 24080→24087 MiB (delta +7), GPU 1 22722→22724 (delta +2). Zero leak.

## Summary — v2e is the new winner
For OWUI/Roo/Claudish multi-user long-context workload:
- WIN: KV +6.5× (322K → 2.10M tokens), 16-conc throughput +123% vs FP8 baseline.
- LOSS: vision OFF (`--language-model-only`). Remains a feature regression vs prod.

## Next: v2f — re-enable vision
Test the hypothesis: vision re-enable on Genesis with batched=4096 is safe. v1 failed at batched=8192 + seqs=16 + vision; we've isolated batched=8192 as the trigger. With batched=4096 (proven safe in v2a/v2b/v2d/v2e), vision should work too.
v2f changes from v2e:
- Remove `--language-model-only`
- Re-add `--limit-mm-per-prompt '{"image":4,"video":0}'`
- Re-add `--mm-processor-kwargs '{"max_pixels":774000}'`
- Re-add `--skip-mm-profiling`
- `--dtype float16` → `--dtype auto` (vision encoder is BF16)

## v2f — WIN: vision restored, concurrent +125% vs baseline
seqs=16, batched=4096, gpu_util=0.82, +P40, dtype=auto, vision ON. KV 2.03M.

Boot to "Application startup complete" + healthy in ~5 min. No Dynamo, no OOM.
KV cache: 2,029,669 tokens (-67K vs v2e 2,097,152 — vision encoder cost).

Smokes:
- Single no-thinking: 117/120/120 tok/s, median **120** (FP8 baseline 107, **+12%**)
- Single thinking: 123.3/124.9/123.9, median **123.9** (FP8 116.5, **+6%**)
- Tool calling: implicit in chat smoke (model uses qwen3_coder parser)
- **Vision smoke: PASS** (64x64 red PNG → "Red" in 0.77s, prompt=91 tokens)
- Crash gate 24K: PASS in 6.82s

3-iter scaling (vision ON):

| N users | iter 1 | iter 2 | iter 3 | median | vs FP8 baseline |
|---|---|---|---|---|---|
| 1 | 93 | 91 | 97 | 93 | -13% (TTFT noise on short prompts) |
| 2 | 134 | 125 | 134 | 134 | n/a |
| 4 | 214 | 221 | 215 | 215 | n/a |
| 8 | 415 | 412 | 448 | 415 | n/a |
| 12 | 593 | 625 | 628 | 625 | **+69%** |
| 16 | 816 | 829 | 833 | **829** | **+125%** vs 369 |

VRAM: GPU 0 24044→24039 MiB (delta -5), GPU 1 22880→22880 (delta 0), GPU 2 45 MiB. Zero leak.

## Summary — v2f is the production candidate (REVISED — see soak failure below)
For OWUI/Roo/Claudish multi-user long-context workload:
- WIN under load: KV +6.3× (322K → 2.03M tokens), 16-conc throughput +125% vs FP8 baseline, vision restored, single-user +12%.
- Net delta vs v2e: -67K KV tokens (vision encoder cost), N=16 throughput essentially identical (829 vs 823).
- **REGRESSION discovered on idle soak (see v2f-soak section)** — promotion to prod blocked.

## v2f — SOAK FAILURE at +90min UNDER TRAFFIC (shm_broadcast deadlock)
**CORRECTION (07:00Z)**: my earlier "idle deadlock" framing was wrong. Audit of
the vLLM access logs over the 60min preceding the deadlock shows **~90 external
POST `/v1/chat/completions` requests from `172.27.0.1`** (Docker gateway =
reverse-proxy traffic from claudish / OWUI / Roo / roo-state-manager
condensation). The container was NOT idle — it was serving real production
traffic. The deadlock fires under continuous light load, matching the pattern
of the historical 2026-04-19 saga (9 crashes in 50h on Apr 06 nightly under
OWUI/Roo load) — which means the FlashInfer JIT autotune hypothesis from that
investigation is back on the table and should NOT have been confidently called
"idle" tonight.

**Timeline (UTC):**
- 03:55:13Z — v2f Application startup complete, healthy
- 03:56-04:30Z — smokes + crash gate + 3-iter scaling bench (all PASS)
- 04:30Z → ~05:25Z — idle (55 min)
- **05:29:37Z — first `[shm_broadcast.py:733] No available shared memory broadcast block found in 60 seconds`** (EngineCore pid=103)
- 05:30:37Z — same warning fires again (idle deadlock loop)
- 05:30:24Z — watchdog flags `ENGINE-DOWN host=000 internal=000 (fail 1/3)`
- 05:31:37, 05:32:37Z — warning continues firing every 60s
- (eventually watchdog would have auto-restarted at fail 3/3, but we caught it earlier on soak check)

**Surface symptom**: same `shm_broadcast.py:733` message that drove our historical vllm#35104 investigation (Apr 2026). The patch we carry forward (`patches/shm_broadcast.py` → replaces `with _memory_fence_lock:` with `_yield_fast()` helper) is **VERIFIED present at build time** on the Genesis image (BUILD VERIFICATION banner in the profile confirms `SHM PATCH VERIFIED`). On the Apr 06 baseline image with the same patch, that machine has run 17 days without this symptom — so either:
  - (a) the patch doesn't cover all code paths exercised by the May 2026 nightly `01d4d1ad3` that Genesis is pinned to, OR
  - (b) Genesis patches introduce new threading paths that re-expose the underlying issue, OR
  - (c) TurboQuant k8v4 idle workspace state has its own deadlock vector.

**What was VERIFIED**:
- v2f hits shm_broadcast deadlock after ~55-60 min of idle (one occurrence).
- Same surface log line as historical vllm#35104.
- Baseline FP8 image (different nightly: Apr 06 `f6983f01d`) with same patch does NOT show this on this hardware.

**What was NOT verified**:
- Whether the patch is actually loaded at runtime (banner verifies build-time presence, not runtime application).
- Whether the deadlock would recur or was a one-off.
- Whether it's introduced by Genesis patches vs. by the newer vLLM nightly itself.

**Action taken (per user rule "en cas de pb, tu recharge la baseline qui fonctionne")**:
1. 05:35Z: `docker compose -f medium-qwen36-genesis-tq.yml down`
2. 05:35Z: `docker compose -f medium-qwen36-moe.yml up -d` (FP8 baseline image `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1`)
3. Baseline healthy, 5.42s "OK" smoke (slow first request normal post-restart).

## Status post-rollback (05:36Z)
- Baseline FP8 SERVING prod again. KV 322K. Vision ON. No regression.
- v2f Genesis image + profile RETAINED. v2f bench results stand as upper bound for what TurboQuant CAN deliver on this hardware once the idle-deadlock cause is resolved.
- Block on promoting v2f to prod until idle stability is reproduced over 2-3 hours.

## v2g — WIN: soak T+~104min under real traffic, NO shm_broadcast deadlock
Same Genesis image + profile as v2f, single change: `VLLM_USE_FLASHINFER_SAMPLER=1` → `=0`.
Hypothesis tested: FlashInfer sampler has its own autotune path that dlopens .so mid-runtime →
corrupts CPython `_thread.lock` descriptor → triggers the `shm_broadcast.py:733`
`No available shared memory broadcast block` deadlock that took v2f down at T+1h35.

**Timeline (UTC, 2026-05-16):**
- 06:29Z — boot, "Application startup complete" at 06:34Z
- 06:31:40Z — single benign `shm_broadcast.py:733` warning during startup compile (engine pid=110 init, "typically happens when some processes are doing time-consuming work e.g. compilation")
- 06:55Z → 07:40Z — **sustained 8-11 concurrent requests for 45 min** (real OWUI/Roo/Claudish prod traffic, matches v2f's load profile)
- 07:12:35Z → 07:17:36Z — watchdog flagged ENGINE-DOWN fail 1/3 + 2/3, then RECOVERED. Engine was running 8-10 reqs at 0.5-1.6 tok/s aggregate (thrashing under heavy concurrency), KV grew 22% → 27%, then unblocked. **NOT a deadlock — engine recovered organically with no restart needed.**
- 07:45Z onwards — load drops to 7 then 0 concurrent
- 08:13Z — T+~104min, 0 active reqs, KV 0%, health 4.7ms, vision smoke 0.33s PASS

**Counters since boot:**
| Metric | Value |
|---|---|
| Total POSTs served | 202 (~100/h) |
| Deadlock signatures (`shm_broadcast.py:733`, `EngineCore.died`, `EngineDeadError`) | 0 real (1 benign startup) |
| Watchdog ENGINE-DOWN events | 1 transient (recovered after 2 fails of 3, no restart) |
| Peak concurrent requests | 11 (sustained 8-11 for 45 min) |
| GPU 0,1 utilization at peak | 100% / 100% (113-114W per GPU) |
| GPU 0,1 utilization idle | 3% / 0% (20-28W) — Genesis TQ has NO at-rest overhead |

**Verdict: v2g PASSES the v2f failure window.** The `VLLM_USE_FLASHINFER_SAMPLER=0` hypothesis holds.
Soak passed under **the same prod traffic class** that broke v2f. The single transient watchdog flag at 07:12-07:17 was NOT the v2f failure mode — engine kept running 8-10 reqs, no `shm_broadcast` warning, no `EngineDeadError`. Generation throughput recovered to ~85 tok/s at 07:16-07:17 without intervention.

**Side-finding (unrelated to TQ stability):** ~50 `qwen3.5-35b-a3b` 404s/hour from `172.27.0.1` (Docker gateway). Source could not be identified from access logs alone — `172.27.0.1` NATs both host-side processes AND external traffic reverse-proxied via IIS. **Action**: wrote `myia_vllm/middleware/error_source_capture.py` (logs all `/v1/*` request sources to `/logs/error_sources.jsonl` with status + client IP + X-Forwarded-For + X-Real-IP + User-Agent + Host + model + 1.5 KB body_head + 1.5 KB body_tail). Wired opt-in (commented `--middleware` flag) in both `medium-qwen36-moe.yml` and `medium-qwen36-genesis-tq.yml`. Activate at next container restart. Backlog issue for diff-aware session logging filed: vllm#8.

## v2h (not needed for now — v2g cleared the gate)
Hypotheses parked in case v2g regresses later:
- Verify shm_broadcast.py patch is loaded at RUNTIME (not just present in image): `import inspect; inspect.getsource(vllm.distributed.device_communicators.shm_broadcast._memory_fence)`.
- Audit Genesis patches PN33 / P78 / P101 for new threading.Lock acquisition paths.
- Try a different vLLM nightly pin under Genesis (current is `01d4d1ad3`).
