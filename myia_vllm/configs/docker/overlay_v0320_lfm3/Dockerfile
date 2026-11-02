# Overlay image: stock vllm/vllm-openai:v0.32.0 + LFM3 (Lfm3ForCausalLM)
#
# ÉVAL po-2025 02/11/2026 (GO user "tentes avec le greffe") — NON-PROD.
#
# Pourquoi cet overlay : LFM3-1.7B (LiquidAI, tri-hybride 13 conv / 5 SWA / 6
# attention globales, 256K, 128K vocab) n'existe PAS dans vLLM — vérifié le
# 02/11 sur upstream main : lfm3.py 404, registry 5 entrées Lfm2 / 0 Lfm3.
# La carte HF liste "BF16 → vLLM" mais le lien pointe vers une page de doc
# LFM2.5 ; la PR upstream est ouverte depuis le 01/11.
#
# Source : PR vllm-project/vllm#64959 "[Model] Add LiquidAI LFM3
# (Lfm3ForCausalLM)" (autonome : elle embarque le kernel width-7 de #64647,
# pas besoin des deux). Base de la PR = main ; le apply 3-way des hunks
# runtime sur v0.32.0 est PROPRE, et la préimage est vérifiée : les deux
# fichiers patchés de l'image de base sont byte-identiques au tag v0.32.0
# (sha256 cb16cc92… / 16ed7ca9…).
#
# Greffe (3 fichiers runtime, tests/docs de la PR non embarqués) :
#   - models/lfm3.py                    : NOUVEAU (391 lignes, PR entière)
#   - models/registry.py                : +1 ligne ("Lfm3ForCausalLM")
#   - layers/mamba/ops/causal_conv1d.py : kernel width-7 (fwd + update)
#
# Retirer cet overlay dès qu'une release upstream porte #64959 (ou équivalent).

FROM vllm/vllm-openai@sha256:befccf0e7e4089aa23926bb6f887a85c0d46c2a99e6de5c5ffdf5cb7957c5b34
COPY vllm/model_executor/models/lfm3.py /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/lfm3.py
COPY vllm/model_executor/models/registry.py /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/registry.py
COPY vllm/model_executor/layers/mamba/ops/causal_conv1d.py /usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/mamba/ops/causal_conv1d.py
RUN python3 -m compileall -q /usr/local/lib/python3.12/dist-packages/vllm/model_executor/models/lfm3.py \
 && python3 -c "\
from vllm.model_executor.models.registry import _VLLM_MODELS; \
assert _VLLM_MODELS.get('Lfm3ForCausalLM') == ('lfm3', 'Lfm3ForCausalLM'); \
import vllm.model_executor.models.lfm3; \
import vllm.model_executor.layers.mamba.ops.causal_conv1d as c1d; \
assert hasattr(c1d, 'causal_conv1d_fn') and hasattr(c1d, 'causal_conv1d_update')"
LABEL org.myia.overlay="v0320-lfm3" org.myia.base="vllm/vllm-openai:v0.32.0" org.myia.upstream="vllm-project/vllm PR #64959 (lfm3/text-model)"
