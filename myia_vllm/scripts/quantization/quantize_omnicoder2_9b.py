#!/usr/bin/env python3
"""
Quantization script for OmniCoder-2-9B (Qwen3.5-9B VLM finetune).

Two methods available:
  1. AutoRound (RECOMMENDED) — Intel's accuracy-first quantization
     - Best quality for Qwen3.5 architecture (benchmarked by kaitchup)
     - Vision tower automatically kept in 16-bit
     - Supports torch.compile acceleration
     - Output: compressed-tensors format, vLLM-compatible

  2. LLM Compressor (FALLBACK) — vLLM project's own tool
     - GPTQ W4A16 with manual vision layer exclusion
     - Well-tested but lower accuracy than AutoRound on Qwen3.5

Requirements (method 1 - AutoRound):
    pip install auto-round transformers>=4.48.0 accelerate

Requirements (method 2 - LLM Compressor):
    pip install llmcompressor>=0.9.0 transformers>=4.48.0 accelerate datasets

Usage:
    # AutoRound (recommended)
    python quantize_omnicoder2_9b.py --method autoround

    # LLM Compressor (fallback)
    python quantize_omnicoder2_9b.py --method llmcompressor

    # Just check dependencies
    python quantize_omnicoder2_9b.py --check-only

Output: ./models/OmniCoder-2-9B-AWQ-4bit/
Estimated time: 30-60 minutes on RTX 4090
"""

import argparse
import logging
import os
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

MODEL_ID = "Tesslate/OmniCoder-2-9B"
DEFAULT_OUTPUT = "./models/OmniCoder-2-9B-AWQ-4bit"


def check_dependencies(method: str):
    """Verify required packages are installed."""
    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                logger.info(f"  GPU {i}: {props.name} ({props.total_memory / 1e9:.1f} GB)")
        else:
            logger.warning("CUDA not available!")
    except ImportError:
        logger.error("PyTorch not found")
        sys.exit(1)

    try:
        import transformers
        logger.info(f"transformers version: {transformers.__version__}")
    except ImportError:
        logger.error("transformers not found - pip install transformers>=4.48.0")
        sys.exit(1)

    if method == "autoround":
        try:
            import auto_round
            logger.info(f"auto-round version: {auto_round.__version__}")
        except ImportError:
            logger.error("auto-round not found - pip install auto-round")
            sys.exit(1)
    elif method == "llmcompressor":
        try:
            import llmcompressor
            logger.info(f"llmcompressor version: {llmcompressor.__version__}")
        except ImportError:
            logger.error("llmcompressor not found - pip install llmcompressor>=0.9.0")
            sys.exit(1)


def quantize_autoround(model_id: str, output_dir: str):
    """
    Quantize using AutoRound CLI (recommended method for Qwen3.5).

    AutoRound automatically:
    - Keeps vision tower in 16-bit
    - Keeps lm_head, normalization, embeddings in 16-bit
    - Uses NeelNanda/pile-10k for calibration by default
    - Outputs compressed-tensors format compatible with vLLM
    """
    logger.info("=" * 60)
    logger.info("Method: AutoRound (Intel, accuracy-first)")
    logger.info("=" * 60)

    cmd = [
        sys.executable, "-m", "auto_round",
        "--model", model_id,
        "--scheme", "W4A16",
        "--output_dir", output_dir,
        "--enable_torch_compile",
        "--trust_remote_code",
    ]

    logger.info(f"Running: {' '.join(cmd)}")
    logger.info("")
    logger.info("AutoRound will automatically:")
    logger.info("  - Keep vision tower in 16-bit")
    logger.info("  - Keep lm_head, norms, embeddings in 16-bit")
    logger.info("  - Use pile-10k for calibration")
    logger.info("  - Output compressed-tensors format")
    logger.info("")

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        logger.warning("auto_round module failed, trying auto-round-best CLI...")
        cmd_alt = [
            "auto-round-best",
            "--model", model_id,
            "--scheme", "W4A16",
            "--output_dir", output_dir,
            "--enable_torch_compile",
        ]
        logger.info(f"Running: {' '.join(cmd_alt)}")
        result = subprocess.run(cmd_alt, check=True)

    logger.info(f"Quantization complete! Model saved to: {output_dir}")
    _print_next_steps(output_dir)


def quantize_llmcompressor(
    model_id: str,
    output_dir: str,
    num_samples: int = 512,
    max_seq_length: int = 4096,
):
    """
    Quantize using LLM Compressor (fallback method).
    GPTQ W4A16 with explicit vision layer exclusion.
    """
    from llmcompressor.modifiers.quantization import GPTQModifier
    from llmcompressor import oneshot
    from datasets import load_dataset
    from transformers import AutoProcessor

    logger.info("=" * 60)
    logger.info("Method: LLM Compressor (vLLM project, GPTQ W4A16)")
    logger.info("=" * 60)

    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"

    logger.info("Loading processor...")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    # Coding-oriented calibration dataset
    logger.info("Loading calibration dataset...")
    try:
        ds = load_dataset("sahil2801/CodeAlpaca-20k", split="train")
    except Exception:
        logger.info("Fallback to Open-Platypus dataset...")
        ds = load_dataset("garage-bAInd/Open-Platypus", split="train")

    ds = ds.shuffle(seed=42).select(range(min(num_samples, len(ds))))

    def preprocess(example):
        instruction = example.get("instruction", example.get("input", ""))
        output = example.get("output", example.get("response", ""))
        return {"text": f"### Instruction:\n{instruction}\n\n### Response:\n{output}"}

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    logger.info(f"Calibration dataset: {len(ds)} samples")

    recipe = GPTQModifier(
        scheme="W4A16",
        targets="Linear",
        ignore=[
            "lm_head",
            "re:.*visual.*",
            "re:.*merger.*",
        ],
        dampening_frac=0.01,
        block_size=128,
    )

    os.makedirs(output_dir, exist_ok=True)

    # Load model
    logger.info("Loading model...")
    try:
        from transformers import Qwen3_5ForConditionalGeneration
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True,
        )
        logger.info("Loaded with Qwen3_5ForConditionalGeneration")
    except (ImportError, AttributeError):
        from transformers import AutoModelForVision2Seq
        model = AutoModelForVision2Seq.from_pretrained(
            model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True,
        )
        logger.info(f"Loaded with AutoModelForVision2Seq: {type(model).__name__}")

    logger.info("Starting quantization (30-60 min)...")
    oneshot(
        model=model,
        recipe=recipe,
        output_dir=output_dir,
        dataset=ds,
        max_seq_length=max_seq_length,
    )

    processor.save_pretrained(output_dir)
    logger.info(f"Quantization complete! Model saved to: {output_dir}")
    _print_next_steps(output_dir)


def _print_next_steps(output_dir: str):
    logger.info("")
    logger.info("Next steps:")
    logger.info(f"  1. Test loading:")
    logger.info(f'     python -c "from vllm import LLM; LLM(\'{output_dir}\')"')
    logger.info("")
    logger.info(f"  2. Deploy with Docker:")
    logger.info(f"     docker compose -f myia_vllm/configs/docker/profiles/mini-omnicoder.yml --env-file myia_vllm/.env up -d")
    logger.info("")
    logger.info(f"  3. Test vision + thinking:")
    logger.info(f"     curl localhost:5001/v1/chat/completions -d '{{\"model\":\"omnicoder-2-9b\", ...}}'")


def main():
    parser = argparse.ArgumentParser(
        description="Quantize OmniCoder-2-9B (Qwen3.5 VLM) to W4A16 for vLLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Methods:
    autoround      (RECOMMENDED) Intel AutoRound — best accuracy for Qwen3.5
    llmcompressor  (FALLBACK) vLLM LLM Compressor — GPTQ W4A16

Examples:
    python quantize_omnicoder2_9b.py --method autoround
    python quantize_omnicoder2_9b.py --method llmcompressor --num-samples 1024
    python quantize_omnicoder2_9b.py --check-only

Notes:
    - Vision encoder (ViT) stays in BF16/FP16 (both methods)
    - Output: ~5-6 GB (vs ~18 GB BF16)
    - AutoRound outputs compressed-tensors format (vLLM native)
        """
    )

    parser.add_argument(
        "--method", type=str, default="autoround",
        choices=["autoround", "llmcompressor"],
        help="Quantization method (default: autoround)"
    )
    parser.add_argument(
        "--model-id", type=str, default=MODEL_ID,
        help=f"HuggingFace model ID (default: {MODEL_ID})"
    )
    parser.add_argument(
        "--output-dir", type=str, default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--num-samples", type=int, default=512,
        help="Calibration samples for llmcompressor (default: 512)"
    )
    parser.add_argument(
        "--max-seq-length", type=int, default=4096,
        help="Calibration seq length for llmcompressor (default: 4096)"
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Only check dependencies"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OmniCoder-2-9B (Qwen3.5 VLM) W4A16 Quantization")
    logger.info(f"Method: {args.method}")
    logger.info("=" * 60)

    check_dependencies(args.method)

    if args.check_only:
        logger.info("Dependency check passed.")
        return

    if args.method == "autoround":
        quantize_autoround(args.model_id, args.output_dir)
    else:
        quantize_llmcompressor(
            args.model_id, args.output_dir,
            args.num_samples, args.max_seq_length,
        )


if __name__ == "__main__":
    main()
