#!/usr/bin/env python3
"""
Quantization script for ZwZ-8B (Qwen3-VL-8B finetune) using LLM Compressor.

ZwZ-8B is a fine-grained visual perception model from inclusionAI.
This script quantizes it to W4A16 (4-bit weights, 16-bit activations)
for efficient deployment on RTX 4090.

Key difference from text models:
    - Vision encoder (ViT) is EXCLUDED from quantization
    - Patch merger (vision-text connector) is EXCLUDED from quantization
    - Only the language model layers are quantized

Requirements:
    pip install llmcompressor>=0.9.0 transformers>=4.48.0 accelerate datasets

Usage:
    python quantize_zwz_8b.py [--output-dir OUTPUT_DIR] [--num-samples N]

Output:
    Quantized model saved to ./models/ZwZ-8B-AWQ-4bit/ (or custom path)

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
        # Verify Qwen3-VL support
        if not hasattr(transformers, 'Qwen3VLForConditionalGeneration'):
            logger.warning("Qwen3VLForConditionalGeneration not found - transformers upgrade may be needed")
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
    Quantize ZwZ-8B to W4A16 using GPTQ.

    Critical for VL models:
        - Vision encoder (visual.*) is kept in original precision
        - Patch merger (merger.*) is kept in original precision
        - Only language model Linear layers are quantized

    Args:
        model_id: HuggingFace model ID or local path
        output_dir: Directory to save quantized model
        num_calibration_samples: Number of samples for calibration
        max_seq_length: Maximum sequence length for calibration
    """
    from llmcompressor.modifiers.quantization import GPTQModifier
    from llmcompressor import oneshot
    from datasets import load_dataset
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    logger.info(f"Starting W4A16 quantization for: {model_id}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Calibration samples: {num_calibration_samples}")

    # Set trust_remote_code via environment variable for transformers
    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"

    # Load processor (tokenizer + image processor)
    logger.info("Loading processor...")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    # Load and prepare calibration dataset
    # Using Open-Platypus as general-purpose instruction dataset
    # For VL-specific calibration, consider HuggingFaceM4/FineVision
    logger.info("Loading calibration dataset (open_platypus)...")
    ds = load_dataset("garage-bAInd/Open-Platypus", split="train")
    ds = ds.shuffle(seed=42).select(range(min(num_calibration_samples, len(ds))))

    def preprocess(example):
        # Format as instruction-response pairs
        text = f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"
        return {"text": text}

    ds = ds.map(preprocess, remove_columns=ds.column_names)
    logger.info(f"Calibration dataset ready: {len(ds)} samples")

    # GPTQ recipe for W4A16 quantization
    # CRITICAL for VL models: exclude vision components
    # Note: Qwen3-VL uses "model.visual.*" prefix, not just "visual.*"
    recipe = GPTQModifier(
        scheme="W4A16",
        targets="Linear",
        ignore=[
            "lm_head",              # Output projection - keep FP16 for accuracy
            "re:.*visual.*",        # Vision transformer (ViT) - regex to catch all visual layers
            "re:.*merger.*",        # Vision-text connector - regex pattern
        ],
        dampening_frac=0.01,  # Dampening for numerical stability
        block_size=128,       # GPTQ block size
    )

    logger.info("Recipe configured:")
    logger.info("  Scheme: W4A16 (4-bit weights, 16-bit activations)")
    logger.info("  Targets: Linear layers")
    logger.info("  Ignored: lm_head, re:.*visual.*, re:.*merger.* (regex patterns)")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Load model explicitly with correct class for VL models
    # Qwen3-VL uses Qwen3VLForConditionalGeneration architecture
    logger.info("Loading model...")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype="auto",
        device_map="auto",
        trust_remote_code=True,
    )
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
    logger.info("Validation steps:")
    logger.info(f"  1. Test loading:")
    logger.info(f"     python -c \"from vllm import LLM; LLM('{output_dir}')\"")
    logger.info("")
    logger.info(f"  2. Test vision:")
    logger.info(f"     Use /v1/chat/completions with image_url content")
    logger.info("")
    logger.info("  3. (Optional) Upload to HuggingFace:")
    logger.info(f"     huggingface-cli upload your-username/ZwZ-8B-AWQ-4bit {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Quantize ZwZ-8B (Qwen3-VL finetune) to W4A16 for vLLM deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (default settings)
    python quantize_zwz_8b.py

    # Custom output directory
    python quantize_zwz_8b.py --output-dir /mnt/models/zwz-8b-awq

    # Faster calibration (lower quality)
    python quantize_zwz_8b.py --num-samples 256

    # Higher quality calibration (slower)
    python quantize_zwz_8b.py --num-samples 1024

Notes:
    - Vision encoder (ViT) is NOT quantized - kept in BF16/FP16
    - This preserves visual perception quality
    - Output model is ~5.5GB (vs ~17GB BF16)
        """
    )

    parser.add_argument(
        "--model-id",
        type=str,
        default="inclusionAI/ZwZ-8B",
        help="HuggingFace model ID or local path (default: inclusionAI/ZwZ-8B)"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models/ZwZ-8B-AWQ-4bit",
        help="Output directory for quantized model (default: ./models/ZwZ-8B-AWQ-4bit)"
    )

    parser.add_argument(
        "--num-samples",
        type=int,
        default=512,
        help="Number of calibration samples (default: 512, range: 256-1024)"
    )

    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=4096,
        help="Calibration sequence length (default: 4096)"
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies, don't run quantization"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ZwZ-8B (Qwen3-VL) W4A16 Quantization Script")
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
