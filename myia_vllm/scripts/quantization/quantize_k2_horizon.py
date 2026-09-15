#!/usr/bin/env python3
"""
Quantization script for IFM/K2-Horizon-MoVA-36B-A4B -> W4A16 (compressed-tensors,
pack-quantized) for vLLM serving on 2x RTX 4090 (SM89, Marlin MoE kernels).

Eval candidate (2026-09-04, GO user). No W4A16 quant of this model exists
(only GGUF/FP8/MLX) — this is the home-made quant, iso-family with prod
(cyankiwi Qwen3.6-35B-A3B: compressed-tensors W4A16 asym GS32).

v2 (2026-09-15): PER-LAYER CHECKPOINT + RESUME. llmcompressor.oneshot has no
native resume (verified: SequentialPipeline loops subgraphs, GPTQModifier packs
weights at on_sequential_epoch_end, nothing is persisted between layers). Three
full 11-16h runs were lost at the last kilometer (transformers save bug, Windows
Update reboot, host strain) — per user rule, no long job launches without a
tested resume path (memory: feedback_long_jobs_resume.md).

Mechanics (verified against llmcompressor 0.13.0 / compressed_tensors sources
in /home/jesse/k2-quant-venv):
  - SequentialPipeline.__call__ runs one subgraph per decoder layer; after each
    subgraph's calibrate pass it calls LifecycleCallbacks.sequential_epoch_end.
  - GPTQModifier.on_sequential_epoch_end -> compress_modules() runs GPTQ and
    writes packed params (weight_packed/weight_scale/...) onto the modules via
    update_offload_parameter. After that call, module.state_dict() holds the
    compressed tensors — this is our checkpoint payload, saved per layer.
  - Resume: completed layers stay recipe TARGETS (so apply_quantization_config
    attaches their scheme, keeping module forwards compressed for propagation)
    but their calibrate_module hook early-returns -> no Hessian -> they are
    never re-compressed; their packed params are re-injected at
    on_calibration_start from the checkpoint files.
  - Calibration order is deterministic (dataset shuffle seed=42, same args —
    enforced against the manifest), so resumed propagation through injected
    packed params matches the uninterrupted run (bit-exactness asserted by
    --verify-checkpoints in the pre-launch test protocol).

Run environment (WSL Ubuntu, GPU 2 — CoursIA slot): CUDA_VISIBLE_DEVICES=2,
HF_HOME=/home/jesse/.cache/huggingface, venv /home/jesse/k2-quant-venv.
Checkpoint dir default: /home/jesse/k2-ckpt-k2quant (layer_NN.pt + manifest.json,
~25 GB total for 49 layers, ~0.5 GB sequential write per layer).

Test protocol before any real run (REQUIRED, memory feedback_long_jobs_resume):
  1. --num-samples 8 --checkpoint-dir <TEST>            # fresh, kill after layer ~5
  2. rerun same command                                   # resume: skips done layers,
                                                          #   "RESUME: injected" logged
  3. --verify-checkpoints <TEST> <TEST2>                 # bit-exact layer tensors
     where TEST2 = a second fresh 8-sample run to the same layer count
  4. only then launch the real run (announced, calm window)

Usage (inside WSL):
    CUDA_VISIBLE_DEVICES=2 HF_HOME=/home/jesse/.cache/huggingface \
        /home/jesse/k2-quant-venv/bin/python quantize_k2_horizon.py --check-only
    CUDA_VISIBLE_DEVICES=2 HF_HOME=/home/jesse/.cache/huggingface \
        /home/jesse/k2-quant-venv/bin/python quantize_k2_horizon.py --num-samples 256

Estimated: ~13.8 min/layer x 49 layers on GPU 2 (host-load dependent).
Output: ~20 GB (vs 74.9 GB BF16). Resume cost: propagation-only through done
layers (~half the per-layer cost), full work from the first pending layer.
"""

import argparse
import json
import logging
import os
import re
import sys
import time

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

LAYER_RE = re.compile(r"model\.layers\.(\d+)\.")

# checkpoint state shared with the modifier class (module-level: pydantic-safe)
_CKPT = {"dir": None, "done": set(), "args": {}, "scheme_used": None}


def _layer_idx(name):
    m = LAYER_RE.search(name or "")
    return int(m.group(1)) if m else None


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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


def _make_modifier_class():
    from llmcompressor.modifiers.gptq import GPTQModifier
    from compressed_tensors.offload import update_offload_parameter

    # checkpoint state lives in a module-level dict: GPTQModifier is a pydantic
    # model, so plain non-field attribute assignment on instances is unsafe —
    # only underscore private attrs (their own _hessians pattern) are
    class CheckpointedGPTQModifier(GPTQModifier):

        # ---- authoritative name map (own copy: covers never-hooked modules too)
        def on_initialize(self, state, **kwargs):
            ok = super().on_initialize(state, **kwargs)
            self._name_map = {id(m): n for n, m in state.model.named_modules()}
            return ok

        def _name_of(self, module):
            return getattr(self, "_name_map", {}).get(id(module))

        # ---- skip Hessian accumulation for checkpointed layers: no entry in
        # _num_samples -> compress_modules() never re-quantizes them
        def calibrate_module(self, module, args, _output):
            li = _layer_idx(self._name_of(module))
            if li is not None and li in _CKPT["done"]:
                return
            super().calibrate_module(module, args, _output)

        # ---- inject packed params before the first forward pass
        def on_calibration_start(self, state, event, **kwargs):
            super().on_calibration_start(state, event, **kwargs)
            if not _CKPT["done"]:
                return
            import torch
            payloads = {}
            for li in sorted(_CKPT["done"]):
                p = os.path.join(_CKPT["dir"], f"layer_{li:02d}.pt")
                payloads.update(torch.load(p, map_location="cpu"))
            injected = 0
            for _, module in state.model.named_modules():
                name = self._name_map.get(id(module))
                li = _layer_idx(name)
                if li is None or li not in _CKPT["done"]:
                    continue
                prefix = name + "."
                attrs = {k[len(prefix):]: v for k, v in payloads.items() if k.startswith(prefix)}
                if not attrs:
                    continue
                for attr, val in attrs.items():
                    update_offload_parameter(module, attr, val)
                # the stale BF16 `weight` from the fresh load must go: the module
                # is pack-quantized now (config attached at init); a lingering
                # weight would risk being re-saved at final save time
                if "weight_packed" in attrs and hasattr(module, "weight"):
                    module._parameters.pop("weight", None)
                injected += 1
            logger.info(f"RESUME: injected packed params for {injected} modules "
                        f"across {len(_CKPT['done'])} layers")

        # ---- after GPTQ compressed this subgraph's live modules, persist them
        def on_sequential_epoch_end(self, state, event, modules, **kwargs):
            live = []
            for m in modules:
                li = _layer_idx(self._name_of(m))
                if li is None or li not in _CKPT["done"]:
                    live.append(m)
            super().on_sequential_epoch_end(state, event, modules=live, **kwargs)

            import torch
            per_layer = {}
            for m in live:
                name = self._name_of(m)
                li = _layer_idx(name)
                if li is None:
                    continue
                for k, v in m.state_dict().items():
                    per_layer.setdefault(li, {})[f"{name}.{k}"] = v.detach().to("cpu", copy=True)
            for li in sorted(per_layer):
                path = os.path.join(_CKPT["dir"], f"layer_{li:02d}.pt")
                tmp = path + ".tmp"
                torch.save(per_layer[li], tmp)
                os.replace(tmp, path)
                _CKPT["done"].add(li)
                logger.info(f"CKPT: layer {li} saved ({len(_CKPT['done'])} done)")
            if per_layer:
                _atomic_json(os.path.join(_CKPT["dir"], "manifest.json"), {
                    "done": sorted(_CKPT["done"]),
                    "ts": time.time(),
                    "args": _CKPT["args"],
                    "scheme_used": _CKPT["scheme_used"],
                })

    return CheckpointedGPTQModifier


def verify_checkpoints(dir_a, dir_b):
    import torch
    files_a = sorted(f for f in os.listdir(dir_a) if f.startswith("layer_"))
    files_b = set(os.listdir(dir_b))
    all_ok = True
    for f in files_a:
        if f not in files_b:
            logger.warning(f"{f}: MISSING in {dir_b}")
            all_ok = False
            continue
        a = torch.load(os.path.join(dir_a, f), map_location="cpu")
        b = torch.load(os.path.join(dir_b, f), map_location="cpu")
        if set(a) != set(b):
            logger.warning(f"{f}: key sets differ")
            all_ok = False
            continue
        bad = [k for k in a if not torch.equal(a[k], b[k])]
        if bad:
            logger.warning(f"{f}: {len(bad)}/{len(a)} tensors DIFFER (first: {bad[0]})")
            all_ok = False
        else:
            logger.info(f"{f}: bit-exact ({len(a)} tensors)")
    print("VERIFY_RESULT=" + ("IDENTICAL" if all_ok else "DIFFER"))
    return all_ok


def quantize(model_id, output_dir, num_samples, max_seq_length, ckpt_dir):
    from llmcompressor import oneshot
    from datasets import load_dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer

    os.environ["HF_HUB_TRUST_REMOTE_CODE"] = "1"
    os.makedirs(ckpt_dir, exist_ok=True)

    # ---- resume state
    manifest_path = os.path.join(ckpt_dir, "manifest.json")
    done_layers, prev_args, prev_scheme = set(), None, None
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            man = json.load(f)
        done_layers = set(man.get("done", []))
        prev_args = man.get("args", {})
        prev_scheme = man.get("scheme_used")
        logger.info(f"RESUME: manifest found, {len(done_layers)} layers done: {sorted(done_layers)}")
    run_args = {"model_id": model_id, "num_samples": num_samples,
                "max_seq_length": max_seq_length, "seed": 42}
    if prev_args is not None and prev_args != run_args:
        logger.error(f"ARGS MISMATCH vs checkpoint manifest — resume would be unsound.\n"
                     f"  manifest: {prev_args}\n  current:  {run_args}\n"
                     f"  Use a fresh --checkpoint-dir or repeat the exact original args.")
        sys.exit(1)
    if prev_args is None:
        _atomic_json(manifest_path, {"done": [], "ts": time.time(), "args": run_args})

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
    # default) — log loudly so the delta vs prod is known. The scheme actually used
    # is recorded in the manifest, and a resume refuses to mix schemes.
    scheme = {
        "weights": {"num_bits": 4, "group_size": 32, "symmetric": False, "strategy": "group"},
        "activations": None,
    }
    Cls = _make_modifier_class()
    try:
        recipe = Cls(scheme=scheme, targets="Linear", ignore=IGNORE, dampening_frac=0.01, block_size=128)
        scheme_used = "W4A16-asym-gs32"
    except Exception as e:
        logger.warning(f"Explicit scheme dict rejected ({e}); falling back to scheme='W4A16' (GS128 sym default)")
        recipe = Cls(scheme="W4A16", targets="Linear", ignore=IGNORE, dampening_frac=0.01, block_size=128)
        scheme_used = "W4A16-preset-gs128-sym"
    _CKPT["dir"] = ckpt_dir
    _CKPT["done"] = done_layers
    _CKPT["args"] = run_args
    _CKPT["scheme_used"] = scheme_used
    if done_layers and prev_scheme and prev_scheme != scheme_used:
        logger.error(f"SCHEME MISMATCH: manifest={prev_scheme} current={scheme_used} — fresh ckpt dir required")
        sys.exit(1)

    logger.info("Loading model (74.9 GB BF16, CPU RAM + GPU 2 offload)...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True,
    )

    logger.info("Running oneshot quantization with per-layer checkpoints...")
    oneshot(
        model=model,
        recipe=recipe,
        output_dir=output_dir,
        dataset=ds,
        max_seq_length=max_seq_length,
    )
    tokenizer.save_pretrained(output_dir)

    logger.info(f"Done. Quantized model at: {output_dir}")
    logger.info(f"Checkpoints kept at: {ckpt_dir} (safe to delete after output is validated)")
    logger.info("Validation (at eval window):")
    logger.info(f"  docker run --gpus '\"device=2\"' -v {output_dir}:/m "
                "vllm/vllm-openai:nightly-e962733e08d10f7ca65dac4df99e116460b8b174 "
                "--model /m --max-model-len 8192 --gpu-memory-utilization 0.9 "
                "--trust-remote-code --reasoning-parser k2_horizon --tool-call-parser k2_horizon")


def main():
    p = argparse.ArgumentParser(description="Quantize K2-Horizon-MoVA-36B-A4B to W4A16 (checkpointed)")
    p.add_argument("--model-id", default="IFM/K2-Horizon-MoVA-36B-A4B")
    p.add_argument("--output-dir", default="/home/jesse/k2-quant-out")
    p.add_argument("--num-samples", type=int, default=256,
                   help="Calibration samples (256 default; 512 = better, slower)")
    p.add_argument("--max-seq-length", type=int, default=4096)
    p.add_argument("--checkpoint-dir", default="/home/jesse/k2-ckpt-k2quant",
                   help="Per-layer checkpoint dir (resume is automatic if manifest exists)")
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--verify-checkpoints", nargs=2, metavar=("DIR_A", "DIR_B"),
                   help="Compare two checkpoint dirs tensor-by-tensor (resume validation)")
    args = p.parse_args()

    logger.info("=" * 60)
    logger.info("K2-Horizon-MoVA-36B-A4B W4A16 quantization (v2 checkpointed)")
    logger.info("=" * 60)
    if args.verify_checkpoints:
        ok = verify_checkpoints(*args.verify_checkpoints)
        sys.exit(0 if ok else 2)
    check_dependencies()
    if args.check_only:
        logger.info("--check-only: dependencies OK, exiting.")
        return
    quantize(args.model_id, args.output_dir, args.num_samples, args.max_seq_length,
             args.checkpoint_dir)


if __name__ == "__main__":
    main()
