#!/usr/bin/env python3
"""
Quantization script for IFM/K2-Horizon-MoVA-36B-A4B -> W4A16 (compressed-tensors,
pack-quantized) for vLLM serving on 2x RTX 4090 (SM89, Marlin MoE kernels).

Eval candidate (2026-09-04, GO user). No W4A16 quant of this model exists
(only GGUF/FP8/MLX) — this is the home-made quant, iso-family with prod
(cyankiwi Qwen3.6-35B-A3B: compressed-tensors W4A16 asym GS32).

Weight map (verified from model.safetensors.index.json, 2026-09-04):
    model.layers.N.self_attn.{q,k,v,o,gate}_proj   -> QUANTIZE (std attention proj)
    model.layers.N.self_attn.v_proj                -> QUANTIZE
    model.layers.N.self_attn.v_router.{weight,bias}-> KEEP BF16 (MoVA value router,
                                                      novel, routes in fp32)
    model.layers.N.self_attn.v_experts.N.weight    -> KEEP BF16 (MoVA value experts,
                                                      novel dynamics — analog of the
                                                      GDN in_proj ignore in the prod
                                                      cyankiwi recipe)
    model.layers.N.mlp.experts.N.{gate,up,down}_proj -> QUANTIZE (bulk of 74.9 GB)
    model.layers.N.mlp.shared_experts.*            -> QUANTIZE
    model.layers.N.mlp.{gate_proj,up_proj,down_proj} -> QUANTIZE (dense MLP)
    model.layers.N.mlp.gate.{weight,bias}          -> KEEP BF16 (expert router)
    embed_tokens / lm_head / norms                 -> KEEP BF16 (vocab 250624:
                                                      ~2 GB each in BF16, standard)

Run environment (WSL Ubuntu, GPU 2 — CoursIA slot):
    CUDA_VISIBLE_DEVICES=2. Host RAM: need ~100 GB free inside WSL (verified
    100 GB available 2026-09-04). Model BF16 downloads into jesse's own cache
    (/home/jesse/.cache/huggingface — the prod cache /home/user/vllm/... is
    root-owned, do NOT write there). Started 2026-09-04 (detached nohup, log
    /home/jesse/k2_download.log).

    # venv exists (hub 1.30); at slot time add the heavy deps:
    /home/jesse/k2-quant-venv/bin/pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130
    /home/jesse/k2-quant-venv/bin/pip install "llmcompressor>=0.9" "transformers==5.15.*" accelerate datasets

Usage (inside WSL):
    CUDA_VISIBLE_DEVICES=2 HF_HOME=/home/jesse/.cache/huggingface \
        /home/jesse/k2-quant-venv/bin/python quantize_k2_horizon.py --check-only
    CUDA_VISIBLE_DEVICES=2 HF_HOME=/home/jesse/.cache/huggingface \
        /home/jesse/k2-quant-venv/bin/python quantize_k2_horizon.py --num-samples 256

Estimated: RTN/GPTQ oneshot on 1x 4090, 2-5 h at 256 samples (8B took 30-60 min).
Output: ~20 GB (vs 74.9 GB BF16).
"""

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

IGNORE = [
    "lm_head",
    "model.embed_tokens",
    "re:.*self_attn\\.v_router.*",       # MoVA value router
    "re:.*self_attn\\.v_experts.*",      # MoVA value experts
    "re:.*mlp\\.gate\\.weight$",         # expert router (NOT mlp.gate_proj)
    "re:.*mlp\\.gate\\.bias$",
]


def check_dependencies():
    missing = []
    for mod, pkg in [("llmcompressor", "llmcompressor>=0.9"), ("transformers", "transformers==5.15.*"),
                     ("torch", "torch"), ("datasets", "datasets"), ("accelerate", "accelerate")]:
        try:
            m = __import__(mod)
            logger.info(f"{mod}: {getattr(m, '__version__', '?')}")
        except ImportError:
            missing.append(pkg)
    import torch
    if not torch.cuda.is_available():
        logger.error("CUDA unavailable — quantization needs GPU 2 (CUDA_VISIBLE_DEVICES=2)")
        sys.exit(1)
    visible = torch.cuda.device_count()
    props = torch.cuda.get_device_properties(0)
    logger.info(f"CUDA: {visible} GPU visible, first = {props.name} ({props.total_memory/1e9:.1f} GB)")
    logger.info(f"  -> MUST be the single GPU 2 (24 GB). Abort if it shows 2+ GPUs.")
    if missing:
        logger.error(f"Missing packages: {', '.join(missing)}")
        logger.error("Install with: pip install " + " ".join(missing))
        sys.exit(1)


def quantize(model_id, output_dir, num_samples, max_seq_length):
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import GPTQModifier
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer

    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"

    logger.info(f"Loading tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    logger.info("Loading calibration dataset (open_platypus)...")
    ds = load_dataset("garage-bAInd/Open-Platypus", split="train")
    ds = ds.shuffle(seed=42).select(range(min(num_samples, len(ds))))

    def preprocess(example):
        return {"text": f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"}

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    logger.info(f"Calibration: {len(ds)} samples, seq <= {max_seq_length}")

    # W4A16 asym group_size 32 to match the prod quant family. If this llmcompressor
    # version rejects the explicit scheme dict, fall back to scheme="W4A16" (GS128
    # default) — log loudly so the delta vs prod is known.
    scheme = {
        "weights": {"num_bits": 4, "group_size": 32, "symmetric": False, "strategy": "group"},
        "activations": None,
    }
    try:
        recipe = GPTQModifier(scheme=scheme, targets="Linear", ignore=IGNORE, dampening_frac=0.01, block_size=128)
    except Exception as e:
        logger.warning(f"Explicit scheme dict rejected ({e}); falling back to scheme='W4A16' (GS128 sym default)")
        recipe = GPTQModifier(scheme="W4A16", targets="Linear", ignore=IGNORE, dampening_frac=0.01, block_size=128)

    logger.info("Loading model (74.9 GB BF16, CPU RAM + GPU 2 offload)...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True,
    )

    logger.info("Running oneshot quantization (2-5 h expected)...")
    oneshot(
        model=model,
        recipe=recipe,
        output_dir=output_dir,
        dataset=ds,
        max_seq_length=max_seq_length,
    )
    tokenizer.save_pretrained(output_dir)

    logger.info(f"Done. Quantized model at: {output_dir}")
    logger.info("Validation (at eval window):")
    logger.info(f"  docker run --gpus '\"device=2\"' -v {output_dir}:/m "
                "vllm/vllm-openai:nightly-e962733e08d10f7ca65dac4df99e116460b8b174 "
                "--model /m --max-model-len 8192 --gpu-memory-utilization 0.9 "
                "--trust-remote-code --reasoning-parser k2_horizon --tool-call-parser k2_horizon")


def main():
    p = argparse.ArgumentParser(description="Quantize K2-Horizon-MoVA-36B-A4B to W4A16")
    p.add_argument("--model-id", default="IFM/K2-Horizon-MoVA-36B-A4B")
    p.add_argument("--output-dir", default="/home/jesse/k2-quant-out")
    p.add_argument("--num-samples", type=int, default=256,
                   help="Calibration samples (256 default for the 4-8h slot; 512 = better, slower)")
    p.add_argument("--max-seq-length", type=int, default=4096)
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()

    logger.info("=" * 60)
    logger.info("K2-Horizon-MoVA-36B-A4B W4A16 quantization")
    logger.info("=" * 60)
    check_dependencies()
    if args.check_only:
        logger.info("--check-only: dependencies OK, exiting.")
        return
    quantize(args.model_id, args.output_dir, args.num_samples, args.max_seq_length)


if __name__ == "__main__":
    main()
