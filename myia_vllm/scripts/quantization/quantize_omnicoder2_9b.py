#!/usr/bin/env python3
"""
Quantization script for OmniCoder-2-9B (Qwen3.5-9B VLM finetune) using LLM Compressor.

OmniCoder-2-9B is an agentic coding model by Tesslate, built on
Qwen3_5ForConditionalGeneration (VLM backbone with vision encoder).
This script quantizes it to W4A16 (4-bit weights, 16-bit activations)
for deployment on RTX 4090 (GPU 2).

Key design choices:
    - Vision encoder (ViT) is EXCLUDED from quantization (preserve visual accuracy)
    - Patch merger (vision-text connector) is EXCLUDED from quantization
    - Only language model Linear layers are quantized
    - Uses coding-oriented calibration dataset (not general text)

Requirements:
    conda activate llmcompressor
    pip install llmcompressor>=0.9.0 transformers>=4.48.0 accelerate datasets

Usage:
    python quantize_omnicoder2_9b.py
    python quantize_omnicoder2_9b.py --num-samples 1024  # higher quality
    python quantize_omnicoder2_9b.py --check-only         # verify deps

Output:
    Quantized model saved to ./models/OmniCoder-2-9B-AWQ-4bit/

Estimated time: 30-60 minutes on RTX 4090
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

MODEL_ID = "Tesslate/OmniCoder-2-9B"
DEFAULT_OUTPUT = "./models/OmniCoder-2-9B-AWQ-4bit"


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
        missing.append("transformers>=4.48.0")

    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        if torch.cuda.is_available():
            logger.info(f"CUDA available: {torch.cuda.device_count()} GPU(s)")
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                logger.info(f"  GPU {i}: {props.name} ({props.total_memory / 1e9:.1f} GB)")
        else:
            logger.warning("CUDA not available - quantization will be very slow!")
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
    max_seq_length: int = 4096,
):
    """
    Quantize OmniCoder-2-9B to W4A16 using GPTQ.

    The model uses Qwen3_5ForConditionalGeneration (VLM class).
    Vision encoder and patch merger are kept in original precision.

    Args:
        model_id: HuggingFace model ID or local path
        output_dir: Directory to save quantized model
        num_calibration_samples: Number of samples for calibration
        max_seq_length: Maximum sequence length for calibration
    """
    from llmcompressor.modifiers.quantization import GPTQModifier
    from llmcompressor import oneshot
    from datasets import load_dataset
    from transformers import AutoProcessor, AutoModelForVision2Seq
    import transformers

    logger.info(f"Starting W4A16 quantization for: {model_id}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Calibration samples: {num_calibration_samples}")

    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"

    # Load processor (tokenizer + image processor)
    logger.info("Loading processor...")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    # Use coding-oriented calibration dataset for an agentic coding model
    logger.info("Loading calibration dataset (code_instructions_120k_alpaca)...")
    try:
        ds = load_dataset("sahil2801/CodeAlpaca-20k", split="train")
    except Exception:
        logger.info("Fallback to Open-Platypus dataset...")
        ds = load_dataset("garage-bAInd/Open-Platypus", split="train")

    ds = ds.shuffle(seed=42).select(range(min(num_calibration_samples, len(ds))))

    def preprocess(example):
        instruction = example.get("instruction", example.get("input", ""))
        output = example.get("output", example.get("response", ""))
        text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
        return {"text": text}

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    logger.info(f"Calibration dataset ready: {len(ds)} samples")

    # GPTQ recipe: W4A16, excluding vision components
    # OmniCoder-2-9B uses Qwen3.5 architecture with visual.* and merger.* prefixes
    recipe = GPTQModifier(
        scheme="W4A16",
        targets="Linear",
        ignore=[
            "lm_head",              # Output projection - keep FP16 for accuracy
            "re:.*visual.*",        # Vision transformer (ViT) - preserve visual quality
            "re:.*merger.*",        # Vision-text connector
        ],
        dampening_frac=0.01,
        block_size=128,
    )

    logger.info("Recipe configured:")
    logger.info("  Scheme: W4A16 (4-bit weights, 16-bit activations)")
    logger.info("  Targets: Linear layers")
    logger.info("  Ignored: lm_head, re:.*visual.*, re:.*merger.*")

    os.makedirs(output_dir, exist_ok=True)

    # Load model - try Qwen3.5 VLM class, fallback to auto
    logger.info("Loading model...")
    try:
        # Try the specific Qwen3.5 VLM class first
        from transformers import Qwen3_5ForConditionalGeneration
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
        )
        logger.info("Loaded with Qwen3_5ForConditionalGeneration")
    except (ImportError, AttributeError):
        # Fallback to AutoModel
        logger.info("Qwen3_5ForConditionalGeneration not found, using AutoModelForVision2Seq")
        model = AutoModelForVision2Seq.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
        )
        logger.info(f"Loaded with AutoModelForVision2Seq: {type(model).__name__}")

    logger.info("Model loaded successfully")

    # Run one-shot quantization
    logger.info("Starting quantization... (this may take 30-60 minutes)")

    oneshot(
        model=model,
        recipe=recipe,
        output_dir=output_dir,
        dataset=ds,
        max_seq_length=max_seq_length,
    )

    # Save processor alongside model
    processor.save_pretrained(output_dir)

    logger.info(f"Quantization complete! Model saved to: {output_dir}")
    logger.info("")
    logger.info("Next steps:")
    logger.info(f"  1. Test loading:")
    logger.info(f"     python -c \"from vllm import LLM; LLM('{output_dir}')\"")
    logger.info("")
    logger.info(f"  2. Deploy with Docker:")
    logger.info(f"     docker compose -f myia_vllm/configs/docker/profiles/mini-omnicoder.yml --env-file myia_vllm/.env up -d")
    logger.info("")
    logger.info(f"  3. Test vision:")
    logger.info(f"     curl localhost:5001/v1/chat/completions -d '{{\"model\":\"omnicoder-2-9b\", ...}}'")


def main():
    parser = argparse.ArgumentParser(
        description="Quantize OmniCoder-2-9B (Qwen3.5 VLM) to W4A16 for vLLM deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (default settings)
    python quantize_omnicoder2_9b.py

    # Custom output directory
    python quantize_omnicoder2_9b.py --output-dir /mnt/models/omnicoder-awq

    # Higher quality calibration (slower)
    python quantize_omnicoder2_9b.py --num-samples 1024

Notes:
    - Vision encoder (ViT) is NOT quantized - kept in BF16/FP16
    - OmniCoder-2-9B uses Qwen3_5ForConditionalGeneration (VLM backbone)
    - Output model is ~5-6GB (vs ~18GB BF16)
    - Uses coding-focused calibration dataset
        """
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
        help="Number of calibration samples (default: 512, range: 256-1024)"
    )
    parser.add_argument(
        "--max-seq-length", type=int, default=4096,
        help="Calibration sequence length (default: 4096)"
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Only check dependencies, don't run quantization"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OmniCoder-2-9B (Qwen3.5 VLM) W4A16 Quantization Script")
    logger.info("=" * 60)

    check_dependencies()

    if args.check_only:
        logger.info("Dependency check passed. Exiting (--check-only mode).")
        return

    quantize_model(
        model_id=args.model_id,
        output_dir=args.output_dir,
        num_calibration_samples=args.num_samples,
        max_seq_length=args.max_seq_length,
    )


if __name__ == "__main__":
    main()
