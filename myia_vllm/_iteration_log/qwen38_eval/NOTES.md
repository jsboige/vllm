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

### A/B même-journée (08-19, 3.6 restauré 11:04Z, batterie validate.py 11:08Z, 13/13 PASS)

| Métrique | Qwen3.8-27B AWQ+MTP-3 fp8 | Qwen3.6-35B-A3B TQ (prod) | Référence 3.6 du 08-14 |
|---|---|---|---|
| Boot (chaud/vierge) | **4 min 20 s** (volume compile vierge !) | 8 min 20 s (chaud) | ~8 min |
| Vision | 2,1 s, 4/4 | 4,3 s, 4/4 | — |
| Tool calling | **0,6 s** | 1,9 s | 0,47 s |
| Thinking (17×23) | **5,1 s** (effort low) | 15,1 s (défaut) | — |
| Single-stream (no-think, 300 tok) | 43 t/s max | 47 t/s max | **~120 t/s** |
| **Concurrent N=16 (chaud)** | **376 t/s** | 213 t/s | **956 t/s** |
| Prefill 30K | 1 879 tok/s | 3 957 tok/s | 5 346–8 177 |
| Prefill 253K | 1 316 tok/s | 3 375 tok/s | ~4 300 |
| KV tokens | 342 691 (**1,31× fenêtre**) | 1 030 407 (3,93×) | idem |

### ⚠️ Le biais qui domine la lecture : la machine, encore

Les DEUX modèles sont aujourd'hui à ~1/3 de leurs références du 08-14 (3.6 : 47 vs ~120 single, 213 vs 956 N=16 ; 3.8 : 43 vs 84 Todd-sur-3090). suspect initial = training CoursIA sur GPU 2 (9,1 GiB, absent le 08-14)… **mais à la capture post-batterie le job est IDLE (210 MHz, 2 %, 32 W)** — contention affaiblie, pas exclue (état pendant la batterie inconnu). Nouveau point pour l'enquête machine ouverte : le 08-19 les deux stacks dégradent ENSEMBLE.

Ce que l'A/B d'aujourd'hui prouve quand même (mêmes conditions pour les deux) :
- **N=16 chaud : le dense 3.8+MTP a battu le MoE (376 vs 213)** — inimaginable à machine saine, mais c'est la mesure du jour. Le MTP aide le dense sous charge là où le MoE est étranglé par la machine.
- **Prefill : le MoE gagne nettement (×2,3–2,6)** — 3B actifs vs 27B, structurel. Pour les charges 253K, 193 s vs 75 s.
- **Latences fonctionnelles : le 3.8 gagne partout** (vision 2×, tools 3×, boot 2×).

### Verdict de fenêtre (provisoire — A/B contaminé par l'état machine)

1. **Remplacement immédiat : NON.** On ne remplace pas le MoE sur la base d'un jour où il est à 22 % de sa mesure de la semaine dernière ; ses chiffres sains (956 N=16, 120 single) restent la référence de capacité.
2. **Le 3.8 est un excellent candidat** — fonctionnellement supérieur (reasoning_effort, vidéo, latences), MTP validé (0,82), stable 17/17. À re-mesurer à machine saine (GPU 2 libre) pour des chiffres propres : single-stream vrai, N=16 vrai, et l'hypothèse group_size 32 vs 128 (43 vs 84 t/s Todd) mérite un quant GS-128.
3. **Le chemin qualité**: GSM8K/IFEval/MMStar sur le harness local — non exécutés ce jour (fenêtre), à programmer au prochain run.
4. **KV 1,31× est le vrai goulot structurel** pour « traces agentiques longues » : gpu-util ↑ (≈4,5 GiB libres/GPU) et/ou variante TQ (canary obligatoire).
