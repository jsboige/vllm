# Qwen3.8-27B + DFlash2 (W4A16 drafter) eval — 2026-09-22 — window 1 BLOCKED on stock, window 2 PASS on PR-#51684 overlay

## Window 2 (16:26→16:43Z, GO user): overlay image `vllm-openai-v0300-s51684:v1` — THE FIX WORKS

User asked to build a dedicated image with upstream PR **vllm-project/vllm#51684**
("Handle quantized qkv_proj in DFlash fused-KV buffers", SayHelloToWorld, @ b1b3aefa40ca).
Overlay method (same as the August `overlay_v0271_s51812`): file-for-file replacement of
the PR's 4 runtime files on top of stock `vllm/vllm-openai:v0.30.0`. Verified clean:
PR base 73fb19151f4f is an ancestor of v0.30.0 (compare behind=0) and NONE of the 4
files changed in the 291 commits in between — the overlay reverts nothing. The PR routes
the fused-KV precompute through `quant_method` with a tiered strategy (fused quantized
GEMM / dequant) instead of slicing raw `.weight`. Overlay: `configs/docker/overlay_v0300_s51684/`
(Dockerfile + fetched files), import-verified before boot.

- Boot: **~5.5 min to healthy** (16:26:26 → 16:32Z), RC=0, no AttributeError — past the
  exact point where both quants crash-looped on stock (37 loops, window 1). Target this
  time: philbert440 GS-128 (profile default; cyankiwi-on-overlay untested, the crash was
  quant-agnostic).
- **KV 262,504 tokens** = exactly 1.0× the 262K window (August fp8 without drafter:
  383,696). The DFlash2 drafter (1.28 GB) + its num_spec_tokens+1 lookahead margin eat
  the surplus. VRAM GPU 0 20,687 / GPU 1 19,884 MiB (within bounds, < 23,000 alert).
- **Gate battery 16/17 PASS** (validate38.py): vision 4/4 (1.5 s), tools 0.7 s, thinking,
  preserve_thinking, prefills 31K/102K/253K at **1,924 / 1,760 / 1,408 tok/s** (each with
  survival), **quality canary PASS at ratio4g=0.00** (the TQ×spec-dec degenerate family
  does not apply here), single-stream **46/46/41 t/s**, N=16 **155 → 180 t/s**.
- The one FAIL is the acceptance RE-READ after the N=16 legs: 0.48 idle (410/856) →
  **0.21 cumulative under load** (4,964/23,176) — the DSpark pattern, attenuated (DSpark:
  0.07). DFlash2 drafts lose accuracy under batched verification.
- Bench B1 (bench_concurrent_scaling, BENCH_MODEL=qwen3.8-27b): N=1 20 t/s (first-pass
  JIT tax; battery measured 46), N=16 299 t/s. A-brackets on the MoE same-day:
  A1 15:1xZ N1 86.3 / N16 815.9; **A2 16:50Z N1 70.5 / N16 750.9** (machine drifted
  ~10-15% down over the window — evening pattern; bracket confirms no collapse).
- **Ratios (best-B vs worst-A): single 46 vs 70.5 = 0.65×; N=16 299 vs 750.9 = 0.40×.**
  True N16 is likely 180-300 (battery vs bench spread) → 0.22-0.40× — consistent with
  August's 5.7× under MTP, DFlash2 buying some of it back at concurrency.
- Upstream datapoint posted on vllm-project/vllm#51684 (validation from this host:
  pack-quantized target, Ada SM89, WSL2, TP=2 — boot fixed, 16/17 gates, canary clean,
  acceptance 0.48/0.21) to help the merge.

## Verdict

- **The FIX is validated** (that was the ask) — clean boot on a config that
  crash-looped 37× on stock, quality canary clean. Re-test trigger for prod-grade use:
  the PR merging (then stock image suffices).
- **Adoption of the 27B on this host remains a pure quality trade**: single-stream
  0.5-0.66× the MoE, N=16 0.22-0.40×, prefill ~4× slower — DFlash2 does NOT close the
  single-stream gap here (community 134-154 t/s was 1×GPU TP=1 + fork-optimized; we are
  TP=2 + known machine evening trough). The hoped-for inversion does not materialize.
- **KV/context arithmetic (user question)**: 262,504 tokens = ONE full-window
  conversation. Capping `--max-model-len` to 150K would guarantee ~1.75 concurrent
  full-context conversations; 192K → ~1.37. Real occupancy is 2-7% so this binds only
  for batch-agentic use — the pending claudish traffic histogram (per-client context
  sizes, DM sent 16:43Z) is the missing input before capping anything.

## Window 1 (15:22→15:59Z): BLOCKED UPSTREAM on stock v0.30.0

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

## Traffic histogram (2026-09-23): the missing input, now in

Delivered by po-2025:claudish (hub owner) from the hub captures of 2026-09-22: 29,264
requests paired, context size read from `input_tokens` (Anthropic-shaped responses).

| client vector | n | median | P90 | P99 | >50K | >100K | >150K |
|---|---|---|---|---|---|---|---|
| claude-* (Claude Code + Python SDK) | 23,781 | 826 | 216,647 | 785,462 | 34.3 % | 33.0 % | 25.6 % |
| Hermes | 3,637 | 120,770 | 225,220 | 785,462 | 63.7 % | 57.5 % | 35.9 % |
| other (unidentified) | 746 | 130,205 | 208,829 | 242,868 | 76.5 % | 65.1 % | 35.4 % |
| sk-agent | 545 | 423 | 1,970 | 244,368 | 5.0 % | 3.9 % | 3.1 % |
| NanoClaw | 459 | 102,831 | 155,081 | 195,270 | 59.0 % | 52.5 % | 13.7 % |

Vectors were attributed by prompt-content signature (the request envelope carries no
user-agent); the identical 785,462 max on two rows is either two sessions at the same cap
or a residual pairing error, and it does not move the medians or P90s. Volume over 7 days
is dominated by cloud lanes (glm-5.3 71,937 · MiniMax-M3 46,108 · deepseek-flash 17,804 ·
native Opus 9,487 responses); the local lane shows 4 responses through the hub because
local traffic goes straight to :5002.

**Reading.** At 262,504 tokens of KV, two Hermes or NanoClaw turns fill the 27B. Capping
`--max-model-len` does not help the vectors that matter; only sk-agent's short turns would
fit, and there is no hardware slot for a second service (GPUs 0,1 are prod, GPU 2 TP=1 was
closed as infeasible in #35). Recommendation logged as registry Q6: keep the MoE; re-test
the 27B for information only once vllm-project/vllm#51684 lands in a stock image.
Side note for the adoption mandate: a quarter of claude-* requests exceed 150K and the P99
exceeds even the MoE's 262K window.
