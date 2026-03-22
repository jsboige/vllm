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

**Current deployment**: Qwen3.5-35B-A3B (35B MoE, 3B active, AWQ 4-bit, vision+thinking) on GPUs 0,1 with TP=2+EP. GPU 2: ZwZ-8B (vision, 128K ctx, solo mode) + Kokoro TTS.

**Previous deployment**: GLM-4.7-Flash (31B MoE, AWQ 4-bit) - replaced by Qwen3.5 (+80% decode, +37% concurrent, +vision, +10pts SWE-bench).

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
# Start Qwen3.5-35B-A3B MoE (primary model, GPUs 0,1)
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen35-moe.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-qwen35-moe

# Start ZwZ-8B (vision, GPU 2 solo mode)
docker compose -f myia_vllm/configs/docker/profiles/mini-zwz.yml --env-file myia_vllm/.env up -d

# Legacy: GLM-4.7-Flash (requires custom image build first)
# docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml build
# docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml --env-file myia_vllm/.env up -d
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
python myia_vllm/scripts/python/test_tool_calling.py
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
| **medium-qwen35-moe** | **0,1** | **5002** | **Qwen3.5-35B-A3B-AWQ** | **medium-qwen35-moe.yml** |
| **mini-zwz** | **2** | **5001** | **ZwZ-8B-AWQ-4bit** | **mini-zwz.yml** (gpu-util 0.88, 128K ctx) |
| kokoro-tts | 2 | 8880 | Kokoro TTS (67 voices) | myia-open-webui compose |
| medium-glm | 0,1 | 5002 | GLM-4.7-Flash-AWQ | medium-glm.yml (legacy) |
| medium-qwen35-dense | 0,1 | 5002 | Qwen3.5-27B-AWQ | medium-qwen35-dense.yml (rejected: too slow) |
| mini-solo | 2 | 5001 | Qwen3-VL-8B-Thinking-AWQ | mini-solo.yml (fallback) |

GPUs 0,1 are on faster PCIe bus. GPU 2 runs ZwZ-8B solo (gpu-util 0.88, 128K ctx) + Kokoro TTS (0.5 GB).

### Environment Variables

Configuration via `myia_vllm/.env` (not tracked) based on `.env.example`:
- `HUGGING_FACE_HUB_TOKEN` - Required for model downloads
- `VLLM_API_KEY_*` - API keys per service
- `VLLM_MODEL_QWEN35_MOE` - Qwen3.5 MoE model (default: `cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit`)
- `VLLM_PORT_GLM` - Medium model port (default: 5002, shared by GLM/Qwen3.5)
- `VLLM_MODEL_ZWZ` - ZwZ-8B model path (default: `./models/ZwZ-8B-AWQ-4bit`)

## ZwZ-8B Deployment (Default Vision Model)

### Model Overview

**ZwZ-8B** ([inclusionAI/ZwZ-8B](https://huggingface.co/inclusionAI/ZwZ-8B)) is the **default vision model** on GPU 2 (port 5001) since 2026-02-16. A Qwen3-VL-8B-Instruct finetune specialized for fine-grained visual perception. Key features:
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

4. **MTP speculative decoding doesn't work with AWQ 4-bit** - 0% acceptance rate at 4-bit precision. Only viable with FP8 or FP16 models.

5. **Use `qwen3_coder` tool parser for Qwen3.5** and `qwen3` reasoning parser. Legacy: `glm47`/`glm45` for GLM-4.7-Flash.

6. **Use `--dtype auto` for Qwen3.5 models** - `--dtype half` causes dtype mismatch with BF16 vision encoder. `auto` resolves correctly.

7. **Credentials in `.env` were compromised** - Regenerate HuggingFace token and API keys before production deployment.

## Qwen3.5-35B-A3B Deployment (Current)

### Model Specifications
- **Architecture**: 35B MoE with 3B active parameters per token (256 experts, 9 active: 8 routed + 1 shared)
- **Attention**: Hybrid GatedDeltaNet (linear, fixed state) + Gated Attention (standard KV cache)
- **Vision**: Images, videos, documents (vision encoder preserved in BF16)
- **Thinking**: `<think>...</think>` modulation via `chat_template_kwargs`
- **VRAM**: ~12 GiB per GPU with AWQ 4-bit + TP=2
- **KV cache**: ~335K tokens at 0.85 GPU util with FP8 KV cache (was 438K at 0.92, reduced for Marlin MoE stability)
- **Context window**: 262K native (YaRN extensible to 1M), configured at 262K (full native)
- **Quantization**: AWQ 4-bit (compressed-tensors format) with Marlin MoE kernels
- **Model source**: [cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit](https://huggingface.co/cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit)
- **vLLM class**: `Qwen3_5MoeForConditionalGeneration`
- **Engine**: V1 (async scheduling, piecewise CUDA graphs, automatic chunked prefill)
- **No custom Dockerfile needed** — uses official `vllm/vllm-openai:nightly` (pinned to Feb 23 commit)

### Deployment

```powershell
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen35-moe.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-qwen35-moe
```

### Key vLLM Flags
```yaml
--model cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit
--served-model-name qwen3.5-35b-a3b
--tensor-parallel-size 2
--enable-expert-parallel          # EP=2: 128/256 experts per GPU
--gpu-memory-utilization 0.85      # 0.92/0.88 OOM: Marlin MoE needs 852-994 MiB variable temp allocs
--max-model-len 262144            # Full native 262K context
--kv-cache-dtype fp8              # FP8 KV: 373K tokens (2x vs auto)
--dtype auto                      # MUST be auto (not half) for vision encoder BF16 compat
--max-num-batched-tokens 32768
--max-num-seqs 64
--enable-prefix-caching
--tool-call-parser qwen3_coder    # Qwen3.5 function calling
--reasoning-parser qwen3          # <think>...</think> extraction
--distributed-executor-backend mp
--limit-mm-per-prompt '{"image":4,"video":0}'
--mm-processor-kwargs '{"max_pixels":774000}'
--skip-mm-profiling               # Required: avoids dtype mismatch during profiling
```

### Environment Variables
```yaml
VLLM_MARLIN_USE_ATOMIC_ADD=1      # Optimized Marlin kernel accumulation
VLLM_USE_DEEP_GEMM=0              # Not needed for AWQ
OMP_NUM_THREADS=4                 # CPU parallelism for scheduling
VLLM_USE_FLASHINFER_MOE_FP16=1   # CRITICAL for MoE performance
```

### Thinking Modulation
To disable thinking per-request (clean, direct responses):
```json
{
  "model": "qwen3.5-35b-a3b",
  "messages": [...],
  "chat_template_kwargs": {"enable_thinking": false}
}
```
**IMPORTANT**: `chat_template_kwargs` must be a **top-level** field in the request body, NOT inside `extra_body`.

**Reasoning field**: With thinking enabled, the parser separates reasoning into the `reasoning` field (NOT `reasoning_content`, which is always `null`). Both streaming and non-streaming work correctly on pinned nightly (dev388, Feb 23). The `<think>` tag is injected by the chat template in the prompt; only `</think>` appears in generated output. OWUI needs adaptation to read `delta.reasoning` from SSE chunks (currently only parses `<think>` tags in `content`).

### Performance (Benchmark 2026-02-25, FP8 KV, 262K context)
**Note**: Benchmarked at 0.92 gpu-util. Production now runs at 0.85 (Marlin MoE stability fix). Speed impact is negligible since the bottleneck is compute, not memory.

| Metric | Qwen3.5-35B-A3B | GLM-4.7-Flash (previous) | Improvement |
|--------|:---:|:---:|:---:|
| Decode speed | **86.2 tok/s** | 56.0 tok/s | **+54%** |
| Concurrent 5 users | **269.6 tok/s** | 197.2 tok/s | **+37%** |
| 30K cold TTFT | 0.95s | 0.47s | -102% (MLA wins) |
| 30K cached TTFT | 0.89s | 0.40s | -123% |
| Tool calling | **893ms** | 1440ms | **-38%** |
| Vision | **Yes** | No | New capability |
| KV cache tokens | **335K** (0.85) | 222K | **+51%** |
| Max context | **262K** | 128K | **+105%** |
| SWE-bench | **69.2%** | 59.2% | **+10 pts** |

Note: With auto KV (non-FP8), decode was faster (96-109 tok/s) but KV capacity was only 206K. FP8 KV trades ~15% decode speed for 2x KV capacity — the right tradeoff for multi-agent workloads.

### Quality Benchmarks (2026-02-26, thinking disabled, custom benchmark script)

| Benchmark | Qwen3.5-35B-A3B | Questions | Notes |
|-----------|:---:|:---:|:---:|
| **GSM8K** (math CoT 0-shot) | **88.0%** | 1319 | v2 answer extraction |
| **IFEval** (instruction following) | **88.5%** strict | 541 | Simplified checker |
| **MME** (vision Yes/No) | **1294.7** (91.0%) | 2374 | Perception 926.8, Cognition 367.9 |
| **MMStar** (vision ABCD) | **53.2%** | 1500 | Hard multi-choice, 0 errors |

### Vision Quality (vs ZwZ-8B, MME benchmark partial)

| Category | Qwen3.5 MoE | ZwZ-8B | Delta |
|----------|:---:|:---:|:---:|
| OCR | **98%** | 82% | **+16 pts** |
| artwork | **90%** | 83% | +7 pts |
| position | **88%** | 80% | +8 pts |
| celebrity | 93% | 91% | +2 pts |
| commonsense | 88% | 84% | +4 pts |
| code_reasoning | 95% | 95% | = |
| color | 98% | 97% | = |
| count | 90% | 90% | = |
| numerical_calc | 90% | 90% | = |

**Conclusion**: Qwen3.5 is significantly better than ZwZ-8B on perception tasks (OCR +16pts, artwork +7pts), while cognitive tasks are tied. ZwZ-8B is no longer needed as vision fallback — Qwen3.5 handles everything better.

### Speed Performance (vs ZwZ-8B, manual tests)

| Test | Qwen3.5 MoE (GPUs 0,1) | ZwZ-8B (GPU 2) | Quality |
|------|:---:|:---:|:---:|
| OCR | 43.8 tok/s | ~90 tok/s | Qwen3.5 better |
| Diagram understanding | 98.9 tok/s | 118.5 tok/s | Identical |
| Math from image | 91.0 tok/s | 90.9 tok/s | Identical |

### Comparison with All Previous Deployments

| | **Qwen3.5-35B-A3B** | GLM-4.7-Flash | Qwen3-Coder-Next | Qwen3-32B-AWQ |
|---|---|---|---|---|
| Single user tok/s | **86** | 55 | 5-6 | ~15 |
| Concurrent tok/s | **270** | 216 | 21.6 | ~40 |
| GPUs used | 2 | 2 | 3 | 2 |
| Context | **262K** | 128K | 65K | 32K |
| KV cache | **335K** | 222K | ~65K | ~32K |
| SWE-bench | **69.2%** | 59.2% | 70.6% | N/A |
| Vision | **Yes** | No | No | No |

### Claude Code Integration

Students connect via `ANTHROPIC_BASE_URL`:
```bash
export ANTHROPIC_BASE_URL="https://api.medium.text-generation-webui.myia.io"
claude --model qwen3.5-35b-a3b
```

## GLM-4.7-Flash (Archived)

Replaced by Qwen3.5-35B-A3B on 2026-02-25. Profile: `medium-glm.yml`. Requires custom Dockerfile for `transformers >= 5.0`. Key specs: 31B MoE, 3B active, MLA attention (~54 KB/token KV), 56 tok/s decode, 197 tok/s concurrent, SWE-bench 59.2%. No vision support. Tool parser: `glm47`, reasoning: `glm45`.

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

## Current State (2026-03-21)

- **Qwen3.5-35B-A3B MoE running** on port 5002 (GPUs 0,1) — **production since 2026-02-25**
  - ✅ FlashInfer MoE, Expert Parallelism, CUDA graphs, prefix caching
  - ✅ Vision (images, documents) + Thinking modulation
  - ✅ `--override-generation-config` with defaults (temp 0.6, top_p 0.95, top_k 20, min_p 0.0, rp 1.0)
  - ✅ Middleware DISABLED (removed 2026-03-13, was temporary for sampling investigation)
  - ✅ Watchdog sidecar: dual-ping (host.docker.internal + Docker DNS), auto-restart after 3 fails
  - FP8 KV cache: **335K tokens** (0.85 gpu-util, reduced 0.92→0.88→0.85 for Marlin MoE stability)
  - Performance: **117.8 tok/s decode, 311.2 tok/s concurrent, 910ms tool call** (Mar 05 nightly)
- **GPU 2**: ZwZ-8B on port 5001 — solo mode (gpu-util 0.88, 128K ctx, CUDA graphs, keepalive sidecar)
- **Orpheus TTS moved to po-2023** (2026-03-18): `https://orpheus-tts.myia.io/v1/audio/speech`
- **OWUI sampling calibration** (2026-03-21): 8 model wrappers calibrated for AWQ Q4 (Reddit + HF + local benchmarks). Key Q4 adjustments: temp 1.0→0.7, pp capped at 1.5 (not 2.0), rp 1.05-1.1 anti-bleed, min_p 0.01-0.05. Bug fixed: `-fast` had missing `enable_thinking: false`.
- **SK Agent MCP server** uses Qwen3.5-35B-A3B (port 5002, updated 2026-02-25) with sampling params from config
- **vLLM version**: nightly `d106bf39` (Mar 05, `nightly-d106bf39f56cdc59d08a84094c0de41a0be9ad0f`)
  - Includes PR #28053 (idle crash fix), PR #34779 (reasoning parser fix)
  - Rollback reference: dev388 (Feb 23)
- **API keys rotated** (2026-03-13): all 3 keys regenerated after accidental git exposure, hardcoded keys removed from 13 files
- **Sampling optimization** (2026-03-08): presence_penalty 1.5 reduces repetition 2-3x with no speed impact
- **OWUI routing for Roo: ABANDONED** (2026-03-10): 83+ MCP tools overwhelm OWUI pipe. OWUI wrappers exist for direct OWUI users only.
- **Models rejected**: Qwen3.5-27B Dense (2026-02-25), GPTQ-Int4 (2026-03-03), BNB NF4 distill (2026-03-13)

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [Qwen3.5-35B-A3B-AWQ on HuggingFace](https://huggingface.co/cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit)
- [Qwen3.5 Official Blog](https://qwenlm.github.io/blog/qwen3.5/)
- [GLM-4.7-Flash on HuggingFace](https://huggingface.co/zai-org/GLM-4.7-Flash) (legacy)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
