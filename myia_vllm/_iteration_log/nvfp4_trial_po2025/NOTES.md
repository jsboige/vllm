# Essai quant NVFP4 tiers — FrogNano-4B sur po-2025 (tier mini)

**Date** : 2026-10-08 · **Siège** : po-2025 (RTX 3080 Ti Laptop 16 Go, **SM 8.6**, i9-12900HK, 64 Go)
**Mandat** : user, 08/10 — « Go pour tout ça (et pour le quant dès maintenant si tu veux bien) »
**Issue** : jsboige/vllm#70 (suivi unique du siège)
**Verdict** : **ADOPTÉ** — profil canonique promu, BF16 conservé en rollback armé.

---

## 1. Pourquoi ce checkpoint plutôt que notre quant maison

Le plan d'origine était un AWQ W4A16 maison (llmcompressor, ViT exclue). **Prérequis absents** sur cette
machine : pas d'environnement `llmcompressor`, pas de script de calibration FrogNano. Un checkpoint
**déjà quantifié** a donc été essayé : `capyctl/FrogNano-4B-2609-NVFP4`.

- `base_model` = `microsoft/FrogNano-4B-2609` (vérifié via l'API HF) — **bon modèle de base**.
- Licence MIT (le tag HF est cohérent avec le corps de la carte).
- Producteur : modelopt **0.47.0**, `MIXED_PRECISION` — MLP (`gate/up/down_proj`) en **NVFP4
  group_size 16**, projections attention + GatedDeltaNet en **FP8**, reste BF16.
- `model.safetensors` = 5 121 400 768 o ; **5 144 565 972 o** mesurés en cache après téléchargement
  (vérifié au byte — pas le stub silencieux déjà vu ailleurs sur bind 9p).
- **Dépôt de 4 jours, 35 téléchargements, aucune vérification indépendante** → traité comme un essai.

## 2. La décision du 06/10 était trop large — et c'est ça qui a débloqué l'essai

Le paysage des 17 quants communautaires classait « NVFP4 (Blackwell) » comme inexploitable, sur
l'hypothèse **« NVFP4 ⇒ tensor cores Blackwell »**. Vérifié le 08/10 **dans notre propre image**
`vllm/vllm-openai:v0.31.0`, sans GPU :

| Contrôle | Résultat |
|---|---|
| `marlin_utils_fp4.py:34` `is_fp4_marlin_supported()` | `has_device_capability(75)` → **SM 8.6 passe** |
| `marlin_utils_fp8.py:31` (même garde) | `has_device_capability(75)` → **passe** |
| arches compilées dans l'image | `sm_75, sm_80, sm_86, sm_90, sm_100, sm_120` |
| cubins `sm_86` dans `_C_stable_libtorch.abi3.so` | **49** |

Le producteur écrit lui-même, sur son GPU de mesure (RTX 4090 Laptop, **SM 8.9**) : « that GPU has no
FP4 tensor cores, so every engine ran the NVFP4 layers as FP4 weights with BF16 activations
(**W4A16**) ». Même classe de situation, une génération au-dessus → essai justifié.

## 3. Boot (244 s jusqu'à `/health` 200, **0 erreur**)

```
quantization=modelopt_mixed                                    (auto-détecté)
Using MarlinNvFp4LinearKernel for NVFP4 GEMM
Selected MarlinFP8ScaledMMLinearKernel for {MergedColumnParallel,RowParallel,QKVParallel}Linear
WARNING marlin_utils_fp8.py:108  GPU has no native FP8 support → weight-only via Marlin
WARNING marlin.py:34             GPU has no native FP4 support → weight-only via Marlin
Model loading took 4.2 GiB memory and 60.5 s
Graph capturing finished in 6 s (puis 4 s)   ← PAS d'échec de capture
GPU KV cache size: 208,992 tokens, Maximum concurrency for 32,768 tokens per request: 6.38x
block_size 272 (= 16 × 17) → prefix-match-unit 16 reste divisible
```

**Le piège signalé par le producteur ne se reproduit pas sous vLLM** : il rapportait que sur SM 8.9
SGLang exigeait `SGLANG_DISABLE_SILU_FP4_QUANT_FUSION=1` (noyau fusionné SiLU+FP4-quantize sans build
SM 8.9 → capture CUDA graph en échec). Sous vLLM 0.31.0, **la capture de graphes réussit** du premier
coup, sans variable d'environnement.

## 4. A/B qualité (mêmes 5 prompts, greedy, `thinking=false`, `max_tokens=1024`)

Référence BF16 capturée sur le moteur de production **avant** l'arrêt (protocole identique).

| # | Sujet | BF16 | NVFP4 | Verdict |
|---|---|---|---|---|
| 1 | Fibonacci itératif | 75 tok, 34,9 t/s | 87 tok, 63,0 t/s | **correct** (NVFP4 ajoute une garde `ValueError`) |
| 2 | Somme de dict comprehension | 46 tok, 37,4 t/s | 43 tok, 71,7 t/s | **correct** — les deux disent 30 |
| 3 | Vitesse moyenne 240 km/3 h + 150 km/2 h | 210 tok, 43,1 t/s | 205 tok, 83,7 t/s | **correct** — mêmes 390 km / 5 h |
| 4 | SQL 2ᵉ salaire, gestion des ex æquo | 543 tok, 40,0 t/s | 582 tok, 82,7 t/s | **correct** — NVFP4 explicite les deux lectures |
| 5 | Raccourcir un texte français | 21 tok, 26,9 t/s | 12 tok, 46,2 t/s | **correct** |
| | **Cumul** | **22,6 s / 895 tok** | **11,7 s / 929 tok** | **~1,9×** |

**Aucune réponse n'est byte-identique** (attendu : les poids quantifiés changent le chemin
d'échantillonnage) mais **5/5 correctes des deux côtés**, qualité comparable. C'est une vérification
**par échantillon**, pas une mesure de perplexité — le producteur publie le même ordre de grandeur
(~20 prompts) et le dit explicitement.

## 5. Porte de concurrence — script du siège, critères fixés à l'avance

`myia_vllm/scripts/testing/frognano_gates_1632_po2025.py` (N=16 puis N=32, 128 tok, no-thinking).
Comparaison **même script, même machine**, référence du 07/10 05:07Z :

| Mesure | BF16 (07/10) | **NVFP4 (08/10)** | Δ |
|---|---|---|---|
| Warm-up 1 flux | 38,6 t/s | **60,7 t/s** | **×1,57** |
| N=16 agrégat | 561,6 t/s | **915,2 t/s** | **×1,63** |
| N=16 médiane/flux | 35,2 t/s | **58,8 t/s** | ×1,67 |
| N=32 agrégat | 938,0 t/s | **1 416,5 t/s** | **×1,51** |
| N=32 médiane/flux | 29,4 t/s | **44,8 t/s** | ×1,52 |
| Erreurs HTTP | 0 | **0** | = |
| Temp. max pendant la porte | 65 °C | **69 °C** | +4 °C |
| VRAM au repos | 12 198 MiB | **11 822 MiB** | −376 MiB |

**Critères pré-déclarés** (en-tête du script) : 0 erreur ✓ · temp soutenable < 85 °C ✓ (69 °C max) ·
médiane/flux ≥ 10 t/s ✓ (44,8 au pire) · `maxConcurrency` recommandé = N/2.
→ **N=32 propre ⇒ plafond recommandé 16**, ce qui correspond à ce que claudish pose déjà sur
l'endpoint `frognano` (8 → 16) au prochain redeploy.

**Contrat fonctionnel** : tool-calling vérifié sur NVFP4 — `finish_reason=tool_calls`,
`{"city": "Paris"}`, parser `qwen3_coder` + `--enable-auto-tool-choice` inchangés.

## 6. Le vrai gain : la capacité KV

| | BF16 | NVFP4 |
|---|---|---|
| Poids chargés | ~8,7 Gio (cache) | **4,2 GiB** |
| **KV cache** | 91 853 tok | **208 992 tok (×2,28)** |
| Conversations pleine longueur (32 768) | 2,80× | **6,38×** |

Le tout **dans le même encombrement VRAM** : la mémoire libérée par les poids est allée au cache KV,
pas perdue. C'est exactement le levier que la mission du siège cherchait (« haute vitesse,
disponibilité et **parallélisme** »).

**Pourquoi plus rapide alors que vLLM avertit d'une dégradation** : l'avertissement vise les charges
compute-lourdes (`--prefill`). Sur une carte **limitée par la bande passante**, décoder des poids 4×
plus petits accélère le *decode* — c'est ce que mesure la porte sur les deux régimes (1 flux et
32 flux).

## 7. Décision et rollback

**ADOPTÉ** (08/10). Profil canonique = `mini-frognano-4b-po2025.yml` (NVFP4).
Rollback armé = `mini-frognano-4b-po2025-bf16-rollback.yml` :

```
docker compose -f myia_vllm/configs/docker/profiles/mini-frognano-4b-po2025.yml --env-file myia_vllm/.env down
docker compose -f myia_vllm/configs/docker/profiles/mini-frognano-4b-po2025-bf16-rollback.yml --env-file myia_vllm/.env up -d
```

Les deux profils partagent le `container_name` (un seul stack tourne à la fois) et le volume de cache
de compilation — le rollback reste chaud.

## 8. Points ouverts (honnêtes)

1. **Profondeur de la preuve qualité** : 5 prompts + le contrôle du producteur. Suffisant pour un
   essai, pas pour une adoption « qualité verrouillée ». Une passe plus large (ex. le banc
   tool-calling du dépôt, ou un échantillon > 100 prompts comparés) reste à faire si le tier mini
   monte en charge externe.
2. **Checkpoint tiers** : dépôt de 4 jours, un seul auteur, aucune reproduction indépendante. Le
   rollback armé est la contre-mesure.
3. **Garde thermale SYSTEM toujours absente** : la tâche `GPU-Thermal-Governor-po2025` **n'existe
   pas** (vérifié 08/10) — le registre Q2 reste ouvert, il attend la fenêtre UAC unique du user. La
   porte a culminé à 69 °C, loin du cap de 88 °C, donc rien de bloquant ; mais toute charge
   **soutenue** reste conditionnée à ce garde-fou (non-négociable #1 du siège).
4. **Hygiène** : le secret du siège passe par `--api-key` en ligne de commande, donc lisible via
   `docker inspect`/`ps`. À basculer sur `VLLM_API_KEY` (variable d'environnement) au prochain
   redémarrage planifié.

## 9. Artefacts

- Profils : `configs/docker/profiles/mini-frognano-4b-po2025.yml` (canonique, NVFP4) +
  `…-bf16-rollback.yml` (rollback armé).
- Rapport de porte : `gate_nvfp4_20261008.json` + référence `gate_bf16_reference_20261007.json`
  (recopiés ici depuis `myia_vllm/_logs/`, qui est **gitignoré** — la copie versionnée est la
  seule qui survit).
- A/B : `ab_nvfp4_20261008.json` + `ab_bf16_reference_20261008.json`.
