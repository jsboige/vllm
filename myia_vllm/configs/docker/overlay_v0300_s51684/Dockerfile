# Overlay image: stock vllm/vllm-openai:v0.30.0 + vllm-project PR #51684
# "Handle quantized qkv_proj in DFlash fused-KV buffers" @ b1b3aefa40ca
#
# EVAL-ONLY image (2026-09-22): file-for-file replacement of the 4 runtime
# files the PR touches. Verified clean: none of these files changed between
# the PR base (73fb19151f4f) and the v0.30.0 release commit — the overlay
# reverts nothing. PR base is an ancestor of v0.30.0 (compare: behind 0).
#
# Fixes our eval crash: qwen3_dflash.py:472 _build_context_kv_buffers sliced
# the TARGET's qkv_proj.weight — nonexistent on pack-quantized (AWQ INT4)
# targets. The PR routes the fused-KV precompute through quant_method with a
# tiered strategy (fused quantized GEMM / dequant).
#
# NEVER promote to prod unless the PR merges upstream — reproducibility rule.
# Test file (tests/) not included: irrelevant for serving.

FROM vllm/vllm-openai:v0.30.0
COPY vllm/model_executor/models/ /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/
