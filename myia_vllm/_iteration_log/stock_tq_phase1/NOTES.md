# Phase 1 — vLLM upstream stock + TurboQuant k8v4, sans Genesis

**Date :** 2026-08-10
**Machine :** myia-ai-01, **GPU 2 uniquement** (réservée via dashboard CoursIA, prod GPUs 0,1 intacte)
**Statut :** terminé — **succès** (GPU 2 rendue à CoursIA ; phase 2 en attente d'un GO séparé)

## Question posée

Peut-on abandonner l'arbre de patches downstream **Genesis** et revenir à une image vLLM **stock** ?

La prod tourne sur `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` uniquement parce que
[vllm#41726](https://github.com/vllm-project/vllm/issues/41726) — `AssertionError` à
`turboquant_attn.py:720:_continuation_prefill` (« Workspace is locked but allocation …
requires 29.73 MB, current size is 16.31 MB ») — faisait crasher l'EngineCore au premier
prefill de continuation avec `--kv-cache-dtype turboquant_k8v4`. Genesis P22+P38 corrige
exactement ça.

Enjeu réel = **robustesse, pas perf** : l'image de prod est *irreproductible* (sa base
`vllm/vllm-openai:nightly-01d4d1ad3…` a été GC'd de Docker Hub, rétention ~5 j). Une image
stock basée sur un tag **release** (non GC'd) supprimerait cette fragilité.

## Ce qui a changé depuis notre dernier test (2026-05-06)

4 bugfixes TurboQuant mergés upstream :

| PR | Date | Titre |
|---|---|---|
| #44053 | 2026-06-23 | [Bugfix][V1][TurboQuant] Reserve workspace before CUDA graph capture |
| #47609 | 2026-07-05 | [Bugfix][TurboQuant] Preserve KV cache dtype in backend shape |
| #39988 | 2026-07-10 | [Bugfix] Fix turboquant FP8 cast failure for BF16 models on Ampere GPUs |
| #50533 | 2026-07-31 | [Bugfix][TurboQuant] Add KV quant mode for turboquant |

Les 4 sont dans `v0.27.0` (taggée 2026-08-07 ; **image pas encore publiée** au 08-10).
Les fixes candidats historiques #40798 et #39995 sont **CLOSED non-mergés**.

Par ailleurs #41726 reste **OPEN**, mais un commentaire du 2026-08-06 (BenjaminGittins)
rapporte le crash **non reproduit** sur 115 runs / vLLM 0.24.0 — avec des réserves fortes :
Blackwell **sm_120** (nous : Ada **sm_89**), Qwen3.5-**9B NVFP4** (nous : 35B-A3B AWQ MoE),
et l'auteur refuse explicitement de conclure à un fix.

## Pourquoi un petit modèle sur une seule carte suffit

Le bug **n'est pas spécifique au modèle** : bissecté upstream sur Qwen3-4B et
Llama-3.1-8B, et reproduit par des tiers sur un 9B. Notre modèle de prod
(~22 GiB de poids, TP=2) ne tient pas sur une seule 4090 — inutile, un proxy fidèle suffit.

**Proxy retenu : `cyankiwi/Qwen3.5-9B-AWQ-4bit`**, qui partage les 4 propriétés
qui comptent avec la prod :

| Propriété | Prod (35B-A3B) | Proxy (9B) |
|---|---|---|
| Attention hybride GDN + full | 10 full / 40 | **8 full / 32** (`full_attention_interval: 4`) |
| Quantification | compressed-tensors AWQ 4-bit | **idem** (même auteur `cyankiwi`) |
| Classe vLLM | `Qwen3_5MoeForConditionalGeneration` | `Qwen3_5ForConditionalGeneration` |
| `model_type` | `qwen3_5` | `qwen3_5` |

Différence assumée : dense au lieu de MoE (pas d'EP, pas de Marlin MoE). Le chemin
`_continuation_prefill` de TurboQuant n'en dépend pas.

## Protocole

Le crash d'origine survenait **au premier prefill de continuation**, c.-à-d. dès qu'un
prompt dépasse `--max-num-batched-tokens` et se fait découper en chunks. On force donc
ce chemin : `--max-num-batched-tokens 4096` + prompt ~30 K tokens ⇒ ~8 chunks.

1. **Contrôle** — même config en `--kv-cache-dtype fp8` : doit passer. Valide le harnais.
2. **Test** — `--kv-cache-dtype turboquant_k8v4` : c'est la manip.
3. Chaque run : boot, puis prompt ~30 K, puis un second prompt court (vérifie que le
   moteur survit et ne s'est pas wedgé).

**Critère de succès :** les deux requêtes aboutissent, et `docker logs` ne contient ni
`turboquant_attn.py`, ni `Workspace is locked`, ni `EngineDeadError`.

## Résultat

**Verdict : le crash ne se reproduit PAS sur stock upstream. Le blocage de 2026-05-06 est levé
sur cette architecture.**

Image testée : `vllm/vllm-openai:nightly-b22afe45ac797ae58e67a7a3ad79ee5714024420`
(moteur `v0.26.1rc1.dev542+gb22afe45a`, torch 2.13.0+cu130, transformers 5.14.1).
Les 4 PR du tableau ci-dessus sont confirmées **ancêtres git** de `b22afe45a` — c'est bien
une image qui les contient toutes, pas une supposition de date.

| | Contrôle `fp8` | Test `turboquant_k8v4` |
|---|---|---|
| Boot | OK | OK — `Using TURBOQUANT attention backend out of potential backends: ['TURBOQUANT']` |
| Prefill 31 376 tokens, `Prefix cache hit rate: 0.0%` | **OK** (112,6 s à froid) | **OK** (304,9 s à froid) |
| Requête courte après coup (survie moteur) | OK 0,1 s | OK 0,2 s |
| `Workspace is locked` / `turboquant_attn.py` / `EngineDeadError` | **0** | **0** |
| KV cache | 598 016 tokens (14,60×) | **812 373 tokens (19,83×)** — +36 % |

Le chemin fautif a bien été emprunté : `enable_chunked_prefill=True` confirmé dans le dump de
config du moteur, `max_num_batched_tokens=4096` avec un prompt de 31 376 tokens ⇒ ~8 chunks à
`q_len ≈ 4096`, très au-dessus de `_CONTINUATION_DECODE_THRESHOLD = 128` qui aiguille vers
`_continuation_prefill`. C'est exactement la configuration qui tuait l'EngineCore le 2026-05-06.

Le correctif visible dans la source (`turboquant_attn.py`, PR #44053) est une réservation
d'espace **à la construction** du backend (`_reserve_workspace()`), dimensionnée sur
`max_model_len`, au lieu d'une croissance de workspace tentée après verrouillage. Coût VRAM
calculable : `2 × num_kv_heads × max_model_len × head_size × 2 o`, soit pour la prod
(`num_kv_heads=2`, `head_size=256`, TP=2, 262 K) ≈ **0,27 GB/GPU** — négligeable devant nos
~3,4 GB de marge à gpu-util 0.70.

### Débit prefill : équivalent à chaud

À chaud, sur prompts à préfixes uniques (0 % de cache) : **TurboQuant 8214 tok/s**,
**fp8 7900 / 8282 / 8311 puis 7968 / 8065 / 8043 tok/s**. Pas de pénalité mesurable.

TurboQuant paie en revanche un **JIT Triton à froid** — descente 328 s → 187 s → 3,8 s sur les
trois premiers prompts, avec l'avertissement explicite du moteur
(`Triton kernel JIT compilation during inference: _tq_full_dequant_kv. This causes a latency
spike`). Conséquence pour la phase 2 : les premières requêtes après un boot seraient très
lentes, et la grâce de warm-up du watchdog v5 (3 sondes à 120 s) pourrait ne pas suffire.

### Deux réserves d'honnêteté sur ce banc

1. **Stalls intermittents non expliqués, indépendants du dtype.** En milieu de série fp8, cinq
   requêtes identiques sont passées à 35,9 s / 154,4 s / 185,3 s / 155,2 s / 122,3 s, puis sont
   revenues d'elles-mêmes à 3,9 s. Pendant ces épisodes le moteur affiche
   `Running: 1 reqs, Avg prompt throughput: 0.0 tokens/s` — c'est un **gel**, pas un calcul lent.
   Comme le phénomène frappe aussi fp8, la « descente JIT » de TurboQuant est partiellement
   confondue avec lui (les avertissements JIT sont réels, leur amplitude exacte ne l'est pas).
   **Aucune conclusion de perf par dtype n'est défendable au-delà de « équivalents à chaud ».**
2. **`nvidia-smi` côté hôte est aveugle à ce conteneur.** GPU 2 affiche **152 MiB** y compris
   *pendant* un prefill à 8000 tok/s. Le garde-fou de [run.sh](run.sh) (`abort si > 500 MiB`)
   **ne peut donc pas** détecter un entraînement CoursIA concurrent : à remplacer avant toute
   réutilisation (inventaire des conteneurs, ou accord explicite sur le dashboard).

## ⚠️ Incident prod pendant la fenêtre de test (13:20:47Z → 15:02:02Z, ~1 h 41, **5 restarts**)

> **Correction 2026-08-11.** La première rédaction annonçait « 14:17:34Z → 15:02:02Z, ~44 min,
> trois restarts ». Elle reposait sur un `docker logs --since 60m` qui ne couvrait que
> 14:00Z→15:00Z. La fenêtre 12 h de la surveillance a révélé **deux restarts antérieurs**
> (13:21:57 et 13:56:03). La chronologie ci-dessous est la bonne ; elle **resserre** la
> corrélation avec mon test au lieu de la desserrer (voir « responsabilité » plus bas).

La prod (GPUs 0,1) a été indisponible pendant une grande partie du test. **Cinq restarts watchdog :**

| Heure (UTC) | Événement |
|---|---|
| **13:19:04** | *(repère)* premières lignes de log de **mon** conteneur de banc sur GPU 2 |
| 13:20:47 / 13:21:57 | `WEDGE health=200 decode=000 (24 tok >40s)` 1/2 puis 2/2 → **RESTARTING (1ᵉ)** |
| 13:39:51 → 13:40:52 | `ENGINE-HUNG … docker=unhealthy` 1/4 → 3/4 (boot laborieux, n'atteint pas 4) |
| 13:54:53 / 13:56:03 | `WEDGE health=200 decode=000` 1/2 puis 2/2 → **RESTARTING (2ᵉ)** |
| 14:17:34 / 14:18:44 | `WEDGE health=200 decode=000` 1/2 puis 2/2 → **RESTARTING (3ᵉ)** |
| 14:40:15 → 14:41:45 | `ENGINE-HUNG … docker=unhealthy` 1/4 → 4/4 → **RESTARTING (4ᵉ)** |
| 14:51:54 / 14:54:24 | `WARMUP … decode=000` puis `decode=500` (grâce v5, non comptés en wedge) |
| 14:56:03 → 14:57:33 | `ENGINE-DOWN host=000 internal=000 docker=healthy` ×4 |
| 14:58:03 | `ENGINE-HUNG … docker=unhealthy` → **RESTARTING (5ᵉ)** |
| 15:02:02 | health **200**, decode 200 en 0,79 s, RC=0, `healthy` — KV 1 238 046, boot nominal en ~3 min |

**Non causes, écartées sur preuve :** 0 `out of memory` depuis le boot ; cache HF à **47 G**
(donc pas de phantom mount) ; RAM hôte 73 GB libres sur 191 GB (pas d'épuisement WSL).

**Ma responsabilité n'est ni établie ni écartée — mais la chronologie corrigée l'aggrave.**
Le premier wedge tombe **1 min 43 après** le démarrage de mon conteneur de banc (13:19:04 →
13:20:47). La version initiale de ces notes affirmait au contraire qu'il tombait « dans un creux
où mon conteneur était inactif » : c'était un artefact de la fenêtre de logs tronquée, et
cette affirmation est **retirée**. Les échecs de boot suivants (14:41, 14:58) restent
concomitants des gels de mon propre conteneur (14:44 → 14:58), et la prod n'a réussi son boot
qu'une fois la GPU 2 libérée. Deux moteurs vLLM malades dans la même fenêtre continue
d'orienter vers une cause **hôte** plutôt que GPU — mais un simple « c'est indépendant » n'est
plus soutenable.

**Hypothèse principale (non prouvée) : pagination WDDM sur GPU 0.** Avant l'incident, GPU 0 a
été relevée à **22 966 – 23 386 MiB / 24 564** — au-dessus du seuil d'alerte 23 000 de la
procédure de surveillance, consommée par le bureau Windows (`explorer`, 2× `msedgewebview2`,
`StartMenuExperienceHost`, `SearchHost`, `asus_framework`). C'est exactement le mécanisme
documenté qui écroule le décodage et imite un wedge. Il est indépendant du test.

**Conséquence pour la phase 2 :** ne pas lancer tant que GPU 0 n'est pas redescendue
franchement sous 23 000 MiB, et ne plus faire tourner un second moteur vLLM en parallèle de
la prod même sur une carte séparée.

## Suites

Phase 1 étant un **succès**, la suite serait la phase 2 — **qui n'a PAS de GO** :

- Fenêtre prod 1 h 30 – 2 h, créneau mesuré **10 h–14 h locale un week-end** (hors des pics
  d'agents toutes les 6 h à 01/07/13/19Z, qui portent aussi les payloads > 50 KB).
- TP=2 sur GPUs 0,1, vrai modèle 35B-A3B MoE, 262 K, image **release** `v0.27.0` dès sa
  publication (les tags release ne sont pas GC'd — c'est tout l'intérêt : reproductibilité).
- Ce que la phase 1 ne dit **pas** et que seule la phase 2 tranchera : MoE + EP=2 + Marlin,
  `max_model_len` 262 144 (Gittins signale par ailleurs un bug d'ordonnancement à cette
  frontière exacte), et le comportement sous trafic réel multi-tenant.
- Pré-requis avant de la lancer : ramener GPU 0 sous les 23 000 MiB (bureau Windows), et
  prévoir que le JIT TurboQuant à froid peut faire tomber les premières sondes du watchdog.

Rollback de la phase 2 = l'image Genesis actuelle, sauvegardée dans `D:\vllm_image_backups\`.
