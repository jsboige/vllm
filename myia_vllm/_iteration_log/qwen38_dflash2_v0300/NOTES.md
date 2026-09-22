# Qwen3.8-27B + DFlash2 (W4A16 drafter) eval — 2026-09-22, BLOCKED UPSTREAM at boot

Window 15:22→15:59Z (GO user, "lance l'eval maintenant"). Prod restored healthy 15:59:22Z
(boot ~4 min on warm `…-v0300` compile volume), RC=0, outage ~37 min. Baseline A1 was
captured before the swap (bench_concurrent_scaling.py, warm MoE):
N=1 86.3 · N=2 111.0 · N=4 212.7 · N=8 441.7 · N=12 627.8 · N=16 815.9 t/s.

## Goal

Re-open the line closed 08-20 (TP=2: N=16 5.7-6.3x): DFlash2 #52816 now ships in our prod
image v0.30.0, a W4A16 drafter exists (`syvai/Qwen3.8-27B-DFlash2-W4A16`, 1.28 GB), and
measured prod utilization is <1% (peak N=4/16) — the dense throughput cost is a future
cost. Eval profile: `medium-qwen38-27b-dflash2.yml` (v0.30.0, fp8 KV, philbert440 GS-128
default / cyankiwi GS-32 fallback, `--prefix-match-unit 16` + mamba fp16 for parity with
prod PR #37).

## What worked (validated before the crash)

- Profile renders correctly (`docker compose config` verified — no flag truncation).
- Drafter checkpoint mechanics WORK: `Resolved architecture: DFlash2DraftModel` — the
  syvai card's speculator section auto-maps, conv/selector fields flow, `method:"dflash"`
  at serve is correct. fp8 KV accepted, spec scheduler engaged
  (`max_num_scheduled_tokens 4096 based on the speculative decoding`).
- V2 runner + pin-memory env: no UVA error (the gate held, as in the v0.30.0 bump).

## Root cause of the boot crash (VERIFIED in source)

Both quants, every restart (37 crash-loops on cyankiwi leg), both TP workers:

```
AttributeError: 'QKVParallelLinear' object has no attribute 'weight'
```

`vllm/model_executor/models/qwen3_dflash.py:472`, `_build_context_kv_buffers()` (called
from `_build_fused_kv_buffers()` after weight load):

```python
kv_weights = [a.qkv_proj.weight[a.q_size :] for a in layers_attn]
self._fused_kv_weight = torch.cat(kv_weights, dim=0)
```

The DFlash(2) drafter slices the TARGET's attention KV projections into one fused GEMM
buffer. On a pack-quantized target (compressed-tensors pack AWQ INT4 — both cyankiwi and
philbert440), `qkv_proj` exposes `weight_packed`, not `weight` → hard crash. Not a
quant-specific issue: philbert440 and cyankiwi failed identically, ~45 s into weight
loading, deterministic.

Implications:
- DFlash/DFlash2 spec on vLLM v0.30.0 requires an UNQUANTIZED target (fp8 per-channel is
  also wrong here: the code slices weight rows but not the per-channel scale — drafts
  would be silently incorrect, so that path is not a workaround).
- Qwen3.8-27B BF16 = 54 GB > 2×24 GB pool → no viable unquantized target on this host.
- The club-3090 community run (AutoRound INT4 + DFlash2) used the oceanplexian FORK,
  whose patch set ("guard LM head UnquantizedEmbedding/Linear") addresses exactly this
  family — upstream is still unpatched.

## Philbert440 note (secondary finding)

philbert440/Qwen3.8-27B-W4A16-AWQ boots no further than cyankiwi — same AttributeError,
same phase. (On v0.27.1-overlay in August it booted; that proves nothing about v0.30.0 —
the crash is spec-path, not quant-path.) GS-128 KV advantage (+11%) remains unmeasured
here.

## Drafter download gotcha (operator, reusable)

`hf download` through a `\\wsl.localhost` 9p bind with Xet storage enabled leaves a
~0-byte stub blob and prints "✓ Downloaded" — silent corruption. Fix: re-download with
`HF_HUB_DISABLE_XET=1` (plain HTTP), verify `du -sb` inside WSL against the repo size
(1,280,633,960 B — exact match after the fix). Also: in Git Bash, `-v '//wsl...'`
forward slashes make Docker create a PHANTOM local dir; use the exact `.env`
HF_CACHE_PATH backslash form via PowerShell.

## Where this leaves the reopened line

- **DFlash2 leg: blocked upstream** until `_build_context_kv_buffers` handles (or
  config-validates against) pack-quantized targets. Upstream issue filed (see below).
- **Remaining viable spec-dec for an AWQ target: MTP-3** (BF16 head, cyankiwi's ignore
  list = the Todd recipe). August shape: single 25-42 t/s, N=16 119-138 t/s — the
  quality tier costs single-stream responsiveness vs the MoE's 86-94 t/s.
- The 27B line stays OPEN as a quality-tier option; the decision now needs either (a) an
  MTP-3 same-window A/B (known trade, measurable today) or (b) waiting for upstream
  pack-quant support for dflash. Registry Q6 updated.

## Artifacts

- Profile: `myia_vllm/configs/docker/profiles/medium-qwen38-27b-dflash2.yml` (kept —
  becomes runnable the day upstream lands the fix; drafter + both quants are in cache)
- Bench parameterized: `BENCH_MODEL` env in `bench_concurrent_scaling.py`
- Compile volume `vllm-compile-cache-qwen38-dflash2-v0300` left in place (fresh, ~empty)
