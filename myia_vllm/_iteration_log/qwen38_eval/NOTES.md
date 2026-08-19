# Qwen3.8-27B AWQ-INT4 + MTP-3 — évaluation d'opportunité

**Statut :** en cours (pré-téléchargement lancé 2026-08-19, fenêtre GPUs 0,1 en attente).
**Décision évaluée :** remplacer / compléter le MoE Qwen3.6-35B-A3B (prod) par le dense Qwen3.8-27B.
**PR :** [jsboige/vllm#16](https://github.com/jsboige/vllm/pull/16) — profil + batterie.

## Pourquoi

- Benchs massifs vs génération 3.6 (tier dense ≈ notre MoE) : SWE-bench Pro 61.7 vs 53.5,
  Terminal Bench 2.1 73.0 vs 63.4, QwenSWEBench 79.0 vs 49.3, OSWorld 84.3 vs 63.9,
  IFBench 79.5 vs 69.1, DeepSWE 42.2 vs 13.3. Apache-2.0.
- Feature-parité + vidéo native + `reasoning_effort` adaptatif (xhigh/medium/low).
- MTP head entraînée dans le checkpoint → spec-dec « gratuit » si la head survit au quant.
- `cyankiwi/Qwen3.8-27B-AWQ-INT4` : head MTP + vision + lm_head + GDN in_proj en BF16
  (vérifié dans config.json `ignore`) — la recette qui préserve l'acceptance en 4 bits.
- Stack : image stock v0.27.1 inchangée (transformers 5.15.0 ≥ 5.8.0 ; classes `qwen3_5`).

## Le coût attendu (à mesurer, pas supposer)

Concurrent N=16 : dense 27B estimé 200–350 tok/s vs MoE 956. MAIS concurrence réelle
mesurée (2026-08-19, fenêtre 5 j) : 15 977 req, ~8 tok/s de moyenne, 0 préemption,
0 attente-capacité → le coût dense est un coût d'échelle future, pas du présent.

## Correcteur TurboQuant (décision KV = fp8, TQ = variante B)

`turboquant_k8v4 × MTP` n'est PAS prouvé sur stock : #40831 (ngram) et #40880
(MTP × CUDA-graph, hybride) clos par l'arbre Genesis (P65/P66/P64/P68/P69), pas
upstream. Mode de défaillance = sortie dégénérée SILENCIEUSE qui passe tous les
health checks → le canary qualité de validate38.py est obligatoire pour toute
config spéculative. fp8 seul couvre ~2× la fenêtre (16/64 couches d'attention).

## Gate

Batterie : [`validate38.py`](validate38.py) (adaptée de phase 2 + mtp-acceptance +
canary + single-stream). Contre-référence A/B : le MoE 3.6 re-déployé la MÊME
soirée, même batterie (validate.py original).

## Chronologie

| heure (UTC) | événement |
|---|---|
| 2026-08-19 | GO utilisateur. Recherche (modèle/quants/recette/DFlash2/TQ-forensics). PR #16. Pré-download lancé (21 G, conteneur CPU-only, prod intacte). |

## Résultats

*(à remplir pendant la fenêtre)*
