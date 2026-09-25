# Swift-1.5-Qwen3.8-27B promotion (eval 2026-09-24 → prod 2026-09-25)

## Context and decision

User pivot (2026-09-24): the fleet engine moves from the Qwen3.6-35B-A3B MoE to
**Swift-1.5-Qwen3.8-27B** (ukisai finetune, token-economy). Reasons:

1. **The 27B tier is where the ecosystem iterates** — Swift-1.5 finetunes exist,
   Qwen 4 27B was announced at Apsara (22/09) as the permanent open-weight local
   tier, while the 35B-A3B MoE line has no announced successor.
2. **Lean prover quality** (#1453): "il sera nécessaire d'avoir le meilleur
   modèle qu'on peut héberger sur notre matériel" — the 27B dense is the quality
   tier (SWE-bench Pro +8.2 vs MoE).
3. **Window-based access was ruled out** ("on va galérer avec des fenêtres
   d'utilisation") → permanent replacement, not an eval window pattern.

Model: `ukisai/Swift-1.5-Qwen3.8-27b-W4A16-AWQ` — compressed-tensors pack-
quantized W4A16 group_size 128; ignore list = vision blocks + linear_attn +
lm_head (attention and GDN stay BF16, routed weights quantized). Hybrid 48 GDN
linear-attention + 16 full-attention layers, class `Qwen3_5ForConditionalGeneration`
(same family as the prod MoE — same parsers, same chat template, vision preserved).
`mtp_num_hidden_layers: 1`, `mtp_use_dedicated_embeddings: false`. 262K native
context. License Swift Open v1.0 (free under $1M revenue). Card claims: −58.5%
thinking tokens, LiveCodeBench 81.71 vs base 76.76.

Slot: **TP=2 on GPUs 0,1** (TP=3 impossible: intermediate_size 17408 and
num_key_value_heads 4 are not divisible by 3; GPU 2 is also on the slower bus —
TP never spans it). Same VRAM envelope as the MoE.

## Timeline (all UTC)

- 20:0x download (hf CLI; `huggingface-cli` is deprecated in v0.30.0), ~19.6 GiB
  quant landed in the WSL HF cache.
- Eval profile `eval-swift15-27b-mtp.yml` derived from `medium-qwen38-27b-dflash2.yml`
  (proven TP=2 boot on this host, stock v0.30.0). Alias `qwen3.6-35b-a3b` kept —
  consumers transparent.
- **MTP-3 boot CRASH** (see bug below) — diagnosed in ~7 min, `--speculative-config`
  line removed, relaunch clean.
- **Engine healthy 20:56:40Z**, boot ~3.5 min warm-ish (fresh compile-cache volume
  `vllm-compile-cache-swift15-27b-v1`; cold was 10-25 min on earlier stacks).
- nbaudit-hourly **disabled** for the window (schtasks /Change /Disable).
- Prover pass 3 started 22:30:01Z (target `Lidman.lean:81 unknotting_11n102_upper`,
  MoE baseline 2→2 in 3,276 s) — result: see below.
- Promotion 2026-09-25: prod profile `medium-swift15-27b.yml` (engine + watchdog
  v5 + wedge-telemetry), 13-gate battery, swap, nbaudit re-enabled.

## Measured on this host (eval window, no spec-dec, fp8 KV, gpu-util 0.70)

| Metric | Swift-1.5-27B | Prod MoE (reference) |
|---|---|---|
| KV cache tokens | **465,423** (1.78× the 262K window) | 934,660 (3.56×) |
| VRAM GPU 0 / GPU 1 | 19,911 / 18,786 MiB | 19,344 / 18,294 |
| Single decode | 48.3 t/s | ~86 t/s (A1 baseline 09-22) |
| N=4 concurrent agg | ~99 t/s | — (N=16 ~834) |
| Prefill @101K | 1,812 t/s | 5,448-8,316 t/s (N=1 probes) |
| Boot | ~3.5 min | ~4.5 min |

Fleet-impact read (the honest trade): **fresh long-context first turns are
~3-4× slower to first token** (prefill scales with active params: 27B vs 3B);
decode ~0.5-0.6×. Prefix caching (prefix-match-unit 16, verified live on this
engine) is the mitigation for repeated contexts. The user accepted this for the
quality tier; consumers on hot paths (claudish reroute, condensation, sk-agent
short turns) are unaffected in practice — see condensation A/B below.

## Dashboard condensation A/B (same real input, 24/09 evening)

Faithful replica of RSM condensation (`dashboard.ts`: system prompt, temp 0.3,
max_tokens 7200, enable_thinking false — thinking disabled at every call site
since 2026-05-26, so **no provisioning change** and Luna 6.0 stays a plan B, not
a requirement):

- Small input: 15.6 s.
- Real-size input (old status + 18 intercom messages incl. 3 kept):
  **30.8 s, 2,575 → 1,578 tok out**.
- **Quality ≥ MoE on the same input**: Swift preserved the numeric metrics AND
  kept the #2767(b) "recreate drainé 14:18Z était un no-op compose" nuance that
  the MoE's actual condensation had dropped. Local condensation viable.

## Prover pass 3 (quality signal)

Setup identical to the MoE baselines: all roles local (reasoning/fast/tactic/
search/critic), max_iter 8, workflow_timeout 1800s, file backup `Lidman.lean.pre-pass3`.
MoE baselines: Folk 1→1 (2,073 s), Lidman 2→2 (3,276 s — honest failure, no false
success).

RESULT: **FAILED (honest) — sorry 2→2, 3,037.6 s (wall 3,642 s), 3 iterations,
file intact** (POST count 2, delta 0). Same outcome as the MoE baseline (2→2 in
3,276 s) on this deliberately hard target → parity, no regression signal. Notable:
the build-aware guard caught 5 implicit sorries (apply?/exact?/solve_by_elim) the
agents introduced and REVERTED the file to entry state — the #1453 iter-3 guard
worked as designed. Coordinator correctly marked the goal intractable at +802 s
but the workflow ran its full reasoning budget (SearchAgent → TacticAgent chain).

## 13-gate battery (first run, 2026-09-24 ~23:34Z): 9/13 + causal analysis

PASS: smoke, vision (4/4 couleurs), tool-calling (get_weather Lyon), thinking,
preserve_thinking, prefill-30k (1,885 t/s), survie, prefill-95k (1,726 t/s),
survie. prefill-95k consistent with the eval-window 1,812 t/s.

FAIL ×4 — ALL cascading from ONE event at prefill-235k:

1. 235K-token prefill on the dense 27B takes ~136 s at 1,726 t/s (MoE: ~58 s).
2. The watchdog's 24-token decode probe could not complete for 2×40 s
   (decode=000 at 23:34:39 and 23:35:49Z) → WEDGE path → `docker restart` at
   23:35:49Z (watchdog v5 working as designed).
3. The restart killed the API server mid-request → validate.py got
   RemoteDisconnected → "moteur mort" for the survie probe → the two N=16
   gates ran against a rebooting engine → 0 tok/s.

**So the engine never crashed and left no traceback** — this is a
long-prefill-vs-watchdog conflict: any request whose prefill monopolizes the
scheduler ≥80 s trips the wedge detector. On the MoE the same gate ran in
58.6 s, under the 80 s window. Fleet exposure: hermes/nanoclaw tails
(150-250K prompts) would trip a restart per request. Mitigations to test:
**Solo retest at 4096 chunks (23:41Z)**: the 235K request PASSED (253,502 tokens
in 179.4 s ≈ 1,414 t/s with queueing) — engine never at fault. But 3 consecutive
25-s probes timed out during it: **real starvation of new requests** — chunked
prefill does NOT interleave arrivals on this config (chunks pipeline; the decode
queue stays empty for the whole prefill). The watchdog's 40 s probes squeaked
through this time (no restart) vs tripping at the gate battery: the 235K wall
sits right at the ~80 s wedge frontier. Marginal behavior, not a bug.

**16K chunk test (user ask, 23:45Z)** — verdict **REJECTED**:
- KV 387,721 (1.48x) — **−17 % vs 4096** (465,423 / 1.78x)
- Boot ~4 min (torch.compile 55 s extra)
- prefill-95k: 1,401 t/s (SLOWER than 1,885 t/s at 4096)
- prefill-235k: watchdog restart AGAIN at 23:52:04Z — chunking does not shorten
  total prefill monopolization (~130-170 s at this throughput), so it does not
  clear the wedge threshold. −17 % KV for nothing → reverted to 4096.

**Open design question (user registry)**: on the dense 27B, ANY request ≥~100K
tokens starves new arrivals for >80 s → watchdog wedge-restart. Options: watchdog
GEN_TIMEOUT 40→120 s + WEDGE_MAX 2→3 (≈240 s tolerance, weaker real-wedge
protection — a true decode wedge would now cost up to 4 min before restart), or
accept restarts on giant prefills (self-healing, but the giant request is lost).
Deferred — prod runs 4096 with the historical watchdog thresholds meanwhile.

## MTP-3 loader bug (reported upstream: vllm-project/vllm#58807, filed 2026-09-26)

Boot crash on v0.30.0 (stock image) with `--speculative-config
'{"method":"mtp","num_speculative_tokens":3}'`:

```
ValueError: There is no module or parameter named 'fc.weight' in
Qwen3_5MultiTokenPredictor
```

at `utils.py:417` via `qwen3_5_mtp.py` load_weights. Root cause shape: the
checkpoint's MTP head is BF16 dense (`mtp.*` tensors present, 1 layer,
`mtp_use_dedicated_embeddings: false`), but the draft head's Linear layers are
built from the **target's** pack-quantized quant config (the ignore list covers
vision/linear_attn/lm_head but NOT mtp), so the loader expects packed weights
(`weight_packed` naming) that the BF16 checkpoint doesn't carry. Cousin of
#51581 (DFlash2 `_build_context_kv_buffers` slicing `weight` on a pack-quantized
target). Consequence: **MTP is impossible on this quant until fixed** — and
TurboQuant KV + any spec-dec remains forbidden anyway (#53180). Re-test at the
upstream fix; report the bug with this profile as repro.

## Promotion artifacts

- **Prod profile**: `myia_vllm/configs/docker/profiles/medium-swift15-27b.yml`
  (engine + watchdog v5 adapted: container `myia_vllm-medium-swift15-27b`, probe
  model alias, dual `--served-model-name qwen3.6-35b-a3b swift-1.5-27b` — lanes
  migrate to the honest name at their own pace, alias dropped when nothing
  references it) + wedge-telemetry. Compile-cache volume REUSED from the eval
  (`vllm-compile-cache-swift15-27b-v1`) → warm swap.
- **Rollback (armed)**: `medium-qwen36-stock-tq.yml` (MoE + TQ k8v4, KV 936,660,
  compile-cache `vllm-compile-cache-qwen36-stock-tq-v0300` kept). Swap = `docker
  compose -f medium-swift15-27b.yml down && docker compose -f
  medium-qwen36-stock-tq.yml --env-file myia_vllm/.env up -d`.
- Chunk test: `--max-num-batched-tokens` raised 4096 → 16384 (user ask) —
  measured before promotion: [TBD — KV/VRAM/prefill delta]
- Gates: [TBD 13/13]

## Operator traps (specific to this window)

- `hf download` (not `huggingface-cli`) in the v0.30.0 image.
- `-v '\\wsl.localhost\...'` in Git Bash mangles the UNC path — run docker via
  PowerShell for binds, and use the exact `.env` HF_CACHE_PATH.
- Eval profile is engine-only on purpose: a watchdog WEDGE restart would kill a
  prover pass mid-flight. The prod profile carries the sidecars.
