# Fenêtre A+B — granularité du prefix cache + état mamba fp16 (2026-09-11)

Origine : issue [jsboige/vllm#36](https://github.com/jsboige/vllm/issues/36), items 1 et 2, après
l'étude du stack [syv-ai/qwen38-27b-rtx3090](https://github.com/syv-ai/qwen38-27b-rtx3090).
GO user : « Go et Go pour la suite ».

## Le problème mesuré (avant)

Le prefix caching du profil par défaut **ne cachait rien sous la taille de bloc physique** :

| Sonde (même moteur, avant) | cold | repeat | hits |
|---|---|---|---|
| 7 699 tokens | 1,044 s | 0,412 s | +5 536 = 2 × 2768 (2 blocs sur 3) |
| 403 tokens | 0,178 s | 0,192 s | **+0** — aucune accélération |

Cause : `mamba_cache_mode='align'` par défaut (posé par `MambaModelConfig` dès que le prefix caching
est actif, `model_executor/models/config.py:622-649`) aligne `mamba_block_size` sur `block_size`, et
sans `--prefix-match-unit` les clés de cache sont calculées **au bloc** (2768 tokens). Résultat en
prod : `prefix_cache_queries_total=520 101 / hits=0` (mesuré la veille).

## Le changement

Deux flags ajoutés au profil `medium-qwen36-stock-tq.yml` :

```
--prefix-match-unit 16            # granularité de matching, était block_size (2768)
--mamba-ssm-cache-dtype float16   # état ssm SEULEMENT (le conv reste 'auto')
```

Écarté après lecture du source : `--enable-mamba-fine-grained-prefix-cache` — il ne s'active
qu'avec EAGLE/MTP sur le groupe mamba (`config/cache.py:198-203`) et nous ne faisons pas de
spec-decode ; il aurait été inerte.

## Le résultat (après, même nuit)

| Sonde | cold | repeat | hits |
|---|---|---|---|
| 7 699 tokens | 1,543 s | **0,078 s** | +7 696 = **tout le prompt** |
| 403 tokens | 0,185 s | 0,181 s | **+400** = 25 × 16 |

La sonde courte est le cas réaliste (OWUI/Roo) : **0 → 400 hits** sur 403 tokens. La latence de la
sonde courte ne bouge pas visiblement (0,181 s) parce que son prefill est déjà dominé par d'autres
coûts — c'est le compteur qui prouve le mécanisme, et le prompt long qui montre le gain (0,412 →
0,078 s, ×5,3).

Signal fort : les 16 requêtes concurrentes de la batterie, qui **partagent un prompt de 3 200
tokens**, passent de 527 à **1 008 tok/s** au second passage (+91 %) — c'est exactement le cas
« 64 requêtes partageant un system prompt : 222 s → 17 s » du playbook syv-ai, reproduit ici.

## Effets de bord mesurés

- `block_size` **2768 → 1424** : la taille de bloc physique re-dérive de l'unité de matching
  (alignement de page TQ). `num_gpu_blocks` 360 → 688, `kv_cache_size_tokens` 934 374 → **944 267**
  (+1,1 %), `kv_cache_max_concurrency` 3,564 → 3,602. Net positif.
- Avertissement au boot (attendu, documenté) : le config HF demande `float32`
  (`model_executor/models/config.py:799` → « Using the user-specified value »). Choix délibéré :
  syv-ai mesure une perplexité inchangée à 3 décimales, et c'est l'état ssm qui borne la
  concurrence des hybrides.

## Validation

- **13/13 gates PASS** — prefill 8 363 / 7 312 / **5 704** tok/s (30K/95K/235K, meilleur que la
  référence 5 448 du 09-01), survie OK après chaque, vision/tool-calling/thinking/preserve_thinking OK.
- Scan d'erreurs ciblé sur le segment vivant (`Workspace is locked|turboquant_attn|EngineDead|out of
  memory|Traceback`) : **0**.
- Bench concurrence (prompts distincts) : N=4 196→212, N=8 395→**438**, N=12 587→605,
  N=16 799→**766** (−4,2 %). Un seul point en léger recul, la majorité en hausse → dans la variance
  machine documentée (débit sensible à l'uptime/CPU hôte), **pas de régression systématique**.

## Fenêtre

Coupure 2026-09-11T21:16:52Z → moteur healthy 21:21Z (boot ~4 min, volume compile-cache conservé).
Rollback = retirer les 2 lignes du profil + `compose down && up -d --env-file myia_vllm/.env`.

## Suites

- Le gain réel se lit désormais sur `prefix_cache_hits_total` en prod (était 0 %) — à suivre au
  prochain cycle de surveillance, en gardant à l'esprit que 84 % du trafic est la sonde décodage
  24-tokens du watchdog (sous tout seuil de matching).
- Le gain #36-item-1 (fp16 ssm) reste borné : ~15 MiB/slot/GPU, utile surtout si la concurrence monte.
