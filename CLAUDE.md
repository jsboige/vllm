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
# Benchmark GLM-4.7-Flash
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

1. **Do NOT increase `gpu-memory-utilization` above 0.9** - CUDA graphs allocate hidden memory. Reduce to 0.8-0.85 if OOM occurs.

2. **MLA backends on RTX 4090 don't support FP8 KV cache** - Use `--kv-cache-dtype auto` (not fp8). TRITON_MLA is the only working backend on Ada Lovelace.

3. **Use `glm47` tool parser for GLM-4.7-Flash** - NOT hermes, NOT granite. Reasoning parser: `glm45`.

4. **Use `hermes` tool parser for Qwen models** - Official Qwen recommendation for function calling.

5. **Credentials in `.env` were compromised** - Regenerate HuggingFace token and API keys before production deployment.

## GLM-4.7-Flash Deployment (Current)

### Model Specifications
- **Architecture**: 31B MoE with 3B active parameters per forward pass
- **Attention**: MLA (Multi-Latent Attention) - very compact KV cache (~54 KB/token)
- **VRAM**: ~8.75 GiB per GPU with AWQ 4-bit + TP=2
- **KV cache**: 11.38 GiB available per GPU → 225K token capacity
- **Context window**: 200K native, configured at 65K (max concurrency: 3.44x)
- **Quantization**: AWQ 4-bit with Marlin kernels (auto-detected)
- **Model source**: [QuantTrio/GLM-4.7-Flash-AWQ](https://huggingface.co/QuantTrio/GLM-4.7-Flash-AWQ)
- **vLLM requirement**: nightly build (glm4_moe_lite architecture + transformers >= 5.0)

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

**Step 3: Benchmark**
```powershell
python myia_vllm/scripts/testing/benchmark_coder_next.py --model glm-4.7-flash --api-key $VLLM_API_KEY_MEDIUM
```

### Key vLLM Flags for GLM-4.7-Flash
```yaml
--model QuantTrio/GLM-4.7-Flash-AWQ
--served-model-name glm-4.7-flash
--tensor-parallel-size 2       # TP=2 on GPUs 0,1
--gpu-memory-utilization 0.90  # ~12GB left for KV cache per GPU
--max-model-len 65536          # 64K context (can try higher, MLA is efficient)
--kv-cache-dtype auto          # FP8 NOT supported with MLA on RTX 4090
--tool-call-parser glm47       # GLM-4.7 specific tool calling parser
--reasoning-parser glm45       # GLM-4.5 style reasoning/thinking
--enforce-eager                # Stable operation on RTX 4090
--distributed-executor-backend mp  # Required for WSL
```

### Performance (Benchmark Results)
| Metric | Single User | 5 Concurrent Users |
|--------|-------------|-------------------|
| Tokens/sec | 13.8-15.1 tok/s | 70.2 tok/s aggregate |
| Tool calling | Supported | Supported |
| Multi-tool agentic | Supported | Supported |
| Tool result cycle | Supported | Supported |

### Comparison with Previous Deployments
| | GLM-4.7-Flash | Qwen3-Coder-Next | Qwen3-32B-AWQ |
|---|---|---|---|
| Single user tok/s | **13.8-15.1** | 5-6 | ~15 |
| Concurrent tok/s | **70.2** | 21.6 | ~40 |
| GPUs used | 2 | 3 | 2 |
| Context | 65K | 65K | 32K |
| SWE-bench | 59.2% | 70.6% | N/A |

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

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [GLM-4.7-Flash on HuggingFace](https://huggingface.co/zai-org/GLM-4.7-Flash)
- [GLM-4.X vLLM Recipes](https://docs.vllm.ai/projects/recipes/en/latest/GLM/GLM.html)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
- [Unsloth Claude Code Integration](https://unsloth.ai/docs/basics/claude-codex)
