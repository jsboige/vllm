# v0.27.1 → v0.28.0 image bump + upstream review (2026-09-01)

**Verdict: PROMOTED.** Stock `vllm/vllm-openai:v0.28.0` on the unchanged prod profile
(`medium-qwen36-stock-tq.yml`, gpu-util 0.70, batch 4096, TurboQuant k8v4, 262K context)
passed 13/13 gates and matched or beat the same-night v0.27.1 baseline at every concurrency level.
Interruption: 20:10:28Z (`compose down`) → healthy ~20:14:50Z (**~4.5 min**, cold compile-cache volume).

## Why v0.28.0 (and not a nightly)

Release tag 2026-08-26, 584 commits over v0.27.1, Ubuntu 24.04 runtime, Transformers 5.15.
Nightlies stay rejected: ~5-day GC on Docker Hub makes them irreproducible (the Genesis lesson).
What v0.28.0 carries that touches us:

| Change | PR | Effect here |
|---|---|---|
| Prefix caching default-on for Mamba/GDN, cache mode `align` | #50991 | boot log now says so; we already ran `--enable-prefix-caching` |
| KV-cache layout refactor touching `turboquant_attn.py` | #51704 / #51718 | the reason for the full 250K-prefill re-gate — passed |
| `max_num_batched_tokens` default → 16384 | — | inert, we pin 4096 (see "candidate experiments") |
| Qwen3.5 GDN MTP kernels | #51674 / #51812 | inert without a drafter (none exists for 3.6-35B-A3B in MTP form) |
| DFlash2 + DSpark spec-dec, adaptive verification | #52816 / #47808 / #51310 | not used — see spec-dec section |
| `reasoning_content` → `reasoning` | #50624 | we already read `reasoning` (CLAUDE.md) |

**Not in v0.28.0 — landed 08-22..08-27, in `v0.28.1rc0`, no image yet (watch list):**
- #52676 fused QK-norm + MRoPE + gate for Qwen3.6 (decode perf on exactly our model)
- #52789 Mamba/GDN prefill checkpoints, +9–25 % TTFT claimed
- #53955 CUDA-graph profiling memory released before KV allocation — directly relevant to the
  boot-OOM history (the "+2.1 GiB out-of-pool" overshoot at gpu-util 0.70)

## Procedure

1. Fork sync: `upstream/main` merged into `main` (merge `ab04787120`, 744 commits, 0 conflicts), pushed.
2. `docker pull vllm/vllm-openai:v0.28.0` → `61fc8a896b0a`. **Pull first failed** with
   `authentication required` — a stale Docker Desktop Hub login (credsStore `desktop`, via
   `hubproxy.docker.internal`). Fixed with `docker logout` (+ `docker logout https://index.docker.io/v1/`)
   then an anonymous pull. **Side effect: the host's Docker Hub session is now logged out.**
3. Same-night baseline on v0.27.1 at 20:09Z (`bench_concurrent_scaling.py`, table below).
4. Profile edit — three lines only: `image:` → v0.28.0, compile-cache volume renamed to
   `vllm-compile-cache-qwen36-stock-tq-v0280` (per-image cache; the v0.27.1 volume left intact
   for rollback), matching `volumes:` entry. `compose config --quiet` OK.
5. `compose down && up -d --env-file myia_vllm/.env` at 20:10:28Z.
6. `validate.py` (13 gates, `stock_tq_phase2/validate.py`) then the bench, on v0.28.0.

## Boot (cold compile cache) — StartedAt 20:10:37Z

| Step | v0.28.0 | v0.27.1 reference (08-14, warm) |
|---|---|---|
| Model loading | 82.0 s (11.52 GiB) | ~80 s |
| torch.compile | 17.75 s | ~18 s |
| KV cache | **1,038,194 tokens** (3.96× the 262K window) | 1,030,407 (3.93×) |
| Graph capture | 10 s, 0.82 GiB | ~10 s |
| init engine | 84.98 s | ~85 s |
| VRAM after gates | GPU 0 **20,006 MiB** / GPU 1 **19,002** | 19,336 / 19,040 |
| Backends | MARLIN WNA16 MoE + TURBOQUANT attention, EP=2 | same |

Only "errors" in the boot log: 8 transformers docstring nags (`min_frames`/`max_frames` in
`Qwen3VLVideoProcessorInitKwargs`) — harmless. No `Workspace is locked`, no `turboquant_attn.py`
traceback, no `EngineDead`, no OOM after the 253,503-token prefill.

## Gates (20:15:47Z → 20:19Z) — 13/13 PASS

| Gate | v0.28.0 | v0.27.1 (08-14) |
|---|---|---|
| smoke / vision 4/4 / tool-calling / thinking / preserve_thinking | PASS | PASS |
| prefill-30k (31,417 tok) | 3.8 s → **8,316 tok/s** | 5.9 s → 5,346 |
| prefill-95k (101,838 tok) | 14.0 s → **7,292 tok/s** | ~12.5 s → 8,177 |
| prefill-235k (253,503 tok) | 46.5 s → **5,448 tok/s** | 58.6 s (v0.27.0 gate) |
| survival after each prefill | 0.09–0.10 s `VIVANT` | PASS |
| concurrent-N16 (2 runs) | 542 → **986 tok/s** | 956 |

## Same-night A/B (bench_concurrent_scaling.py, 20:09Z vs 20:19Z)

| N | v0.27.1 agg tok/s | v0.28.0 agg tok/s | Δ |
|---|---:|---:|---:|
| 1 | 85.1 | 93.1 | +9 % (21-token probe, noisy) |
| 2 | 116.1 | 134.2 | +16 % |
| 4 | 215.8 | 222.0 | +3 % |
| 8 | 403.4 | 443.3 | +10 % |
| 12 | 622.9 | 633.5 | +2 % |
| 16 | 813.1 | **828.2** | +2 % |

Read as "no regression, possibly a few % better" — the machine's own noise is larger than
most of these deltas (see `project_machine_throughput_investigation.md`).

## Rollback (armed)

`image:` back to `vllm/vllm-openai:v0.27.1` and the volume name back to
`vllm-compile-cache-qwen36-stock-tq` (both marked in the profile), then
`compose down && up -d --env-file myia_vllm/.env`. Both images are local.

## Investigation — what upstream offers us today (2026-09-01)

### TurboQuant and equivalents
- **Our issue [vllm#53180](https://github.com/vllm-project/vllm/issues/53180)** (TQ × MTP degenerates
  silently on stock) is a **duplicate of #52475**, which has a fix pair open since 08-22 by
  `giannisanni`: **#53406** (correctness: `UNIFORM_BATCH` cudagraph support contradicted
  `supports_spec_as_decode=False`, so verify batches were FULL-captured through a non-capturable
  Python prefill loop → repetition collapse / illegal memory access) and **#53410** (perf follow-up:
  spec-as-decode so verify batches keep FULL cudagraphs — without it TQ+MTP decodes *slower* than
  fp8 KV). Both `REVIEW_REQUIRED`, no maintainer review yet. → propose linking #53180 to #52475.
- **#53060** (`xupinjie`): page-local TQ KV ABI + fused store + fused decode attention (q_len=1,
  BF16, head dim 64/128/256, GQA) — a decode-path speedup for exactly our backend. Open, unreviewed.
- **#50248**: TQ cache dtype propagation fix + FP8 store on Ampere — init failures we do not hit
  on Ada (SM89) with this profile.
- **KVarN [#46812](https://github.com/vllm-project/vllm/pull/46812)** still stuck in merge conflicts.
- KV dtype menu unchanged for us: `nvfp4_4over6` is Blackwell-only; `int4_per_token_head` is
  TRITON_ATTN-only. At 2–7 % KV occupancy none of it is a lever anyway.

### Speculative decoding
- **DSpark drafter exists for our exact target**: `RedHatAI/Qwen3.6-35B-A3B-speculator.dspark`
  (`Qwen3DSparkModel`, 5 layers, 1.9 GB BF16, `target_layer_ids` 2/10/20/30/37, 8 spec tokens,
  reported mean accepted length 3.4–5.0). Flag:
  `--speculative-config '{"model":"RedHatAI/Qwen3.6-35B-A3B-speculator.dspark","num_speculative_tokens":8,"method":"dspark"}'`.
- **Blocker with our KV**: `Qwen3DSparkModel` extends the DFlash model → non-causal attention;
  `supports_non_causal` is implemented in flash_attn / flashinfer / triton_attn but **not** in
  `turboquant_attn.py`. fp8-KV non-causal dequant is SM100 trtllm-gen only. On SM89 a DSpark run
  means **bf16 KV (~394K tokens)** — still 1.5× the 262K window, but a KV-dtype change plus a
  drafter is two variables. **Candidate for a dedicated maintenance-window A/B, not done tonight.**
- #53929 (adaptive DSpark verification for Qwen GDN, ragged batches) open since 08-26 — wait for it
  before evaluating, it changes the acceptance profile on hybrid models.
- No MTP or DFlash2 drafter exists for 3.6-35B-A3B. Prior findings (MTP 0 % with AWQ, DFlash −15 %
  at N=5) unchanged.

### Model variants at our size
- `Qwen/Qwen3.8-Flash-Next` (`qwen4_exp`, 512 experts, ~360 GB BF16 ≈ 180B) and GLM-5.3-Flash
  (328 GB) do not fit 2×24 GB even at 4-bit. `Qwen-AgentWorld-35B-A3B` is an environment world
  model, not a chat model. `Qwen3.8-Distill-35B-A3B` is a PoC. → **no replacement candidate**;
  3.6-35B-A3B stays.

### Candidate experiments (deferred, one variable at a time, off-peak)
1. **Batch 8192 / 16384** — the 4096 ceiling was a Genesis P28 buffer artifact; stock has no such
   buffer and v0.28.0's own default is 16384. Needs the FORCING test (several concurrent 2–3K
   prefills summing into one forward >4096) and a watchdog watch.
2. **DSpark on bf16 KV** (above), gated on #53929 or a same-night A/B against TQ at N=1/4/16.
3. **v0.28.1** when tagged: #52676 + #52789 + #53955 are all on our model / our boot-OOM problem.

---

## Experiment: batch 4096 -> 8192 (2026-09-02, 06:28Z)

**Verdict: KEEP 8192 — correctness cleared, throughput neutral, KV cost immaterial.**

Motivation: the 4096 ceiling was a Genesis P28 buffer artifact (v0.28.0's own default is 16384;
stock has no such size-limited buffer). One variable only — batch 8192, max-num-seqs 16 unchanged.

Procedure: profile `--max-num-batched-tokens 4096` -> `8192`, `compose down && up -d --env-file
myia_vllm/.env` (06:28:12Z), healthy 06:32:05Z (~4 min).

Boot: KV **934,374 tokens** (3.56x, was 1,038,194 @4096 — big cudagraphs steal ~10% of the KV
pool, immaterial at 2-7% occupancy), graph capture 10 s / **0.76 GiB** (was 0.82 @4096 — measured
LOWER, so no added boot-OOM surface), VRAM GPU 0 20,006 / GPU 1 19,002 after gates, no
OOM / `Workspace is locked` / Traceback.

GATES: **13/13 PASS** — prefill-30k 8,791 tok/s, prefill-95k 7,573, prefill-235k 5,617 (each
FASTER than batch 4096's 8,316 / 7,292 / 5,448), concurrent-N16 958 tok/s, all survival PASS.

FORCING test (the range (4096, 8192] the Genesis P28 crash lived in): 6 concurrent 2,702-token
prefills, every codeword correct, engine alive after — **PASS**. The Genesis P28 overflow does
not reproduce on stock at batch 8192.

CONFOUND — do not read the A/B table as batch-driven:
- baseline batch4096 was measured 06:26Z on an engine up ~10 h (the uptime-linked degradation
  from `project_machine_throughput_investigation`); batch8192 was measured 06:34Z on a FRESH
  engine (min old). The engine restart alone recovers throughput, so the large "+%" at every N
  (N=1 45->92, N=16 749->816) is engine-freshness, NOT the batch.
- The honest same-freshness comparison is batch8192@06:34Z (N=16 816) vs batch4096@20:19Z last
  night on a fresh engine (N=16 828) — **neutral** (816 vs 828, within machine noise).

Why KEEP: correctness is cleared (13/13 + FORCING), which is the real deliverable (the old
Genesis fear is gone). The concurrency ceiling (3.56x) is still ample and a larger batch absorbs
the multi-tenant prefill-burst pattern better than 4096, even though the flat N=16 microbench
shows no ceiling win. KV cost (934K) immaterial. Rollback = the single `--max-num-batched-tokens`
line back to 4096.

## Experiment: DSpark speculative decoding on bf16 KV (2026-09-02, ~06:38Z) — ABORTED

**Verdict: NOT VIABLE on this host (v0.28.0 / WSL2) — hard blocker found and identified.**

Goal: test the DSpark drafter for our exact target
(`RedHatAI/Qwen3.6-35B-A3B-speculator.dspark`, prefetched) under
`--speculative-config {"model":...,"num_speculative_tokens":8,"method":"dspark"}` with
`--kv-cache-dtype auto` (bf16) and `--attention-backend flash_attn`, as a same-window A/B vs the
batch-8192 TQ prod.

What WORKED: the drafter loads and is recognized — `Resolved architecture: Qwen3DSparkModel`,
`speculative_config=SpeculativeConfig(method='dspark', model='RedHatAI/...', num_spec_tokens=8)`,
and the quote handling was fixed (see below). The model/attention config is accepted.

What FAILED — root cause: the engine cannot initialize because DSpark selects the **V2 model
runner** (`gpu_worker.py:396 Using V2 Model Runner`), and V2 requires **UVA (unified virtual
addressing)**:
```
vllm/v1/worker/gpu/buffer_utils.py:47  raise RuntimeError("UVA is not available")
  at UvaBuffer.__init__ <- StagedWriteTensor <- RequestState <- GPUModelRunnerV2.init_device
```
Prod (TQ, batch 8192) runs the **V1** model runner, so it does not touch UVA — but it is the ONLY
thing that is not the drafter. DSpark (or its attention config) flips the runner to V2, which needs
UVA; UVA is unavailable under **WSL2 GPU passthrough** (the same constraint family as the
`pin_memory=False as WSL is detected` line and the 08-31 libnvidia-ml loss — a WSL2-boundary limit,
not a vLLM bug and not fixable from the profile).

So the earlier "wait for #53929 / non-causal on turboquant_attn" concern is moot on this host:
DSpark will not boot here in v0.28.0 regardless of KV dtype, because V2's UVA requirement is
environmental (WSL2). A V1-runner override (if one exists) was not found; that is the only
remaining avenue and is a further, separate investigation.

Notes:
- `--speculative-config` must be wrapped in SINGLE quotes in the profile (the command block is
  run through `sh -c`). Without them the double-quoted JSON loses its quotes and argparse rejects
  it ("Value {model:...} cannot be"). Same convention as the existing `--mm-processor-kwargs`.
- Drafter footprint on disk: 1.9 GB in the shared HF cache (already present, no re-download).
- No model or non-causal error was reached — the failure is at worker `init_device`, before model
  load. Profile retained as `medium-qwen36-stock-dspark-bf16.yml` (documentation).
- Follow-up (if ever pursued): find what forces V2 (likely `--attention-backend flash_attn` or
  spec-dec itself) and whether a V1 override exists; or run on a non-WSL2 host.
