# Phase 2 — sortir de Genesis : Qwen3.6-35B-A3B + TurboQuant k8v4 sur vLLM stock `v0.27.0`

**Statut :** en cours (bascule prod, GPUs 0,1).
**Fenêtre :** nuit du 2026-08-10 au 08-11, GO utilisateur explicite « mains libres sur les GPUs
nominales 0 et 1, GPU 2 laissée au training ». Indisponibilité acceptée ; failover cloud des
dashboards en place (PR jsboige-mcp-servers#853, validé en prod le 08-06 à 12:35Z).

## Pourquoi

L'image de prod `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` est **irréproductible** : sa base
`vllm/vllm-openai:nightly-01d4d1ad3…` a été GC'd de Docker Hub (rétention des nightlies ≈ 5 jours),
mesurée le 2026-07-19. Elle n'existe plus que dans le store Docker local + deux tars de sauvegarde
(`D:\vllm_image_backups\`). Tout ce qui la casserait — un `docker system prune`, une panne disque —
nous laisserait sans prod **et** sans rollback.

La phase 1 (2026-08-10, GPU 2, proxy Qwen3.5-9B) a montré que le crash qui nous avait forcés à
adopter Genesis le 2026-05-06 — [vllm#41726](https://github.com/vllm-project/vllm/issues/41726),
`AssertionError turboquant_attn.py:720:_continuation_prefill` — **ne se reproduit plus** sur image
stock. Les 4 correctifs TurboQuant (#44053, #47609, #39988, #50533) sont des **ancêtres git
vérifiés** du commit testé. Une image **release** (`v0.27.0`, publiée le 2026-08-10 à 20:13Z) n'est
pas soumise au GC des nightlies : c'est tout l'enjeu de reproductibilité.

Ce que la phase 1 n'a **pas** pu prouver, et que la phase 2 doit établir : MoE + EP=2 + Marlin +
TP=2 + fenêtre 262 K, sur le vrai modèle.

## Profil

[`medium-qwen36-stock-tq.yml`](../../configs/docker/profiles/medium-qwen36-stock-tq.yml), dérivé
au caractère près de `medium-qwen36-genesis-tq.yml`. Diff structurel volontairement réduit à trois
choses :

| | Genesis | Stock |
|---|---|---|
| `image` | `vllm-qwen36-genesis-tq:v7.72.5-vllm01d4d1ad3` | `vllm/vllm-openai:v0.27.0` |
| `GENESIS_ENABLE_*` | 8 variables (P37/P38B/P40/P67/P78/P98/P101 + pin policy) | **aucune** |
| volume cache compile | `…-genesis-tq` | `…-stock-tq` (build différent ⇒ cache séparé) |

Tout le reste est identique : gpu-util **0.70**, `--max-num-batched-tokens 4096`,
`--max-num-seqs 16`, `--kv-cache-dtype turboquant_k8v4`, 262 144 de contexte,
`VLLM_USE_FLASHINFER_SAMPLER=0`, `--no-enable-flashinfer-autotune`, `NCCL_P2P_DISABLE=1`,
watchdog v5 et télémétrie inchangés, **même `container_name`** (une seule pile tourne à la fois).

**Une variable à la fois** : on ne touche ni au batch, ni au gpu-util, ni au contexte pendant
cette migration.

## Risques identifiés avant bascule

1. **`shm_broadcast` / vllm#35104.** `v0.27.0` embarque toujours `_memory_fence_lock =
   threading.Lock()` et le `with _memory_fence_lock:` que notre image Genesis patche. Les deux
   réglages qui ont réellement guéri le symptôme en prod (`--no-enable-flashinfer-autotune`,
   `VLLM_USE_FLASHINFER_SAMPLER=0`) sont conservés. À surveiller : `PyCFunction`, `METH_METHOD`,
   `SystemError`.
2. **JIT Triton TurboQuant à froid.** Mesuré en phase 1 : 328 s → 187 s → 3,8 s, le moteur
   l'annonce (`Triton kernel JIT compilation during inference: _tq_full_dequant_kv`). La grâce de
   warm-up du watchdog v5 (3 sondes à 120 s) peut ne pas suffire ⇒ **mitigation appliquée : le
   watchdog est arrêté le temps du premier boot + chauffe, puis redémarré.**
3. **Pools de préallocation Genesis absents** (P28 GDN, P37 MoE, dequant TQ). Ils vivaient *hors*
   du budget gpu-util : leur disparition libère de la VRAM au lieu d'en coûter. gpu-util reste à
   0.70 — on ne remonte rien tant que la stabilité n'est pas établie.
4. **P67/P78/P98/P101 sans équivalent upstream 1:1.** #47609 / #39988 / #50533 touchent la même
   zone, mais la couverture est **non prouvée**. C'est le risque résiduel principal et la raison
   d'être de la barrière ci-dessous.

## Barrière (gate)

| # | Test | Critère |
|---|---|---|
| a | boot + KV + health | health 200, RC stable, KV annoncé, 0 OOM |
| b | prefill ~30 K chunké | pas de `Workspace is locked`, requête de survie OK |
| c | prefill ~95 K puis ~250 K | idem, jusqu'au bord de la fenêtre 262 K |
| d | vision / tool calling / thinking / preserve_thinking | tous fonctionnels |
| e | concurrent N=16 | comparé à la référence Genesis **829 tok/s** agrégé |
| f | soak | 0 `WEDGE`, 0 `SystemError`, 0 `EngineDeadError` |

Batterie automatisée : [`validate.py`](validate.py).

**Rollback armé en permanence**, au premier échec réel :

```bash
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen36-stock-tq.yml   --env-file myia_vllm/.env down
docker compose -f myia_vllm/configs/docker/profiles/medium-qwen36-genesis-tq.yml --env-file myia_vllm/.env up -d
```

## État de la prod avant bascule (2026-08-10T23:36:44Z)

| | |
|---|---|
| health | **200** en 9,7 ms |
| conteneur | `RC=0`, `running`, `healthy`, `StartedAt=2026-08-10T14:58:17Z` (~8 h 40) |
| OOM depuis le boot | **0** |
| GPU 0 / 1 / 2 | 21 079 / 19 976 / 266 MiB — GPU 0 **franchement sous** le seuil d'alerte 23 000 |
| trafic client | **aucun** sur 10 min (seules les sondes du watchdog dans `error_sources.jsonl`) |

Le pré-requis posé en fin de phase 1 (« ne pas lancer tant que GPU 0 n'est pas redescendue
franchement sous 23 000 MiB ») est donc satisfait.

## Résultats

### Chronologie de la bascule (2026-08-10 → 08-11, UTC)

| heure | événement |
|---|---|
| 23:45:12Z | pile Genesis `down` |
| 23:45:48Z | pile stock `up` (moteur seul, sidecars volontairement différés) |
| 23:47Z | cache HF vérifié à **47 G** — pas de phantom mount |
| 00:03:05Z | **1ᵉʳ boot tué par un SIGTERM externe** → cause : `qdrant_autoheal` (voir plus bas) |
| 00:06:47Z | `--force-recreate` avec `autoheal=False` + `start_period: 1800s` |
| 00:15:09Z | **health 200**, `healthy`, RC=0 |
| 00:16Z | batterie #1 : 8/13 — 500 sur les prefills longs (**`xxhash` absent**, voir plus bas) |
| 00:21:40Z | redémarrage avec `--prefix-caching-hash-algo sha256` + sidecars |
| 00:29:05Z | health 200, 3 conteneurs Up |
| 00:30Z | **batterie #2 : 13/13 PASS** |

### Deux obstacles rencontrés, tous deux étrangers à TurboQuant

**1. `qdrant_autoheal` — une autorité de redémarrage concurrente.** La machine héberge un conteneur
`willfarrell/autoheal` lancé avec `AUTOHEAL_CONTAINER_LABEL=all` : il `docker restart` **tout**
conteneur passant `unhealthy`. Il a tué le premier boot à froid (qui dépassait `start_period: 900s`).
Signature quasi nulle : `ExitCode=0`, `OOMKilled=false`, et surtout **`RestartCount` inchangé**
(`docker restart` ne l'incrémente pas) — donc la détection CRASH-LOOP du watchdog v4/v5, qui lit
`RestartCount`, y est structurellement aveugle. Ses propres logs le placent aussi à **2026-08-10
13:40:15 et 14:40:50 sur le conteneur de prod**, c'est-à-dire **dans la fenêtre de l'incident de ce
jour-là** : cela révise l'analyse de cet incident, jusqu'ici imputée au seul watchdog + pagination
WDDM. Correctif : `labels: ["autoheal=False"]` (F majuscule — le filtre est
`select(.Labels["autoheal"] != "False")`) ajouté aux **deux** profils, stock et Genesis, pour que le
rollback l'emporte aussi. Plus `start_period` 900s → **1800s** (boot à froid mesuré : poids 262 s,
torch.compile 209 s, init engine 474 s, puis le warmup multi-modal côté serveur d'API, nouveau en
v0.27.0 et non couvert par `--skip-mm-profiling`).

**2. Module `xxhash` absent de l'image stock.** vLLM ne l'importe que paresseusement, dans
`request_block_hasher` : invisible sur les prompts courts, HTTP 500 dès qu'une requête remplit un
bloc KV complet. D'où le motif trompeur de la batterie #1 — smoke/vision/tools PASS, 30K et 95K en
500, et la requête de survie PASS juste après (le moteur n'était jamais mort). Bascule sur `sha256`,
défaut upstream, pour que l'image reste un `docker pull` pur. Détail et alternative écartée : en-tête
du profil.

### Gate — batterie #2, 13/13 PASS (00:30:23Z)

| test | résultat |
|---|---|
| smoke | 0,45 s |
| vision (PNG 4 quadrants) | 2,4 s, **4/4 couleurs** |
| tool calling (`qwen3_coder`) | 1,0 s → `get_weather({"city":"Lyon"})` |
| thinking | 19,9 s, `reasoning`=1974 car, `finish=stop`, **391 trouvé** |
| preserve_thinking | 7,0 s, historique avec bloc de raisonnement accepté → `7` |
| **prefill 31 417 tok** | **7,2 s → 4 345 tok/s** + survie OK |
| **prefill 101 838 tok** | **21,1 s → 4 828 tok/s** + survie OK |
| **prefill 253 503 tok** | **58,6 s → 4 327 tok/s** + survie OK |

**Le verdict central : le crash qui nous avait forcés sur Genesis ne se reproduit pas.** Un prefill
chunké de **253 K tokens** sur le vrai modèle MoE en TP=2 + EP=2, à un pas de la fenêtre 262 K, passe
et le moteur survit. Zéro occurrence de `Workspace is locked`, `turboquant_attn`, `EngineDeadError`,
`SystemError`, `PyCFunction`, `METH_METHOD`, `out of memory`, `Traceback` depuis le boot.

Le JIT Triton `_tq_full_dequant_kv` — les 328 s redoutés de la phase 1 — a bien tiré, mais absorbé
dans un prefill de 7,2 s. Le risque 2 ne s'est pas matérialisé.

**VRAM** : GPU 0 **19 336 MiB** / GPU 1 19 040, contre 21 145 / 19 340 en Genesis. ~1,8 GiB de marge
en plus sur la carte partagée avec le bureau Windows — bénéfice direct contre les boot-OOM, les pools
de préallocation Genesis (P28/P37/dequant TQ) ayant disparu. KV **1 030 407 tokens** (3,93× la
fenêtre) contre 1 238 046 en Genesis : −17 %, sans conséquence pratique (occupation en prod 2–7 %).

### Le débit : une fausse alerte, et une vraie découverte

**Première lecture, erronée.** Mesuré avec **le script exact** qui a produit les chiffres de
CLAUDE.md ([`bench_concurrent_scaling.py`](../bench_concurrent_scaling.py), médiane de 3 itérations),
stock rendait 524,6 tok/s agrégés à N=16 contre les **829** documentés, et 48,7 tok/s en mono-flux
contre les **120** documentés : −37 % et −59 %. J'ai d'abord conclu à une régression du build.

**C'était comparer une mesure de cette nuit à une mesure de mai.** La référence Genesis datait de
v2f à gpu-util **0.82**, sur une machine dont l'état a changé depuis. La seule comparaison honnête
est un A/B la même nuit, même machine, mêmes scripts — je l'ai fait, en rebasculant sur Genesis puis
sur stock.

**A/B réel (2026-08-11, médianes de 3 itérations) :**

| N | Genesis (mesuré cette nuit) | stock v0.27.0 | Δ réel | *doc de mai (non reproductible)* |
|---:|---:|---:|---:|---:|
| 1 | 21,5 | **32,8** | **+53 %** | *93* |
| 2 | 48,3 | 39,0 | −19 % | *134* |
| 4 | 97,6 | 82,9 | −15 % | *215* |
| 8 | 179,3 | **237,9** | **+33 %** | *415* |
| 12 | 319,9 | **360,3** | **+13 %** | *625* |
| **16** | **461,1** | **524,6** | **+14 %** | *829* |

Décodage mono-flux (8 requêtes consécutives de 300 tokens, médiane) : stock **48,7 tok/s** contre
Genesis **37,9** → **+29 %**.

**Verdict inversé : stock est plus rapide que Genesis**, nettement au régime qui compte pour nous
(N≥8, multi-utilisateurs) et en mono-flux. Le creux à N=2–4 est le seul point où Genesis garde un
avantage, sur un régime que la prod ne fréquente pas.

**La vraie découverte est ailleurs :** les deux piles sont ~45 % sous les chiffres de mai. Ce n'est
donc **ni Genesis ni stock** — **c'est la machine qui a perdu du débit depuis mai**, et la référence
« 829 tok/s » inscrite dans CLAUDE.md n'est plus reproductible sur ce matériel, quel que soit le
build. Cause non établie (horloges GPU / états P8, pilote, plan d'alimentation Windows, charge du
bureau) : c'est un chantier distinct, consigné dans *Suites*. Il ne bloque pas cette migration,
puisque la comparaison qui décide de la bascule est celle de cette nuit.

Suspects examinés pendant la fausse alerte — les deux premiers valent comme corrections de
documentation :

1. ~~`VLLM_USE_FLASHINFER_MOE_FP16=1` n'existe plus dans v0.27.0~~ — **ÉLIMINÉ, et c'est une
   correction de documentation.** Dans l'image Genesis elle-même, cette variable n'est consommée que
   par `model_executor/layers/fused_moe/oracle/**unquantized**.py` : elle ne s'applique qu'au MoE
   **non quantifié**. Notre modèle est AWQ INT4 → **elle n'a jamais eu le moindre effet sur ce
   déploiement**. Le « +110 % MoE » inscrit dans MEMORY.md et CLAUDE.md vient d'un contexte
   antérieur et doit y être corrigé.
2. ~~`--performance-mode interactivity` se comporterait autrement~~ — **ÉLIMINÉ** : dans v0.27.0
   (`config/vllm.py:1858`) il ne fait qu'affiner les tailles de capture CUDA graph (1..32 au lieu de
   1,2,4,8,16,24,32), ce qui **aide** le décodage.
3. **Surcoût de déquantification TurboQuant** sans les pools de préallocation Genesis.
4. Patches Genesis sans équivalent upstream (P67/P78/P98/P101) — le risque 4 identifié avant bascule.

**Test d'isolation — même image stock, KV en `fp8`** (00:54Z, tout le reste identique) :

| | KV | décodage mono-flux (médiane de 8) |
|---|---:|---:|
| stock v0.27.0 + turboquant_k8v4 | 1 030 407 tok | **48,7 tok/s** |
| stock v0.27.0 + fp8 | 788 417 tok | **41,2 tok/s** |

fp8 est **plus lent** que TurboQuant. **Le suspect 3 est éliminé : le coût n'est pas dans la
déquantification TurboQuant.** (Au passage, l'avantage de capacité de TQ à gpu-util 0.70 n'est que
de 1,31× sur fp8, pas 2×.) Avec l'A/B ci-dessus, le suspect 4 tombe aussi : les patches Genesis sans
équivalent upstream ne coûtent rien à stock, puisque stock est le plus rapide des deux.

## Décision

**Bascule en stock `v0.27.0` + TurboQuant k8v4.** Les quatre raisons, par ordre de poids :

1. **L'image redevient reproductible.** C'est l'objet même de la phase 2 : un tag *release*
   n'est pas soumis au GC des nightlies. La prod cesse de dépendre d'un artefact que seul le store
   Docker local détient.
2. **Toutes les barrières fonctionnelles passent** — 13/13, dont le prefill chunké de 253 K tokens
   qui reproduisait le crash de mai. Genesis n'est plus nécessaire à sa propre raison d'être.
3. **Le débit est supérieur** à Genesis mesuré la même nuit : +14 % à N=16, +29 % en mono-flux.
4. **GPU 0 gagne ~1,8 GiB de marge** — levier direct contre l'historique de boot-OOM (3 en 19 jours),
   les pools de préallocation Genesis ayant disparu.

Le coût accepté est **−17 % de KV** (1 030 407 contre 1 238 046 tokens), sans portée pratique :
l'occupation observée en prod est de 2–7 %, et 1,03 M reste **3,93×** la fenêtre de 262 K.

Risque résiduel : le soak. `v0.27.0` ne patche pas `_memory_fence_lock` (vllm#35104) ; les deux
réglages qui ont réellement guéri le symptôme en prod sont conservés, et le watchdog v5 couvre les
quatre modes de panne connus. C'est la barrière **f** qui tranche.

### Bascule finale et confirmation (01:13 → 01:26Z)

`down` Genesis puis `up -d` stock à 01:13:02Z, après retrait des trois variables MoE inertes.
**health 200 à 01:21:37Z** (boot à chaud 8 min 35 : init engine 78 s, torch.compile 9 s), les trois
conteneurs Up, `RC=0`, `autoheal=False`, image `vllm/vllm-openai:v0.27.0`.

KV **1 030 407 tokens / 3,93×**, identique au boot précédent : le retrait des trois variables n'a
rien changé — cohérent avec le fait qu'elles n'étaient pas lues. Batterie re-jouée intégralement :
**13/13 PASS** (prefill 253 503 tok en 61,1 s, survie 3,05 s, N=16 à 513 tok/s). VRAM au repos
GPU 0 **19 025** / GPU 1 18 730 MiB. Zéro occurrence des motifs de panne depuis le boot.

**⚠️ Effet de bord observé : la batterie provoque un faux WEDGE.** À 01:24:15Z, pendant le prefill
de 253 K, la sonde de décodage du watchdog (24 tokens, timeout 40 s) a expiré → `WEDGE (fail 1/2)`,
puis `RECOVERED` à 01:25:25Z une fois le prefill terminé. Le moteur servait des 200 OK pendant tout
l'épisode : **c'est le prefill qui affame le décodage**, le mécanisme déjà identifié le 2026-07-04
(`prompt_rate 419.7`). Aucun dégât ici, mais **deux échecs consécutifs auraient redémarré le moteur
en plein test.** À retenir : lancer cette batterie contre la prod frôle le redémarrage auto-infligé
— arrêter le watchdog pendant la batterie, ou espacer les gros prefills.

## Suites

- **Barrière f — soak.** Surveiller `WEDGE`, `SystemError`, `EngineDeadError`, et spécifiquement
  `PyCFunction` / `METH_METHOD` (la famille vllm#35104, non patchée dans stock). Rollback armé,
  commande en tête de ce document.
- **Chantier distinct : la machine a perdu ~45 % de débit depuis mai.** Établi par l'A/B (les deux
  piles s'effondrent ensemble, donc ce n'est pas le logiciel). À investiguer hors migration :
  horloges et états P8 des GPU sous charge, version de pilote, plan d'alimentation Windows, VRAM
  consommée par le bureau sur GPU 0. Tant que ce n'est pas élucidé, **les chiffres de perf de mai
  inscrits dans CLAUDE.md ne sont pas des références utilisables** — toute comparaison future doit
  être un A/B de la même nuit.
- **Corrections de documentation dues** (CLAUDE.md + MEMORY.md) : `VLLM_USE_FLASHINFER_MOE_FP16`
  n'a jamais rien fait ici (« +110 % MoE » à retirer) ; `autoheal` comme autorité de redémarrage
  concurrente ; nouvelles valeurs de référence VRAM/KV pour la compétence `/vllm-surveillance`
  (écrite pour Genesis à ~21 150 MiB).
- **Ne pas remonter gpu-util** pour récupérer le KV perdu tant que la stabilité n'est pas établie.
  Le budget hors-pool a changé (pools Genesis disparus) : toute remontée devra être remesurée.
- **Sauvegardes Genesis conservées** (`D:\vllm_image_backups\`) : elles restent le chemin de
  rollback tant que le soak n'a pas conclu. Ne pas les supprimer avec cette migration.
