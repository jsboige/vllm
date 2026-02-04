#!/usr/bin/env python3
"""
Quantization script for Qwen3-Coder-Next using LLM Compressor.

This script quantifies the 80B MoE model to W4A16 (4-bit weights, 16-bit activations)
for deployment on 3x RTX 4090 GPUs (72GB total VRAM).

Requirements:
    pip install llmcompressor>=0.9.0 transformers accelerate

Usage:
    python quantize_qwen3_coder_next.py [--output-dir OUTPUT_DIR] [--num-samples N]

Output:
    Quantified model saved to ./models/Qwen3-Coder-Next-W4A16/ (or custom path)

Estimated time: 2-4 hours on GPU (MoE calibration is slower than dense models)
"""

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """Verify required packages are installed."""
    missing = []

    try:
        import llmcompressor
        logger.info(f"llmcompressor version: {llmcompressor.__version__}")
    except ImportError:
        missing.append("llmcompressor>=0.9.0")

    try:
        import transformers
        logger.info(f"transformers version: {transformers.__version__}")
    except ImportError:
        missing.append("transformers")

    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        if torch.cuda.is_available():
            logger.info(f"CUDA available: {torch.cuda.device_count()} GPU(s)")
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                logger.info(f"  GPU {i}: {props.name} ({props.total_memory / 1e9:.1f} GB)")
        else:
            logger.warning("CUDA not available - quantification will be very slow!")
    except ImportError:
        missing.append("torch")

    if missing:
        logger.error(f"Missing packages: {', '.join(missing)}")
        logger.error("Install with: pip install " + " ".join(missing))
        sys.exit(1)


def quantize_model(
    model_id: str,
    output_dir: str,
    num_calibration_samples: int = 512,
):
    """
    Quantify Qwen3-Coder-Next to W4A16 using GPTQ.

    Args:
        model_id: HuggingFace model ID or local path
        output_dir: Directory to save quantified model
        num_calibration_samples: Number of samples for calibration (more = better quality, slower)
    """
    from llmcompressor.modifiers.quantization import GPTQModifier
    from llmcompressor import oneshot
    from datasets import load_dataset
    from transformers import AutoTokenizer

    logger.info(f"Starting W4A16 quantification for: {model_id}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Calibration samples: {num_calibration_samples}")

    # Set trust_remote_code via environment variable for transformers
    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"

    # Load tokenizer for dataset preparation
    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    # Load and prepare calibration dataset
    logger.info("Loading calibration dataset (open_platypus)...")
    ds = load_dataset("garage-bAInd/Open-Platypus", split="train")
    ds = ds.shuffle(seed=42).select(range(min(num_calibration_samples, len(ds))))

    def preprocess(example):
        # Format as instruction-response pairs
        text = f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"
        return {"text": text}

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    logger.info(f"Calibration dataset ready: {len(ds)} samples")

    # GPTQ recipe for W4A16 quantification
    # - scheme="W4A16": 4-bit weights, 16-bit activations
    # - targets="Linear": Apply to all linear layers
    # - ignore=["lm_head"]: Keep language model head in FP16 for accuracy
    recipe = GPTQModifier(
        scheme="W4A16",
        targets="Linear",
        ignore=["lm_head"],
        dampening_frac=0.01,  # Dampening for numerical stability
        block_size=128,  # GPTQ block size
    )

    logger.info("Recipe configured:")
    logger.info(f"  Scheme: W4A16 (4-bit weights, 16-bit activations)")
    logger.info(f"  Targets: Linear layers")
    logger.info(f"  Ignored: lm_head (kept in FP16)")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Run one-shot quantification
    logger.info("Starting quantification... (this may take 2-4 hours)")

    oneshot(
        model=model_id,
        recipe=recipe,
        output_dir=output_dir,
        dataset=ds,
        max_seq_length=4096,  # Calibration sequence length
    )

    logger.info(f"Quantification complete! Model saved to: {output_dir}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Test the model locally:")
    logger.info(f"   python -c \"from vllm import LLM; llm = LLM('{output_dir}', tensor_parallel_size=3)\"")
    logger.info("")
    logger.info("2. Deploy with Docker:")
    logger.info("   docker compose -f configs/docker/profiles/medium-coder.yml up -d")
    logger.info("")
    logger.info("3. (Optional) Upload to HuggingFace:")
    logger.info(f"   huggingface-cli upload your-username/Qwen3-Coder-Next-W4A16 {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Quantify Qwen3-Coder-Next to W4A16 for vLLM deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (default settings)
    python quantize_qwen3_coder_next.py

    # Custom output directory
    python quantize_qwen3_coder_next.py --output-dir /mnt/models/qwen3-coder-w4a16

    # Faster calibration (lower quality)
    python quantize_qwen3_coder_next.py --num-samples 256

    # Higher quality calibration (slower)
    python quantize_qwen3_coder_next.py --num-samples 1024
        """
    )

    parser.add_argument(
        "--model-id",
        type=str,
        default="Qwen/Qwen3-Coder-Next",
        help="HuggingFace model ID or local path (default: Qwen/Qwen3-Coder-Next)"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models/Qwen3-Coder-Next-W4A16",
        help="Output directory for quantified model (default: ./models/Qwen3-Coder-Next-W4A16)"
    )

    parser.add_argument(
        "--num-samples",
        type=int,
        default=512,
        help="Number of calibration samples (default: 512, range: 256-1024)"
    )


    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies, don't run quantification"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Qwen3-Coder-Next W4A16 Quantification Script")
    logger.info("=" * 60)

    check_dependencies()

    if args.check_only:
        logger.info("Dependency check passed. Exiting (--check-only mode).")
        return

    quantize_model(
        model_id=args.model_id,
        output_dir=args.output_dir,
        num_calibration_samples=args.num_samples,
    )


if __name__ == "__main__":
    main()
