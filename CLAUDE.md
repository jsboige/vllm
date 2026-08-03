# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Self-Maintenance Instructions

**You MUST keep this file and your memory (`MEMORY.md`) up to date as you work.** Do not wait for the user to ask:
- After completing a significant task (optimization, config change, benchmark), update the relevant sections of CLAUDE.md and MEMORY.md immediately
- Update performance numbers when you measure new benchmarks
- Record what you tested and rejected (with reasons) so you don't repeat failed experiments
- Update the "Current State" section at the bottom when the deployment changes
- Before ending a session, verify both files reflect the current state of the project

## Project Overview

This is a **vLLM fork** with a custom `myia_vllm/` directory for self-hosting LLMs on **3x RTX 4090 GPUs** (72GB total VRAM). The project provides OpenAI-compatible API endpoints for LLMs, accessible via reverse proxy at `*.text-generation-webui.myia.io`.

**Current deployment (2026-05-17, promoted after 35h+ soak)**: **Qwen3.6-35B-A3B MoE + TurboQuant K8V4 (Genesis-patched)** on GPUs 0,1 with TP=2 + EP=2, image `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (Sandermage Genesis patch tree on nightly `01d4d1ad3`). Profile `medium-qwen36-genesis-tq.yml`. KV cache 2.03M tokens (×6.3 vs prior FP8 322K), 262K context preserved, vision OK, concurrent N=16 = **829 tok/s aggregate (+125%)**, single decode 120 tok/s (+12%), single thinking 124 tok/s (+6%). **GPU 2 fully freed 2026-05-01** (78 MiB driver baseline only) for CoursIA training jobs.

**Promotion path (2026-05-16 → 2026-05-17)**:
1. v2f (Genesis-TQ + vision) PASSED active load benches but regressed on +55min idle soak (shm_broadcast.py:733 deadlock). Rolled back to FP8 baseline 05:35Z.
2. v2g = v2f + `VLLM_USE_FLASHINFER_SAMPLER=0` (FlashInfer sampler had its own JIT autotune path corrupting CPython `_thread.lock` descriptor under load). Deployed 2026-05-16 06:29Z.
3. v2g soak 35h+ clean — promoted as new baseline 2026-05-17.

**Why this path beats the 2026-05-06 attempt**: 2026-05-06 used `vllm-qwen36-tq:nightly-e47c98ef-patched1` (stock nightly + transformers/shm patches), which crashed on first ~30K chunked-prefill continuation (`AssertionError turboquant_attn.py:720`). Genesis patch tree includes P22+P38 which fix exactly that crash (externally confirmed in [vllm#41726](https://github.com/vllm-project/vllm/issues/41726) by `xyehya`). Upstream candidate fix PR [#40798](https://github.com/vllm-project/vllm/pull/40798) remains OPEN+BLOCKED, so Genesis was the actionable Option B.

**Prior baseline** (`vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` Apr 06 + shm patch + FP8 KV) and **TQ image** (`vllm-qwen36-tq:nightly-e47c98ef-patched1`) retained on disk for instant rollback. Rollback command: `docker compose -f medium-qwen36-genesis-tq.yml down && docker compose -f medium-qwen36-moe.yml up -d`.

## Key Directories

```
myia_vllm/                    # PRIMARY - all customizations live here
├── configs/docker/           # Docker configs
│   ├── profiles/             # Docker-compose deployment profiles
│   └── Dockerfile.glm-flash  # Custom image for GLM-4.7-Flash
├── scripts/                  # PowerShell & Python deployment scripts
│   ├── quantization/         # Model quantization (W4A16, FP8)
│   └── testing/              # Config validation & benchmarks
├── docs/                     # Documentation (missions, guides)
├── qwen3_benchmark/          # Benchmarking framework
├── archives/                 # Archived legacy configurations
└── entrypoints/              # Custom tool parsers
```

## Common Commands

### Deployment

```powershell
# Start Qwen3.6-35B-A3B MoE + FP8 KV (primary model, GPUs 0,1, current baseline)
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen36-moe.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-qwen36-moe

# To re-test TurboQuant once upstream PR #40798 merges:
# 1. Edit medium-qwen36-moe.yml: image → vllm-qwen36-tq:nightly-e47c98ef-patched1
#    and --kv-cache-dtype fp8 → --kv-cache-dtype turboquant_k8v4
# 2. docker compose down + up -d
# (Image already local; rolled back 2026-05-06 due to upstream issue #41726)

# Legacy: GLM-4.7-Flash (archived 2026-04-24, requires custom image build first)
# docker compose -f myia_vllm/archives/2026/profiles_legacy/medium-glm.yml build
# docker compose -f myia_vllm/archives/2026/profiles_legacy/medium-glm.yml --env-file myia_vllm/.env up -d
```

### Testing

```powershell
# Benchmark GLM-4.7-Flash (A/B benchmark tool, supports any backend name)
python myia_vllm/scripts/testing/benchmark_llamacpp_vs_vllm.py --backend vllm
python myia_vllm/scripts/testing/benchmark_llamacpp_vs_vllm.py --compare

# Benchmark Qwen3.5 MoE
python myia_vllm/scripts/testing/benchmark_coder_next.py --model qwen3.5-35b-a3b

# Run all tests
.\myia_vllm\run_all_tests.ps1

# Quick API test
python myia_vllm/scripts/python/tests/test_qwen3_tool_calling.py
```

### Grid Search Optimization

```powershell
# Run configuration optimization
.\myia_vllm\grid_search_optimization.ps1
```

## Architecture

### Docker Deployment Pattern

Qwen3.5-35B-A3B uses the official `vllm/vllm-openai:nightly` image directly (no custom Dockerfile needed).

GLM-4.7-Flash (legacy) used a custom Dockerfile (`Dockerfile.glm-flash`) with `transformers >= 5.0` for `glm4_moe_lite` architecture support.

### GPU Assignment

| Service | GPUs | Port | Model | Profile |
|---------|------|------|-------|---------|
| **medium-qwen36-moe** | **0,1** | **5002** | **Qwen3.6-35B-A3B-AWQ + FP8 KV** | **medium-qwen36-moe.yml** |
| **GPU 2 — FULLY FREED 2026-05-01** | **2** | — | training jobs (CoursIA) | 78 MiB driver baseline only |
| medium-qwen36-27b | 0,1 | 5002 | Qwen3.6-27B-AWQ-INT4 + TQ K8V4 | archives/2026/medium-qwen36-27b.yml.rejected-2026-05-06 (rejected: -50% decode) |
| kokoro-tts (migrated to po-2023) | — | — | Kokoro TTS (67 voices) | now at `https://tts.myia.io/kokoro/v1` (po-2023, sleep mode) |
| mini-omnicoder | 2 | 5001 | OmniCoder-9B-AWQ-4bit | archived 2026-04-30 (GPU 2 freed for trainings) |
| medium-qwen35-moe | 0,1 | 5002 | Qwen3.5-35B-A3B-AWQ | archived 2026-04-17 (replaced by 3.6) |
| mini-zwz | 2 | 5001 | ZwZ-8B-AWQ-4bit | mini-zwz.yml (replaced by OmniCoder) |
| medium-glm | 0,1 | 5002 | GLM-4.7-Flash-AWQ | archives/2026/profiles_legacy/medium-glm.yml |
| medium-qwen35-dense | 0,1 | 5002 | Qwen3.5-27B-AWQ | medium-qwen35-dense.yml (rejected: too slow) |
| mini-solo | 2 | 5001 | Qwen3-VL-8B-Thinking-AWQ | mini-solo.yml (fallback) |

GPUs 0,1 are on faster PCIe bus. **GPU 2 fully freed 2026-05-01** (78 MiB driver baseline) for CoursIA training jobs (queue 5-7d, sprint sustainable + Sudoku large + RL extension). Previously: OmniCoder-9B + Kokoro TTS. OmniCoder archived 2026-04-30, Kokoro TTS migrated to po-2023 (`https://tts.myia.io/kokoro/v1`, sleep mode) on 2026-05-01 — 7/7 OWUI tenants switched, ai-01 compose service `kokoro-tts` removed.

### Environment Variables

Configuration via `myia_vllm/.env` (not tracked) based on `.env.example`:
- `HUGGING_FACE_HUB_TOKEN` - Required for model downloads
- `VLLM_API_KEY_*` - API keys per service
- `VLLM_MODEL_QWEN36_MOE` - Qwen3.6 MoE model (default: `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`)
- `VLLM_PORT_GLM` - Medium model port (default: 5002, shared by all medium profiles)
- `VLLM_MODEL_ZWZ` - ZwZ-8B model path (default: `./models/ZwZ-8B-AWQ-4bit`)

## OmniCoder-9B Deployment (Current GPU 2 Model)

### Model Overview

**OmniCoder-9B** ([Tesslate/OmniCoder-9B](https://huggingface.co/Tesslate/OmniCoder-9B)) is the **current model** on GPU 2 (port 5001) since 2026-03-28. A Qwen3.5-9B finetune specialized for agentic coding. Key features:
- **Architecture**: Qwen3.5-9B dense, hybrid Gated Delta Networks + standard attention
- **Training**: 425K+ agentic coding trajectories (Claude Opus, GPT-5.3, Gemini 3.1 Pro)
- **Thinking mode**: `<think>...</think>` reasoning chains
- **Vision**: Images, documents (vision encoder preserved in BF16)
- **Tool calling**: `qwen3_coder` parser (XML format: `<function=name><parameter=key>value</parameter>`)
- **Context**: 262K native, configured at 131072 (VRAM constraint)
- **License**: Apache 2.0
- **Quantization**: AWQ 4-bit from [cyankiwi/OmniCoder-9B-AWQ-4bit](https://huggingface.co/cyankiwi/OmniCoder-9B-AWQ-4bit)

### Custom Dockerfile Required

Qwen3.5 dense models use `model_type: qwen3_5` and `TokenizersBackend`, which require `transformers >= 5.0`. vLLM nightly ships `transformers 4.57.6`. Custom `Dockerfile.omnicoder` adds the layer:
```dockerfile
FROM vllm/vllm-openai:nightly
RUN pip install --no-cache-dir "transformers>=5.0" "tokenizers>=0.21" "huggingface_hub>=0.30"
```

### Key vLLM Flags
```yaml
--model cyankiwi/OmniCoder-9B-AWQ-4bit
--served-model-name omnicoder-9b
--gpu-memory-utilization 0.85          # 0.88 OOM with Kokoro TTS on same GPU
--max-model-len 131072
--kv-cache-dtype fp8
--dtype auto                           # MUST be auto for BF16 vision encoder
--tool-call-parser qwen3_coder         # XML format, NOT hermes
--reasoning-parser qwen3
--trust-remote-code
--enable-prefix-caching
--skip-mm-profiling
```

### Performance (Benchmark 2026-03-28, fresh compile cache)

| Metric | OmniCoder-9B | ZwZ-8B (previous) |
|--------|:---:|:---:|
| Decode tok/s | **96-107** | 90-118 |
| Vision tok/s | **90-105** | 90-118 |
| Concurrent 5 text | **293 tok/s agg** | N/A |
| Tool call latency | **1.09s** | N/A (hermes) |
| Thinking mode | Yes | No |

**CRITICAL**: torch.compile cache corruption causes 10-15x slowdown (7-10 tok/s instead of 90-107). Fix: `docker volume rm profiles_vllm-compile-cache-omnicoder` and restart. Fresh compile takes ~150s.

### Quality Benchmarks (2026-03-28, vs ZwZ-8B)

| Benchmark | OmniCoder-9B | ZwZ-8B | Delta |
|-----------|:---:|:---:|:---:|
| **MME Total** | **1258.5** | 1248.1 | **+10.4** |
| MME Perception | 907.8 | 889.5 | +18.3 |
| MME Cognition | 350.7 | 358.6 | -7.9 |
| **MMStar** | 58.5% | **63.0%** | -4.5 pts |
| OCR | **97.5%** | 82.5% | **+15 pts** |
| code_reasoning | 87.5% | **95.0%** | -7.5 pts |

### Deployment (ARCHIVED 2026-04-30 — GPU 2 freed for CoursIA trainings)

OmniCoder profile + Dockerfile archived to `myia_vllm/archives/2026/mini-omnicoder.yml.archived-2026-04-30` and `Dockerfile.omnicoder.archived-2026-04-30`. To restore (NOT recommended without coordinating with CoursIA training queue):

```powershell
# Restore profile from archive first
git mv myia_vllm/archives/2026/mini-omnicoder.yml.archived-2026-04-30 myia_vllm/configs/docker/profiles/mini-omnicoder.yml
git mv myia_vllm/archives/2026/Dockerfile.omnicoder.archived-2026-04-30 myia_vllm/configs/docker/Dockerfile.omnicoder
docker compose -f myia_vllm/configs/docker/profiles/mini-omnicoder.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-mini-omnicoder
```

## ZwZ-8B (Replaced by OmniCoder-9B)

### Model Overview

**ZwZ-8B** ([inclusionAI/ZwZ-8B](https://huggingface.co/inclusionAI/ZwZ-8B)) was the vision model on GPU 2 (port 5001) from 2026-02-16 to 2026-03-28. Replaced by OmniCoder-9B. A Qwen3-VL-8B-Instruct finetune specialized for fine-grained visual perception. Key features:
- **Single-pass inference**: No iterative zooming like "Thinking-with-Images" methods
- **Region-to-Image Distillation**: Trained with Qwen3-VL-235B and GLM-4.5V as teachers
- **Training data**: 74K VQA samples from inclusionAI/ZwZ-RL-VQA
- **License**: Apache 2.0

### Differences from Qwen3-VL-8B-Thinking

| Feature | Qwen3-VL-8B-Thinking | ZwZ-8B |
|---------|---------------------|--------|
| Reasoning mode | ✅ deepseek_r1 parser | ❌ None |
| Fine-grained vision | Standard | Optimized |
| Tool calling | ✅ hermes | ✅ hermes |
| Single-pass inference | Yes | Yes |

### Quantization (Required)

ZwZ-8B is only available in BF16 (~17GB). Must create AWQ 4-bit for deployment:

```bash
# Create llmcompressor environment
conda create -n llmcompressor python=3.11 -y
conda activate llmcompressor
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124
pip install "llmcompressor>=0.9.0" "transformers>=4.48.0" accelerate datasets

# Run quantization (30-60 min)
python myia_vllm/scripts/quantization/quantize_zwz_8b.py \
  --model-id inclusionAI/ZwZ-8B \
  --output-dir ./models/ZwZ-8B-AWQ-4bit \
  --num-samples 512
```

**Critical**: Vision encoder (ViT) is excluded from quantization - kept in BF16 to preserve visual accuracy.

### Deployment

```powershell
# Switch from mini-solo (Qwen3-VL-Thinking) to ZwZ
docker compose -f myia_vllm/configs/docker/profiles/mini-solo.yml down
docker compose -f myia_vllm/configs/docker/profiles/mini-zwz.yml --env-file myia_vllm/.env up -d

# Monitor startup
docker logs -f myia_vllm-mini-zwz
```

### Key vLLM Flags for ZwZ-8B
```yaml
--model ./models/ZwZ-8B-AWQ-4bit
--served-model-name zwz-8b
--gpu-memory-utilization 0.88
--max-model-len 131072
--kv-cache-dtype fp8
--tool-call-parser hermes
# NO --reasoning-parser (ZwZ has no thinking mode)
```

## Critical Configuration Notes

1. **Do NOT add `--enable-chunked-prefill` or `--num-scheduler-steps`** - These flags force V0 engine fallback. V1 engine (default on nightly) handles chunked prefill automatically.

2. **CUDA graphs (PIECEWISE mode) work well at 0.85 gpu-memory-utilization** - Piecewise CUDA graphs have minimal overhead. **gpu-memory-utilization reduced 0.92→0.88→0.85**: Marlin MoE `fused_marlin_moe.py` needs 852-994 MiB variable temporary allocations (`intermediate_cache13`). At 0.85: 335K tokens KV cache (still >262K max-model-len), ~2.3 GiB headroom. Bug tracked in vLLM RFC [#27951](https://github.com/vllm-project/vllm/issues/27951) — no fix as of Feb 27 2026. **Do NOT use `--enforce-eager`** (tested: 3-4x slower on all metrics - 12 tok/s vs 45 tok/s decode).

3. **MLA backends on RTX 4090 don't support FP8 KV cache** - Use `--kv-cache-dtype auto` (not fp8). TRITON_MLA is the only working MLA backend on Ada Lovelace (SM89).

4. **MTP speculative decoding doesn't work with AWQ 4-bit** - 0% acceptance rate at 4-bit precision (tested on GLM-4.6-AWQ). MTP heads are part of the target model and get AWQ-quantized along with it; at 4-bit the auxiliary heads have insufficient capacity → noise predictions. **Only viable with FP8 or FP16 models.**

   **DFlash speculative decoding is architecturally different and DOES work with AWQ** — drafter is a separate 0.5B BF16 model with its own quantization config (vLLM `get_draft_quant_config()`), independent of target's quantization. Block diffusion approach generates K candidates per step. **Locally validated 2026-04-24**: 26-47% acceptance rate per-position on Qwen3.6-35B-A3B-AWQ-4bit target (4-7 tokens accepted per draft step). Single-user decode +23 to +94% but loses 5-user concurrent throughput (-15%) and context capacity (262K → 160K, since flash_attn rejects fp8 KV cache). See "Current State" DFlash bullet for full bench + decision.

5. **Use `qwen3_coder` tool parser for Qwen3.5** and `qwen3` reasoning parser. Legacy: `glm47`/`glm45` for GLM-4.7-Flash.

6. **Use `--dtype auto` for Qwen3.5 models** - `--dtype half` causes dtype mismatch with BF16 vision encoder. `auto` resolves correctly.

7. **Credentials in `.env` were compromised** - Regenerate HuggingFace token and API keys before production deployment.

## TurboQuant K8V4 Migration Attempt (2026-05-06, REJECTED)

### Why we tried
PR [#39931](https://github.com/vllm-project/vllm/pull/39931) "TurboQuant: support hybrid models and uniform quantization" merged upstream 2026-05-05 00:14 UTC (commit `4f2af1a7c`). This unblocks `--kv-cache-dtype turboquant_k8v4` for hybrid GDN+attention models — Qwen3.6 family included.

### What we tested

**Attempt 1: Qwen3.6-27B Dense + TurboQuant K8V4** — Booted cleanly. Bench tripped all 3 of the migration plan's "consider rollback" thresholds:

| Metric | 27B Dense + TurboQuant | MoE 35B-A3B (baseline) | Δ |
|---|:---:|:---:|:---:|
| Decode tok/s (single, no thinking) | 52-54 | 107 | **-50%** |
| Decode tok/s (thinking) | 50.5 | 116.5 | **-57%** |
| 5 concurrent (aggregate) | 189 | 369 | **-49%** |
| Tool call latency | 0.66s | 0.47s | +40% |
| KV cache size | 516K tokens | 322K | +60% |
| Repetition 4-gram | 0.044 | 0.028 | **+59% worse** |
| GSM8K (300 samples) | 91.7% | 87.6% (full 1319) | +4.1pts (CIs overlap) |
| IFEval (300 samples) | 91.0% | 87.6% (full 541) | +3.4pts (CIs overlap) |

Quality gains within sampling noise on the benchmarks we ran locally. Profile archived to `myia_vllm/archives/2026/medium-qwen36-27b.yml.rejected-2026-05-06`.

**Attempt 2: Qwen3.6-35B-A3B MoE + TurboQuant K8V4** (same image, switch model + add `--enable-expert-parallel`) — Booted cleanly with **1,494,999 tokens KV cache (+4.6× vs FP8 baseline 322K)**, hybrid layer detection `[3, 7, 11, 15, 19, 23, 27, 31, 35, 39]` (10/40), Marlin MoE active, EP=2 working.

EngineCore crashes on first chunked-prefill continuation request (~30K-token prompt from real OWUI traffic):
```
AssertionError: Workspace is locked but allocation from
'turboquant_attn.py:720:_continuation_prefill' requires 29.73 MB,
current size is 16.31 MB. Workspace growth is not allowed after locking.
```

Already filed upstream as [vllm#41726](https://github.com/vllm-project/vllm/issues/41726) (filed 2026-05-05 by `jhsmith409`). Bug is **not hybrid-specific** and **predates #39931** — bisected to pre-merge nightly on plain dense Qwen3-4B and Llama-3.1-8B. Candidate fix: PR [#40798](https://github.com/vllm-project/vllm/pull/40798) "Share decode scratch workspace across layers" (open). [Our reproduction comment](https://github.com/vllm-project/vllm/issues/41726#issuecomment-4389387531) confirms the bug persists post-#39931 merge on hybrid MoE + Ada hardware.

### Rollback completed (2026-05-06)
Restored MoE + FP8 KV with proven baseline image `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 nightly, stable since 2026-04-19). The TQ image (`vllm-qwen36-tq:nightly-e47c98ef-patched1`) and Dockerfile (`Dockerfile.qwen36-tq`) **retained** for re-test once #40798 merges.

To re-test TurboQuant later:
1. Edit [medium-qwen36-moe.yml](myia_vllm/configs/docker/profiles/medium-qwen36-moe.yml) line 36 → `image: vllm-qwen36-tq:nightly-e47c98ef-patched1`
2. Edit line 51 → `--kv-cache-dtype turboquant_k8v4`
3. `docker compose down && docker compose up -d`

## Qwen3.6-35B-A3B Deployment (Current — production since 2026-04-17, FP8 KV)

### Model Specifications
- **Architecture**: 35B MoE with 3B active parameters per token (256 experts, 9 active: 8 routed + 1 shared, 40 layers)
- **Attention**: Hybrid GatedDeltaNet (30 layers, linear fixed state) + Gated Attention (10 layers, standard KV cache)
- **Vision**: Images, videos, documents (vision encoder preserved in BF16)
- **Thinking**: `<think>...</think>` modulation via `chat_template_kwargs`
- **NEW in 3.6**: `preserve_thinking: True` retains reasoning across multi-turn conversations — **ENABLED BY DEFAULT SERVER-SIDE** via `--default-chat-template-kwargs`
- **VRAM**: ~11 GiB per GPU with AWQ 4-bit + TP=2
- **KV cache**: ~322K tokens at 0.85 GPU util with FP8 KV cache
- **Context window**: 262K native (YaRN extensible to 1M), configured at 262K (full native)
- **Quantization**: AWQ 4-bit (compressed-tensors/pack-quantized, group_size=32) with Marlin MoE kernels
- **Model source**: [cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit](https://huggingface.co/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit)
- **vLLM class**: `Qwen3_5MoeForConditionalGeneration` (same class as 3.5 — HF config reports this)
- **Engine**: V1 (async scheduling, piecewise CUDA graphs, automatic chunked prefill)
- **Image**: `vllm/vllm-openai:nightly-f6983f01de2bf2e92ab468fa735ebac39cddd670` (Apr 06 nightly, v0.19.1.dev45+gf6983f01d — proven stable; Apr 15/16 nightlies have init-time bugs)
- **Stability investigation (2026-04-19)**: 9 crashes in 50h on Apr 06 nightly. **Real root cause**: `SystemError: PyCFunction with class but no METH_METHOD flag` at `shm_broadcast.py:72` in `with _memory_fence_lock:` (a vanilla `threading.Lock`). Same bug as our own [issue #35104](https://github.com/vllm-project/vllm/issues/35104) (filed Feb 2026 for GLM-4.7-Flash idle crashes), but now fires UNDER LOAD on Qwen3.6 — keepalive sidecar not enough. Surface symptom (`shm_broadcast.py:681 No available shared memory broadcast block found in 60 seconds` → 3x → `EngineDeadError`) **looks identical** to the FlashInfer GDN deadlock from #37729 / #36921 / #35465 but the actual stack trace shows a different bug. `memory_fence()` was added by PR #30407 (Dec 2025) and extended by PR #32022 (Jan 2026). **PR #28053 did NOT fix this** (only removed busy-loop in idle reader — memory note correction). **No upstream fix in flight** as of 2026-04-19; design (per-op `threading.Lock` acquire as memory barrier) is fragile under runtime C-extension loads. Mitigations applied: (1) `--gdn-prefill-backend triton` (kept defensively, doesn't fix the crash), (2) **`--no-enable-flashinfer-autotune`** added 2026-04-19 16:05 UTC — hypothesis: FlashInfer JIT autotune dlopens new `.so` mid-runtime → corrupts CPython `_thread.lock` descriptor. Watch 24-48h. NOTE: there is NO env var for autotune — only the CLI flag on KernelConfig (we tried `VLLM_USE_FLASHINFER_AUTOTUNE=0` first, vLLM reported "Unknown environment variable").

### Deployment

```powershell
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen36-moe.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-qwen36-moe
```

### Key vLLM Flags
```yaml
--model cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit
--served-model-name qwen3.6-35b-a3b
--tensor-parallel-size 2
--enable-expert-parallel          # EP=2: 128/256 experts per GPU
--gdn-prefill-backend triton      # Workaround shm_broadcast deadlock (vLLM #37729, added 2026-04-19 after 8 crashes/48h)
--gpu-memory-utilization 0.85      # 0.92/0.88 OOM: Marlin MoE needs 852-994 MiB variable temp allocs
--max-model-len 262144            # Full native 262K context
--kv-cache-dtype fp8              # FP8 KV: 322K tokens (2x vs auto)
--dtype auto                      # MUST be auto (not half) for vision encoder BF16 compat
--max-num-batched-tokens 32768
--max-num-seqs 64
--enable-prefix-caching
--tool-call-parser qwen3_coder    # Qwen3.6 function calling (XML format)
--reasoning-parser qwen3          # <think>...</think> extraction
--distributed-executor-backend mp
--default-chat-template-kwargs '{"preserve_thinking":true}'  # Server-side default: multi-turn thinking retention
--limit-mm-per-prompt '{"image":4,"video":0}'
--mm-processor-kwargs '{"max_pixels":774000}'
--skip-mm-profiling               # Required: avoids dtype mismatch during profiling
```

### Environment Variables
```yaml
VLLM_MARLIN_USE_ATOMIC_ADD=1      # Optimized Marlin kernel accumulation
VLLM_USE_DEEP_GEMM=0              # Not needed for AWQ
OMP_NUM_THREADS=4                 # CPU parallelism for scheduling
VLLM_USE_FLASHINFER_MOE_FP16=1    # CRITICAL for MoE performance
```

### Thinking Modulation
To disable thinking per-request (clean, direct responses):
```json
{
  "model": "qwen3.6-35b-a3b",
  "messages": [...],
  "chat_template_kwargs": {"enable_thinking": false}
}
```
**IMPORTANT**: `chat_template_kwargs` must be a **top-level** field in the request body, NOT inside `extra_body`.

**NEW `preserve_thinking` (Qwen3.6)**: Retains `<think>...</think>` blocks from assistant message history across turns — enables iterative reasoning without redo overhead. **Enabled by default server-side** via `--default-chat-template-kwargs '{"preserve_thinking":true}'` so ALL clients benefit automatically. To opt out per-request: `"chat_template_kwargs": {"preserve_thinking": false}`.

**Reasoning field**: With thinking enabled, the parser separates reasoning into the `reasoning` field (NOT `reasoning_content`, which is always `null`). Both streaming and non-streaming work correctly.

### Performance (Benchmark 2026-04-17, FP8 KV, 262K context, Apr 06 nightly)

| Metric | Qwen3.6-35B-A3B | Qwen3.5-35B-A3B (previous) | Improvement |
|--------|:---:|:---:|:---:|
| Decode speed | **107.0 tok/s** | 86.2 tok/s | **+24%** |
| Thinking decode | **116.5 tok/s** | ~96 tok/s | **+21%** |
| Concurrent 5 users | **369.4 tok/s** | 311.2 tok/s | **+19%** |
| Tool calling | **0.47s** | 0.91s | **-48%** |
| KV cache tokens | 322K (0.85) | 335K | -4% |
| Context | 262K | 262K | = |
| Vision | Yes | Yes | = |
| Thinking | Yes + preserve | Yes | + preserve_thinking |

**Upstream quality improvements (Qwen Team blog)**:
- SWE-bench: 70.0% → **73.4%** (+3.4 pts)
- Terminal-Bench: 40.5% → **51.5%** (+11 pts)
- NL2Repo: 20.5% → **29.4%** (+8.9 pts)
- QwenWebBench: 978 → **1397** (+43%)

### Locally Measured Quality (Benchmark 2026-04-18, AWQ 4-bit)

| Benchmark | Qwen3.6-35B-A3B | Qwen3.5-35B-A3B | Δ |
|---|:---:|:---:|:---:|
| **GSM8K** (math, 1319 q) | 87.6% (1155/1319) | 88.0% (1132/1286) | -0.4 pts (3.6 has **0 errors** vs 33) |
| **IFEval** (instruction, 541 q) | 87.6% (474/541) | 88.5% (476/541) | -0.9 pts (3.6 has **0 errors** vs 3) |
| **MMStar** (vision, 1500 q) | **55.7%** (836/1500) | 53.2% (798/1500) | **+2.5 pts** |
| **MME total** (vision, 2374 q) | 1273.6 | 1294.7 | -1.6% (text_translation -15 pts is the main contributor) |
| MME perception | 918.6 | 926.8 | -0.9% |
| MME cognition | 355.0 | 367.9 | -3.5% |
| **Tool calling accuracy** (12 scenarios) | 83.3% (10/12, 2 intelligent refusals) | not measured | new |
| **Repetition 4-gram** (instruct preset) | 0.028 | 0.042 | **-33%** (less repetition) |
| **TTR diversity** (instruct preset) | 0.78 | 0.54 | **+44%** (more diverse) |

**Key findings:**
- Math/instruction quality essentially unchanged (-0.4 / -0.9 pts within statistical noise) but with **0 errors** vs 33+3 for 3.5 → much more reliable
- Vision: MMStar gains 2.5 pts; MME slightly down (-1.6%) driven by `text_translation` regression (95% → 80%, single category, 40 questions only — investigate if multilingual workloads affected)
- Repetition / lexical diversity meaningfully improved (instruct preset)
- Tool calling: model shows judgment (refused to call `get_weather` when temp already given, refused `calculator` for `sqrt(144)`)
- Upstream SWE-bench / Terminal-Bench / NL2Repo gains NOT yet locally verified — those require dedicated agent harnesses

### Comparison with All Previous Deployments

| | **Qwen3.6-35B-A3B** | Qwen3.5-35B-A3B | GLM-4.7-Flash | Qwen3-Coder-Next |
|---|---|---|---|---|
| Single user tok/s | **107** | 86 | 55 | 5-6 |
| Concurrent tok/s | **369** | 270 | 216 | 21.6 |
| Tool call | **0.47s** | 0.91s | 1.44s | N/A |
| GPUs used | 2 | 2 | 2 | 3 |
| Context | **262K** | 262K | 128K | 65K |
| KV cache | 322K | 335K | 222K | ~65K |
| SWE-bench (upstream) | **73.4%** | 69.2% | 59.2% | 70.6% |
| GSM8K (local AWQ) | 87.6% | 88.0% | n/a | n/a |
| IFEval (local AWQ) | 87.6% | 88.5% | n/a | n/a |
| MME total (local AWQ) | 1273.6 | 1294.7 | n/a | n/a |
| MMStar (local AWQ) | **55.7%** | 53.2% | n/a | n/a |
| Vision | Yes | Yes | No | No |
| preserve_thinking | **Yes** | No | No | No |

### Claude Code Integration

Students connect via `ANTHROPIC_BASE_URL`:
```bash
export ANTHROPIC_BASE_URL="https://api.medium.text-generation-webui.myia.io"
claude --model qwen3.6-35b-a3b
```

## Qwen3.5-35B-A3B (Archived 2026-04-17)

Replaced by Qwen3.6-35B-A3B on 2026-04-17. Profile archived to `myia_vllm/archives/2026/medium-qwen35-moe.yml.archived-2026-04-17`. Key specs: 35B MoE (3B active), hybrid GDN+Gated Attention, AWQ 4-bit, 86 tok/s decode, 269 tok/s concurrent, FP8 KV 335K tokens, SWE-bench 69.2%, IFEval 88.5%, GSM8K 88.0%, MME 1294.7, MMStar 53.2%. Tool parser: `qwen3_coder`, reasoning: `qwen3`. Image: `nightly-f6983f01de2bf2e92ab468fa735ebac39cddd670` (Apr 06).

## GLM-4.7-Flash (Archived)

Replaced by Qwen3.5-35B-A3B on 2026-02-25. Profile archived 2026-04-24 at `myia_vllm/archives/2026/profiles_legacy/medium-glm.yml`. Requires custom Dockerfile for `transformers >= 5.0`. Key specs: 31B MoE, 3B active, MLA attention (~54 KB/token KV), 56 tok/s decode, 197 tok/s concurrent, SWE-bench 59.2%. No vision support. Tool parser: `glm47`, reasoning: `glm45`.

## Qwen3-Coder-Next (Archived)

Archived to `medium-coder.yml`. Pipeline Parallelism (PP=3) caused severe pipeline bubbles (~66% GPU idle), limiting throughput to 5-6 tok/s. Key issues:
- TP=3 fails: `intermediate_size=8192` not divisible by 3
- TP=2 OOM: 46GB model doesn't fit in 48GB (2x24GB)
- PP=3: only viable option but pipeline bubbles destroy autoregressive performance

## Project History & Context

This repository has been maintained primarily by Roo (another AI agent) through 20+ documented missions. Key milestones:
- Missions 1-15: Initial setup, Qwen3 integration, optimization
- Missions 16-17: Vision model support (Qwen3-VL-32B)
- Missions 18-21: FP8 investigations, structure consolidation
- Mission 22+: Migration to Qwen3-Coder-Next (archived)
- Mission 23+: Migration to GLM-4.7-Flash for better performance

Legacy `myia-vllm/` directory has been archived to `myia_vllm/archives/legacy_myia-vllm_*/`.

## Logging Middleware (DISABLED in production)

ASGI middleware (`myia_vllm/middleware/logging_middleware.py`) that intercepts `/v1/chat/completions` and logs full request/response content + timing as JSONL at `/logs/chat_completions.jsonl`. **Disabled since 2026-03-13** due to -40-65% throughput impact. Available for temporary debugging.

- **Captures**: model, messages_count, last_user_message, tools_count, all sampling params, chat_template_kwargs, response_text, reasoning_text, tool_calls, finish_reason, prompt_tokens, completion_tokens, ttft_s, e2e_s
- **Handles both streaming (SSE) and non-streaming** responses
- **Config**: `VLLM_LOG_DIR` (default `/logs`), `VLLM_LOG_REQUESTS_CONTENT` (default `1`)
- **To enable**: add `--middleware logging_middleware.RequestResponseLogger` + `PYTHONPATH=/middleware` to Docker profile
- Volume-mounted read-only: `myia_vllm/middleware:/middleware:ro`

## SK Agent MCP Server

Semantic Kernel-based MCP proxy (`myia_vllm/mcp/sk_agent.py`) exposing any OpenAI-compatible model as MCP tools for Claude Code / Roo Code. Uses pluggable MCP servers for tool calling.

### Tools exposed
- `ask(prompt, system_prompt?)` -- text query with auto tool use
- `analyze_image(image_source, prompt?)` -- vision, converts local paths to base64
- `list_tools()` -- introspection

### Architecture
```
Claude/Roo --stdio--> FastMCP server --> Semantic Kernel
                                          ├── OpenAI Chat Completion --> vLLM
                                          ├── MCPStdioPlugin: SearXNG
                                          └── MCPStdioPlugin: ... (from config)
```

### Config (`sk_agent_config.json`)
- `model.base_url` -- endpoint (vLLM, Open-WebUI, etc.)
- `model.api_key_env` -- env var name for API key
- `model.vision` -- enable image support
- `mcps[]` -- list of MCP servers to plug in (command, args, env)
- Adding a new tool = adding an MCP entry to config, zero code changes

### Registration
```bash
claude mcp add sk-agent --transport stdio \
  -e SK_AGENT_CONFIG="d:/vllm/myia_vllm/mcp/sk_agent_config.json" \
  -e VLLM_API_KEY_MEDIUM="..." \
  -- python d:/vllm/myia_vllm/mcp/sk_agent.py
```
Note: Config points to `qwen3.5-35b-a3b` on port 5002 (updated 2026-02-25).

### Dependencies
```
semantic-kernel[mcp]>=1.39  (requires openai>=1.109)
mcp>=1.7
```

## Sampling Parameter Optimization (2026-03-08)

### Problem
Repetition and language mixing (Chinese in French responses) observed in Roo Code. Root cause: Roo sends only `temperature` (was 0.1, quasi-greedy) with no `presence_penalty`. The `presence_penalty` is critical for Qwen3.5 to avoid repetition loops.

### Qwen Official Sampling Recommendations

| Mode | temp | top_p | top_k | presence_penalty | repetition_penalty |
|------|:----:|:-----:|:-----:|:----------------:|:-----------------:|
| **Thinking General** | 1.0 | 0.95 | 20 | **1.5** | 1.0 |
| **Thinking Coding** | 0.6 | 0.95 | 20 | 0.0 | 1.0 |
| **Instruct General** | 0.7 | 0.8 | 20 | **1.5** | 1.0 |
| **Instruct Reasoning** | 1.0 | 1.0 | 40 | **2.0** | 1.0 |

### vLLM Server-Side Defaults
`--override-generation-config '{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"repetition_penalty":1.0}'`
Supported params in `--override-generation-config` (`vllm/config/model.py:1395-1402`): `repetition_penalty`, `temperature`, `top_k`, `top_p`, `min_p`, `max_new_tokens`.
Note: `presence_penalty` is NOT in this list — default is 0.0, must be injected client-side or via OWUI wrappers.

### OWUI Model Wrappers (Sampling Injection, calibrated 2026-03-21)
8 models in OWUI inject sampling params optimized for AWQ Q4 quantization. Adjusted from official Qwen BF16 recommendations based on Reddit community feedback + local benchmarks.

**Qwen_* preset wrappers:**

| OWUI Model | Usage | temp | pp | rp | top_p | top_k | min_p | thinking |
|------------|-------|:----:|:--:|:--:|:-----:|:-----:|:-----:|:--------:|
| `Qwen_think` | General | 0.7 | 1.5 | — | 0.95 | 20 | — | yes |
| `Qwen_think-code` | Coding | 0.6 | 0.0 | — | 0.95 | 20 | — | yes |
| `Qwen_think-reason` | Reasoning | 1.0 | 1.5 | — | 1.0 | 40 | — | yes |
| `Qwen_instruct` | Chat | 0.7 | 1.5 | 1.1 | 0.8 | 20 | 0.01 | no |

**Original model wrappers (aligned 2026-03-21):**

| OWUI Model | Usage | temp | pp | rp | top_p | top_k | min_p | thinking |
|------------|-------|:----:|:--:|:--:|:-----:|:-----:|:-----:|:--------:|
| `Local.qwen3.5-35b-a3b` | Chat général | 0.7 | 1.5 | — | 0.95 | 20 | — | yes |
| `Local.qwen3.5-35b-a3b-fast` | Bots/FAQ | 0.6 | 0.5 | 1.1 | 0.85 | 20 | 0.01 | no |
| `expert-analyste` | Analyse/coding | 0.6 | 0.0 | — | 0.95 | 20 | — | yes |
| `redacteur-technique` | Rédaction | 0.8 | 0.5 | 1.05 | 0.95 | 20 | 0.05 | yes |

**Q4 adjustments vs official BF16**: temp 1.0→0.7 (thinking general), pp 2.0→1.5 (reasoning, language mixing risk), rp 1.05-1.1 (anti "reasoning bleed-through"), min_p 0.01-0.05 (quantization artifact filter).

**OWUI endpoint for Roo**: `https://open-webui.myia.io/api` (NOT /v1)
**API**: `POST /api/v1/models/model/update` to modify params (full replace, not partial)
**Mechanism**: `params` (native: temp, top_p, min_p, pp, fp) + `custom_params` (top_k, rp, chat_template_kwargs) deep-merged into request body. `ModelParams` uses `extra="allow"`.

### Repetition Benchmark Results (2026-03-08, AWQ 4-bit)

| Preset | 4gram | 8gram | TTR | RepLine | tok/s |
|--------|:-----:|:-----:|:---:|:-------:|:-----:|
| baseline (0.3, pp=0) | 0.104 | 0.041 | 0.450 | 0.028 | 110.7 |
| roo-current (0.6, pp=0) | 0.108 | 0.035 | 0.441 | 0.036 | 102.1 |
| think-code (0.6, pp=0) | 0.077 | 0.024 | 0.482 | 0.028 | 117.9 |
| **think-general (1.0, pp=1.5)** | 0.071 | 0.030 | 0.522 | 0.012 | 111.3 |
| **think-reason (1.0, pp=2.0)** | 0.050 | 0.015 | 0.555 | 0.016 | 116.6 |
| **instruct (0.7, pp=1.5)** | **0.042** | **0.013** | **0.540** | **0.013** | 106.9 |

**Key findings**:
- `presence_penalty` 1.5-2.0 reduces 4-gram repetition by **2-3x** vs pp=0
- No speed impact from penalties (~100-118 tok/s across all presets)
- `instruct` (pp=1.5, no thinking) has lowest repetition + highest diversity
- These results apply to AWQ 4-bit quant (BF16 may differ)

### SK Agent Sampling Support
SK Agent (`sk_agent.py`) now reads sampling params from `sk_agent_config.json`:
```json
"sampling": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 1.5, "max_tokens": 4096}
```
Passed via `OpenAIChatPromptExecutionSettings` to `ChatCompletionAgent.get_response()`.
Non-standard params (top_k, min_p) sent via `extra_body`.

## Current State (2026-08-04: gpu-util lowered again 0.78→0.70 — 0.78 was not a durable cure, boot-OOM recurred twice more on the desktop-shared GPU 0 — KV now 1,238,046; batch stays 4096; 413 guard removed; v2g baseline since 2026-05-17)

- **Qwen3.6-35B-A3B MoE + Genesis TurboQuant k8v4** on port 5002 (GPUs 0,1) — promoted from experimental to production baseline 2026-05-17 after the +35h post-deploy soak completed clean
  - Image: `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` (Sandermage Genesis patch tree on nightly `01d4d1ad3`)
  - Profile: `medium-qwen36-genesis-tq.yml` (Genesis patches P3/P4/P6/P22[skipped]/P26[skipped]/P37/P38B/P40/P67/P78/P98/P101 + PN33 by-default + custom env)
  - **`--gpu-memory-utilization 0.70`** (0.82 → 0.78 on 2026-07-14 → **0.70 on 2026-08-04**). GPU 0 is shared with the Windows desktop (explorer/VSCode/Edge, fluctuating VRAM baseline); GPU 1 has none. A desktop spike between memory-profiling and KV-cache-tensor allocation pushes GPU 0 over its own gpu-util pool cap → **boot-time CUDA-OOM crash-loop** at `_allocate_kv_cache_tensors`. Three occurrences in 19 days: 2026-07-13 @0.82 (RestartCount 53→59+, OOM on a 34 MiB alloc with "9.91 GiB free" = pool-cap not true exhaustion), then **again at 0.78** on 07-28 and 08-01 (686 MiB alloc failing with 2.66 GiB free) — the 0.82→0.78 step had moved the failure point by only ~0.2 GiB. **Why the nominal budget lies:** vLLM's real footprint exceeds `gpu-util × 24564` by **+2 768 MiB @0.78 and +2 145 MiB @0.70** (measured on GPU 1, desktop-free) because Marlin-MoE variable temp allocs (RFC #27951), the Genesis prealloc pools (P28 GDN / P37 MoE / TQ-dequant) **and the CUDA graphs** all live outside it — vLLM warns about the last one at boot, since we run `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0`. Pre-change GPU 0 was at 23,745/24,564 MiB = **819 MiB free**. At 0.70: GPU 0 **21,145 MiB**, GPU 1 **19,340 MiB**, KV **1,736,379 → 1,238,046 tokens (−29%, still 4.72× the 262K window; prod occupancy is 2–7%)**, no decode regression. **Untested alternative if KV is ever needed back:** re-enable `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1` and run gpu-util **0.7349** as vLLM's own boot warning suggests. **Watchdog v3 blind spot — FIXED in v4 (2026-07-15, deployed 07-28, field-proven correct-negative 08-01):** a crash-loop re-enters Docker `starting` on each restart → the DOWN-path treated `starting` as boot-safe (never-restart) → the watchdog never intervened (07-13 crash-loop was completely silent). Watchdog **v4** now reads `RestartCount` inside the `starting` branch: a patient cold boot keeps it flat, a crash-loop makes it climb → after 3 restart-increments (~6 min) it emits a loud greppable `CRASH-LOOP` line. No auto-restart (futile while Docker is already relooping the container; the real cure is the gpu-util drop or freeing GPU-0 VRAM) — detection + visibility only. Simulated (flat RC → BOOTING, climbing RC → CRASH-LOOP at churn≥3, single restart → no false positive) and `sh -n` clean; deployed 07-28 and field-proven on 08-01 (flat `RestartCount=2` → patient `BOOTING`, no false `CRASH-LOOP`). Shipped in [PR jsboige/vllm#11](https://github.com/jsboige/vllm/pull/11) with the gpu-util change. Both the gpu-util value and the watchdog comment live OUTSIDE the `command: >` folded scalar (a `#` inside it becomes a literal vLLM arg).
  - Marlin MoE, Expert Parallelism (EP=2), CUDA graphs (full+piecewise), prefix caching (xxhash), chunked prefill, async scheduling
  - ✅ Vision (images, documents) + Thinking modulation + `preserve_thinking` server-side default
  - ✅ `--override-generation-config` defaults (temp 0.6, top_p 0.95, top_k 20, min_p 0.0, rp 1.0)
  - ✅ Watchdog sidecar (dual-ping host + Docker DNS, auto-restart 3 fails)
  - ✅ `error_source_capture` ASGI middleware active (logs body_head + body_tail 1500B to /logs/error_sources.jsonl)
  - **KV cache: 1,238,046 tokens @ gpu-util 0.70 (×3.8 vs prior FP8 322K; was 1,736,379 @0.78 and ~2.0M @0.82)** — `--kv-cache-dtype turboquant_k8v4` + Genesis P22/P38B continuation-prefill workspace fix. Max concurrency 4.72× at 262K.
  - **Single-user decode**: 120 tok/s no-think (+12% vs FP8), 124 tok/s thinking (+6%)
  - **Concurrent**: N=12 → 625 tok/s, N=16 → **829 tok/s aggregate (+125%)** — main reason for promotion. Prior FP8 saturated at ~N=5.
  - **Context**: 262K native, max-model-len 262144
  - **Critical env**: `VLLM_USE_FLASHINFER_SAMPLER=0` (v2f had idle deadlock at +55min; v2g fix). `--no-enable-flashinfer-autotune`. `NCCL_P2P_DISABLE=1`.
  - **Batch stays at `--max-num-batched-tokens 4096` / `--max-num-seqs 16`. The 2026-06-24 attempt to unlock 8192 via Genesis P72+P74 was REVERTED after a prod crash.** **Mechanism CORRECTED 2026-06-28 (verified on our own image via read-only `docker exec`; Sandermage, the patch author, confirmed on [genesis #33](https://github.com/Sandermage/genesis-vllm-patches/issues/33#issuecomment-4811423542)): the overflowing GDN buffer is patch **P28** (`_genesis_gdn_core_attn_buf` prealloc), NOT P72.** P72 (`GENESIS_PROFILE_RUN_CAP_M=4096`) only caps the *profiling* forward at M=4096 (which dodges the 2026-05-24 Dynamo boot crash), letting the engine *boot* at batch 8192 — it does **not** size the runtime buffer. The P28 buffer is sized by the P73 budget resolver, which — with no `GENESIS_PREALLOC_TOKEN_BUDGET` set — falls to its **default 4096** (the `scheduler_config` auto-probe returns None at resolve time, an init-ordering race; every boot logs `[Genesis P73] token budget resolved → 4096 (default fallback)`). P72's cap and P28's default were *coincidentally* both 4096, so it looked like the profile cap coupled the buffer — it did not. A runtime forward >4096 overflows the 4096-sized P28 buffer and killed the worker at 15:23:56Z (~1h25 after deploy): `RuntimeError: setStorage: sizes [5536, 16, 128] … requiring a storage size of 22675456 are out of bounds for storage of size 16777216` (16777216 = 4096×16×128×2; 22675456 = 5536×16×128×2) at `qwen3_next.py:495` via the inductor/cuda-graph `as_strided` path. This crash was the "condensation no longer works" red alert (roo-state-manager :5002 calls got `Connection error` ×3). The 2026-06-24 bench that "validated" 8192 could not trigger it: the 80K crash test is P74-chunked to ≤4096 and N=16 decode is ~16 tok/step — neither produces a forward batch in (4096, 8192]. **4096 IS the effective ceiling** (the P28 default). To run 8192 safely: `GENESIS_PREALLOC_TOKEN_BUDGET=8192` (GLOBAL resolver override — sizes the P28 GDN, P37 MoE, and TQ-dequant pools) + **keep** P72 at 4096 + `--max-num-batched-tokens 8192` + a FORCING test (several concurrent ~2-3K prefills summing one forward into (4096,8192]) off-peak. UNTESTED, DEFERRED — do not retry on prod without that test. Watchdog flapping is NOT fixable by ramping batch (tune the watchdog: done — MAX_FAIL 3→5, --max-time 30→60). Full detail: MEMORY.md `project_genesis_tq_batch_ceiling.md`.
  - **Oversize-request 413 guard REMOVED 2026-06-24** (`VLLM_MAX_REQUEST_BODY_BYTES=0`, kept after the batch revert — independent and safe): the 512 KB HTTP 413 reject turned slow z.ai→qwen fallback overflow into hard-fails → **cluster-wide cascade outage**. Real lever is the claudish-side concurrency cap (no-fallback routing), NOT body-size rejection. `error_source_capture` middleware stays ON for logging; set the env >0 to re-enable the reject if ever needed.
  - Quality upgrades over Qwen3.5 (upstream): SWE-bench 70→73.4, Terminal-Bench 40.5→51.5, NL2Repo 20.5→29.4, QwenWebBench 978→1397
- **Why Genesis (Option B) was the actionable path**: The 2026-05-06 stock attempt with `vllm-qwen36-tq:nightly-e47c98ef-patched1` + `--kv-cache-dtype turboquant_k8v4` crashed on first chunked-prefill continuation ([vllm#41726](https://github.com/vllm-project/vllm/issues/41726): `AssertionError turboquant_attn.py:720`, requires 29.73 MB / has 16.31 MB). Upstream candidate fix [PR #40798](https://github.com/vllm-project/vllm/pull/40798) was OPEN+BLOCKED with no ETA, so we adopted [`Sandermage/genesis-vllm-patches`](https://github.com/Sandermage/genesis-vllm-patches) v7.72.x downstream patch tree whose P22/P38 family fixes exactly that crash (externally confirmed by `xyehya` in vllm#41726).
- **Promotion path 2026-05-16 → 2026-05-17**:
  - v2a/v2d/v2e iterations: tuned KV/concurrent tradeoffs
  - v2f (Genesis-TQ + vision): PASSED active load benches but regressed on +55min IDLE soak (shm_broadcast.py:733 deadlock at 05:29Z). Auto-rolled back to FP8 baseline 05:35Z per user rule.
  - v2g = v2f + `VLLM_USE_FLASHINFER_SAMPLER=0` (FlashInfer sampler had its own JIT autotune path corrupting CPython `_thread.lock` descriptor under load). Deployed 06:29Z. **35h soak clean → promoted 2026-05-17.**
  - Iteration log: `myia_vllm/_iteration_log/genesis_tq_night_log.md`
- **Prior FP8 baseline retained for instant rollback**: `vllm-qwen36-shmpatched:nightly-f6983f01d-patched1` (Apr 06 + shm_broadcast.py patch + transformers>=5.0). Image still local, profile `medium-qwen36-moe.yml` untouched. Rollback: `docker compose -f medium-qwen36-genesis-tq.yml down && docker compose -f medium-qwen36-moe.yml up -d`.
- **Spec-decode experiments — RETIRED to documentation-only (2026-05-17/18)**: 4 attempts across DFlash + MTP, 4 crashes, 2 distinct upstream-trackable bugs + 1 deferred deepcopy poison family. Stay on v2g (829 tok/s aggregate N=16 is excellent for our multi-user workload anyway). Profiles preserved on disk for re-test once upstream patches land.
  - **Att1 — DFlash-v2g Attempt 1** (`medium-qwen36-genesis-tq-dflash.yml`, K=15, with `--default-chat-template-kwargs`): deepcopy/segfault in tokenizer `init_kwargs` (`copy.py:128 memo.get()` with memo being a `code` object). Hypothesis at the time: chat-template-kwargs injected a code object. **Falsified later by Att4**.
  - **Att2 — DFlash-v2g Attempt 2** (K=7, dropped chat-template-kwargs, max-num-batched-tokens 8192): torch.compile fake-tensor mismatch dim 0 (`mul(FakeTensor(65536,128), FakeTensor(16*s59,128))`).
  - **Att3 — DFlash-v2g Attempt 3** (K=7, max-num-batched-tokens 4096): `RuntimeError: Worker failed with error 'Page size mismatch after block_size adjust: 1136064 != 3408192'` (ratio 3:1 exact). TurboQuant k8v4 page (target) ↔ FLASH_ATTN page (drafter) interop gap. Genesis PN9 self-retires when upstream #39930 merged but doesn't close the page-layout gap. **Same family as upstream [vllm#41559](https://github.com/vllm-project/vllm/issues/41559)** — datapoint posted [issuecomment-4472523463](https://github.com/vllm-project/vllm/issues/41559#issuecomment-4472523463). Fix path: PR [#39995](https://github.com/vllm-project/vllm/pull/39995) (DFlash + FlashInfer + FP8 KV) but doesn't cover TurboQuant.
  - **Att4 — FP8+MTP Attempt 4** (`medium-qwen36-fp8-mtp.yml`, `Qwen/Qwen3.6-35B-A3B-FP8` model, MTP method): SAME deepcopy/segfault as Att1, different call site (`transformers/configuration_utils.py:678 → copy.deepcopy(kwargs)` in AutoConfig.from_pretrained). **Falsifies the Att1 chat-template-kwargs hypothesis** (Att4 doesn't have that flag and still crashes). Real pattern: spec-decode + Qwen3.6 multimodal + Genesis image triggers dual-config-load deepcopy poison (similar to vllm#35104 PyCFunction family). **NOT FILED YET** — must repro on stock vLLM `01d4d1ad3` without Genesis layer first to disambiguate venue (vllm-project vs Sandermage).
  - **v2g working datapoint posted**: [vllm#41726 issuecomment-4472611221](https://github.com/vllm-project/vllm/issues/41726#issuecomment-4472611221) — confirms xyehya's 2026-05-09 finding (Genesis P22+P38 fixes the `_continuation_prefill` crash) on Ada SM89 with 35h+ production soak. Mentions `VLLM_USE_FLASHINFER_SAMPLER=0` trap.
  - Profiles kept on disk as documentation: `medium-qwen36-genesis-tq-dflash.yml` (Att2/Att3 config), `medium-qwen36-genesis-tq-mtp.yml` (INERT — AWQ target drops MTP heads), `medium-qwen36-fp8-mtp.yml` (Att4 — re-test if Genesis ships a patch for the dual-config-load deepcopy).
  - Iteration logs: `myia_vllm/_iteration_log/dflash_v2g_attempt{1,2,3}/`, `myia_vllm/_iteration_log/fp8_mtp_attempt4/`, `myia_vllm/_iteration_log/v2g_promotion_followup/`.
- **GPU 2 — FULLY FREED 2026-05-01** for CoursIA training jobs (queue 5-7d : QC ML strategies, Sudoku large, RL extension). State: **78 MiB / 24564 MiB** (driver baseline only, no resident process). OmniCoder-9B archived 2026-04-30 (`myia_vllm/archives/2026/mini-omnicoder.yml.archived-2026-04-30`, `Dockerfile.omnicoder.archived-2026-04-30`). Reasoning: ai-01 piloting double-track (coordination + training) sprint sustainable. Issue CoursIA #626.
- **Kokoro TTS migrated to po-2023** (2026-05-01): final endpoint `https://tts.myia.io/kokoro/v1` (path-strip via IIS, bearer auth required, sleep-mode like Orpheus). 7/7 OWUI tenants switched (myia, epf, epf-genai, ece, esg, epita, pauwels — synthesis tested HTTP 200 with `ff_siwis` voice, MP3 ID3 valid). Service `kokoro-tts` removed from `myia-open-webui` compose stack on ai-01, volume `kokoro-data` purged. Quirks noted: po-2023 endpoint serves `/v1/voices` (200) but NOT `/v1/audio/voices` (404, non-standard); `/v1/audio/speech` works fine (used by OWUI). Commit `d37df601b` (myia-open-webui workspace).
- **Orpheus TTS moved to po-2023** (2026-03-18): `https://orpheus-tts.myia.io/v1/audio/speech`
- **OWUI sampling calibration** (2026-03-21): 8 model wrappers calibrated for AWQ Q4 (Reddit + HF + local benchmarks). Key Q4 adjustments: temp 1.0→0.7, pp capped at 1.5 (not 2.0), rp 1.05-1.1 anti-bleed, min_p 0.01-0.05. Bug fixed: `-fast` had missing `enable_thinking: false`.
- **SK Agent MCP server** uses Qwen3.6-35B-A3B (port 5002, updated 2026-04-17)
- **roo-state-manager condensation** uses Qwen3.6-35B-A3B via `OPENAI_CHAT_MODEL_ID` env var
- **Roo "simple" apiConfig** uses Qwen3.6-35B-A3B (in `roo-extensions/roo-config/model-configs.json`)
- **vLLM versions** (updated 2026-04-17):
  - GPUs 0,1 (Qwen3.6 MoE): **pinned to nightly `f6983f01de2bf2e92ab468fa735ebac39cddd670`** (Apr 06, v0.19.1.dev45+gf6983f01d). Apr 15 nightly hangs at compile init; Apr 16 nightly has broken transformers import (missing pandas). Apr 04 nightly has shm_broadcast PyCFunction bug.
  - GPU 2 (OmniCoder): nightly Apr 04 (v0.19.1) + transformers 5.5.0
- **API keys rotated** (2026-03-13): all 3 keys regenerated after accidental git exposure, hardcoded keys removed from 13 files
- **Sampling optimization** (2026-03-08): presence_penalty 1.5 reduces repetition 2-3x with no speed impact
- **OWUI routing for Roo: ABANDONED** (2026-03-10): 83+ MCP tools overwhelm OWUI pipe. OWUI wrappers exist for direct OWUI users only.
- **Models rejected**: Qwen3.5-27B Dense (2026-02-25), GPTQ-Int4 (2026-03-03), BNB NF4 distill (2026-03-13), Qwen3.5-27B-Claude-Opus-Distilled-v2 AWQ (2026-04-05: 56 tok/s decode -36%, tool calling broken with qwen3_coder, concurrent -53%, KV cache 106K vs 324K), **Qwen3.6-27B dense AWQ INT4 single-GPU** (2026-04-24: 19.06 GB weights don't fit single RTX 4090 24GB with KV cache headroom. Universal upstream guard, not Ampere-specific. Profile `mini-qwen36-27b.yml` retained for TP=2 deployment or future 4B/9B variants), **Qwen3.6-27B dense + TurboQuant K8V4 TP=2** (2026-05-06 same-day cutover attempt: decode -50%, 5-concurrent -49%, tool +40% — all 3 rollback thresholds tripped; quality gains within sampling noise. Profile archived to `archives/2026/medium-qwen36-27b.yml.rejected-2026-05-06`), **Qwen3.6-35B-A3B MoE + TurboQuant K8V4** (2026-05-06: booted with 1.49M-token KV but EngineCore crashes on first chunked-prefill continuation — upstream bug [vllm#41726](https://github.com/vllm-project/vllm/issues/41726), candidate fix [PR #40798](https://github.com/vllm-project/vllm/pull/40798). Re-test when #40798 merges)
- **DFlash speculative decoding** (evaluated 2026-04-24, NOT deployed in prod): drafter `z-lab/Qwen3.6-35B-A3B-DFlash` (8-layer Qwen3 dense, BF16, ~0.5B). Block diffusion, block_size=16, target_layer_ids=[1,10,19,28,37]. Profile `medium-qwen36-moe-dflash.yml` retained as opt-in. **Empirical bench vs baseline 3.6**: single-user code +23% (131 vs 107 tok/s), single-user reasoning **+94%** (226 vs 116.5 tok/s), single-user code long +59% (170 tok/s); 5-user concurrent **-15%** (315 vs 369 tok/s aggregate). **Trade-offs**: requires `--attention-backend flash_attn` which **rejects fp8 KV cache** → max-model-len capped at 160K (vs baseline 262K), KV cache 93K tokens (vs baseline 322K), max concurrency 1.15× (vs baseline 4.69×). **Acceptance rate confirmed compatible with AWQ target**: 26-47% per-position, 4-7 tokens accepted per draft step. **The "0% acceptance with AWQ" claim previously in MEMORY.md was a hallucination** — only MTP (multi-token prediction, vLLM `--speculative-config method=mtp`) shows 0% with AWQ (tested on GLM-4.6-AWQ, see CLAUDE.md "Critical Configuration Notes" #4). DFlash drafter is a separate BF16 model with its own quant config via `vllm.model_executor.models.utils.get_draft_quant_config`, hence AWQ target compatibility. **Decision (2026-04-24)**: rollback to baseline — concurrent throughput + 262K context matter more for our Roo orchestrator + multi-student workload than single-user speedup. Profile retained at `myia_vllm/configs/docker/profiles/medium-qwen36-moe-dflash.yml` for benchmarks or future single-user-heavy use cases.
- **TurboQuant migration — Option B is the actionable path (2026-05-14 review)**: Workload is **multi-user long context** (OWUI/Roo multi-tenant + Claude Code routing) → KV cache **capacity** is the bottleneck → TurboQuant (×4.6 KV: 1.49M vs 322K tokens) is the priority lever (not DFlash, which helps single-user but costs −15% concurrent). **Two paths:**
  - **Option A (upstream) — NOT VIABLE**: PR [#39931](https://github.com/vllm-project/vllm/pull/39931) merged 2026-05-05 unblocks hybrid models but exposes the `_continuation_prefill` workspace crash ([#41726](https://github.com/vllm-project/vllm/issues/41726), hit on our MoE 2026-05-06). Candidate fix [PR #40798](https://github.com/vllm-project/vllm/pull/40798) is **OPEN + BLOCKED** (verified 2026-05-14, no ETA — `gaby`: "TurboQuant does not work at all without this").
  - **Option B (ACTIONABLE)**: [`Sandermage/genesis-vllm-patches`](https://github.com/Sandermage/genesis-vllm-patches) downstream patch tree — v7.72.x, 126 patches, 1958 tests, explicitly targets Qwen3.6-35B-A3B + TurboQuant k8v4 + 256K context. Patches **P22+P38** fix our exact crash — externally confirmed by `xyehya` in issue #41726 (2026-05-09: "patches P38 and P22 ... fixed my issue"). **Next step**: build a genesis-patched image (base nightly ≥2026-05-05 + genesis installer + our transformers>=5.0/shm patches), re-run the 2026-05-06 MoE+TQ attempt against real ~30K-prefix OWUI traffic. Full detail in MEMORY.md `project_turboquant_hybrid_status.md`.
  - Both 27B Dense + TQ (perf regression, rejected) and MoE 35B-A3B + TQ (the crash above) were tried 2026-05-06. Issue [#40807](https://github.com/vllm-project/vllm/issues/40807) (TurboQuant + spec-dec MTP + chunked-prefill) does NOT affect us — no spec-dec in prod.

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [Qwen3.6-35B-A3B-AWQ on HuggingFace](https://huggingface.co/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit)
- [Qwen3.6 Official Blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
- [Qwen3.5-35B-A3B-AWQ on HuggingFace](https://huggingface.co/cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit) (previous model)
- [GLM-4.7-Flash on HuggingFace](https://huggingface.co/zai-org/GLM-4.7-Flash) (legacy)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
