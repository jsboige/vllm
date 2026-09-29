# HyperQwen eval on Swift-1.5-27B — window 2026-09-29 (GO user "Go co maintenant sur nos gpus 0 et 1" + "activer tous les gains de perfs possibles")

## Context

[syv-ai/HyperQwen](https://github.com/syv-ai/HyperQwen): stock vLLM 0.30.0 wheel + patch
series (fork `cpuchip/vllm` branch `qwen38/0.30`, tag `qwen38/0.30-cut5`). Built for
Qwen3.8-27B on one 24 GB card; TP=2 "works" per roadmap (no published TP=2 numbers).
Our interest: (1) MTP on a quantized Qwen3.8-27B checkpoint — family of our loader bug
vllm#58807 (`qwen3_5-embed-quant` patch); (2) DFlash2 lookup-drafting (n-gram over
context; our workloads quote heavily); (3) split-KV verify attention on fp8 KV sm89
(`triton-spec-attn-fp8-kv`); (4) perf extras: INT8_ACT (W4A8 Marlin — weights stay
int4, activations int8; NOT a requant), PREFILL_ATTN=int8-QK (gated on Qwen3.8-27B
geometry, which Swift shares).

## Baseline (prod Swift, same-window, 2026-09-29 ~01:1x local, warm, post-reboot)

`bench_concurrent_scaling.py` (temp 0, no thinking, 256 tok, ladder):

| N | 1 | 2 | 4 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|
| agg tok/s | 44.0 | 60.3 | 103.7 | 196.4 | 293.4 | 450.1 |
| per-stream med | 46.1 | 38.3 | 40.5 | 38.2 | 36.8 | 37.6 |

## Window mechanics

- Announced on `global` (+cross-posts CoursIA, roo-extensions) BEFORE swap. Usage-registry form honored.
- Eval profile: `myia_vllm/configs/docker/profiles/medium-swift15-hyperqwen-eval.yml`
  — same container names/port 5002/dual served names/watchdog v5 (GEN_TIMEOUT=90)/telemetry
  as prod; only image (`ghcr.io/syv-ai/hyperqwen:latest`), compile-cache volume
  (`vllm-compile-cache-swift15-hyperqwen-eval`), and per-mode spec blocks differ.
- Rollback armed at all times: eval down → `medium-swift15-27b.yml` up (prod profile untouched).
- Boots: BASE (prod-identical flags) → gates → DFLASH mode C → MTP mode D → INT8 extras.

## Mode flag deltas (from their single-user/start_qwen.sh)

- DFLASH (mode C analog): `--speculative-config '{"method":"dflash","model":"syvai/Qwen3.8-27B-DFlash2-W4A16","num_speculative_tokens":15,"draft_sample_method":"probabilistic"}'`
  + env `VLLM_DFLASH2_LOOKUP=1`, `VLLM_SPEC_DECODE_ATTN=1`, `VLLM_SPEC_DECODE_ATTN_QMAX=16`
  + `--attention-backend FLASH_ATTN --kv-cache-dtype bfloat16 --max-model-len 65536` (bf16 KV pool).
  Drafter already in local HF cache (`models--syvai--Qwen3.8-27B-DFlash2-W4A16`, 1.2G).
- MTP (mode D analog): `--speculative-config '{"method":"mtp","num_speculative_tokens":3}'`
  + env `VLLM_SPEC_DECODE_ATTN=1` + keep `--kv-cache-dtype fp8 --attention-backend TRITON_ATTN`
  (their k=4 crashes at CTX=long per launcher comments; k=3 it is).
- INT8 extras: env `VLLM_MARLIN_INPUT_DTYPE=int8`, `VLLM_MARLIN_INT8_INCLUDE_RE=mlp|linear_attn|self_attn`,
  `VLLM_PREFILL_ATTN=int8`. Boot-time fail-loud on incompatible quant export; drop if refused.

## Results

(filled as the window progresses)

### BASE boot
HEALTHY in ~6 min (torch.compile 51.7 s, cold volume). KV **465,423 tokens — identical to
prod** (their memory profiling agrees). Thinking on/off + reasoning field + dual served
names OK. Only log "errors" = benign transformers Qwen3VL docstring warnings.
Ladder: N=1 36.0 / N=2 57.1 / N=4 97.1 / N=8 203.5 / N=12 305.4 / N=16 460.3
(vs prod 44.0/60.3/103.7/196.4/293.4/450.1) → concurrent ≈ +2-4 %, single-stream lower
(small-sample N=1; BASE's job was sanity, passed).
Operator incident: single-`$` PATH in profile edit → compose interpolated the HOST PATH
(parentheses) into the container script → dash syntax error crash-loop. Fix `$$PATH`.
Image layout: NGC CUDA 13 base, patched wheel in **/app/venv** (entrypoint custom) →
profile must `export PATH=/app/venv/bin:$$PATH` + `cd /app`; driver 616.92 OK for CUDA 13.

### DFLASH+lookup (k=15, bf16 KV, FLASH_ATTN, 65536 win)
Boot ~10 min (cudagraphs captured to 512). "DFlash2 lookup-augmented drafting on
(k=15 nmin=6 nmax=12 nstrong=6 agree=0 nmin_tail=4 longmin=6)" — 7 drafted + 8 from
context per step. HEALTHY.
Ladder: N=1 33.5 / N=2 **71.0** / N=4 **156.0** / N=8 219.9 / N=12 214.6 / N=16 216.4
→ **N=4 +50-60 % vs prod (per-stream med 57.6 vs ~40)**, N=2 +17-24 %, N≥12 collapses
(−30/−53 %) — exactly their documented "speculation wins below ~8 concurrent".
Our real load (running=0 78-92 % of minutes, 1-4 when active) is squarely in the win zone.
**Quote test (copy 1,433-tok passage verbatim): 343.2 tok/s, output byte-exact** —
7.5× prod single-stream. Acceptance pos-0 ≈ 80 % aggregate over the bench set.
This is the mode that matters for our agent workloads (condensation/nbaudit/prover quote).

### MTP
**FAILED — the EXACT #58807 error, unpatched by their wheel**: `ValueError: There is no
module or parameter named 'fc.weight' in Qwen3_5MultiTokenPredictor` (fc exposes
weight_packed/weight_scale/weight_shape/weight_zero_point). Their `qwen3_5-embed-quant`
patch (quant_config → embedding + MTP module) does NOT cover the draft-Linear-vs-checkpoint
case. Their mode D works because their `prepare/` REQUANTIZES the model themselves — a
third-party W4A16-AWQ checkpoint with a BF16-dense MTP head hits the same wall as stock.
MTP on ukisai/Swift stays blocked upstream (#58807). Crash-looped → swapped out immediately.
(Datapoint worth posting on #58807: another distro's patch series confirms the fix family
is requant-side, not loader-side.)

### INT8 extras (mode C+ = DFlash2 lookup k=15 + VLLM_MARLIN_INPUT_DTYPE=int8 + INT8_LAYERS + VLLM_PREFILL_ATTN=int8)
Boot HEALTHY (no refusal of our compressed-tensors AWQ; Marlin kernel logs unchanged —
int8 layer selection is env-silent). KV 129,593 tok @65536 bf16 (1.98×).
Ladder: N=1 44.0 / N=2 **95.7** / N=4 146.7 / N=8 242.6 / N=12 258.2 / N=16 250.7
**vs prod: N=2 +59 %, N=4 +41 %, N=8 +24 %, single parity; N=16 −44 %** (spec collapse,
documented). INT8 beats pure DFlash2 at every N except N=4 (146.7 vs 156.0, within variance).
**Quote test: 374.3 tok/s, copy exact** (best number of the window; pure dflash 343.2).

## Verdict (window 2026-09-29 01:00→02:00Z)

**Technically excellent, not promotable as fleet engine.** The blocker is structural and
known from the 09-22 DFlash2 eval: mode C caps context at **64K** (bf16 KV + drafter), while
Hermes/NanoClaw medians are 121K/103K and a third of claude-* requests exceed 100K — those
requests would be REJECTED. DFlash2-CTX=long variant (int8_per_token_head KV, 150k) exists in
their launcher but was not tested in this window (follow-up candidate).
The gains are real and large in OUR regime (idle 78-92 %, 1-4 concurrent when active):
- +59 % N=2, +41 % N=4, +24 % N=8, single parity
- quoting/copy workloads (condensation, nbaudit, prover): ~8× single-stream (374 vs ~46)
MTP on a third-party quantized checkpoint: still #58807, unpatched by HyperQwen.
BASE sanity: their wheel serves our checkpoint with IDENTICAL KV (465,423) — drop-in
compatible image if ever needed.
Artifacts kept: eval profile (final state = mode C+), compile-cache volume, image
(14.9 GB), this NOTES. Prod restored 2026-09-29 ~02:0xZ.

## Quote-heavy A/B (same passage, temp 0, copy exact on both)

| engine | decode tok/s |
|---|---|
| prod (stock v0.30.0, fp8, no spec) | **50.3** |
| HyperQwen mode C+ (dflash lookup + int8) | **374.3** |

**7.4× on quote/copy workloads** (condensation, nbaudit, prover). Blocked from prod only
by the 64K window; the dflash2-CTX=long variant (int8 KV, 150k) is the follow-up candidate.

### INT8 extras
(pending)
