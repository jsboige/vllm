# DSpark evaluation on v0.30.0 (2026-09-22, GO user) — **REJECTED for production**

Drafter `RedHatAI/Qwen3.6-35B-A3B-speculator.dspark` (1.77 GiB checkpoint, in HF cache),
target = prod Qwen3.6-35B-A3B-AWQ. Profile `medium-qwen36-stock-dspark-bf16.yml`.

## Why now

The 09-02 attempt died at the WSL2 UVA wall (DSpark forces the V2 model runner). As of
2026-09-22 prod runs V2 (`VLLM_WSL2_ENABLE_PIN_MEMORY=1`) on v0.30.0, which also carries
#55133 (Qwen3 DSpark padded-vocab d2t fix). #53929 (adaptive DSpark verification for
Qwen GDN) is **STILL OPEN** — that turned out to be decisive.

## Boot odyssey (4 attempts, all config-level)

1. **13:21Z — `--enable-expert-parallel` rejected**: `SpeculativeConfig` validation —
   "Number of experts in the model must be greater than 0 when expert parallelism is
   enabled" (the DENSE drafter has 0 experts; EP applies to the whole engine config).
   Fix: drop EP → documented confound (prod TQ runs EP=2; this eval runs pure TP=2
   expert sharding).
2. **13:22Z — flag truncation incident (operator error, mine)**: I inserted `#` comment
   lines INSIDE the backslash-continued shell command. The continuation joins the
   comment line, `#` terminates the command, `exec` replaces the shell → **every flag
   after `--tensor-parallel-size 2` was silently dropped**. Engine booted on defaults
   (gpu-util ~0.9, no parsers, `speculative_config=None`). Detected by the banner, down
   within ~2 min. Signature to remember: `speculative_config=None` in the EngineCore
   banner while `--speculative-config` is in the profile. Lesson persisted to MEMORY.md;
   always render-check (`docker compose config`) after editing a `command:` block.
3. **13:33Z — KV memory check**: weights 12.63 GiB/GPU + drafter ~0.9 + cudagraphs
   1.38 → **2.32 GiB left for KV**, below the 262K requirement (`_check_enough_kv_cache_memory`).
   Fix: `--max-model-len 131072` (the DFlash precedent's playbook).
4. **13:36Z — BOOT OK**: V2 runner, drafter loaded, `speculative_config=SpeculativeConfig`
   populated, **KV 181,163 tokens** (2.32 GiB, max concurrency **1.38×** at 131K),
   health 200 in 3.6 ms.

## Results

**Functional: 12/13 PASS** — the single FAIL is structural (prefill-235K vs 131072
max-model-len; HTTP 400 is the correct rejection). Vision, tool-calling, thinking,
preserve_thinking, prefill 30K (8,465 tok/s) and 95K (7,232 tok/s) + survival all green.

**Acceptance — the verdict** (`/metrics`):
- drafts 4,735 · draft tokens 37,880 (8/step) · **accepted 2,752**
- **7.3 % overall, ≈0.58 accepted token per step**; position 0 ≈ 33 %, near-zero beyond
- vs DFlash on the same target (2026-04-24): 26-47 % per position, 4-7 tokens/step
- Most plausible root cause: **#53929 open** — without adaptive verification the 30 GDN
  layers (75 % of the stack) reject the draft

**Bench A/B same-window** (baseline = v0.30.0+TQ prod, warm, measured ~30 min earlier):

| N | TQ prod warm | DSpark | Δ |
|---:|---:|---:|---:|
| 1 | 91.2-94.0 | 79.4 | **−14 %** |
| 2 | 128.5-129.3 | 137.1 | +6 % |
| 4 | 222.3-226.1 | 290.9 | +30 % |
| 8 | 438.6-455.2 | 503.8 | +12 % |
| 12 | 654.9-660.9 | 479.5 | −27 % |
| 16 | 834.1-847.0 | **559.4** | **−33 %** |

The N=4-8 bump is not credible as a spec-dec effect at 7 % acceptance — more likely the
bf16-KV/TP-sharding path or machine variance. The ends are what matter for our workload:
single-user **worse**, N=16 **−33 %**.

**Structural costs**: context 262K → 131K, KV 934,660 → 181,163 (max concurrency
3.57× → **1.38×** — two users saturate it), EP lost.

**Niche signal (not decisive)**: the thinking gate ran **2.1 s vs 16.0 s** on prod TQ
(~5× on reasoning-style generation, output shorter 1399 vs 1956 chars). Same shape as
DFlash's +94 % single-user reasoning win — and same reason we rejected DFlash: the
workload is multi-user, and concurrent throughput + context capacity win.

## Verdict: **REJECTED** (2026-09-22)

Not viable for production on this target/host today. Re-test when **#53929** (adaptive
DSpark verification for Qwen GDN) merges — that is the single change most likely to move
the 7.3 % acceptance. Profile updated and retained (`medium-qwen36-stock-dspark-bf16.yml`,
now on v0.30.0, EP-free, 131K); dedicated compile-cache volume
`vllm-compile-cache-qwen36-dspark-v0300`.

Rollback to prod executed immediately after measurements (record below).
