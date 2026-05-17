# DFlash-v2g cold boot attempt 1 — CRASH

**Date**: 2026-05-17 ~18:38Z
**Profile**: `medium-qwen36-genesis-tq-dflash.yml`
**Image**: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (same as v2g)
**Compose status**: container removed after crash loop, prior logs lost

## What worked

Genesis dispatcher applied the expected patches:
- PN58 (5/5 files committed atomically) — spec-decode reasoning boundary
- P107 (idempotent) — MTP truncation detector
- P67 — TurboQuant multi-query kernel for spec-decode K+1 (kernel_built: True, SM 8.9)
- P67b — TurboQuant spec-verify forward() routing (FULL CG enable)
- P78 (4 sub-patches) — TQ tolist capture-guard
- P101 — TQ continuation 64-token slicing

**Critical**: PN9 self-retired with message: `upstream drift: 'spec_cfg.attention_backend' present in llm_base_proposer.py — PR #39930 (or equivalent) appears merged; PN9 self-retires (use --speculative-config.attention_backend instead)`.

So the Genesis base nightly `01d4d1ad3` already has #39930 merged. Our `attention_backend: FLASH_ATTN` flag goes straight to upstream code.

vLLM also accepted the spec-dec config, emitting:
`max_num_scheduled_tokens is set to 3928 based on the speculative decoding settings. This may lead to suboptimal performance. Consider increasing max_num_batched_tokens to accommodate the additional draft token slots, or decrease num_speculative_tokens or max_num_seqs.`

So `--speculative-config '{"method":"dflash","model":"z-lab/Qwen3.6-35B-A3B-DFlash","num_speculative_tokens":15,"attention_backend":"FLASH_ATTN"}'` parsed OK.

## DFlash-related patches SKIPPED by default (opt-in only)

- **PN40** — Spec-decode omnibus (A DFlash K-norm + B pool + C adaptive K + D sentinel) — 2026-05-04 — `GENESIS_ENABLE_PN40_DFLASH_OMNIBUS=1`
- **PN38** — DFlash drafter quantization support (PR #40425 backport) — `GENESIS_ENABLE_PN38_DFLASH_QUANT_DRAFTER=1`
- **PN23** — DFlash `combine_hidden_states` dtype cast (vllm#40334) — `GENESIS_ENABLE_PN23_DFLASH_DTYPE_FIX=1`
- **PN21** — DFlash SWA support partial backport (vllm#40898) — `GENESIS_ENABLE_PN21_DFLASH_SWA=1`
- **PN24** — DFlash aux layer +1 indexing fix (vllm#40727) — `GENESIS_ENABLE_PN24_DFLASH_AUX_LAYER_FIX=1`

## What crashed

Traceback in tokenizer/processor loading path:
```
File "/usr/local/lib/python3.12/dist-packages/vllm/transformers_utils/processor.py", line 355, in cached_processor_from_config
  return cached_get_processor_without_dynamic_kwargs(
File "transformers/processing_utils.py", line 1429, in from_pretrained
  args = cls._get_arguments_from_pretrained(pretrained_model_name_or_path, processor_dict, **kwargs)
File "transformers/processing_utils.py", line 1543, in _get_arguments_from_pretrained
  tokenizer = cls._load_tokenizer_from_pretrained(
File "transformers/processing_utils.py", line 1490, in _load_tokenizer_from_pretrained
  tokenizer = auto_processor_class.from_pretrained(
File "transformers/models/auto/tokenization_auto.py", line 728, in from_pretrained
  return tokenizer_class.from_pretrained(pretrained_model_name_or_path, *inputs, **kwargs)
File "transformers/tokenization_utils_base.py", line 1933, in _from_pretrained
  tokenizer = cls(*init_inputs, **init_kwargs)
File "transformers/models/qwen2/tokenization_qwen2.py", line 89, in __init__
  super().__init__(...)
File "transformers/tokenization_utils_base.py", line 1008, in __init__
  self.init_kwargs = copy.deepcopy(kwargs)
File "copy.py", line 136, in deepcopy
File "copy.py", line 221, in _deepcopy_dict
File "copy.py", line 162, in deepcopy
  y = _reconstruct(x, memo, *rv)
File "copy.py", line 253, in _reconstruct
File "copy.py", line 259, in _reconstruct
  state = deepcopy(state, memo)
...
File "copy.py", line 128, in deepcopy
  y = memo.get(d, _nil)
AttributeError: 'code' object has no attribute 'get'
!!!!!!! Segfault encountered !!!!!!!
  File "<unknown>", line 0, in _Py_NoneStruct
```

**Hard memory corruption** — the `memo` argument in `deepcopy` was supposed to be a dict but became a CPython `code` object. Then segfault in `_Py_NoneStruct`.

Same family of crash as v2f → v2g (FlashInfer sampler corrupting `_thread.lock` — fixed with `VLLM_USE_FLASHINFER_SAMPLER=0` which is still active here).

## Hypotheses (ranked)

1. **Chat template kwargs poison**: `--default-chat-template-kwargs '{"preserve_thinking":true}'` combined with `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3` injects a function/code object into the processor's `init_kwargs`. Spec-dec path triggers a second processor load (drafter), which trips on the deepcopy. **Test**: drop `--default-chat-template-kwargs`, leave everything else identical.
2. **Drafter loaded as multimodal**: vLLM treats spec-dec drafter as same multimodal family as target. The drafter `z-lab/Qwen3.6-35B-A3B-DFlash` is text-only (Qwen3 dense 0.5B). Loading it through the multimodal processor path may corrupt state. **Test**: not directly controllable; would need vLLM source check.
3. **K=15 too aggressive**: vLLM warning suggested smaller K or larger `max_num_batched_tokens`. K=15 → `max_num_scheduled_tokens=3928`, just 168 below the 4096 budget. **Test**: K=7 + `--max-num-batched-tokens 8192`.
4. **Missing DFlash opt-in patches**: PN21 (SWA), PN23 (dtype cast), PN24 (aux layer) all skipped. Qwen3.6 has SWA so PN21 might be needed. **Test**: enable PN21+PN23+PN24 opt-in env vars.

## Decision

Retry plan, in order of cheapness/diagnostic value:
- **Attempt 2**: Reduce K=15→7, bump `max_num_batched_tokens=4096→8192`, enable PN21+PN23+PN24.
  - If works: bench DFlash-v2g properly.
  - If still tokenizer-crashes: peel off `--default-chat-template-kwargs` (Attempt 3).
- **Attempt 3** (only if Attempt 2 still crashes in deepcopy): drop `--default-chat-template-kwargs`. Lose server-side `preserve_thinking` (OWUI wrappers can inject client-side).
- **Attempt 4** (only if Attempt 3 still crashes): drop `--limit-mm-per-prompt` and `--mm-processor-kwargs` to disable multimodal path; lose vision but isolates the processor-loading issue.

After any attempt that boots: bench → promote or revert.

## Rollback applied at 18:40Z
v2g back online (cold boot in progress).
