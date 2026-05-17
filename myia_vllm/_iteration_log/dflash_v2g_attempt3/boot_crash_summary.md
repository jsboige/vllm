# DFlash-v2g cold boot attempt 3 — CRASH (page size mismatch)

**Date**: 2026-05-17 ~20:00Z
**Profile**: `medium-qwen36-genesis-tq-dflash.yml` (Attempt 3 retry plan applied)
**Image**: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3`
**Container outcome**: Worker died, rolled back to v2g at 20:02Z.

## Diff vs Attempt 2

- `--max-num-batched-tokens` 8192 → **4096** (revert to v2g default).
- All other Attempt 2 settings retained (K=7, no `--default-chat-template-kwargs`, PN21/23/24).

Compile cache was hot from Attempt 2 → boot reached the worker-init/KV-cache-config phase fast (~5 min).

## What crashed

`EngineCore`:
```
RuntimeError: Worker failed with error
'Page size mismatch after block_size adjust: 1136064 != 3408192'
```

**Exact 3:1 ratio** (3408192 / 1136064 = 3). This is a different failure mode from:
- Attempt 1 (deepcopy/segfault in tokenizer init_kwargs)
- Attempt 2 (torch.compile fake-tensor mul shape mismatch)
- Stock DFlash v2 17:53Z (`AssertionError new_spec.page_size_bytes == max_page_size`)

## Root cause analysis

The mismatch is between **TurboQuant k8v4 KV page byte layout** (target) and **FLASH_ATTN page byte layout** (drafter, per PN9/#39930). The 3× factor is consistent with **per-token KV byte sizes differing by 3×** — likely K/V head count or per-head dim ratio between the 35B target's 10 Gated Attention layers and the DFlash drafter's 8 Qwen3 dense attention layers.

Genesis **PN9 self-retired** at boot (it detected `spec_cfg.attention_backend` in upstream — meaning #39930 IS merged in nightly `01d4d1ad3`). But the upstream "merged" patch only handles attention-backend SELECTION, not page-layout INTEROP across heterogeneous formats. So the K8V4 target's `block_size` adjustment lands on a page size that doesn't match what FLASH_ATTN drafter expects, and vLLM's strict equality check kills the worker.

## Why this likely won't be fixed by remaining DFlash CLI levers

- **K=4 (Attempt 4a)**: page-size mismatch ratio depends on drafter num_kv_heads vs target num_kv_heads, NOT on K. K only affects the number of verify slots per page. So K=4 → same 3:1 mismatch.
- **`--enforce-eager`**: bypasses torch.compile graph capture, but the page-size check fires BEFORE torch.compile (during KV cache config). Won't help.
- **Drop `--limit-mm-per-prompt`**: multimodal isn't involved here. Won't help.
- **Revert `--kv-cache-dtype turboquant_k8v4` → `fp8`**: target attention pages would match FLASH_ATTN better, but this defeats the +6.3× KV gain and loses v2g's whole point. Not a tenable production config.

The DFlash-on-TQ+AWQ path requires a Genesis (or upstream) patch for **cross-attention-backend page interop** that doesn't exist as of v7.72.5. Genesis's PN9 backports `#39930` which only does drafter-attention-backend SELECTION, not page-layout reconciliation.

## Decision: pivot to FP8+MTP (Attempt 4)

DFlash on AWQ-TQ has now failed in 3 distinct ways across 3 attempts (1 stock + 2 Genesis variants). The remaining levers either don't address the root cause or destroy v2g's gains. Per user mandate "**on fait tout et on tente dflash maintenant. Prévoir MTP en backup**", this is the moment to pivot to MTP.

**The FP8 path is now viable** because:
1. `Qwen/Qwen3.6-35B-A3B-FP8` was downloaded in parallel during DFlash investigation (cached locally, 56 files, ~34 GB) — verified per `_hf_downloader.yml` output.
2. FP8 preserves built-in MTP heads (no AWQ stripping issue per [memory: project_mtp_qwen36_blocked.md](../../../../C:/Users/MYIA/.claude/projects/d--vllm/memory/project_mtp_qwen36_blocked.md)).
3. The existing `medium-qwen36-genesis-tq-mtp.yml` profile (currently marked INERT due to AWQ blocker) can be reworked to point at FP8 + drop AWQ-specific tweaks.
4. MTP uses target's own heads → no separate drafter → no page-size cross-backend issue.

**Attempt 4 plan**: clone-and-edit `medium-qwen36-genesis-tq-mtp.yml` into `medium-qwen36-fp8-mtp.yml`:
- Model → `Qwen/Qwen3.6-35B-A3B-FP8`
- KV cache dtype → `fp8` (FP8 target is incompatible with TQ k8v4 quant scheme; FP8 KV is the natural match)
- Genesis env: keep PN8 (vllm#40849 MTP/draft online-quant — verified saves ~1 GiB VRAM on FP8 K=3) + PN58 + P107 + PN33 default
- Drop spec attention_backend hint (MTP heads are inside target, no drafter to route)
- Spec config: `'{"method":"qwen3_next_mtp","num_speculative_tokens":3}'`

**If FP8+MTP also fails**: log it as the second confirmed-impossible spec-dec path on our stack, retire both DFlash and MTP profiles to documentation status, and live with v2g (which is already excellent at concurrent N=16 = 829 tok/s).

## Rollback at 20:02Z

`docker compose -f medium-qwen36-genesis-tq-dflash.yml down` then `docker compose -f medium-qwen36-genesis-tq.yml up -d`. Compile cache was hot from prior v2g boot at 19:34Z, so re-init was quick. v2g resumed serving by 20:03Z.
