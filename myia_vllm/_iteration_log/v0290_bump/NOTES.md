# v0.28.0 → v0.29.0 image bump attempt (2026-09-09)

**Verdict: REJECTED on this WSL2 host; production rolled back to v0.28.0.**

The final `vllm/vllm-openai:v0.29.0` image exists and was pulled successfully:

- digest: `sha256:aa542864b00a69e711a8352448683800d0224ef39d1c2246cdfd741d63711efa`
- release commit label: `98dff2a81d747d1dba01a47f939f48c3526d4206`
- image creation: `2026-09-08T23:34:55Z`
- runtime banner: `0.29.1.dev1+g98dff2a81` despite the final `v0.29.0` tag

## Same-window baseline before swap

Production v0.28.0, batch 8192, TurboQuant k8v4:

| N | Aggregate tok/s |
|---:|---:|
| 1 | 69.3 |
| 2 | 97.8 |
| 4 | 205.3 |
| 8 | 349.0 |
| 12 | 609.6 |
| 16 | **794.9** |

## Boot failure

Only the three per-image profile lines were changed: image, compile-cache mount, and top-level volume. Compose validation passed. On boot, v0.29.0 selected:

```text
Using V2 Model Runner
```

Both TP workers then failed before model loading:

```text
vllm/v1/worker/gpu/states.py:34 -> StagedWriteTensor
vllm/v1/worker/gpu/buffer_utils.py:47 -> UvaBuffer
RuntimeError: UVA is not available
```

Observed state: `RestartCount=1`, `OOMKilled=false`, GPU 0 about 959 MiB, GPU 1 0 MiB. This is not a boot OOM or a TurboQuant workspace failure. It is the same WSL2 UVA boundary found during the DSpark experiment, now reached by the normal production path because Model Runner V2 is the v0.29.0 default when Triton is available.

The release image contains a supported override: `VLLM_USE_V2_MODEL_RUNNER=0` makes `VllmConfig.use_v2_model_runner` return false. It was **not deployed or tested** because that would add a fourth configuration change beyond the pre-authorized image bump. A dedicated maintenance-window evaluation may test v0.29.0 with explicit V1 after user approval.

## Validation status

The boot gate failed, so the remaining battery was deliberately not run:

- 13 functional/long-prefill gates: **NOT EXECUTABLE**
- FORCING batch-(4096,8192] test: **NOT EXECUTABLE**
- post-swap concurrency benchmark: **NOT EXECUTABLE**
- TurboQuant runtime scan: no runtime reached; failure occurred before model loading

## Rollback

The three profile lines were restored to v0.28.0 and the existing `vllm-compile-cache-qwen36-stock-tq-v0280` volume. Rollback verification:

- effective image: `vllm/vllm-openai:v0.28.0`
- health: HTTP 200 in 2.8 ms
- authenticated decode: HTTP 200 in 0.32 s
- `RestartCount=0`, Docker health `healthy`
- KV cache: 934,374 tokens (3.56× 262K)
- engine + watchdog + wedge telemetry: all running
- production profile diff after rollback: empty

The newly created v0.29.0 compile-cache volume is empty and retained; no deletion was performed.
