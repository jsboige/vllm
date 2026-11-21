# Overlay image: stock vLLM v0.34.0 (by digest) + the tiering-race fix
# (tierpin, PR #176 / upstream #63551) + the fs-tier write-admission filter
# (jsboige/vllm#198 Phase 1a, first shipped on v0.32.0 as overlay_v0320_fsadmit,
# PR #202).
#
# NOT deployed: built for testing until a user GO and an announced window.
# Same base digest as overlay_v0340_tierpin (the image in production since
# 2026-11-19), so the only runtime difference against production is the
# admission gate in tiering/manager.py. cpu/manager.py is byte-identical to
# overlay_v0340_tierpin; port.py refuses to emit anything otherwise.
#
# What the filter changes (README.md has the full design): cascades to
# STORAGE (fs/SSD) secondary tiers are frequency-gated -- a chunk is written
# to fs only once it has been found (lookup HIT) in the primary/RAM tier at
# least MYIA_FS_ADMIT_MIN_HITS times (default 2). A refused store costs a
# recompute later, never wrong output.
#
#   MYIA_FS_ADMIT_MIN_HITS=0 restores exact upstream write-through (rollback
#   switch, read once at manager construction: needs a container recreate).
#   MYIA_FS_ADMIT_GDN_LATEST=1 only logs (documented no-op stub).
#
# The build fails unless BOTH patches are present in the installed modules.

FROM vllm/vllm-openai@sha256:cf5b2fdd087eb4f6d261736967cc5cde974bd22ff4df50365f8fa419b6b4c484
COPY vllm/v1/kv_offload/cpu/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/cpu/manager.py
COPY vllm/v1/kv_offload/tiering/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/tiering/manager.py
RUN python3 -m py_compile /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/cpu/manager.py /usr/local/lib/python3.12/dist-packages/vllm/v1/kv_offload/tiering/manager.py \
 && python3 -c "import inspect; from vllm.v1.kv_offload.tiering.manager import TieringOffloadingManager as M; from vllm.v1.kv_offload.cpu import manager as C; t = inspect.getsource(M); c = inspect.getsource(C); assert '_step_hit_keys' in t, 'tierpin fix lost (tiering)'; assert 'extra_protected' in c, 'tierpin fix lost (cpu)'; assert '_record_fs_admit_hit' in t and '_filter_fs_admitted' in t, 'fs-admit filter missing'; print('overlay asserts OK: tierpin + fs-admit')"
LABEL org.myia.overlay="v0340-fsadmit" \
      org.myia.base="vllm/vllm-openai@sha256:cf5b2fdd087eb4f6d261736967cc5cde974bd22ff4df50365f8fa419b6b4c484" \
      org.myia.includes="tierpin (PR #176, upstream #63551) + fs-admit (issue #198, PR #202)"
