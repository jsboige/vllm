# External patch series `uraniumchonk/llm-engine-qwen-optimization` — evaluated, not adopted (2026-11-28)

**Question (user, 2026-11-28 13:34Z).** Should we adopt the vLLM/LMCache patch series published at
`github.com/uraniumchonk/llm-engine-qwen-optimization`?

**Verdict: no — and nothing in it needs porting for correctness.** The series was written for a stack we
do not run (vLLM v0.33.0 + a DFlash2 speculative drafter + LMCache on 2× RTX 3090). Two of its fixes for
problems that do exist on hybrid GDN models **already ship in our v0.34.0 image**, verified in the image
itself. What is left for us is one small decode idea (≈ 2 % of a decode step, behind a compiled
third-party library) and one TTFT idea for short prefills that its own author did not test in our regime.

No script of the repository was executed, no patch was applied, and nothing in the production profile,
image or engine was changed. The clone lives in `.tmp/uwatch/repo` (untrusted content: its `AGENTS.md`
and `skills/` are written for agents and were treated as data).

## What the series is

- 14 vLLM v0.33.0 patches (v1 = E003, E005, E006a/b/c, E031; v2 adds E042–E047, E052, E053) and 4
  LMCache v0.5.6 patches (E014, E030, E033, E034). Apache-2.0. Public, not a fork, 2 stars, created
  2026-11-07, last push 2026-11-28T12:09:56Z (REST).
- Their rig: Qwen3.8-27B AWQ-INT4 (48 GDN + 16 attention layers — the architecture Swift-1.5 derives
  from) with a DFlash2 W4A16 drafter, 7 speculative tokens, 2× RTX 3090 (sm86) TP=2, fp8 KV,
  `--block-size 1600 --max-num-seqs 4 --max-num-batched-tokens 2048`, LMCache multiprocess, torch
  2.14.0 / Triton 3.8.0 / FlashInfer 0.7.2.post1.
- Their result, single request, greedy (reported): decode step 25.11–26.03 ms (0.33.0 stock) → 18.25–18.29
  (v1) → 15.81–15.84 ms (v2); agent-loop TTFT p50 796 → 230 ms; KV pool +18.7 %.
- Their own limits, stated in the README: one model, one rig; "more than 4 concurrent requests and
  preemption were not measured" on v2; "our patches were not checked against" v0.34.0.

## Verified in our image (`vllm-openai-v0340-fsadmit:v1`, read-only, no GPU)

| Fact | Where | Consequence for the series |
|---|---|---|
| The copy-on-write block copy de-duplicates views on `(device, data_ptr, shape, stride, element_size)`, with a comment naming the hybrid case (a Mamba state view spans only the leading bytes of a block that an attention view spans in full) | `vllm/v1/worker/utils.py:927` (`copy_kv_cache_blocks_inplace`) | The silent-KV-corruption half of **E031** (their measure: KL 1.2e-2 before the fix on 0.33.0) **does not exist in v0.34.0**. No correctness exposure here, nothing to port. |
| `in_proj_ba` is run on an auxiliary stream concurrently with `in_proj_qkvz`, under CUDA-graph capture, for steps of ≤ 256 tokens | `vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py:126-129, 1316-1332` (`_BA_PROJ_OVERLAP_MAX_TOKENS`, `execute_in_parallel`) | **E006a/b/c and E043** shrink a GEMM that v0.34.0 already hides behind `in_proj_qkvz` in our decode steps. |
| `VLLM_GDN_DECODE_KERNEL` exists, default `cuda`; the choice only selects the GDN **spec-decode** fused op | `vllm/envs.py:136, 1294-1301`; `qwen_gdn_linear_attn.py:868-881` | The upstream switch their v2 sets (`=triton`) is a no-op for us: no speculative decoding in prod. |
| FlashInfer is **0.7.3**; torch 2.14.0; Triton 3.8.0; `nvcc` present | `/usr/local/lib/python3.12/dist-packages/{flashinfer_*,torch-*,triton-*}.dist-info`, `/usr/local/cuda/bin/nvcc` | **E052** reads private fields of 0.7.2.post1 and exists to remove a `seq_lens.cpu()` wait caused by draft acceptance — moot without a drafter, and a port would have to be re-derived. **E053**'s library is buildable in the image (sm_80 SASS runs on sm_89) but is a compiled artefact to rebuild at every torch or vLLM bump. |

## Patch by patch

| Patch | What it does | For us |
|---|---|---|
| E003 | Triton attention with software fp8 KV decode, so the drafter can leave FlashInfer on pre-SM89 GPUs | No. The 4090 is SM89 with native fp8, and we have no drafter. |
| E005 | Forces the hybrid KV cache group size (`VLLM_KV_GROUP_SIZE=16`) instead of the smallest layer count | No. The padding comes from draft-only sliding-window buckets. Our groups are 48 GDN / 16 attention, so the smallest count is already 16. Upstream fixed the drafter case in vllm#68533 (merged to `main` 2026-11-19, after v0.34.0). |
| E006a/b/c, E043 | Small-M split-K Triton GEMM for GDN `in_proj_ba` during spec decode | No. Already hidden upstream in v0.34.0 (table above). |
| E031 | Prefix hits on a 64-token grid inside the 1,600-token block, plus the copy-on-write fix | No. The lookup half covers the drafter's sliding-window group; we have run `--prefix-match-unit 16` since 2026-09-11 (whole-prompt hits measured then: 7,696 of 7,699 tokens). The copy fix is upstream (table above). |
| E042, E044, E045 | DFlash2 drafter: 3D split-KV sliding-window attention, NVFP4 copy of the drafter's lm_head, local argmax across TP ranks | No. Drafter only. |
| E046 | Text-only steps skip the multimodal embedding merge | No value even on their rig: "no measurable step change". |
| E047 | Prefill steps of ≤ 256 tokens run GDN through one in-place recurrent Triton kernel | **Only patch with a mechanism that reaches us** — see below. Not adopted now. |
| E052 | FlashInfer decode plan built before the sequence-length sync | No. Moot without a drafter; private fields of another FlashInfer version. |
| E053 | Marlin W4A16 GEMMs with M ≤ 8 launch with one block per group of whole output columns (compiled extension) | **One transferable idea** — see below. Not adopted now. |
| E014, E030, E033, E034 | LMCache: checkpoint-only GDN/drafter state, local skip, synchronous eviction | No. We run vLLM's native GPU→RAM→fs tiers, not LMCache. |

### E047 — short GDN prefill (not adopted)

- Reported on their rig: TTFT 39 new tokens 54.9 → 30.8 ms; +131 tokens on a 9,856-token cached prefix
  154.4 → 106.2 ms; at 128K context +50 tokens 216.0 → 197.7 ms. Kernel test: 48-layer GDN prefill
  T=16 26.8 → 3.5 ms, T=256 26.5 → 13.5 ms. The stock path is "bound by CPU kernel launches".
- Why it could matter here: agent-loop turns resume from a cached prefix and prefill a short delta, and
  WSL2 does not make CPU launch overhead cheaper.
- Why not now: it is a v0.33.0 patch to a vendored Flash-Linear-Attention file and would need re-porting to
  0.34.0; its own card says it was **not verified "a short prefill arriving while another request
  decodes"**, which is our normal regime; output is not bitwise identical (KL 4.08e-4); and our time to
  first token under load is queue-bound, not compute-bound — during the 13:00→13:24Z wall the engine sat
  at KV 65–99 % with 0–8 requests waiting, so 20–50 ms of GDN prefill per step is second-order.
- Re-open condition: a window A/B that first measures where our own short-prefill step time goes.

### E053 — whole-column Marlin for small M (not adopted)

- Reported: −0.29 / −0.46 / −0.40 ms per decode step at 16K / 64K / 128K, with M ≤ 8 (one request, 8
  draft tokens). Their kernel-level reading (E049): Marlin at M ≤ 8 costs 4.6–5.2 µs fixed per call plus
  weight bytes, 256 calls per step.
- Relevance: our typical decode step has 3–12 running sequences, so M ≤ 8 is common here; the model is
  the same architecture, so the shapes (N 3,584–17,408, K 1,024–17,408, group 32) are ours.
- Cost: a compiled `.so` (sources are ten upstream vLLM v0.33.0 files pinned by sha256 under
  `csrc/quantization/marlin/`, plus a generator — nothing foreign, but a build step and a rebuild at
  every torch, CUDA, vLLM or architecture change); two more environment variables; output not bitwise
  identical at M = 1 and M = 8 (KL 4.16e-4, "about the 4.5e-4 reference level for a tree or
  compile-cache change"). Not measured by them at M = 2–7.
- Reading: ≈ 2 % of a decode step at low concurrency, for a permanent build artefact in an overlay we are
  trying to keep to a handful of Python files. The underlying observation (Marlin's default launch
  config at M ≤ 8) is upstream-quality; the right home for it is vLLM, not our overlay.

## Why their numbers do not transfer

Single request or 4 requests, `--max-num-seqs 4`, batch 2048, LMCache on, 300 W, bare-metal Linux. Ours:
2–48 concurrent users through the hub, batch 8192, native tiers, WSL2. Our binding constraint is KV
capacity and queueing at long context (24.9 M prompt tokens per hour against 0.71 % served from the disk
tier), not a single stream's decode step. None of the 18 patches targets long-prefill throughput.

## The lever that is not in the patches: `gpu-unlock`

Their 2026-11-28 rows were measured with the GeForce half-rate tensor mode (FP16/BF16 inputs with FP32
accumulate) unlocked by a kernel module, `Zagitta/gpu-unlock`. Reported on their rig (A/B, 3090, v0.33):
cold 72K prefill +32.8 / +38.8 / +40.2 % at 250 / 300 / 350 W; 4-request decode step −8.9 % to −13.7 %;
1-request decode step −0.6 % to −1.2 %; logits identical (KL 0 over 1,978 tokens). The module's README
(read 2026-11-28, public REST) lists the RTX 4090 as **experimental**, the platform as **Linux only**
(a boot-time kernel module that acts "before the stock NVIDIA driver loads"), and says Windows is not
maintained by its author.

For prefill-bound serving that would be the only item in the whole repository worth a window — and it
**does not apply to ai-01**: the host is Windows 11 and the engine runs in WSL2, where the GPU is driven
by the Windows driver and there is no Linux NVIDIA kernel module to hook. Whether the same half rate
limits our 4090s under WSL2 is **not measured here**; the module's table (165 → 329 TFLOPS BF16 on a
4090) is their claim, not our reading. Revisit only if the production host ever moves to bare-metal Linux.

## What we take from it

The method, not the patches: decode-step anatomy per kernel class, a correctness yardstick that is a
top-20 decode-logit KL against a **measured same-build noise floor** rather than text comparison, and
their list of traps (a `torch.compile` trace freezing a shape predicate so a kernel passes its unit test
and never runs; `nsys --cuda-graph-trace=node` inflating a 58 µs graph launch to 954 µs). Candidate
follow-up: give our window A/Bs a logit-KL gate. The MTP A/B of 2026-11-09 could only report "greedy text
diverges at character 81, similarity 0.94".

## Sources

Read in full: repository `README.md`, `qwen3.8-27b/README.md`, `qwen3.8-27b/results/README.md`; cards
E047, E053 and the GDN-decode-kernel note of `qwen3.8-27b/vllm/v0.33.0/README.md`; `ext/meow_wc/`
(`SOURCES.txt`, `fetch_sources.sh`, `build.sh`). Read on our side: the four locations in the table above,
inside `vllm-openai-v0340-fsadmit:v1`. Not read: the 14 `.patch` files themselves (they target v0.33.0
files; no decision here depends on their content beyond the cards), `AGENTS.md`, the `skills/` folders,
`results/step-anatomy.md`.
