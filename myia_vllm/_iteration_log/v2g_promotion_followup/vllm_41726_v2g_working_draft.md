# Draft follow-up comment for vllm-project/vllm#41726

**Target**: https://github.com/vllm-project/vllm/issues/41726
**Action**: comment (follow-up to my 2026-05-06 reproduction comment + xyehya's 2026-05-09 fix confirmation)
**Status**: DRAFT — awaiting user OK before `gh issue comment 41726`

---

## Draft body

Follow-up datapoint confirming @xyehya's 2026-05-09 finding (`Sandermage genesis-vllm-patches P22 + P38 fix this issue`) — same fix path now validated in **production** on a different hardware tier (Ada SM89) and with a longer soak window.

### Config (Genesis-patched build)

- **Base nightly**: vLLM `01d4d1ad3` (2026-05-12, `0.20.2rc1.dev9+g01d4d1ad3`)
- **Genesis layer**: [`Sandermage/genesis-vllm-patches`](https://github.com/Sandermage/genesis-vllm-patches) **v7.72.5** (126 patches, includes P22 + P38 + P5 page-size unification + P6 TQ-aware page size + P101 continuation 64-token slicing)
- **Image tag** (local): `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3`
- **Hardware**: 2× RTX 4090 (Ada SM89, 24 GB each)
- **Model**: `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` (hybrid 30 GDN + 10 Gated Attention)
- **KV**: `--kv-cache-dtype turboquant_k8v4`
- **Parallelism**: TP=2 + EP=2

### Result

- **Boot**: clean
- **Soak**: 35h+ continuous production traffic (multi-tenant OWUI + Claude Code routing), no `_continuation_prefill` AssertionError, no `EngineDeadError`
- **KV capacity**: **2,029,669 tokens** at `gpu-memory-utilization=0.82` (×6.3 vs my prior FP8 baseline = 322K tokens)
- **Context**: 262K natively
- **Throughput** (concurrent N=16): **829 tok/s aggregate** (vs prior FP8 ~370 tok/s, +125%)
- **Single decode**: 120 tok/s no-think, 124 tok/s thinking
- **No** spec-decode active in this config (DFlash and MTP attempts on this same image hit unrelated issues — separately tracked at #41559 for the DFlash + KV-quant page interop gap; the spec-dec-free path you (xyehya) reported is the one running here)

### Critical env flag

One non-obvious flag was required on top of the Genesis layer to clear an idle deadlock at +55min on production traffic:

```
VLLM_USE_FLASHINFER_SAMPLER=0
```

Symptom without this flag: `shm_broadcast.py:733` deadlock during idle, exclusively after FlashInfer sampler had been used to serve at least one request. Setting it to 0 falls back to the in-tree sampler. P22 + P38 alone don't address this — it's a separate path. Mentioning here in case it helps the next person to land on a Genesis-patched build that boots cleanly but doesn't survive long soak.

### What this confirms

1. xyehya's 2026-05-09 fix recipe (P22 + P38) **works on Ada SM89** in addition to whatever hardware they tested on
2. The fix is **stable under production load over 35h+** — not just a successful boot
3. While [PR #40798](https://github.com/vllm-project/vllm/pull/40798) "Share decode scratch workspace across layers" is still open (`gaby` 2026-05-14: "TurboQuant does not work at all without this"), the Genesis downstream layer is an actionable path for Ada/Ampere users who need `turboquant_k8v4` today on hybrid Qwen3.x targets.

### What this does NOT cover

The Genesis layer does **not** close the gap for spec-decode-on-TQ-target paths — I just posted a separate datapoint at #41559 documenting a `Page size mismatch 1136064 != 3408192` (exact 3:1) when combining `turboquant_k8v4` target + DFlash drafter (FLASH_ATTN backend) via Genesis PN9 (their backport of [#39930](https://github.com/vllm-project/vllm/pull/39930)). Spec-decode on a TurboQuant target remains an open question for upstream + Genesis both.

Happy to test any candidate PR (including #40798 once unblocked) on the same Ada 4090×2 box.

---

## Notes for self (not in the posted body)

- This comment references xyehya's 2026-05-09 P22+P38 finding explicitly. Adds value by:
  - Different hardware tier (Ada SM89 vs unknown)
  - Production-grade soak (35h+ vs unknown duration)
  - Specific Genesis version (v7.72.5)
  - VLLM_USE_FLASHINFER_SAMPLER=0 trap not previously mentioned
- Does NOT cover Att1/Att4 deepcopy poison (separate bug, deferred until stock repro)
- Does NOT cover Att2 torch.compile fake-tensor (separate, deferred)
- xyehya's claim ("not using spec decoding") is mirrored here — both confirm the no-spec-dec path. Spec-decode + TQ remains broken.
