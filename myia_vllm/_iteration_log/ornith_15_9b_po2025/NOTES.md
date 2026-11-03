# Ornith-1.5-9B-AWQ-INT4 — fenêtre d'éval po-2025 (03/11/2026)

**Origine** : proposition du user le 03/11 au soir (`cyankiwi/Ornith-1.5-9B-AWQ-INT4`), après rejet
de la base `Qwen/Qwen3.5-9B` (« on veut mieux que ça »). GO user : « Tu as mon go pour tester quand
c'est prêt ». Fenêtre annoncée sur `global` avant le geste.

**Verdict court** : **le modèle tient sur le siège et bat FrogNano sur la classe servie**
(verbatim 14/14 déterministe contre 13/14), au prix de **0,61× le débit** et **0,29× le pool KV**.
C'est un candidat réel, pas une impasse comme le 12B : la décision de promotion est un arbitrage
qualité/débit qui revient au user.

Fenêtre réelle : `:5003` indisponible **≈ 8 min 30 s** (15:01:41Z → ~15:10:15Z), contre ~20 min
annoncées. Aucun consommateur externe (0 requête externe depuis le restart du 02/11).

---

## 0. Pré-vérification géométrique — la leçon Gemma appliquée

Faite **avant** tout téléchargement, sur `config.json` seul :

- `Qwen3_5ForConditionalGeneration` / `model_type: qwen3_5` — la famille déjà servie (Swift-1.5-27B
  sur ai-01, OmniCoder-9B) ⇒ **zéro overlay**, l'image stock v0.32.0 suffit.
- 32 couches dont **24 `linear_attention`** (état fixe, pas de KV par token) et **8 `full_attention`**.
- Poids **8,40 Go** sur disque en 3 shards (3 399 + 5 091 + 85 Mo), vérifiés non-stub (gotcha 9p).
- Contexte natif 262 144, MIT, vision (ViT 27 couches), MTP 1 couche présente.

Le Gemma-4-12B avait été tué par ~343 Ko/tok de KV ; ici la géométrie annonçait ~32 Ko/tok.
**Mesure : ~36,5 Ko/tok** — l'estimation était juste à 12 %, même classe, et le boot l'a confirmée.

## 1. Ce que le moteur a réellement servi (VÉRIFIÉ aux logs)

| Grandeur | Valeur mesurée |
| --- | --- |
| Chargement des poids | **7,61 GiB en 92,6 s** |
| Mémoire KV disponible | **4,17 GiB** |
| **Pool KV** | **122 523 tokens** = **3,74 contextes** de 32 768 |
| KV par token | **~36,5 Ko** |
| `kv_cache_dtype` | `auto` (bf16) — **fp8 interdit sur SM 8.6**, comme prévu |
| Blocs | 528, lcm 528 |
| Boot complet (conteneur → `/health` 200) | **260 s** |
| VRAM en service | 12 530 MiB / 38 °C |

**Le fit est confortable** : 12 530 MiB sur ~14,4 Go de plafond pratique. Rien à voir avec le 12B,
qui ne bootait à aucun contexte utile.

**Le motif horde survit** : N=16 × ~1,5 K tokens ≈ 24 K tokens, très en dessous des 122 K.
Mais la marge de repli est 3,5× plus mince que FrogNano (13,0 contextes), donc le premier
consommateur qui ouvre des sessions longues mange la réserve.

## 2. Fiabilité — le résultat qui compte

Corpus-piège 22 lignes, oracle `grep temp=31C` = **14**. Référence à battre : **FrogNano 13/14, 0 bruit**.

| Épreuve | Résultat |
| --- | --- |
| **R0** sanity | `Paris` correct, **mais délibération dans `content`** (`The user is asking in French… </think>`) — thinking actif par défaut, aucun `--reasoning-parser` chargé |
| **R1** liste verbatim, template par défaut | rendues 54, réelles 14, **couv 14/14**, **bruit 40**, **0 fabriquée** |
| **R1b** idem, `enable_thinking: false` | rendues 14, réelles 14, **couv 14/14**, **bruit 0**, **0 fabriquée** |
| **R1b ×3** (stabilité) | **3/3 strictement identiques** — 14/14, 0 bruit, mêmes compteurs (552 gen) |
| **R2** comptage | **échoue** (`finish=length` à 64 tokens, se lance dans une énumération) — frontière connue du siège, aucun modèle n'y arrive |
| **R3** piège d'hallucination | correct : constate qu'aucune ligne ne parle d'usage GPU et conclut `AUCUNE`, **avec 638 caractères de préambule** |
| **R4** appel d'outil | **`finish=tool_calls`**, `get_weather({"city": "Paris"})` bien formé |

**Les deux enseignements majeurs :**

1. **`enable_thinking: false` fonctionne réellement ici** — et c'est l'inverse exact du cas LFM3, où
   le flag était cosmétique et le raisonnement fuyait quand même. Ici il supprime à la fois le
   préambule et les 40 lignes de bruit, sans perdre une seule ligne de l'oracle.
2. **La classe verbatim servie est meilleure que FrogNano** : **14/14 contre 13/14**, à zéro bruit,
   et **déterministe sur 3 runs** (LFM3 variait d'un run à l'autre, ce qui le rendait inutilisable
   comme producteur). Le seul point noir est le comptage, identique à tout le siège.

**Conséquence de service** : cette phrase était trop forte et a été corrigée par arbitrage user
le 03/11 au soir — **voir l'addendum ci-dessous**.

> **Addendum 03/11 (arbitrage user)** : « le thinking n'est pas un problème en soi, il faut juste
> prévoir dans les tests suffisamment de max_tokens pour absorber le thinking et rendre des
> contenus non vides ». Autrement dit : le §2 ci-dessus ne montre **pas** une perte de capacité
> mais un **coût de volume**. Couverture **inchangée à 14/14** avec thinking actif ; les ~40 lignes
> de bruit sont de la précision d'extraction, pas de l'hallucination (0 fabriquée dans les deux
> modes). `--default-chat-template-kwargs '{"enable_thinking": false}'` reste une **option** pour
> l'appelant qui veut une sortie propre — ce n'est **pas** une condition de service. Une réponse
> vide ou tronquée est une erreur de protocole de test, pas une propriété du modèle. Les épreuves
> à venir tournent thinking actif avec un budget de tokens dimensionné (épopée #365).

## 3. Débit — le prix

Banc `bench_capacity.py` (extraction verbatim sur journal réel, 0 erreur sur 25 requêtes),
**mesuré avec le template par défaut (thinking actif)**, donc en générant la délibération :

| N | Ornith-1.5-9B | FrogNano-4B (réf. 02/11) | Ratio |
| --- | --- | --- | --- |
| 1 | 64,1 tok/s | 115,2 | **0,56×** |
| 8 | 348,2 tok/s | 532,2 | 0,65× |
| 16 | **506,7 tok/s** | 829,1 | **0,61×** |
| TTFT N=16 | 1,18 s méd. / 2,27 s max | 0,70 s | +68 % |

**Lecture honnête** : ce sont des débits sur le chemin « thinking ON ». En thinking OFF le modèle
émet beaucoup moins de tokens, donc le débit agrégé en tok/s baisserait mécaniquement alors que la
latence utile s'améliorerait — les deux chiffres ne sont pas comparables tels quels. Ce qui est
solide : **Ornith rend ~0,6× les tokens de FrogNano par seconde**, cohérent avec un 9B dense contre
un 4B sur la même carte.

## 4. Le tableau de décision

| | FrogNano-4B (prod) | Ornith-1.5-9B |
| --- | --- | --- |
| Verbatim corpus-piège | 13/14 | **14/14** |
| Bruit / fabrications | 0 / 0 | 0 / 0 (thinking off) |
| Stabilité inter-runs | stable | **3/3 identiques** |
| Débit N=16 | **829,1 tok/s** | 506,7 tok/s (0,61×) |
| Pool KV | **426 473 tok** (13,0 ctx) | 122 523 tok (3,74 ctx) |
| Contexte servi | 32 768 | 32 768 (262 K natif disponible) |
| Poids | ~4,8 Go | 8,40 Go |
| VRAM en service | 12 724 MiB | 12 530 MiB |

**Ce n'est pas un remplacement à somme nulle** : Ornith gagne sur la fiabilité de la classe servie
et sur le contexte natif disponible ; FrogNano garde 1,6× le débit et 3,5× la réserve KV qui fait
tenir la horde. Le siège a été bâti comme **tier horde** (mandat 29/10), ce qui plaide pour garder
FrogNano en prod et réserver Ornith à un usage où la justesse prime — ou pour un basculement si le
user juge la fiabilité prioritaire. **Arbitrage user, pas une décision de lane.**

## 5. Incident de cadre — le moteur Docker est tombé juste avant la fenêtre

À 15:54 locale, soit ~10 min après la vigie et avant le geste : `engine DOWN (docker version sans
réponse serveur)` ; à 15:54:17 le garde-fou de la lane Maintenance a tué les 8 processus Docker et
relancé Docker Desktop ; à 15:56:21 `engine UP en < 20 s`. Les deux conteneurs (`myia_vllm-mini-
frognano-4b` et `claudish-proxy`) sont revenus par leur politique `unless-stopped`, **ExitCode 0,
OOMKilled false, RestartCount 0**.

Ni reboot hôte (uptime 95 h), ni redémarrage WSL (distros up 4 j), ni crash conteneur. Avant
d'ouvrir la fenêtre, la santé a été **prouvée par génération réelle** (`Paris`, `finish=stop`) et le
passthrough GPU vérifié depuis le conteneur (3080 Ti vue, 12 718 MiB) — c'est le mode de panne du
08-31 et un `/health` seul ne l'aurait pas distingué.

**Cause de la mort du moteur : non établie.** Le garde-fou traite le symptôme. Le journal Docker
ne portait que les deux `start`, aucun `stop`/`kill`.

> **Correction du 03/11 au soir (mesure Maintenance, à substituer à ma formulation du §5)** :
> l'indisponibilité a duré **~2 min 10 s** (15:54:11 → 15:56:21), pas « < 20 s » — les 20 s sont
> la durée de la **relance**, pas de la panne. **Budgéter 2-3 min par fenêtre moteur.**
> La garde **ne retire pas un moteur sain** (25 lignes « engine UP — nominal » encadrent
> l'incident) : en temps normal son seul geste est d'écrire une ligne. Le risque résiduel est
> ailleurs — sa sonde `docker version` est **bornée à 20 s**, donc un moteur **vivant mais bloqué
> > 20 s** est lu comme DOWN et se fait tuer en pleine fenêtre.
> **Arbitrage retenu : fenêtre annoncée, garde non coupée.** Créneaux à éviter : **03:30–06:30**
> locales (archivage claudish), **04:51**, et **le 1er du mois à 03:00** (export de la distro,
> conteneurs arrêtés). Maintenance occupe 00:53 et 12:53.

## 6. Restauration

`docker rm -f ornith-eval` → délai de stabilisation 16 s (règle du siège) → `docker start
myia_vllm-mini-frognano-4b` → `/health` 200 en **100 s** → **génération réelle** `Paris`,
`finish=stop` → VRAM **12 724 MiB**, `health: healthy`.

Poids Ornith **conservés** dans le cache HF (8,40 Go) : aucun coût, et une décision de promotion
n'aurait pas à re-télécharger.

## Artefacts

| Fichier | Contenu |
| --- | --- |
| `.tmp/start_ornith_eval.sh` | lanceur de la fenêtre (port 5024, util 0.88, 32K, KV auto) |
| `.tmp/ornith_reliability.py` | batterie R0/R1/R1b/R2/R3/R4 |
| `.tmp/ornith_repeat.py` | stabilité R1b ×3 |
| `.tmp/ornith_22_default.txt` / `ornith_22_thinkoff.txt` | sorties brutes comparables |
| `.tmp/ornith_tool.json` | réponse complète de la sonde outil |
| `bench_capacity_out.json` | débit N=1/8/16 |
