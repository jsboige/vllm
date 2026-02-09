# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **vLLM fork** with a custom `myia_vllm/` directory for self-hosting LLMs on **3x RTX 4090 GPUs** (72GB total VRAM). The project provides OpenAI-compatible API endpoints for LLMs, accessible via reverse proxy at `*.text-generation-webui.myia.io`.

**Current deployment**: GLM-4.7-Flash (31B MoE, AWQ 4-bit) on 2 GPUs with TP=2. GPU 2 available for other services.

**Previous deployment**: Qwen3-Coder-Next (80B MoE, PP=3) - archived due to pipeline parallelism bottleneck (5-6 tok/s).

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
# Build GLM-4.7-Flash custom image (first time only)
docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml build

# Start GLM-4.7-Flash service
docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml --env-file myia_vllm/.env up -d

# Monitor startup progress
docker logs -f myia_vllm-medium-glm

# Start legacy medium (32B) service
docker compose -f myia_vllm/configs/docker/profiles/medium.yml up -d
```

### Testing

```powershell
# Benchmark GLM-4.7-Flash (A/B benchmark tool, supports any backend name)
python myia_vllm/scripts/testing/benchmark_llamacpp_vs_vllm.py --backend vllm
python myia_vllm/scripts/testing/benchmark_llamacpp_vs_vllm.py --compare

# Legacy benchmark
python myia_vllm/scripts/testing/benchmark_coder_next.py --model glm-4.7-flash

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

GLM-4.7-Flash uses a custom Dockerfile (`Dockerfile.glm-flash`) extending `vllm/vllm-openai:nightly` with:
- `transformers >= 5.0` for `glm4_moe_lite` architecture support
- MLA (Multi-Latent Attention) architecture patch for efficient KV cache

Other services use the official `vllm/vllm-openai:latest` image directly.

### GPU Assignment

| Service | GPUs | Port | Model | Profile |
|---------|------|------|-------|---------|
| **medium-glm** | **0,1** | **5002** | **GLM-4.7-Flash-AWQ** | **medium-glm.yml** |
| micro | 2 | 5000 | Qwen3-1.7B | micro.yml |
| mini | 2 | 5001 | Qwen3-8B | mini.yml |
| medium | 0,1 | 5002 | Qwen3-32B-AWQ | medium.yml |
| medium-vl | 0,1 | 5003 | Qwen3-VL-32B | medium-vl.yml |
| medium-coder | 0,1,2 | 5002 | Qwen3-Coder-Next | medium-coder.yml (archived) |

GPUs 0,1 are on faster PCIe bus. GPU 2 is on slower bus (available for small models when GLM uses only 0,1).

### Environment Variables

Configuration via `myia_vllm/.env` (not tracked) based on `.env.example`:
- `HUGGING_FACE_HUB_TOKEN` - Required for model downloads
- `VLLM_API_KEY_*` - API keys per service
- `VLLM_MODEL_GLM` - GLM-4.7-Flash model (default: `QuantTrio/GLM-4.7-Flash-AWQ`)
- `VLLM_PORT_GLM` - GLM service port (default: 5002)

## Critical Configuration Notes

1. **Do NOT add `--enable-chunked-prefill` or `--num-scheduler-steps`** - These flags force V0 engine fallback. V1 engine (default on nightly) handles chunked prefill automatically.

2. **CUDA graphs (PIECEWISE mode) work well at 0.92 gpu-memory-utilization** - Piecewise CUDA graphs have minimal overhead. Max viable is 0.92 (0.95 OOM: only 22.26/23.99 GiB free at startup). KV cache: ~222K tokens at 0.92. **Do NOT use `--enforce-eager`** (tested: 3-4x slower on all metrics - 12 tok/s vs 45 tok/s decode).

3. **MLA backends on RTX 4090 don't support FP8 KV cache** - Use `--kv-cache-dtype auto` (not fp8). TRITON_MLA is the only working MLA backend on Ada Lovelace (SM89).

4. **MTP speculative decoding doesn't work with AWQ 4-bit** - 0% acceptance rate at 4-bit precision. Only viable with FP8 or FP16 models.

5. **Use `glm47` tool parser for GLM-4.7-Flash** - NOT hermes, NOT granite. Reasoning parser: `glm45`.

6. **Use `hermes` tool parser for Qwen models** - Official Qwen recommendation for function calling.

7. **Credentials in `.env` were compromised** - Regenerate HuggingFace token and API keys before production deployment.

## GLM-4.7-Flash Deployment (Current)

### Model Specifications
- **Architecture**: 31B MoE with 3B active parameters per forward pass (64 experts, top-4)
- **Attention**: MLA (Multi-Latent Attention) - very compact KV cache (~54 KB/token)
- **VRAM**: ~8.75 GiB per GPU with AWQ 4-bit + TP=2
- **KV cache**: ~222K tokens at 0.92 GPU util with CUDA graphs
- **Context window**: 200K native, configured at 128K
- **Quantization**: AWQ 4-bit with Marlin kernels (`VLLM_MARLIN_USE_ATOMIC_ADD=1`)
- **Model source**: [QuantTrio/GLM-4.7-Flash-AWQ](https://huggingface.co/QuantTrio/GLM-4.7-Flash-AWQ)
- **vLLM requirement**: nightly build (glm4_moe_lite architecture + transformers >= 5.0)
- **Engine**: V1 (async scheduling, piecewise CUDA graphs, automatic chunked prefill)

### Deployment Steps

**Step 1: Build custom image (first time)**
```powershell
docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml build
```

**Step 2: Deploy**
```powershell
docker compose -f myia_vllm/configs/docker/profiles/medium-glm.yml --env-file myia_vllm/.env up -d
docker logs -f myia_vllm-medium-glm
```

**Step 3: Warmup (after container is healthy, ~90s)**
```powershell
python myia_vllm/scripts/testing/warmup_glm.py --wait
```
This pre-captures CUDA graphs for common prompt sizes (50 tok to 50K tok) and eliminates first-request TTFT spikes.

**Step 4: Benchmark**
```powershell
python myia_vllm/scripts/testing/benchmark_coder_next.py --model glm-4.7-flash --api-key $VLLM_API_KEY_MEDIUM
```

### Key vLLM Flags for GLM-4.7-Flash
```yaml
--model QuantTrio/GLM-4.7-Flash-AWQ
--served-model-name glm-4.7-flash
--tensor-parallel-size 2       # TP=2 on GPUs 0,1
--enable-expert-parallel       # EP for MoE: each GPU holds 32/64 experts
--gpu-memory-utilization 0.92  # Max viable (0.95 OOM). KV cache: 222K tokens
--max-model-len 131072         # 128K context (MLA: ~54 KB/token)
--max-num-batched-tokens 32768 # Higher batch budget for MoE throughput
--max-num-seqs 64              # Prevent preemption cascades
--kv-cache-dtype auto          # FP8 NOT supported with MLA on RTX 4090
--dtype half                   # FP16 (optimal for Marlin on SM89)
--tool-call-parser glm47       # GLM-4.7 specific tool calling parser
--reasoning-parser glm45       # GLM-4.5 style reasoning/thinking
--distributed-executor-backend mp  # Required for WSL
--disable-log-requests         # Production: reduce I/O overhead
# NO --enforce-eager           # CUDA graphs + torch.compile enabled (V1 engine)
# NO --enable-chunked-prefill  # V1 does this by default, explicit flag forces V0
# NO --swap-space              # V1 uses recompute, not swap
```

### Environment Variables (Performance)
```yaml
VLLM_MARLIN_USE_ATOMIC_ADD=1   # Optimized kernel accumulation for small batches
VLLM_USE_DEEP_GEMM=0           # Not needed for AWQ (FP8 MoE only)
OMP_NUM_THREADS=4              # Better CPU parallelism for scheduling
VLLM_ENABLE_INDUCTOR_MAX_AUTOTUNE=1            # +30% concurrent throughput
VLLM_ENABLE_INDUCTOR_COORDINATE_DESCENT_TUNING=1  # More kernel search variants
VLLM_FLOAT32_MATMUL_PRECISION=medium           # TF32 for residual FP32 ops
```

### Performance (Benchmark Results)

**Optimized config** (V1 engine, CUDA graphs, EP, torch.compile, Inductor autotune, persistent cache):
| Metric | Single User | Notes |
|--------|-------------|-------|
| Decode speed | **55 tok/s** | Short prompts (with Inductor autotune) |
| Concurrent 5 users | **216 tok/s** | Aggregate throughput |
| 5K prompt TTFT | 0.25s | Warm, cached |
| 30K prompt (cold) | 0.49s TTFT | After warmup (CUDA graphs pre-captured) |
| 30K prompt (cached) | 0.54s TTFT | **Prefix cache hit** |
| Tool call | 1.0s | Short response |
| Context | 128K | 222K tokens KV capacity |

**TTFT optimization** (critical for Roo/agent workloads with large system prompts):
- Persistent torch.compile cache (`vllm-compile-cache` Docker volume) eliminates recompilation on restart
- First request after restart: **1.7s** (vs ~10-14s without persistent cache)
- Warmup script pre-captures CUDA graphs for 50 tok to 50K tok prompt sizes
- Prefix caching reduces TTFT 10x for repeated system prompts (14s -> 1.4s)

**Previous unoptimized** (enforce-eager, V0 fallback, no EP):
| Metric | Single User |
|--------|-------------|
| Tokens/sec | 12-13 tok/s |
| Context | 65K |

### Comparison with Previous Deployments
| | GLM-4.7-Flash (autotune) | GLM-4.7-Flash (initial) | Qwen3-Coder-Next | Qwen3-32B-AWQ |
|---|---|---|---|---|
| Single user tok/s | **55** | 13.8-15.1 | 5-6 | ~15 |
| Concurrent tok/s | **216** | 70.2 | 21.6 | ~40 |
| GPUs used | 2 | 2 | 3 | 2 |
| Context | **128K** | 65K | 65K | 32K |
| SWE-bench | 59.2% | 59.2% | 70.6% | N/A |

### Claude Code Integration

Students connect via `ANTHROPIC_BASE_URL`:
```bash
export ANTHROPIC_BASE_URL="https://api.medium.text-generation-webui.myia.io"
claude --model glm-4.7-flash
```

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

## Current State (2026-02-09)

- **vLLM GLM-4.7-Flash running** on port 5002 (GPUs 0,1) with full Inductor autotune config
- **GPU 2 free** for a complementary small model (micro/mini profiles drafted)
- **llama.cpp benchmark complete** - llama.cpp is 2x faster single-user but vLLM wins for concurrent (216 vs 121 tok/s). Config in `myia_vllm/configs/llamacpp/`
- **Optimization sweep complete** - Inductor autotune is the best gain found (+30% concurrent). block-size 32 and shared-experts-stream were tested and rejected
- **Next**: monitoring under Roo agent load, then deploying a complementary model on GPU 2

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [GLM-4.7-Flash on HuggingFace](https://huggingface.co/zai-org/GLM-4.7-Flash)
- [GLM-4.X vLLM Recipes](https://docs.vllm.ai/projects/recipes/en/latest/GLM/GLM.html)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
- [Unsloth Claude Code Integration](https://unsloth.ai/docs/basics/claude-codex)
