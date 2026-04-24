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

**Current deployment**: Qwen3.6-35B-A3B (35B MoE, 3B active, AWQ 4-bit, vision+thinking+preserve_thinking) on GPUs 0,1 with TP=2+EP. GPU 2: OmniCoder-9B (vision, 131K ctx) + Kokoro TTS.

**Previous deployment**: Qwen3.5-35B-A3B (35B MoE, AWQ 4-bit) - replaced by Qwen3.6 on 2026-04-17 (+24% decode, -48% tool call, +19% concurrent, SWE-bench +3.4pts, Terminal-Bench +11pts, NL2Repo +8.9pts).

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
# Start Qwen3.6-35B-A3B MoE (primary model, GPUs 0,1)
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen36-moe.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-qwen36-moe

# Start ZwZ-8B (vision, GPU 2 solo mode)
docker compose -f myia_vllm/configs/docker/profiles/mini-zwz.yml --env-file myia_vllm/.env up -d

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
| **medium-qwen36-moe** | **0,1** | **5002** | **Qwen3.6-35B-A3B-AWQ** | **medium-qwen36-moe.yml** |
| **mini-omnicoder** | **2** | **5001** | **OmniCoder-9B-AWQ-4bit** | **mini-omnicoder.yml** (gpu-util 0.85, 128K ctx) |
| kokoro-tts | 2 | 8880 | Kokoro TTS (67 voices) | myia-open-webui compose |
| medium-qwen35-moe | 0,1 | 5002 | Qwen3.5-35B-A3B-AWQ | archived 2026-04-17 (replaced by 3.6) |
| mini-zwz | 2 | 5001 | ZwZ-8B-AWQ-4bit | mini-zwz.yml (replaced by OmniCoder) |
| medium-glm | 0,1 | 5002 | GLM-4.7-Flash-AWQ | archives/2026/profiles_legacy/medium-glm.yml |
| medium-qwen35-dense | 0,1 | 5002 | Qwen3.5-27B-AWQ | medium-qwen35-dense.yml (rejected: too slow) |
| mini-solo | 2 | 5001 | Qwen3-VL-8B-Thinking-AWQ | mini-solo.yml (fallback) |

GPUs 0,1 are on faster PCIe bus. GPU 2 runs OmniCoder-9B (gpu-util 0.85, 128K ctx) + Kokoro TTS (0.5 GB).

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

### Deployment

```powershell
docker compose -f myia_vllm/configs/docker/profiles/mini-omnicoder.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-mini-omnicoder

# Rollback to ZwZ-8B
docker compose -f myia_vllm/configs/docker/profiles/mini-omnicoder.yml down
docker compose -f myia_vllm/configs/docker/profiles/mini-zwz.yml --env-file myia_vllm/.env up -d
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

## Qwen3.6-35B-A3B Deployment (Current)

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

## Current State (2026-04-17)

- **Qwen3.6-35B-A3B MoE running** on port 5002 (GPUs 0,1) — **production since 2026-04-17** (replaces Qwen3.5)
  - ✅ FlashInfer MoE, Expert Parallelism (EP=2), CUDA graphs, prefix caching
  - ✅ Vision (images, documents) + Thinking modulation
  - ✅ `--override-generation-config` with defaults (temp 0.6, top_p 0.95, top_k 20, min_p 0.0, rp 1.0)
  - ✅ **NEW: `--default-chat-template-kwargs '{"preserve_thinking":true}'`** — server-side default for multi-turn reasoning retention (works for clients that can't customize chat_template_kwargs)
  - ✅ Watchdog sidecar: dual-ping (host.docker.internal + Docker DNS), auto-restart after 3 fails
  - FP8 KV cache: **322K tokens** (0.85 gpu-util)
  - Performance: **107.0 tok/s decode, 369.4 tok/s concurrent, 0.47s tool call, 116.5 tok/s thinking** (Apr 06 nightly, benchmarked 2026-04-17)
  - vLLM class: `Qwen3_5MoeForConditionalGeneration` (same code path as 3.5)
  - Quality upgrades (upstream): SWE-bench 70→73.4, Terminal-Bench 40.5→51.5, NL2Repo 20.5→29.4, QwenWebBench 978→1397
- **GPU 2**: OmniCoder-9B on port 5001 — **deployed 2026-03-28**
  - Custom Dockerfile: vLLM nightly Mar 28 + transformers 5.x (Qwen3.5-dense arch needs it)
  - gpu-util 0.85, 128K ctx, FP8 KV, CUDA graphs, keepalive sidecar
  - `--tool-call-parser qwen3_coder` (NOT hermes — XML format)
  - Decode 96-107 tok/s, tool call 1.09s, MME 1258.5, MMStar 58.5%
  - **torch.compile cache can corrupt** → 10-15x slowdown. Fix: delete volume + restart (fresh compile ~150s)
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
- **Models rejected**: Qwen3.5-27B Dense (2026-02-25), GPTQ-Int4 (2026-03-03), BNB NF4 distill (2026-03-13), Qwen3.5-27B-Claude-Opus-Distilled-v2 AWQ (2026-04-05: 56 tok/s decode -36%, tool calling broken with qwen3_coder, concurrent -53%, KV cache 106K vs 324K), **Qwen3.6-27B dense AWQ INT4** (2026-04-24: 19.06 GB weights don't fit single RTX 4090 24GB with KV cache headroom — `ValueError: No available memory for the cache blocks` at gpu-util 0.90. TurboQuant KV cache NOT compatible with hybrid GDN+Attention models — `NotImplementedError: TurboQuant KV cache is not supported for hybrid (attention + Mamba) models. Boundary layer protection requires uniform attention layers.` Universal upstream guard, not Ampere-specific. Profile `mini-qwen36-27b.yml` retained for TP=2 deployment or future 4B/9B variants)
- **DFlash speculative decoding** (evaluated 2026-04-24, NOT deployed in prod): drafter `z-lab/Qwen3.6-35B-A3B-DFlash` (8-layer Qwen3 dense, BF16, ~0.5B). Block diffusion, block_size=16, target_layer_ids=[1,10,19,28,37]. Profile `medium-qwen36-moe-dflash.yml` retained as opt-in. **Empirical bench vs baseline 3.6**: single-user code +23% (131 vs 107 tok/s), single-user reasoning **+94%** (226 vs 116.5 tok/s), single-user code long +59% (170 tok/s); 5-user concurrent **-15%** (315 vs 369 tok/s aggregate). **Trade-offs**: requires `--attention-backend flash_attn` which **rejects fp8 KV cache** → max-model-len capped at 160K (vs baseline 262K), KV cache 93K tokens (vs baseline 322K), max concurrency 1.15× (vs baseline 4.69×). **Acceptance rate confirmed compatible with AWQ target**: 26-47% per-position, 4-7 tokens accepted per draft step. **The "0% acceptance with AWQ" claim previously in MEMORY.md was a hallucination** — only MTP (multi-token prediction, vLLM `--speculative-config method=mtp`) shows 0% with AWQ (tested on GLM-4.6-AWQ, see CLAUDE.md "Critical Configuration Notes" #4). DFlash drafter is a separate BF16 model with its own quant config via `vllm.model_executor.models.utils.get_draft_quant_config`, hence AWQ target compatibility. **Decision (2026-04-24)**: rollback to baseline — concurrent throughput + 262K context matter more for our Roo orchestrator + multi-student workload than single-user speedup. Profile retained at `myia_vllm/configs/docker/profiles/medium-qwen36-moe-dflash.yml` for benchmarks or future single-user-heavy use cases.
- **DEFERRED**: TurboQuant migration (PR #39931 targets Qwen3.5 hybrid support, still in review as of 2026-04-16)

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [Qwen3.6-35B-A3B-AWQ on HuggingFace](https://huggingface.co/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit)
- [Qwen3.6 Official Blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
- [Qwen3.5-35B-A3B-AWQ on HuggingFace](https://huggingface.co/cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit) (previous model)
- [GLM-4.7-Flash on HuggingFace](https://huggingface.co/zai-org/GLM-4.7-Flash) (legacy)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
