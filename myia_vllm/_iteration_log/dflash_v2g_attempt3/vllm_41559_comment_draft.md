# Draft comment for vllm-project/vllm#41559

**Target**: https://github.com/vllm-project/vllm/issues/41559
**Action**: comment (NOT a new issue)
**Status**: DRAFT — awaiting user OK before `gh issue comment 41559`

---

## Draft body

Additional datapoint from **Ada SM89** (dual RTX 4090, 24 GB each) confirming the same root cause is reachable on a third combo: **TurboQuant `k8v4` KV (target) + FLASH_ATTN drafter via `--speculative-config.attention_backend`** (i.e. through the [#39930](https://github.com/vllm-project/vllm/pull/39930) path you just landed). The crash surfaces as a slightly different error string than the original report:

```
RuntimeError: Worker failed with error
'Page size mismatch after block_size adjust: 1136064 != 3408192'
```

The ratio is **exactly 3:1** (3408192 / 1136064 = 3). I assume it relates to the per-token KV byte size difference between the target's 10 Gated Attention layers (TurboQuant k8v4 page layout) and the DFlash drafter's 8 Qwen3 dense attention layers (FLASH_ATTN page layout) — if useful, I'm happy to dig into which exact factor (num_kv_heads ratio, per-head dim, block_size adjust value) produces the 3×.

### Config that triggered it

- **vLLM nightly**: `0.20.2rc1.dev9+g01d4d1ad3` (post-#39930 merge, so the drafter-attention-backend selection IS in effect — verified by the upstream config log emitting `attention_backend: FLASH_ATTN`)
- **GPU**: 2× RTX 4090, TP=2 + EP=2
- **Target**: `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` (hybrid 30 GDN + 10 Gated Attention)
- **Drafter**: `z-lab/Qwen3.6-35B-A3B-DFlash`
- **Flags**: `--kv-cache-dtype turboquant_k8v4` + `--speculative-config '{"method":"dflash","model":"z-lab/Qwen3.6-35B-A3B-DFlash","num_speculative_tokens":7,"attention_backend":"FLASH_ATTN"}'`

This crash fires at the `KVCacheConfig` validation step (worker init), strictly before any compile pass. Switching K from 7 → 4 doesn't change the ratio, confirming K isn't the dimension that mismatches.

### Cross-check vs the original report

| | seantechco (this issue) | Lucebox/MidasMining cross-post | This datapoint |
|---|---|---|---|
| Arch | Ampere SM86 (3090) | Ampere SM86 (3090) | **Ada SM89 (4090×2)** |
| Target quant | AutoRound int4 | Q4_K_M (llama.cpp) | AWQ 4-bit |
| KV dtype | `fp8_e5m2` / `turboquant_4bit_nc` | TQ3_0 (llama.cpp) | **`turboquant_k8v4`** |
| Drafter backend | FLASH_ATTN / FLEX / FLASHINFER (all reject) | n/a (ggml port) | FLASH_ATTN via #39930 |
| Error surface | `KV cache dtype X not supported for non-causal` | works (ggml) | **`Page size mismatch after block_size adjust 1136064 != 3408192`** |

The TurboQuant **k8v4** variant exposes the page-layout side of the same fundamental gap. `turboquant_4bit_nc` ("nc" suffix is presumably "non-causal") hardcodes `causal=True` per the original report; `k8v4` doesn't carry the `_nc` suffix and reaches a different code path (`KVCacheConfig.adjust_block_size` rather than the attention `supported_kv_cache_dtypes` check) — same outcome.

### Genesis-patched stack note (for triage purposes only)

Our build uses Sandermage's [genesis-vllm-patches](https://github.com/Sandermage/genesis-vllm-patches) v7.72.5 layered on the same nightly. PN9 (Genesis's pre-#39930 backport) **self-retires** at boot when it detects upstream `spec_cfg.attention_backend` (i.e. when #39930 is merged), so the code path executing here is plain upstream + the patch set's other patches (notably P5 "KV cache page size unification (v1_lcm_pad_max)" and P6 "TurboQuant-aware attention page size"). Neither P5 nor P6 closes the FLASH_ATTN-drafter ↔ TQ-target gap.

If you'd like, I can re-run the exact same flags on a stripped image (stock `01d4d1ad3` without the Genesis layer) and post the resulting stack trace so you can confirm this is the same upstream bug rather than a Genesis interaction. The Genesis layer otherwise has no patch claiming to address cross-attention-backend page interop.

### Question on the fix path

The comment from @benchislett mentions [#39995](https://github.com/vllm-project/vllm/pull/39995) (DFlash + FlashInfer + FP8 KV) is in flight, validated on RTX 4090. Is the plan to:
1. Cover FP8 variants only and leave TurboQuant `k8v4`/`4bit_nc` for a separate PR?
2. Add `BatchPrefillWithPagedKVCacheWrapper(causal=False)` semantics to the TurboQuant backend as well?

Happy to test once a PR is ready — same Ada 4090×2 box, same nightly base.
