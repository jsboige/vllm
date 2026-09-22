# Overlay: v0.30.0 + vLLM PR #56637 "[Model] Fix K2-Horizon MoVA weight loading and support GPTQ INT4"
# PR head f9c5e3f2f7451fdd075d545e612913fa8e0256ce (branch k2-horizon-mova-fix)
# Base commit 7ee8a6dd is an ancestor of v0.30.0 and k2_horizon.py is unchanged
# in between (verified via compare API) -> clean file-for-file replacement.
# Enables serving GPTQ INT4 K2-Horizon quants (urakozz AutoRound, Siladrim).
FROM vllm/vllm-openai:v0.30.0
COPY vllm/model_executor/models/k2_horizon.py /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/k2_horizon.py
