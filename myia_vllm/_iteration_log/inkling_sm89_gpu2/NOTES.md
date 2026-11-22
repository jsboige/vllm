# Inkling 2 Mini on SM89 — GPU 2 feasibility test (22/11/2026)

**Status:** harness ready, slot requested from ai-01:CoursIA-2 (dashboard machine,
`ai01-vllm-gpu2-inkling-slot-20261122`). Nothing has run on GPU 2 yet.

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

## Results

*(pending slot)*
