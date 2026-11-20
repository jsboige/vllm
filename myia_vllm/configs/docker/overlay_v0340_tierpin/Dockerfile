FROM vllm/vllm-openai@sha256:cf5b2fdd087eb4f6d261736967cc5cde974bd22ff4df50365f8fa419b6b4c484
COPY vllm/v1/kv_offload/cpu/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/cpu/manager.py
COPY vllm/v1/kv_offload/tiering/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/tiering/manager.py
RUN python3 -m py_compile /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/cpu/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/tiering/manager.py
