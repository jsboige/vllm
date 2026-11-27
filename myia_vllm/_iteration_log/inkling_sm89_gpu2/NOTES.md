# Inkling 2 Mini on SM89 — GPU 2 feasibility test (22/11/2026)

**Status:** run in the GPU 2 slot granted by ai-01:CoursIA-2 (thread
`ai01-vllm-gpu2-inkling-slot-20261122`), 11:30→13:25Z, under `run_guarded.py` with the ledger
reservation held. Four runs. **Inkling 2 Mini boots and serves on a 4090 (SM89) once the
extensible KV cache is disabled**, CUDA graphs on. Results below.

**Why:** registry Q67, user GO (a) on 22/11 08:41Z: « Ok demande un créneau et continue à
suivre ce dossier en parallèle de tes activités. Peut-être qu'un TurboQuant ou équivalent
permettrait d'augmenter le QVCache? » The context is in memory `project-inkling2-mini-evaluation`.
On 21/11 the model could not run on SM89. Since then, upstream PR
[vllm#69165](https://github.com/vllm-project/vllm/pull/69165) (Ar4ikov, head `e966dafbb`) adds an
SM80/86/89 path. The PR validated it on 2×3090; **SM89 itself has never been executed**. The PR
says: « SM89 takes native e4m3 without PDL, a combination that nothing above executed or
compiled ». The capacity obstacle is still open: about 226K KV tokens in bf16 at TP=2 (peaster),
against 793,516 for Swift.

## TurboQuant: not applicable, fp8 KV is the equivalent lever (verified in code, not run)

Inkling has its own attention backend:
- `Inkling2AttentionBackend(FlashAttentionBackend)`, with relative-attention Triton kernels;
- its own KV spec, through `SlidingWindowManager` and `FullAttentionManager`.

None of this goes through `turboquant_attn.py`. The capacity levers are:

- **KV fp8.** `vllm/models/inkling2/nvidia/attention.py:295` only opens `fp8` on
  `is_device_capability_family(120)`, and #69165 does not change that line. The SM8x loaders
  (`ops/attention_sm90.py:_load_fp8_kv`) convert natively with `cvt.rn.f16x2.e4m3x2`, which needs
  sm_89 or later. peaster's compose says so too: « the fp8 KV kernels in this build need
  sm_89+ ». That would mean ~2× KV (SUPPOSED, this test measures it).
- **INT4 AWQ weights** (#69141, not in this overlay): 7.49 vs 8.88 GiB/GPU at TP=2.
- **Text only, no drafter:** peaster measured pools of 287K–405K at TP=2.
- **Low `--max-num-batched-tokens`:** the sliding-window reservation grows with it.

## Overlay `inkling-sm89-test:v1` (source: `overlay/`)

- Base: `vllm/vllm-openai:nightly-647a76866b4559a74e27d1c6b55fbffe85c07ce4` (22/11 07:20). It
  carries #69028, #69021 and #69168, with `torch_cuda_arch_list` including 8.9.
- #69165 was merged onto that commit with `git merge-tree` (tree `e51aaa7e`). There is one
  conflict, in `ops/linear.py`, and it is import-only: the nightly renamed `gemv` to
  `ll_gemm_sm120`, and the PR adds `use_pdl` and `pdl`. Both sides are kept. No other file of the
  overlay references `gemv`.
- `files/vllm/` holds the PR's 15 runtime files (including the new `e4m3.py` and `pdl.py`) as
  merged, plus `nvidia/attention.py`. That file carries **one line that is not upstream**: fp8 KV
  is opened on sm_89+ only when `MYIA_INKLING_FP8_KV_SM89=1`, and is off by default. With that,
  one image serves both modes.
- `files/tests/models/inkling2/`: the full upstream test directory, as merged.
- `MANIFEST.txt` + `SHA256SUMS`: 24 files.

## Harness

- `serve_inkling.sh`: GPU 2 only, `CUDA_DEVICE_ORDER=PCI_BUS_ID` + `CUDA_VISIBLE_DEVICES=2`
  (`--gpus device=2` alone no longer isolates under WSL2, measured 30/10).
  - TP=1, text only, no drafter.
  - `MAXLEN=4096`, `--max-num-batched-tokens 1024`, `--max-num-seqs 2`, gpu-util 0.90.
  - Selectors: `KV=bf16|fp8` and `EAGER=0|1`.
  - Weights: `C:/vllm_models/Inkling-2-Mini` at revision `b85c3cfa`, the original NVFP4/MXFP8
    checkpoint. At TP=1 they take 17.64 GiB (peaster), so a 4090 with the 2.02 GiB DXG tax has
    little KV room. **The bf16/fp8 pool RATIO is the measurement**; absolute TP=1 capacity
    does not predict TP=2.
- `test_window.sh`, run under `run_guarded.py --gpu-entity myia-ai-01#gpu2` with a hard
  `STOP_AT`:
  1. isolation probe, which must show exactly one device on pci 72:00.0;
  2. upstream unit tests (`pytest tests/models/inkling2`, bounded);
  3. bf16 boot, then KV pool, passage NLL, single-stream decode and GSM8K (budgeted);
  4. the same with fp8 KV.
  - Abort if GPU 0 grows more than 1.5 GiB during a boot.
- `probe_nll.py`: teacher-forced passage NLL through `prompt_logprobs=0`.
  **Instrument validated on prod Swift (22/11): NLL 1.697 over 246 tokens, 0 multi-entry
  positions.**
- `probe_decode.py`: single-stream greedy decode, tok/s from `usage`. Validated on prod Swift.

## Results (22/11, GPU 2, TP=1, `MAXLEN=4096`, text only)

Isolation probe passed on every run: one device, pci 72:00.0. GPU 0 never grew during a boot.
The weights take **17.64 GiB** at TP=1, as peaster measured.

| Run | Change | bf16 | fp8 |
|---|---|---|---|
| 1 | first try | unit tests not collected (`tests/__init__.py` from dist-packages shadowed the copy); boots failed, root cause lost by `--tail 80` | same |
| 2 | test-path and log fixes | **fails**: 2.13 GiB KV needed at 4096, 1.5 GiB available | **fails**: 1.81 GiB needed, 1.5 GiB available |
| 3 | `EAGER=1` | **fails**: 2.13 needed, 1.59 available | **fails**: 1.81 needed, 1.59 available |
| 4 | `EXTKV=0` (`--no-enable-extensible-kv-cache`), graphs on | **boots: KV 6,826 tokens, 1.67× at 4096** | **boots: KV 8,006 tokens, 1.95× at 4096** |

Raw outputs: `results/run1/` … `results/run4/`. Run 4 also keeps the `run_guarded.py` log:
the window ended `rc=0` in 2,376 s, and the GPU 2 ledger hold was released at 13:08:41Z, with
GPU 2 back to 0 MiB.

### Why runs 2-3 failed: the extensible KV cache, not CUDA graphs

The profiler found **3.64 GiB** for the KV cache in runs 2 and 3. Then, after warmup,
`finalize_extensible_kv_cache` (`v1/core/kv_cache_planning.py:1811`) kept **1.88 GiB "for
transient activations"** (log: "1.54 GiB allocated at peak, 1.88 GiB of torch reservation
growth") and left 1.5–1.59 GiB to the KV cache, below the 2.13 GiB one 4096-token request needs.
Eager mode (run 3) moved this by only 0.09 GiB, so CUDA graphs were not the cause. The nightly
turns the cache on by default and sets gpu-util to 1.0 with it.

With the cache disabled (run 4): 3.55 GiB available, CUDA graphs captured in 25 s for 0.09 GiB.
This is the same feature prod disables on Swift (`--disable-extensible-kv-cache`, 19/11), where it
had halved the pool after warmup (412,345 against 793,516). The flag's name differs: the nightly
uses `--no-enable-extensible-kv-cache` (BooleanOptionalAction).

### Run 4, bf16 KV

- KV pool **6,826 tokens** (3.55 GiB), max concurrency **1.67× at 4096**.
- Passage NLL **1.596** over 267 tokens (ppl 4.93), `prompt_logprobs=0`. Prod Swift scored 1.697
  on the same passage with the same instrument; the tokenizers differ, so this is a sanity check
  that the SM89 path computes sensible logits, not a quality ranking.
- Single-stream greedy decode **49.4 tok/s** (1,267 tokens in 25.6 s). Prod Swift does
  ~54 tok/s on TP=2.
- GSM8K **129/150 = 86.0 %**, 0 request errors: the first 150 questions in file order, 2 workers,
  stopped by the 465 s budget (`rc=124` is the timeout, expected). This is a partial,
  unrandomized subset. For scale only: the Qwen3.6 MoE scored 87.6 % on the full 1,319 in April.
  It is not a comparison.

### Run 4, fp8 KV (`MYIA_INKLING_FP8_KV_SM89=1`, the overlay's opt-in line)

- KV pool **8,006 tokens**, max concurrency **1.95× at 4096**: **+17.3 %** over bf16 (6,826).
  That matches the per-request costs runs 2-3 printed (2.13 → 1.81 GiB, −15 %).
- Passage NLL **1.5952** against 1.5959 in bf16 (Δ −0.0007 over 267 tokens): on this passage,
  fp8 KV did not change the logits measurably.
- Single-stream greedy decode **45.6 tok/s** (1,417 tokens in 31.1 s): **−7.7 %** against bf16,
  plausibly the e4m3 → f16 conversion in the SM8x loaders (SUPPOSED, not profiled; one run
  of 3 requests each side).
- GSM8K **319/386 = 82.6 %**, 0 request errors, stopped by its 1,200 s budget. On the 150
  questions both modes answered: **bf16 129, fp8 126** (86.0 vs 84.0 %). A 3-question gap on
  150 is within the noise of one run; no quality loss from fp8 KV is established either way.

### Upstream unit tests on SM89 (run 2, `pytest tests/models/inkling2`, 845 s)

**236 passed, 6 failed, 45 errors, 83 skipped.** This was the first execution of #69165's suite
on SM89.

- **2 failures are real SM89 numerics**:
  - `test_core_ops.py::test_e4m3_conversions_match_torch`: the SM89 e4m3 conversion bug that
    [vllm#69200](https://github.com/vllm-project/vllm/pull/69200) fixes;
  - `test_moe.py::test_nvfp4_quantize_picks_better_of_four_and_six`: `assert tensor(False)`.
- **4 failures are harness-side**: the four `test_model.py::test_tiny_model_generates`
  parametrizations fail with `ModuleNotFoundError: No module named 'tests.v1'`, because the overlay
  copies only `tests/models/inkling2`.
- **The 45 errors are harness-side too**: `test_moe`, `test_model` and `test_dspark` need the
  `dist_init` fixture from vLLM's top-level `conftest.py`, which the overlay does not copy.

So the SM89 path is not clean upstream yet: one known bug with a fix PR open, and one nvfp4
quantizer mismatch with no tracked fix.

## What this means for « TurboQuant ou équivalent »

- **The lever that unblocked SM89 was the extensible KV cache, not quantization.** Disabling it
  gave back 1.9 GiB at TP=1, enough to boot.
- **fp8 KV is the TurboQuant-class lever available here, and it buys +17 % at 4K, not ×2.**
  Measured: pool 6,826 → 8,006 tokens, NLL unchanged, decode −7.7 %, GSM8K within noise. The
  printed per-request cost drops from 2.13 to 1.81 GiB. If fp8 halves what it compresses, that
  is 0.64 GiB compressed and ~1.49 GiB left untouched. Which state makes up the untouched part
  (sliding-window, short-conv) is inferred from the two printed costs, not read from the
  allocator. On long contexts the full-attention part should dominate, so the fp8 gain should
  grow with length (SUPPOSED, not measured beyond 4096).
- TurboQuant proper does not apply: Inkling's attention backend does not go through
  `turboquant_attn.py` (see the section above).
- **The real candidate is still TP=2 on GPUs 0/1, in place of Swift.** That needs a prod window
  and the user's GO. At TP=1 a 4090 holds about 1.7 requests of 4K: a feasibility answer, not a
  capacity one.

## Paired capability bench vs Swift (23/11/2026, 23:40:13Z → 01:15:22Z, GPU 2)

Until 24/11 this run lived only in a scratch draft and a CoursIA comment. The draft is kept here
as [`paired_bench_20261123.md`](paired_bench_20261123.md). Engine: image `inkling-sm89-test:v2` =
nightly `647a76866` (v0.34.0rc1) + #69165 + #69141 (INT4 experts) + #69181 (tail-only widened to
SM8x) + fp8 KV, batch 1024, async scheduling off, extensible KV off. `MAXLEN=16384`,
`max_tokens=8192`, weights 14.87 GiB, TP=1.

- **Pool: 227,429 KV tokens in fp8 on ONE 4090 at gpu-util 0.90** (13.88 requests of 16,384).
  It replaces the 8,006 of the day before, which was measured at `MAXLEN=4096` without tail-only.
- **Paired verdict**: MMLU-Pro 76.7 % vs 83.8 % raw (p = 0.0201), **p = 0.82 on the 184 items
  Inkling did not truncate**; IFEval 94.0 % vs 89.5 % (117 of 200 items, p = 0.125); tools
  81.2 % vs 100 % (**p = 0.0312**); LiveCodeBench not run (window over).
- **Per-request decode**, computed on 24/11 from the bench files (`completion_tokens / latency_s`,
  4 concurrent, same prompts): Inkling median **40.9 / 44.0 / 31.4 tok/s** vs Swift
  **24.6 / 26.2 / 24.5** on MMLU-Pro / IFEval / tools. Inkling had a dedicated card and Swift was
  measured on prod under real traffic, so the ratio favours Inkling.
- **End-to-end latency for the same task is no better, because Inkling writes more.** Median
  completion tokens 1021 vs 458 (MMLU-Pro), 1428 vs 815 (IFEval), 134 vs 75 (tools). Median
  latency 24.0 s vs 19.6 s (MMLU-Pro), 33.3 s vs 33.6 s (IFEval), 15.6 s vs 4.5 s (tools).
- **The six tool failures are behavioural, not parser errors** (read on 24/11 in the bench's
  `tools.jsonl`, OpenAI path): it answers the arithmetic itself instead of calling `calculator`
  (`calc_sqrt`; `calc_percentage` has the same signature: no call, `end_turn`), asks for the
  timezone instead of calling `set_alarm` (the Anthropic twin: no call, 496 tokens), emits
  `web_search` without its `query` argument, and calls `get_weather` although the weather is given.
- **Not established**: context above 16,384 (prod serves 262,144); capacity and throughput at TP=2
  on GPUs 0/1 at gpu-util 0.71 with 48 streams; code quality (LiveCodeBench missing).

## Upstream watch — 2026-11-27 06:1xZ (REST, one call per artifact)

- **`vllm#69165` (SM8x kernels) MERGED 2026-11-27T04:12:08Z**, after 32 comments (third-party
  validation on RTX 4090, then SM120, SM80 and SM86). Our `inkling-sm89-test:v2` was built as
  nightly `647a76866` + #69165 + #69141 + #69181, so **the SM8x layer is now upstream**: the next
  release that carries it removes that local patch. Nothing to rebuild for a bench that is already
  planned — the existing image stays valid.
- **New third-party measurement on `#69181`** (`LDD19`, 2026-11-26T17:01:34Z): SM86, TP2 on
  2×RTX 3080 20 GB, DSpark, run on #69165's head at 32K, with the tail-only gate widened to SM8x
  (RAPPORTÉ, not measured by us). It points the same way as the SM89 and XPU datapoints.
- `#69444`: mergify conflict only (2026-11-26T15:13:59Z), no new content; `mgaruccio`'s XPU
  +22.0 % capacity is already recorded above.
- **GPU-2 slot status**: granted (a), undated. Its condition — host commit ≤ 90 % — is **met**
  (55.1 % at 2026-11-27T06:05Z) and GPU 2 is free (0 MiB), **but the bench cannot run**: the
  host's GPU prestart hook has been broken since 2026-11-26T15:58Z (NVIDIA driver installed under
  the running WSL VM), so **no `--gpus` container starts at all**. The slot now waits on the same
  repair as the production engine, not on capacity.
