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

---

# SECOND ATTEMPT — 2026-09-11: **PASSED** (issue #34 window)

Same image, same digest: `sha256:aa542864b00a…` (verified against the running container). The
09-09 failure was **purely configuration**. What changed is one environment line:

```
VLLM_WSL2_ENABLE_PIN_MEMORY=1
```

## Why that line is the whole story

`UvaBuffer.__init__` (v1/worker/gpu/buffer_utils.py:44-50) raises when `is_uva_available()` is
False, and that function (utils/platform_utils.py:51-57) is literally:

```python
return is_pin_memory_available() or current_platform.is_cpu()
```

Under WSL2, `is_pin_memory_available()` (platforms/cuda.py:299-318) returns the env var
`VLLM_WSL2_ENABLE_PIN_MEMORY` — **default False** — on kernels >= 4.19.121. So the "WSL2 UVA wall"
was a default-off compatibility gate, not an environmental limit. Verified inside the v0.29.0
image itself before the window.

## Boot

| Step | 09-09 (failed) | 09-11 (passed) |
|---|---|---|
| Runner selected | V2 Model Runner | V2 Model Runner |
| Worker init | `RuntimeError: UVA is not available` at `UvaBuffer` | **both workers load** |
| Model loading | never reached | 11.52 GiB, 34.9 s (TP1) / 35.9 s (TP0) |
| health | never | **200 in 2.9 ms**, RC=0, 3/3 containers |

Cold-ish compile cache on the dedicated `…-stock-tq-v0290` volume; window opened 21:27:37Z,
healthy ~21:32Z.

## Post-boot state

- `block_size=1424`, `prefix_match_unit=16`, `mamba_ssm_cache_dtype=float16` (windows A+B carried over)
- KV **934,660 tokens**, `num_gpu_blocks=681`, `kv_cache_max_concurrency=3.57`
- VRAM **GPU 0 19,127 / GPU 1 18,296 MiB** — slightly *below* v0.28.0's 19,744 / 18,830, consistent
  with #53955 (cudagraph memory released before the KV allocation, our boot-OOM lever)

## Battery

**13/13 gates PASS**, error scan (`Workspace is locked|turboquant_attn|EngineDead|out of memory|Traceback`) = **0**.

| Gate | v0.28.0 + A+B | v0.29.0 | Δ |
|---|---|---|---|
| prefill 30K | 8,363 tok/s | **8,737** | +4.5% |
| prefill 95K | 7,312 | **7,670** | +4.9% |
| prefill 235K | 5,704 | **5,827** | +2.2% |
| N=1 | 83.5 | **88.4** | +5.9% |
| N=2 | 93.7 | **125.3** | +33.7% |
| N=4 | 211.9 | **223.6** | +5.5% |
| N=8 | 437.8 | **465.8** | +6.4% |
| N=12 | 604.5 | **654.3** | +8.2% |
| N=16 | 766.1 | **869.5** | **+13.5%** |

N=16 869.5 tok/s is above every previous same-machine figure (828 on 09-01, 794.9 on 09-09).
Concurrent gate (16 requests sharing a 3,200-token prompt) 542 → 1,103 tok/s on the repeat run,
i.e. the A+B prefix-cache win is intact under v0.29.0.

## Remaining risk / rollback

The V2 model runner is new on this host — the gates and bench are a strong correctness clearance,
but not a soak. Watch the next cycles; rollback is four lines (image, compile-cache volume mount,
volume declaration, env var) plus `down && up -d --env-file`.

## Bonus

DSpark was blocked by the same UVA boundary — this unblocks a re-evaluation, and the v0.28.1 watch
is superseded (we are now above it).
