# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **vLLM fork** with a custom `myia_vllm/` directory for self-hosting LLMs on **3x RTX 4090 GPUs** (72GB total VRAM). The project provides OpenAI-compatible API endpoints for Qwen models, accessible via reverse proxy at `*.text-generation-webui.myia.io`.

**Current deployment**: Qwen3-32B-AWQ on 2 GPUs with tensor parallelism.

**Target deployment**: Qwen3-Coder-Next (80B MoE, 3B active parameters) with Unsloth 4-bit quantization (~46GB VRAM) for agentic use with Claude Code.

## Key Directories

```
myia_vllm/                    # PRIMARY - all customizations live here
├── configs/docker/profiles/  # Docker-compose deployment profiles
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
# Deploy medium (32B) service with monitoring
.\myia_vllm\scripts\deploy\deploy_medium_monitored.ps1

# Start with docker-compose profile
docker compose -f myia_vllm/configs/docker/profiles/medium.yml up -d

# Monitor container health
.\myia_vllm\scripts\monitoring\monitor_medium.ps1
```

### Testing

```powershell
# Run all tests
.\myia_vllm\run_all_tests.ps1

# Quick API test
python myia_vllm/scripts/python/test_tool_calling.py

# Benchmark suite
python myia_vllm/qwen3_benchmark/core/benchmark_runner.py
```

### Grid Search Optimization

```powershell
# Run configuration optimization
.\myia_vllm\grid_search_optimization.ps1
```

## Architecture

### Docker Deployment Pattern

Uses official vLLM image (`vllm/vllm-openai:latest`) with parameters passed via docker-compose command. No custom Dockerfile needed.

Key vLLM flags for Qwen models:
- `--quantization awq_marlin` - AWQ with Marlin kernels for Ampere+
- `--kv-cache-dtype fp8` - FP8 KV cache for memory efficiency
- `--tensor-parallel-size 2` - Multi-GPU tensor parallelism
- `--tool-call-parser hermes` - Recommended for Qwen function calling
- `--reasoning-parser qwen3` - Native Qwen3 reasoning parser
- `--rope_scaling '{"rope_type":"yarn","factor":4.0,...}'` - Extended context (only if needed >32K)

### GPU Assignment

| Service | GPUs | Port | Model | Profile |
|---------|------|------|-------|---------|
| micro | 2 | 5000 | Qwen3-1.7B | micro.yml |
| mini | 2 | 5001 | Qwen3-8B | mini.yml |
| medium | 0,1 | 5002 | Qwen3-32B-AWQ | medium.yml |
| medium-vl | 0,1 | 5003 | Qwen3-VL-32B | medium-vl.yml |
| **medium-coder** | **0,1,2** | **5002** | **Qwen3-Coder-Next-W4A16** | **medium-coder.yml** |

GPUs 0,1 are on faster PCIe bus. GPU 2 is on slower bus (uses all 3 for Coder-Next).

### Environment Variables

Configuration via `myia_vllm/.env` (not tracked) based on `.env.example`:
- `HUGGING_FACE_HUB_TOKEN` - Required for model downloads
- `VLLM_API_KEY_*` - API keys per service
- `CUDA_VISIBLE_DEVICES_*` - GPU assignment per service
- `GPU_MEMORY_UTILIZATION_*` - Memory usage (default 0.85, reduce if OOM)

## Critical Configuration Notes

1. **Do NOT increase `gpu-memory-utilization` above 0.9** - CUDA graphs allocate hidden memory. Reduce to 0.8-0.85 if OOM occurs.

2. **RoPE scaling degrades short-context performance** - Only enable for contexts >32K tokens. Use factor 2.0 for 65K, not 4.0.

3. **Use `hermes` tool parser, not `granite`** - Official Qwen recommendation for function calling.

4. **Credentials in `.env` were compromised** - Regenerate HuggingFace token and API keys before production deployment.

## Qwen3-Coder-Next Migration Strategy

### Model Specifications
- **Architecture**: 80B MoE with 3B active parameters per forward pass
- **VRAM requirement**: ~46GB at W4A16 quantization
- **Context window**: 262K native, target 128K (min 64K) for 72GB VRAM
- **Quantization**: W4A16 via LLM Compressor (no pre-quantified model on HuggingFace)
- **vLLM requirement**: >= v0.15.0 (official Qwen3-Coder-Next support)

### Deployment Steps

**Step 1: Quantify the model (one-time, 2-4 hours)**
```powershell
pip install llmcompressor>=0.9.0
python myia_vllm/scripts/quantization/quantize_qwen3_coder_next.py
```

**Step 2: Deploy with Docker**
```powershell
# Validate configuration
.\myia_vllm\scripts\testing\test_coder_next_config.ps1 -SkipStart

# Start service
docker compose -f myia_vllm/configs/docker/profiles/medium-coder.yml up -d

# Run benchmarks
python myia_vllm/scripts/testing/benchmark_coder_next.py
```

### Context Window Strategy (adjust dynamically)

| Context | Memory | Action |
|---------|--------|--------|
| 128K | ~66-76GB | Target with `--kv-cache-dtype fp8` |
| 96K | ~69GB | Fallback if FP8 KV bug (#26646) persists |
| 64K | ~61GB | Minimum acceptable for agentic use |

Start at 128K + FP8 KV, reduce progressively if OOM until stable.

### Claude Code Integration

Students connect via `ANTHROPIC_BASE_URL`:
```bash
export ANTHROPIC_BASE_URL="https://api.medium.text-generation-webui.myia.io"
claude --model qwen3-coder-next
```

### Key vLLM Flags for Coder-Next
```yaml
--tensor-parallel-size 3       # Distribute across all 3 GPUs
--enable-expert-parallel       # EP for MoE expert distribution
--gpu-memory-utilization 0.88  # Leave headroom for KV cache
--tool-call-parser qwen3_coder # Native parser for Coder-Next
--kv-cache-dtype fp8           # Memory-efficient KV cache (if supported)
```

### Fallback: llama.cpp server

If vLLM has issues with Qwen3-Coder-Next, create a **separate repository** for llama.cpp deployment (this repo stays vLLM-focused):
```bash
llama-server --model unsloth/Qwen3-Coder-Next-GGUF/Q4_K_XL.gguf \
  --tensor-split 0.4,0.4,0.2 --ctx-size 262144 --jinja
```

## Project History & Context

This repository has been maintained primarily by Roo (another AI agent) through 20+ documented missions. Key milestones:
- Missions 1-15: Initial setup, Qwen3 integration, optimization
- Missions 16-17: Vision model support (Qwen3-VL-32B)
- Missions 18-21: FP8 investigations, structure consolidation
- Mission 22+: Migration to Qwen3-Coder-Next for agentic use

Legacy `myia-vllm/` directory has been archived to `myia_vllm/archives/legacy_myia-vllm_*/`.

## Related Resources

- [vLLM Documentation](https://docs.vllm.ai)
- [Unsloth vLLM Guide](https://unsloth.ai/docs/basics/inference-and-deployment/vllm-guide)
- [Unsloth Claude Code Integration](https://unsloth.ai/docs/basics/claude-codex)
- [Qwen3-Coder-Next on HuggingFace](https://huggingface.co/models?other=base_model:quantized:Qwen/Qwen3-Coder-Next)
