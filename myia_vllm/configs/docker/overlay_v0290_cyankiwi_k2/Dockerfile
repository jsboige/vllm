# cyankiwi vLLM fork — K2-Horizon MoVA quantized value-experts (compressed-tensors INT4)
# Per the model card of cyankiwi/K2-Horizon-MoVA-36B-A4B-AWQ-INT4:
#   branch k2-mova-quant-v-experts, precompiled wheel pinned to upstream commit
#   d2906091bfc579cebefe3d8e8fb9077397ce9882 (2026-09-09, v0.29.0-era, ancestor of v0.30.0).
# Base image v0.29.0 (local digest aa542864b00a) matches the fork's torch/deps era.
# The fork's k2_horizon.py is CUDA-native (standard fused_experts W4A16 path,
# compressed-tensors quant_config on the module — Marlin machinery, no XPU gate,
# unlike upstream PR #56637 which is XPU-WNA16-only).
FROM vllm/vllm-openai:v0.29.0
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "cmake>=3.26.1" "setuptools-scm>=8.0" "setuptools-rust>=1.9.0" ninja
RUN git clone --depth 1 -b k2-mova-quant-v-experts https://github.com/cyankiwi/vllm.git /opt/vllm-fork
WORKDIR /opt/vllm-fork
RUN VLLM_USE_PRECOMPILED=1 \
    VLLM_PRECOMPILED_WHEEL_COMMIT=d2906091bfc579cebefe3d8e8fb9077397ce9882 \
    pip install . --no-build-isolation
