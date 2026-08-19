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
| 2026-08-19 | GO utilisateur. Recherche (modèle/quants/recette/DFlash2/TQ-forensics). PR #16. Pré-download 21 G (conteneur CPU-only, prod intacte). |
| 08-19 10:31 | Pile 3.6 down (propre). Pile 3.8 up. |
| 08-19 10:37 | **Boot OK en 4 min 20 s** (health 200, RC=0) — dense 27B plus léger que le MoE, compile plus courte. KV : **342 691 tokens = 1,31× fenêtre** (⚠️ très en deçà de Todd 560 900 — mais lui à gpu-util 0.95 et max-num-seqs 4, nous 0.70/16). VRAM GPU0 20,0 / GPU1 19,2 GiB. `Qwen3_5MTP` résolu, drafter chargé. |
| 08-19 10:39–10:44 | **Batterie 17/17 effectif** (le seul FAIL = bug du canary v1 : `'132'` correct de 3 car échouait le seuil >30 — corrigé, re-PASS). |

## Résultats batterie (2026-08-19 10:39Z, machine même-journée)

| Gate | Résultat | Détail |
|---|---|---|
| smoke | PASS | 0,43 s → 'OK' |
| canary (v2) | PASS | 3 prompts sains, ratio 4-gram max 0,00 — **aucune dégénérescence** (fp8+MTP sain) |
| vision | PASS | 2,1 s, **4/4 couleurs** |
| tool-calling | PASS | 0,6 s → get_weather(Lyon) |
| thinking | PASS | 5,1 s, 391 trouvé, effort low |
| preserve_thinking | PASS | '7' |
| **mtp-acceptance (1ᵉʳ)** | **PASS** | **0,82** (446/543) — bande officielle FP8/NVFP4 ; head BF16 de cyankiwi drafter très bien |
| prefill-30k | PASS | 31 417 tok / 16,7 s → **1 879 tok/s** |
| prefill-95k | PASS | 101 838 tok / 60,4 s → 1 685 tok/s |
| prefill-235k | PASS | 253 503 tok / 192,6 s → **1 316 tok/s** + survie |
| single-stream | PASS | **37/36/43 t/s** (temp 0.7, no-think) — ⚠️ moitié de Todd 84 (2×3090 !) |
| concurrent-N16 (froid) | PASS | 164 tok/s |
| concurrent-N16 (chaud) | PASS | **376 tok/s** agrégé, 0 échec |
| mtp-acceptance (cumulé) | PASS | 0,48 (4 683/9 801) — retombe sous charge/temp 0.7 |

### Lecture

- **MTP fonctionne réellement** : 0,82 au premier passage, head BF16 intacte (le piège #3 est évité). Acceptance cumulée 0,48 sous charge chaude/temp 0.7.
- **Single-stream 43 t/s = décevant** : Todd mesure 84 t/s sur 2×**3090** avec le même modèle W4A16+MTP. Nos 4090 devraient faire mieux, pas 2× moins. Hypothèses à tester plus tard : (1) **AWQ group_size 32 (cyankiwi) vs 128 (Todd)** — surcoût de déquant Marlin 4× ; (2) le warning `max_num_scheduled_tokens=4096` du spec-dec ; (3) harness différent.
- **Concurrent N=16 376 t/s** : dans l'estimation 200–350 (légèrement au-dessus) — le coût dense attendu, à confronter au 3.6 même-journée.
- **KV 342 691 = 1,31× fenêtre** : UNE requête 262K à la fois. Pour le scénario « traces agentiques longues concurrentes », fp8@0.70 ne suffit pas → soit gpu-util ↑ (marge VRAM GPU0 ≈ 4,5 GiB), soit **TurboQuant** (variante B + canary obligatoire), soit les deux.

*(A/B 3.6 même-journée : à remplir après le swap retour.)*
