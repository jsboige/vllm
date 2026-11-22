# MYIA SM89 feasibility test for Inkling 2 Mini (NOT a prod image).
# Base: upstream nightly 647a76866b (22/11) = #69028 + #69021 + #69168, arch list incl. 8.9.
# Overlay: upstream PR vllm#69165 (head e966dafbb, "Run on Ampere and Ada") merged onto that
# nightly with `git merge-tree` (one import-only conflict in ops/linear.py, both sides kept),
# plus one env-gated line opening fp8 KV on sm_89 (MYIA_INKLING_FP8_KV_SM89=1, default off).
FROM vllm/vllm-openai:nightly-647a76866b4559a74e27d1c6b55fbffe85c07ce4
COPY files/vllm /tmp/overlay/vllm
COPY files/tests /opt/inkling-tests/tests
RUN set -e; \
    D=$(python3 -c "import importlib.util,os;print(os.path.dirname(importlib.util.find_spec('vllm').origin))"); \
    cp -r /tmp/overlay/vllm/. "$D"/; \
    echo "overlay -> $D"; \
    python3 -m pip install --no-cache-dir pytest >/dev/null 2>&1 || echo "pytest install failed (offline?)"
