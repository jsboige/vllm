# Spark-X2.6-4B (modèle de BASE) sous image `latest` + plugin — po-2025, 24/10/2026

**Question posée par le user (24/10)** : « Est-ce que tu as testé
https://huggingface.co/XHToken/Spark-X2.6-4B sous image latest comme je t'avais
demandé ? »

**Réponse courte** : non, ça n'avait pas été fait — et l'axe « latest » était en
réalité déjà couvert. La fenêtre ci-dessous comble le trou réel, et le verdict est
**SERVABLE, mais seulement après un correctif du plugin amont**.

---

## 1. Ce qui avait été testé le 21/10 (et ce qui ne l'avait pas été)

| Axe | 21/10 | 24/10 (cette fenêtre) |
|---|---|---|
| Modèle | Spark-X2.6-4B **INT4** | Spark-X2.6-4B **de base (BF16)** |
| Image | `vllm/vllm-openai:v0.32.0` épinglée | `latest` — **même digest** que v0.32.0 |
| Plugin `XHToken/Spark-plugin` | absent | **présent (v3, patché)** |
| Résultat | refus `ModelConfig` (arch inconnue) | **boot sain + génération réelle** |

`vllm/vllm-openai:latest` **est** v0.32.0 : même digest `sha256:befccf0e7e40…`
(vérifié via l'API Docker Hub). L'image n'était donc pas la variable — le cœur
vLLM ne connaît pas `Spark2_5ForCausalLM`, et aucune PR/issue upstream ne le
mentionne. **La seule voie sur NVIDIA est le plugin.**

> Piège opérateur mesuré : `FROM vllm/vllm-openai:latest` **ne re-tire pas** un tag
> déjà présent localement. Le tag `latest` local avait 14 mois et a produit un
> overlay v1 cassé (`ModuleNotFoundError: No module named 'vllm.tool_parsers'`).
> D'où l'épinglage explicite `FROM …:v0.32.0` + un assert de version dans l'image.

## 2. Bug bloquant trouvé dans le plugin amont (et correctif)

Premier boot v2 : `TypeError: AutoWeightsLoader.__init__() got an unexpected
keyword argument 'skip_prefixes'` (`spark2_5.py:389`).

Vérifié : `skip_prefixes` **n'existe dans aucune version publiée de vLLM** —
v0.30.0, v0.31.0, v0.32.0 et `main` exposent
`ignore_unexpected_prefixes` / `ignore_unexpected_suffixes`, et le commit que le
plugin déclare avoir testé (`TESTED_VLLM = 81efe788…`, 2026-08-22) ne l'a pas non
plus. Le motif upstream documenté pour ignorer un préfixe de poids
(`vllm/models/step5/nvidia/model.py:2454`) est un `WeightsMapper` qui mappe ces
préfixes à `None`.

Correctif appliqué dans l'overlay `v3` (4 lignes) :

```python
mapper = self.hf_to_vllm_mapper
if self.config.tie_word_embeddings:
    mapper = mapper | WeightsMapper(orig_to_new_prefix={"lm_head.": None})
loader = AutoWeightsLoader(self)
return loader.load_weights(weights, mapper=mapper)
```

→ **boot sain en 210 s**, zéro erreur dans les logs. Sans ce correctif, le modèle
n'est servable sur **aucune** version de vLLM.

## 3. Mesures (base BF16, gpu-util 0.78, max-model-len 32 768, fp8 KV non activé)

| Métrique | Valeur |
|---|---|
| Boot (préremplissage du compile-cache vide) | **210 s** jusqu'à `/health` 200 |
| `torch.compile` (backbone) | 29,5 s |
| Init engine (profil, KV, warmup) | 72,85 s |
| **KV cache** | **58 128 tokens** — concurrence **1,77×** à 32 768 tok/req |
| VRAM (pic) | 14 808 MiB / 16 384 |
| RAM conteneur | 2,99 Gio / 16 Gio |
| **Décodage single-stream** | **27,3 tok/s** (187 tok en 6,85 s) |
| Thinking OFF (`chat_template_kwargs`) | **fonctionne** — `reasoning=None`, réponse propre |
| Génération réelle | « La capitale de la France est Paris. », `stop` |

Note : sans `enable_thinking: false`, le modèle **raisonne dans `content`**
(pas de parser de raisonnement activé dans ce profil) — à garder en tête pour
tout consommateur.

## 4. Fiabilité — batterie 7 axes (protocole identique aux deux moteurs)

Spark base : **4 PASS / 1 PARTIAL / 2 FAIL**. Détail :

| Axe | Verdict | Lecture |
|---|---|---|
| A0 contrôle KV | PASS | `41.5C` + `22107MB` exacts |
| A1 comptage homogène (60) | PASS | `60` exact |
| A2 comptage hétérogène par rayon | PASS | 4/4 rayons exacts (6,6,6,6) |
| **A3 moyenne dérivée** | **FAIL** | `10.30` vs vérité `11.37` — erreur arithmétique |
| A4 comptage de log | PARTIAL | `ERROR 8` vs 7, `WARN 6` vs 5 — surestimation +1, aucune absence fabriquée |
| A5 condensation avec citations | PASS | 3/3 citations verbatim préservées |
| **A6 tag + attribution** | **FAIL (forme)** | 6/6 tags et 6/6 machines **justes**, mais suffixe `\|workspace` supprimé et crochets conservés → rejeté par le comparateur strict. **Échec de forme, pas de fond.** |

## 5. A/B même nuit vs FrogNano (même batterie, même heure, thinking OFF)

| Axe | Spark base (BF16) | FrogNano (NVFP4 + fp8 KV) |
|---|---|---|
| A0 contrôle KV | PASS | PASS |
| A1 comptage homogène | PASS | PASS |
| A2 comptage hétérogène | PASS | PASS |
| **A3 moyenne dérivée** | **FAIL** (`10.30` vs 11.37) | **FAIL** (`10.77` vs 11.37) |
| A4 comptage de log | PARTIAL (`8`/`6` vs `7`/`5`) | **PASS** (exact) |
| A5 condensation + citations | PASS (3/3) | PASS (3/3) |
| A6 tag + attribution | FAIL **de forme** (6/6 tags et machines justes, suffixe `\|workspace` perdu) | **PASS** (6/6 + 6/6 exacts) |
| **Score** | **4 PASS / 1 PARTIAL / 2 FAIL** | **6 PASS / 0 PARTIAL / 1 FAIL** |
| Somme latences batterie | 12,86 s | **5,90 s** |
| **Décodage single-stream** | **27,3 tok/s** | **66,0 tok/s** (×2,4) |
| KV cache | 58 128 tok (1,77× à 32K) | 421 582 tok (mesure de prod) |

Deux enseignements qui ne sont pas de simples « FrogNano gagne » :

1. **L'axe moyenne dérivée échoue sur les deux moteurs** — ce n'est pas une
   faiblesse de Spark seul, c'est une limite du tier 4B sur un calcul dérivé.
   FrogNano s'en approche (`10.77` vs `10.30`) sans l'atteindre : ni l'un ni
   l'autre n'est fiable pour une agrégation arithmétique.
2. **A6 est le seul axe où la différence est qualitative, pas quantitative** :
   FrogNano restitue la chaîne d'auteur complète `myia-po-2025|vllm`, Spark
   s'arrête à la machine. Sur un dashboard où l'attribution par workspace porte
   la coordination, c'est un vrai écart — pas un détail de formatage.

## 6. Verdict

**Oui, le modèle de base se sert sous `latest` — mais pas avec le plugin tel que
publié.** Il a fallu corriger un bug amont qui bloque le chargement sur **toutes**
les versions de vLLM ; une fois corrigé, le boot est sain et la génération réelle
fonctionne. L'axe « image latest » n'était pas la variable : `latest` *est*
v0.32.0.

**Non, ce n'est pas un remplaçant de FrogNano sur ce siège** : ×2,4 plus lent en
décodage, 2 axes de fiabilité en moins, et surtout perte de l'attribution par
workspace. FrogNano reste le moteur de production.

**Piste suivante** : la variante **INT4** avec le plugin `v3` — **testée le même
jour, voir §8**. Le refus du 21/10 était l'arch non enregistrée — c'est
exactement ce que le plugin résout. Verdict §8 : plus rapide que le BF16 mais
**toujours 0,71× FrogNano, et qualité en retrait vs BF16** — la ligne est close.

**Recommandation à porter en amont** (`XHToken/Spark-plugin`) : le correctif
`skip_prefixes` → `WeightsMapper`. Le plugin déclare `TESTED_VLLM` sur un commit
qui ne contient pourtant pas ce kwarg — soit le développement s'est fait sur un
fork privé, soit la constante n'a jamais été vérifiée. À signaler avec le diff.

## 7. Rollback

`docker compose -f mini-spark26-4b-latest-po2025.yml down` puis
`docker compose -f mini-frognano-4b-po2025.yml --env-file myia_vllm/.env up -d`
→ FrogNano sain en 120 s, génération réelle vérifiée, 66,0 tok/s.

Le profil Spark reste sur disque, `restart: "no"` + `autoheal=False` : il ne
peut pas crash-looper la nuit.

## 8. Fenêtre INT4 (Q8 du registre, GO user 24/10 ~09:35 locale)

**Question** (user, 24/10 matin) : « si tu penses qu'on peut encore faire un
nouveau test pourquoi pas, mais si notre modèle actuel gagne sur toutes les
métriques… ça m'a l'air d'être un no brainer. Enfin c'est à confirmer. »

**Réponse : confirmé chiffré — FrogNano gagne sur TOUTES les métriques, la
ligne Spark est close sur ce siège.**

### 8.1 Incident opératoire d'abord : le figerage au premier kernel (2 boots)

Premier boot INT4 07:44Z : init complète (poids 3,81 GiB / 28,4 s, compile,
graphs CUDA, KV 51 641 tok) puis **figerage** au premier kernel post-init —
GPU 100 %, EngineCore 93 % CPU, aucune ligne de log pendant 14 min. La
restauration FrogNano immédiate (08:01Z) a **figé au même point logique** :
`Warming up Qwen GDN Triton kernels` démarré, jamais terminé, GPU 100 %.

Diagnostic discriminant : un conteneur CUDA vierge interroge le GPU sans
problème (`nvidia-smi` in-container OK, pas de Xid, P0) — la couche DXG est
saine ; c'est le kernel de warmup qui ne revient pas. Le `compose down` du
moteur figé **libère le GPU** (100 % → 38 %, 15,8 → 8,4 GiB).

**Cause (mesurée, n=1 par cas)** : les deux boots morts ont été lancés
**immédiatement** après le kill d'un moteur ; le boot suivant un `down` +
**15 s de délai** passe en 91-106 s. C'est le gotcha connu du siège
(« le contexte CUDA d'un moteur tué met ~10 s à se libérer » — cf. faits
GPU-2 d'ai-01) qui se manifeste ici au niveau kernel : boot sans délai =
premier kernel lancé dans un contexte à moitié libéré → boucle infinie.
**Règle pour ce siège : TOUJOURS ≥15 s entre `compose down` d'un moteur et
`up` du suivant.** Attribution SUPPOSE (n=2 stalls sans délai, n=2 boots OK
avec délai, jamais testé l'inverse).

Coût de l'incident : ~35 min de slot :5003 noir (07:44→08:19Z),dont 2
restaurations. Aucune requête perdue (0 trafic mesuré sur la fenêtre).

### 8.2 Mesures INT4 (image plugin v3, gpu-util 0.78, 32 768, settle respecté)

| Métrique | INT4 | Base BF16 (§3) | FrogNano |
|---|---|---|---|
| Boot jusqu'à `/health` 200 | **106 s** | 210 s | 91 s (chaud) |
| Poids chargés | **3,81 GiB** | ~8,8 GB | — |
| KV cache | 51 641 tok (1,58×) | 58 128 tok (1,77×) | **421 582 tok** |
| **Décodage single-stream** | **46,9 tok/s** (47,0/46,8/44,8) | 27,3 tok/s | **66,0 tok/s** |
| Thinking OFF | fonctionne (`reasoning=None`) | fonctionne | par défaut |
| **Batterie 7 axes** | **3 PASS / 2 PARTIAL / 2 FAIL** | 4 PASS / 1 PARTIAL / 2 FAIL | **6 PASS / 0 PARTIAL / 1 FAIL** |

Écarts de batterie INT4 vs BF16 : **A2 (comptage hétérogène) PASS→FAIL**,
**A4 PARTIAL→PARTIAL** (2 axes en PARTIAL cette fois), A5 PASS conservé.
La quantification **dégrade la fiabilité** en plus de rester derrière
FrogNano partout. Anomalie notée sans explication : KV INT4 (51 641) <
KV BF16 (58 128) malgré des poids ~5 Go plus petits — la mémoire libérée
n'est pas allée au KV à iso-gpu-util (0,78) ; non instruit, sans impact sur
le verdict.

### 8.3 Verdict final de la ligne Spark

| | Spark INT4 | Spark BF16 | **FrogNano (prod)** |
|---|---|---|---|
| Vitesse | 0,71× | 0,41× | **1,0× (66 tok/s)** |
| Fiabilité batterie | 3/2/2 | 4/1/2 | **6/0/1** |
| KV | 1,58× | 1,77× | **12,9×** |
| Attribution workspace (A6) | PARTIAL | FAIL forme | **PASS** |

**FrogNano domine sur chaque axe mesuré, y compris l'intelligence
opérationnelle (batterie = extraction fiable, l'usage réel du siège).**
Le « no brainer » du user est confirmé par la mesure. La ligne Spark-X2.6
est **close** sur po-2025 : profils et plugin v3 restent sur disque et dans
ce dépôt, rejouables en une commande.

Artefacts : `results_spark26_int4.json`, profil
`mini-spark26-4b-int4-po2025.yml`, log du boot figé
`spark26_int4_boot_stall_log.txt`.
