# Overlay image: OUR prod overlay (v0.32.0 + tiering-race fix) + upstream PR
# vllm#58813 "Build the Qwen3.5 MTP head unquantized when the checkpoint ships
# it dense".
#
# EVAL WINDOW 2026-11-05 (user GO). Purpose: produce the boot-time evidence that
# PR #58813's author (he-yufeng) asked for in the PR body ("Boot-time validation
# against the reporter's checkpoint needs the AWQ model and GPUs, which I don't
# have; the reporter offered to test a fix branch") — that reporter is us.
#
# Why OUR tierpin base and not stock v0.32.0: the prod profile runs the RAM+fs
# KV tiering; without the tierpin fix the engine crash-loops on
# "AssertionError: Chunk ... not found in cache" (5 crashes on 2026-10-24).
# This image must carry BOTH fixes to be bootable on the prod profile.
#
# Upstream source pinned to PR head 1c911bd8abfaeb8f884b6dfa2590c488816f2e2d:
#   vllm/model_executor/models/qwen3_5_mtp.py   sha256 39617c6de697483c…
#   tests/v1/spec_decode/test_qwen3_5_mtp_dense_head.py  (naming-contract tests)
#
# Feasibility verified 2026-11-05 before building: the prod image's
# qwen3_5_mtp.py is BYTE-IDENTICAL to tag v0.32.0 (sha256 fbf31b1dd2b63eaf…),
# the PR's diff is 81 net lines, and its only new dependency
# (vllm.transformers_utils.repo_utils.try_get_local_file) already ships in the
# base image (repo_utils.py:434).
#
# Symptom this unblocks (vllm#58807, ours): the checkpoint ukisai/Swift-1.5-
# Qwen3.8-27b-W4A16-AWQ ships its MTP head BF16-dense in a separate shard
# (all 15 mtp.* tensors are plain .weight), but vLLM built the predictor from
# the target's pack-quantized config → "no module or parameter named
# 'fc.weight'" at weight load, on both TP workers.
#
# REMOVE this image once #58813 merges into a release we bump to.

FROM vllm-openai-v0320-tierpin:v1

COPY vllm/model_executor/models/qwen3_5_mtp.py /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/qwen3_5_mtp.py
COPY tests/v1/spec_decode/test_qwen3_5_mtp_dense_head.py /opt/s58813-tests/test_qwen3_5_mtp_dense_head.py

# Build-time proof the patch is live — STATIC only: importing the model module
# needs a CUDA device (vllm.config.device raises "Failed to infer device type"
# during a GPU-less build), so we parse the AST instead.
RUN python3 -m compileall -q /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/qwen3_5_mtp.py \
 && python3 -c "\
import ast;\
p='/usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/qwen3_5_mtp.py';\
t=ast.parse(open(p).read());\
names={n.name for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.ClassDef))};\
assert {'_mtp_weight_names','_checkpoint_ships_dense_mtp'} <= names, names;\
print('s58813 patch present (static)')"

LABEL org.myia.overlay="v0320-s58813-mtpdense" org.myia.base="vllm-openai-v0320-tierpin:v1" org.myia.pr="vllm-project/vllm#58813@1c911bd8"
