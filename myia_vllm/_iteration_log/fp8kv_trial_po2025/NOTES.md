# Essai fp8 KV sur le moteur NVFP4 — FrogNano-4B sur po-2025 (tier mini)

**Date** : 2026-10-08 après-midi · **Siège** : po-2025 (RTX 3080 Ti Laptop 16 Go, SM 8.6)
**Mandat** : user 08/10 — « maximiser le service multi-agents sans starving les machines », puis « OK pour ta reco / Go pour les tests immédiats »
**Issue** : jsboige/vllm#70 · **Proposal + annonce de fenêtre** : dashboard workspace-vllm (08/10 ~13:45 locale)
**Verdict** : **ADOPTÉ** — fp8 KV promu ; **tier RAM refusé** (garde anti-starvation) ; gpu-util inchangé.

---

## 1. Ce qui a été testé et pourquoi

La PROPOSAL du 08/10 (~13:40 locale, mandat user) classait trois leviers. Celui-ci est le
test du levier 1 : `--kv-cache-dtype fp8` sur le moteur NVFP4 promu le matin même. **Un seul
drapeau** de différence avec la production d'alors — vérifié au diff compose (1 occurrence de
`--kv-cache-dtype` dans l'essai, 0 dans le canonique). Hypothèse : KV 32 → 16 Ko/tok ⇒ ~×2
tokens à VRAM égale. Inconnu : **SM 8.6** — la prod familiale de référence (ai-01,
Swift-1.5-27B, hybride GDN même lignée, W4A16 + FP8 KV + mamba fp16) est en SM 8.9, et
l'échange perf ai-01 du 06/10 disait exactement « fp8 KV SM 8.6 = à tester en fenêtre, le boot
parle en 30 s ».

## 2. Boot — verdict propre (fenêtre 13:43→13:46 locale, ~3 min)

```
Selected MarlinFP8ScaledMMLinearKernel for MergedColumnParallel/RowParallelLinear
Using FLASHINFER attention backend out of potential backends: ['FLASHINFER', 'TRITON_ATTN']
GPU KV cache size: 391,748 tokens, Maximum concurrency for 32,768 tokens per request: 11.96x
Graph capturing finished in 5 secs / 3 secs      ← capture OK
health 200 ; 0 erreur
```

Le KV fait **391 748** et non les ~417 K théoriques (granularité de blocs + stockage des
scales) — ×1,87 réel. Aucun refus de backend : **le fp8 KV passe sur SM 8.6**, y compris
prefix caching et `--mamba-ssm-cache-dtype float16` inchangés.

## 3. Portes de concurrence — script du siège, critères pré-déclarés

Comparaison **même script, même machine, même jour** contre la référence NVFP4-KV-auto du matin :

| Mesure | NVFP4 KV auto (matin) | **NVFP4 + fp8 KV** | Δ |
|---|---|---|---|
| **KV cache** | 208 992 tok | **391 748 tok** | **×1,87** |
| Concurrence pleine longueur (32K) | 6,38× | **11,96×** | |
| Warm-up 1 flux | 60,7 t/s | **74,9 t/s** | ×1,23 |
| N=16 agrégat | 915,2 t/s | **1 073,4 t/s** | **×1,17** |
| N=16 médiane/flux | 58,8 t/s | **67,5 t/s** | ×1,15 |
| N=32 agrégat | 1 416,5 t/s | **1 642,4 t/s** | **×1,16** |
| N=32 médiane/flux | 44,8 t/s | **51,7 t/s** | ×1,15 |
| Erreurs HTTP | 0 | **0** | = |
| Temp. max porte | 69 °C | **68 °C** | = |
| VRAM après | ~11,97 Gio | **~12,36 Gio** | ≈ |

Critères pré-déclarés : 0 erreur ✓ · temp < 85 °C ✓ · médiane/flux ≥ 10 t/s ✓ · 0 finish
non-stop ✓. **Contrat fonctionnel** : tool-calling OK (`finish=tool_calls`,
`{"city": "Paris"}`) · décode qualité OK sur les deux noms servis (problème de train résolu
correctement, réponse identique sur `mini` et `frognano-4b`).

**Le gain de débit n'était PAS l'hypothèse de départ.** Des KV deux fois plus petites à lire
par token allègent un decode limité par la bande passante — même mécanisme que la promotion
NVFP4 du matin, un cran de plus. Cumulé sur la journée : BF16 → NVFP4+fp8 KV = **N=16
561,6 → 1 073,4 t/s (×1,91), N=32 938,0 → 1 642,4 t/s (×1,75), KV 91 853 → 391 748 (×4,26)**.

## 4. Tier RAM offload — évalué et REFUSÉ (la décision « sans les affamer »)

Mesures pendant la fenêtre : **RAM hôte libre 7,2 Go** (14,2 le matin — vmmemWSL a grossi au
boot, 15,5/32 Go de plafond .wslconfig), garde du siège **≥4 Go libres**. Un tier conforme à
la règle ai-01 (≥1,5× le KV GPU ≈ 9 Go) enfoncerait la garde à pleine charge ; le maximum
« abordable » (~3 Go) serait **inférieur au KV GPU (6 Go) = puits write-only** (leçon ai-01 :
un tier plus petit que la cache GPU évictée ne rejoue rien). **Refusé**, à réévaluer seulement
si le socle RAM hôte change (fermeture d'applications, autre répartition). gpu-util 0,78
inchangé pour la même raison de prudence (GPU partagé desktop, leçons boot-OOM ai-01).

## 5. Décision et rollback

**ADOPTÉ** (08/10 après-midi). Profil canonique = `mini-frognano-4b-po2025.yml`
(NVFP4 + fp8 KV). Rollbacks :
- **1 pas** : `mini-frognano-4b-po2025-kvauto-rollback.yml` (NVFP4, KV auto/BF16 — la prod du matin) ;
- **2 pas** : `mini-frognano-4b-po2025-bf16-rollback.yml` (BF16 intégral — la prod d'avant le 08/10).
Les trois partagent `container_name` et volume de cache de compilation ⇒ retours chauds.

Le moteur d'essai n'a jamais été arrêté entre l'essai et la promotion : le conteneur qui
tournait pendant les gates EST la production (seuls les fichiers de profil ont tourné).

## 6. Points ouverts (honnêtes)

1. **Qualité fp8 KV** : décode spot-check + tool-calling + portes sans anomalie ; pas de
   passe de qualité large (même état que la promotion NVFP4 — registre **Q5**, qui couvre
   désormais les deux changements cumulés).
2. **Interaction FLASHINFER + fp8 KV sous charge longue** : le backend a été sélectionné
   proprement et les portes sont passées, mais pas de soak > 15 min. La vigie 4 h surveille.
3. **Précédent flotte utile** : SM 8.6 =validé⇒ le fp8 KV est transposable au siège jumeau
   po-2026 (embeddings, 3080 Ti SM 8.6) et à tout siège SM ≥ 8.0 qui hésitait — signalé dans
   la PROPOSAL.

## 7. Artefacts

- Profils : `configs/docker/profiles/mini-frognano-4b-po2025.yml` (canonique, fp8 KV) +
  `…-kvauto-rollback.yml` (1 pas) + `…-bf16-rollback.yml` (2 pas).
- Rapport de porte : `gate_fp8kv_20261008.json` + référence `gate_nvfp4_kvauto_reference_20261008.json`
  (recopiés depuis `myia_vllm/_logs/`, gitignoré).
- Proposal + annonce de fenêtre : dashboard `workspace-vllm` (`po2025-vllm-capacity-proposal-20261008`,
  `po2025-vllm-fp8kv-window-announce-20261008`).
