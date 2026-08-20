# vLLM v0.27.1 + upstream PR #51812 (Align Qwen GDN gates with speculative tokens)
#
# Why: v0.27.1 predates #51812 (merged 2026-08-11). Without it, MTP speculative
# decoding on Qwen hybrid GDN models can consume misaligned a/b gate rows when a
# mixed batch places non-speculative tokens before speculative ones — a
# CORRECTNESS bug (wrong tokens' gates feed the fused recurrent update), not a
# perf one. Our 2026-08-19 eval ran MTP without it (canary was clean, but the
# residual risk is real). This overlay is the image we actually want to deploy.
#
# The patch (29 lines, one file, pure Python — see pr51812.diff alongside)
# applies cleanly to the v0.27.1 blob (verified `git apply --check`), so a
# single-file COPY over dist-packages is sufficient: python recompiles the .pyc
# from the fresher .py (mtime invalidation). No compiled extension involved.
#
# Base is a release tag => reproducible (nightly tags are GC'd after ~5 days).
FROM vllm/vllm-openai:v0.27.1

COPY vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py \
     /usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py

# Sanity: static check only — `import vllm` infers the device at import time
# and fails without a GPU, so we never import here. ast.parse proves the file
# is valid python; the marker proves the patched copy landed in dist-packages.
RUN python3 -c "\
import ast; \
p = '/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py'; \
src = open(p).read(); \
ast.parse(src); \
assert 'a_spec = a' in src, 'patch marker missing — overlay did not land'; \
print('overlay landed:', p)"
