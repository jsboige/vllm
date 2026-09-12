# Qwen3.8-27B GPU-2 re-test (fork issue #35) — 2026-09-12

Window: ~16:50Z start, GPU 2 exclusive, prod :5002 untouched. GO user 09-12
(preempts the unanswered 09-11 ASK to CoursIA). Announced on workspace-CoursIA
+ workspace-vllm.

Goal: re-evaluate the quality-tier 27B (08-20 verdict: quality yes, throughput
no) on the unexplored "GPU 2 TP=1" slot, with the levers validated in prod on
09-11 (fp16 mamba state, prefix-match-unit 16) + v0.29.0 + MTP-3 + fp8 KV.

## Config (serve_qwen38.sh)

`cyankiwi/Qwen3.8-27B-AWQ-INT4` (GS-32, BF16 MTP head), TP=1, GPU 2 strict
(`--gpus device=2`), port 127.0.0.1:5022 keyless, image `vllm/vllm-openai:v0.29.0`
(digest aa542864b00a, same as prod), `VLLM_WSL2_ENABLE_PIN_MEMORY=1`,
`VLLM_USE_FLASHINFER_SAMPLER=0`, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`,
fresh compile-cache volume `vllm-compile-cache-qwen38-27b-eval-v0290`,
`--kv-cache-dtype fp8` (NOT TQ: TQ×MTP degenerate on stock, vllm#53180),
`--speculative-config mtp/3`, `--mamba-ssm-cache-dtype float16`,
`--prefix-match-unit 16`, `--prefix-caching-hash-algo sha256`,
`--default-chat-template-kwargs {"reasoning_effort":"medium"}`,
parsers qwen3_coder/qwen3, `--dtype auto`, `--no-enable-flashinfer-autotune`,
HF_HUB_OFFLINE=1.

Final memory config after boot saga: **max-model-len 32768, gpu-util 0.90,
max-num-seqs 16, mm DISABLED** (`--limit-mm-per-prompt {"image":0,"video":0}`
+ `--skip-mm-profiling`) — eval is text-only.

## Boot saga (11 attempts, 7 distinct findings)

1. **HF hub nesting trap** (attempt 1): the WSL-side hub nests one extra level
   (`.../huggingface/hub/hub/models--...`). Prod mounts the PARENT onto
   `/root/.cache/huggingface` (HF_HOME). Mounting the parent onto
   `/root/.cache/huggingface/hub` puts models one level too deep →
   `LocalEntryNotFoundError` under HF_HUB_OFFLINE. Fix: mount
   `...\hub\hub` → `/root/.cache/huggingface/hub`.
2. **WSL2/DXG VRAM tax on containers** (attempts 2-4): a BARE CUDA context in a
   `--gpus device=2` container sees only **21.97/23.99 GiB free** (host
   nvidia-smi: 45 MiB). ~2 GiB is consumed by the paravirtualization layer
   before vLLM allocates anything → effective gpu-util ceiling ≈ **0.91**
   (0.92 fails the startup check deterministically; 21.91 < 22.07).
3. **Footprint too big with mm ON + 64K** (attempt 2, util 0.90): PyTorch at
   22.42 GiB + 2.37 GiB KV ask = 24.79 GiB wanted — structurally impossible on
   one card. Weights ~16 GiB (Process bytes 17179869184) + MTP head + mm
   profiling activations. Fix: mm off + 32K context.

4. **`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` breaks on WSL2 DXG**
   (attempts 5-6, twice, deterministic): passes a plain 3 GiB alloc but dies
   with `RuntimeError: CUDA driver error: device not ready` inside the Marlin
   repack (`marlin_utils.py:518`, advanced indexing `zp[...][:, scale_perm]`)
   during `process_weights_after_loading`. Without the env var the repack
   passes. Do not use expandable_segments in GPU-2 containers on this host.
5. **MTP-3 structurally impossible on ONE card with this checkpoint**
   (attempts 2 & 7): after weights+overhead PyTorch sits at 21.55 GiB and the
   drafter's BF16 vocab embedding asks a fixed **2.37 GiB**
   (`qwen3_5_mtp.py:244` → `vocab_parallel_embedding create_weights`) → 23.9
   GiB total on a card whose usable ceiling is ~21.9 GiB (DXG tax). MTP
   dropped for this eval; acceptance was already characterized on TP=2
   (08-20: 0.75-0.79 solo, ÷1.6 under load). Also seen at attempt 2 with mm
   ON at 22.42 GiB — same fixed 2.37 GiB ask, so the mm savings (~0.9 GiB)
   were never going to close a 2.37+ gap.

6. **KV accounting is dominated by the CUDA-graph estimate, not activations**
   (attempts 9-10): with the cudagraph memory profiler OFF, available KV
   went NEGATIVE (-2.99 GiB at batch 8192); with `--max-num-batched-tokens
   2048` (profiler back ON) it got WORSE (-3.33 GiB) — the batch cap did not
   help and the estimator dominates the budget (~3 GiB). Best accounting seen:
   attempt 8 (profiler ON, batch default, mm off, no MTP, 32K): **+0.15 GiB
   available KV ≈ 5K tokens** — still short of even one 16K sequence.
7. **STRUCTURAL: this quant cannot serve with usable KV on ONE 4090.**
   Weights ~16 GiB + activation/profiling ~2.4 GiB + cudagraphs ~3 GiB
   ≈ 21.4 GiB of the ~21.9 GiB usable (DXG tax). Every lever short of
   disabling cudagraphs leaves ≤0.15 GiB. The 08-20 note ("KV très serré,
   ~14 Go poids — non exploré") is now explored: it is not tight, it is
   infeasible. Salvage path for the QUALITY half of #35: `--enforce-eager`
   (attempt 11, drops the ~3 GiB graph budget entirely; decode ~÷3, but
   GSM8K/IFEval only need correct outputs, not speed). Throughput on this
   slot is answered structurally: no graphs = no production-grade serving;
   with graphs = no KV.

Also: after `docker rm -f`, the killed engine's CUDA context takes seconds to
release — an immediate re-run trips the free-memory check (attempt 3 was this
race, not a real regression). `sleep 10` added to the script.

Side observation (attempt 1 boot, before OOM): with `--mamba-ssm-cache-dtype
float16`, the GDN decode path falls back to **Triton** — `qwen_gdn_linear_attn.py:511
"Falling back to the Triton GDN decode path: the fused CUDA kernel requires a
BF16 GDN model"`. Same flag family as prod; watch decode throughput.

## Results

**No server could be booted — the eval closed at the feasibility gate.**
12 boot attempts over ~35 min (16:50-17:25Z), 7 distinct failure modes
isolated (see saga above). Best case across every lever: **+0.15 GiB KV
(~5K tokens)** — less than one 16K sequence (0.58 GiB), let alone a serving
pool. No GSM8K/IFEval/bench could run; the quality question was already
answered by the 08-20 TP=2 eval (SWE-bench Pro +8.2; GSM8K/IFEval paired)
and this window's open question was exactly the single-card throughput slot.

### Memory map (measured, one RTX 4090, WSL2 DXG)

| Item | GiB |
|---|---|
| Card total | 23.99 |
| − WSL2/DXG paravirtualization tax (bare CUDA context) | **2.02** |
| = Usable ceiling (startup-check cap ⇒ gpu-util ≤ 0.91) | 21.97 |
| − Weights (cyankiwi AWQ-INT4 + BF16 extras, EngineCore proc) | ~16.0 |
| − Activation/profiling peak (batch 8192, mm OFF) | ~2.4 |
| − CUDA graphs (estimate w/ profiler ON) | ~3.1 |
| = Best observed leftover for KV | **+0.15** |

With MTP-3 the drafter's BF16 vocab embedding alone adds a fixed **2.37 GiB**
on top — structurally impossible. philbert440 GS-128 (~19 GB) is strictly
worse.

## Verdict (fork issue #35)

**The "complément GPU 2 TP=1" slot is INFEASIBLE for Qwen3.8-27B with the
cached quants.** The 27B quality tier remains real (08-20 data), but every
deployment shape on this host is now closed:

- **TP=1, one 4090**: infeasible (this window — no KV survives the weights).
- **TP=2, GPUs 0,1**: measured 08-20, rejected (N=16 5.7×-6.3× slower than
  prod MoE; 119-138 vs 683-872 tok/s).
- The 27B line is therefore **fully explored and closed** unless a
  substantially smaller quant (~≤12 GiB weights) or a different slot
  materializes.

Side findings that outlive this eval (they make the NEXT GPU-2 window
cheaper): hub-nesting mount trap, DXG ~2 GiB tax ⇒ util ≤ 0.91,
expandable_segments breaks Marlin repack under WSL2 ("device not ready"),
MTP head costs a fixed 2.37 GiB, cudagraph estimate ~3.1 GiB vs eager's
higher activation peak. Applicable to the K2-Horizon re-test and any
DSpark/drafter experiment on this slot.

### Decision gates status

- Quality vs prod 3.6: UNCHANGED from 08-20 (tier qualité) — not re-measured
  (no server); no new evidence.
- Throughput vs prod 3.6: answered structurally — the slot cannot host the
  model at serving-grade config; ratios moot.
- Canary TQ×MTP: N/A (neither TQ nor MTP could be loaded).

### Artifacts

- `serve_qwen38.sh` — final config + all the traps in comments (reusable
  skeleton for any GPU-2 vLLM eval: strict pinning, port 5022, DXG ceiling).
- `quality_27b.py`, `bench_27b.py`, `paired_27b.py` — ready-to-run harness
  (unused this window; validated by construction on the K2 originals).
- No results/ directory (nothing ran).
