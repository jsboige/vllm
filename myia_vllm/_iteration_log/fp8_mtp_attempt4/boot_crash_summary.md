# FP8+MTP cold boot attempt 4 — CRASH (deepcopy/segfault) + CORRECTION of Att1 analysis

**Date**: 2026-05-17 ~20:30Z
**Profile**: `medium-qwen36-fp8-mtp.yml` (first boot)
**Image**: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (same Genesis image as v2g)
**Model**: `Qwen/Qwen3.6-35B-A3B-FP8` (cached locally)
**Container outcome**: restart loop → rolled back to v2g at 20:32Z.

## What worked

Genesis applied **P5** ("KV cache page size unification") + **P6** ("TurboQuant-aware attention page size") automatically — interesting because these patches were NOT explicitly enabled by env vars; they're default-on. (Worth noting in the Sandermage report: P5/P6 don't fix the cross-backend page interop for FLASH_ATTN drafter on a TQ target, but they ARE applied.)

vLLM recognized the FP8 model's MTP heads:
```
[model.py:563] Resolved architecture: Qwen3_5MoeMTP
[cache.py:261] Using fp8 data type to store kv cache
[speculative.py:513] method `qwen3_next_mtp` is deprecated and replaced with mtp
[speculative.py:659] Enabling num_speculative_tokens > 1 will run multiple times of forward on same MTP layer, which may result in lower acceptance rate
```

So:
1. **FP8 preserves MTP heads** — confirms [project_mtp_qwen36_blocked.md](C:\Users\MYIA\.claude\projects\d--vllm\memory\project_mtp_qwen36_blocked.md) hypothesis (AWQ-cyankiwi strips them, FP8-official keeps them).
2. **`qwen3_next_mtp` → `mtp`** — vLLM is renaming the method internally. The Sandermage Genesis profile and our `medium-qwen36-genesis-tq-mtp.yml` should be updated to use `method: "mtp"` directly when re-trying.

## What crashed

```
File "vllm/multimodal/processing/context.py", line 204, in get_hf_processor
  → cached_processor_from_config(...)
File "vllm/transformers_utils/processor.py", line 355, in cached_processor_from_config
File "transformers/processing_utils.py", line 1429, in from_pretrained
  → cls._get_arguments_from_pretrained(pretrained_model_name_or_path, processor_dict, **kwargs)
File "transformers/processing_utils.py", line 1543, in _get_arguments_from_pretrained
File "transformers/processing_utils.py", line 1490, in _load_tokenizer_from_pretrained
File "transformers/models/auto/tokenization_auto.py", line 687, in from_pretrained
File "transformers/models/auto/configuration_auto.py", line 374, in from_pretrained
File "transformers/configuration_utils.py", line 678, in get_config_dict
  original_kwargs = copy.deepcopy(kwargs)
...
File "copy.py", line 128, in deepcopy
  y = memo.get(d, _nil)
AttributeError: 'code' object has no attribute 'get'
!!!!!!! Segfault encountered !!!!!!!
  File "<unknown>", line 0, in Py_FinalizeEx
  File "<unknown>", line 0, in Py_RunMain
```

`memo` (which should be a dict) has become a `code` object → segfault during Py_FinalizeEx.

## **CRITICAL: this is the SAME crash as DFlash-v2g Attempt 1**

Att1 traceback ended in the EXACT same deepcopy/code-object/segfault, but the deepcopy call site was different:
- **Att1**: `transformers/tokenization_utils_base.py:1008 → init_kwargs = copy.deepcopy(kwargs)` (Qwen2Tokenizer init)
- **Att4**: `transformers/configuration_utils.py:678 → original_kwargs = copy.deepcopy(kwargs)` (AutoConfig.from_pretrained)

Both end in `copy.py:128 memo.get()` with `memo` being a `code` object. The deepcopy machinery itself is poisoned — any deepcopy site downstream of the poisoning event will fail the same way.

## **Att1 hypothesis "chat-template-kwargs poison" was WRONG**

In Att1 I hypothesized that `--default-chat-template-kwargs '{"preserve_thinking":true}'` injected a function/code object into the processor's `init_kwargs`. I dropped that flag in Att2/Att3/Att4. **Att4 has NO chat-template-kwargs and still hits the same deepcopy crash.** The hypothesis is falsified.

## Revised hypothesis

The crash is reachable on **any spec-decode method + Qwen3.6 multimodal + this Genesis image**, independent of:
- Quant format (Att1 = AWQ, Att4 = FP8 — both crash)
- Spec-dec method (Att1 = DFlash drafter, Att4 = MTP heads — both crash)
- Chat template kwargs (Att4 doesn't have it; both crash)

v2g (Genesis-TQ, NO spec-decode) on the same image never hits this. So spec-decode is the trigger condition. **What spec-decode adds**:
- A **secondary config/processor load** (drafter config in DFlash; MTP head config detection in MTP)
- That secondary load goes through `vllm/multimodal/processing/context.py:204` and triggers `transformers/configuration_utils.py:678 → deepcopy(kwargs)`
- By the time the secondary load runs, **some C-extension imported during the first load has overwritten the function descriptor of `copy.deepcopy`'s internal `memo` argument** — causing `memo` to dereference as a `code` object instead of a dict.

This pattern is the same family as our 2026-02 [vllm#35104](https://github.com/vllm-project/vllm/issues/35104) (shm_broadcast PyCFunction crash): C-extension dlopen at runtime corrupting CPython internals.

Candidate culprits (need to disentangle stock vs Genesis):
- **FlashInfer JIT autotune** (already disabled here via `--no-enable-flashinfer-autotune`)
- **Triton kernel compilation** (P67 multi-query kernel, P67b spec-verify forward — both active under DFlash AND MTP)
- **Genesis patch tree injects C-extension hooks** that survive across the dual-load

To disentangle: try the SAME spec-decode config on **stock nightly `01d4d1ad3` without Genesis layer** — would crash differently OR not at all.

## Decision: retire both DFlash + MTP profiles to documentation-only status

After 4 attempts:
- Att1 (AWQ + DFlash) → deepcopy/segfault
- Att2 (AWQ + DFlash, dropped chat-template-kwargs, K=7, batched=8192) → torch.compile fake tensor
- Att3 (AWQ + DFlash, K=7, batched=4096) → page_size mismatch 1136064 != 3408192 (= [vllm#41559](https://github.com/vllm-project/vllm/issues/41559))
- Att4 (FP8 + MTP, K=3) → deepcopy/segfault (same as Att1)

We have:
- 1 reproducible upstream-tracked bug (Att3 → #41559, PR #39995 in flight for FP8+FlashInfer path, no TurboQuant path yet)
- 1 Genesis-or-vLLM bug that crashes on dual config load with spec-decode (Att1 + Att4)
- 1 torch.compile shape issue (Att2) that may be partly downstream of the spec-decode dual load

**Production decision**: stay on v2g. It already delivers **829 tok/s aggregate at N=16** which is excellent for our multi-user workload. Single-user speedups from spec-decode (DFlash +94% reasoning, MTP +5-10% TPS) are not worth chasing further until upstream/Genesis ship a working spec-decode path on Ada+Genesis-image.

**Profiles preserved on disk** as documentation:
- `medium-qwen36-genesis-tq-dflash.yml` (Att2/Att3 config, has commit message about the failure)
- `medium-qwen36-genesis-tq-mtp.yml` (still marked INERT — was placeholder for AWQ-with-MTP-preserved; remains accurate but consider archiving)
- `medium-qwen36-fp8-mtp.yml` (Att4 — could be tested again if Genesis ships a patch addressing dual-config-load deepcopy poisoning)

## Rollback at 20:32Z

`docker compose -f medium-qwen36-fp8-mtp.yml down && docker compose -f medium-qwen36-genesis-tq.yml up -d`. Compile cache hot from prior v2g boots → quick re-init.

## Reporting implications

- **#41559 comment** (Att3 datapoint): STILL VALID, the page_size mismatch on TQ+FLASH_ATTN is a real bug.
- **NEW issue idea** (Att1+Att4 deepcopy): NOT TO FILE YET. Must first reproduce on stock vLLM `01d4d1ad3` without Genesis layer to know whether to file vllm-side or Sandermage-side. Deferred.
