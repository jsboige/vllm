#!/bin/bash
# =============================================================================
# OmniCoder-2-9B Deployment Script
# =============================================================================
# Runs in WSL: installs deps, quantizes model (AutoRound), deploys via Docker
#
# Usage (from Windows):
#   wsl -e bash /mnt/d/vllm/myia_vllm/scripts/deploy_omnicoder2.sh
#
# Steps:
#   1. Install Python venv + dependencies (auto-round, torch CUDA)
#   2. Quantize OmniCoder-2-9B to AWQ 4-bit via AutoRound
#   3. Stop ZwZ-8B container
#   4. Start OmniCoder-2-9B container
#   5. Verify health
# =============================================================================

set -euo pipefail

# --- Configuration ---
VENV_DIR="/home/$USER/venvs/autoround"
MODEL_ID="Tesslate/OmniCoder-2-9B"
OUTPUT_DIR="/mnt/d/vllm/models/OmniCoder-2-9B-AWQ-4bit"
VLLM_DIR="/mnt/d/vllm"
QUANT_SCRIPT="$VLLM_DIR/myia_vllm/scripts/quantization/quantize_omnicoder2_9b.py"
ZWZ_PROFILE="$VLLM_DIR/myia_vllm/configs/docker/profiles/mini-zwz.yml"
OMNI_PROFILE="$VLLM_DIR/myia_vllm/configs/docker/profiles/mini-omnicoder.yml"
ENV_FILE="$VLLM_DIR/myia_vllm/.env"

# Use GPU 2 (same as ZwZ-8B, will need it free for quantization)
export CUDA_VISIBLE_DEVICES=2

echo "============================================================"
echo "  OmniCoder-2-9B Deployment Pipeline"
echo "============================================================"
echo "  Model:  $MODEL_ID"
echo "  Output: $OUTPUT_DIR"
echo "  GPU:    $CUDA_VISIBLE_DEVICES (RTX 4090)"
echo "============================================================"
echo ""

# --- Step 0: Check if already quantized ---
if [ -d "$OUTPUT_DIR" ] && [ -f "$OUTPUT_DIR/config.json" ]; then
    echo "[SKIP] Model already quantized at $OUTPUT_DIR"
    echo "       Delete the directory to re-quantize."
    SKIP_QUANT=1
else
    SKIP_QUANT=0
fi

# --- Step 1: Install dependencies ---
if [ "$SKIP_QUANT" -eq 0 ]; then
    echo "[1/5] Setting up Python environment..."

    # Install python3-venv if needed
    if ! python3 -m venv --help &>/dev/null; then
        echo "  Installing python3-venv..."
        sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv python3-dev
    fi

    # Create venv
    if [ ! -d "$VENV_DIR" ]; then
        echo "  Creating venv at $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
    fi

    source "$VENV_DIR/bin/activate"

    # Install PyTorch with CUDA
    echo "  Installing PyTorch + CUDA..."
    pip install --upgrade pip -q
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 -q

    # Install auto-round + deps
    echo "  Installing auto-round + transformers + accelerate..."
    pip install "auto-round" "transformers>=4.48.0" "accelerate" -q

    # Verify CUDA
    python3 -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available!'
print(f'  PyTorch {torch.__version__}, CUDA {torch.version.cuda}')
print(f'  GPU: {torch.cuda.get_device_name(0)}')
print(f'  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"
    echo ""

    # --- Step 2: Stop ZwZ-8B to free GPU 2 ---
    echo "[2/5] Stopping ZwZ-8B to free GPU 2..."
    cd "$VLLM_DIR"
    docker compose -f "$ZWZ_PROFILE" --env-file "$ENV_FILE" down 2>/dev/null || true
    echo "  ZwZ-8B stopped."

    # Wait for GPU memory to clear
    sleep 5
    echo ""

    # --- Step 3: Quantize ---
    echo "[3/5] Quantizing OmniCoder-2-9B (AutoRound W4A16)..."
    echo "  This will take 30-60 minutes..."
    echo "  Vision encoder will be kept in BF16."
    echo ""

    cd "$VLLM_DIR"
    python3 "$QUANT_SCRIPT" \
        --method autoround \
        --model-id "$MODEL_ID" \
        --output-dir "$OUTPUT_DIR"

    echo ""
    echo "  Quantization complete!"
    deactivate
else
    echo "[1/5] Dependencies: skipped (model already quantized)"
    echo "[2/5] Stop ZwZ-8B: proceeding..."
    cd "$VLLM_DIR"
    docker compose -f "$ZWZ_PROFILE" --env-file "$ENV_FILE" down 2>/dev/null || true
    echo "  ZwZ-8B stopped."
    echo "[3/5] Quantization: skipped (already done)"
fi

echo ""

# --- Step 4: Deploy OmniCoder-2-9B ---
echo "[4/5] Deploying OmniCoder-2-9B on GPU 2..."
cd "$VLLM_DIR"
docker compose -f "$OMNI_PROFILE" --env-file "$ENV_FILE" up -d

echo "  Container starting... (model load + CUDA graphs ~3-5 min)"
echo ""

# --- Step 5: Wait for health ---
echo "[5/5] Waiting for health check..."
MAX_WAIT=360  # 6 minutes
ELAPSED=0
INTERVAL=15

while [ $ELAPSED -lt $MAX_WAIT ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' myia_vllm-mini-omnicoder 2>/dev/null || echo "not_found")

    if [ "$STATUS" = "healthy" ]; then
        echo ""
        echo "============================================================"
        echo "  OmniCoder-2-9B is HEALTHY!"
        echo "============================================================"
        echo "  Port:  5001"
        echo "  Model: omnicoder-2-9b"
        echo "  GPU:   2 (RTX 4090)"
        echo ""
        echo "  Test:"
        echo "    curl -s http://localhost:5001/v1/models -H 'Authorization: Bearer \$VLLM_API_KEY_MINI'"
        echo ""
        echo "  Rollback to ZwZ-8B:"
        echo "    docker compose -f $OMNI_PROFILE down"
        echo "    docker compose -f $ZWZ_PROFILE --env-file $ENV_FILE up -d"
        echo "============================================================"
        exit 0
    fi

    echo "  [$ELAPSED/${MAX_WAIT}s] Status: $STATUS"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
echo "WARNING: Health check timed out after ${MAX_WAIT}s"
echo "Check logs: docker logs myia_vllm-mini-omnicoder"
exit 1
