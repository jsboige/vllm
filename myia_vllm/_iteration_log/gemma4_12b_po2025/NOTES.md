# Gemma-4-12B-AWQ — INFaisable sur po-2025 (fenêtre 03/11/2026)

**Question du user** : « Pourquoi pas un test gemma, mais le modèle est un peu
vieux, donc voir ce qu'on gagne vraiment en fiabilité. Tu as mon Go. »

**Réponse mesurée : la fiabilité n'a pas pu être mesurée — le modèle ne tient
pas sur la carte.** La géométrie KV (fenêtre glissante 16K à têtes
hétérogènes) exige plus que les 16 Go du siège n'offrent, à tout contexte
utile. FrogNano reste en production, restauré et prouvé.

Fenêtre annoncée sur `global` avant le geste (TASK 11:02Z), GO user en poche.
**Déroulement réel : ~2 h 05 d'indisponibilité `:5003` (11:16→13:21Z) au lieu
des 15-20 min annoncés** — un crash de session harnais entre la tentative 2
(11:39Z) et la tentative 3 (13:16Z) a laissé la fenêtre ouverte ~1,5 h, GPU
inactif, sans que personne ne pilote. Aucun consommateur externe n'existait
(compteurs à 4 depuis le restart du 02/11), impact trafic nul. L'excès de
durée est un fait, rendu tel quel.

---

## 1. Les trois tentatives, chacune une cause distincte

Même base à chaque fois : `vllm/vllm-openai:v0.32.0` (stock, aucune overlay —
`gemma4_unified` est dans le registre v0.32.0, c'est ce qui rendait le
candidat intéressant), `axteam/gemma-4-12B-it-AWQ-4bit` (W4A16
compressed-tensors, 7,87 Go téléchargés, vérifiés non-stub), GPU 0 unique,
prefix caching, mm désactivé.

| # | Config | Échec | Ce que ça enseigne |
|---|---|---|---|
| 1 | util 0.85, `max-model-len 32768`, KV auto | `ValueError` : KV requis **5,82 GiB** > dispo **2,79 GiB** ; longueur max estimée **8 672** | poids OK (~8,45), mais 190,6 Ko/tok à 32K |
| 2 | util 0.88, 32K, **KV fp8** | `ValueError` : **FP8 KV non supporté par le backend Triton sur RTX 3080 Ti Laptop (SM 8.6)** ; fp8e4nv exige SM89+ | la moitié-KV est interdite par le matériel — même famille de garde que NVFP4 (SM89+) sur les cartes Ada |
| 3 | util 0.88, **`max-model-len 16384`**, KV auto | `ValueError` : KV requis **5,25 GiB** > dispo **3,29 GiB** ; longueur max estimée **10 240** | la fenêtre glissante domine (voir §2) |

Faits positifs au passage : chargement **8,45 GiB en 84,6 s** (l'estimation
~9-10 Go du watchlist tenait), CUDA graphs 11+2 capturés sans incident
(0,12 GiB), backend d'attention **TRITON_ATTN forcé** — `Gemma4 model has
heterogeneous head dimensions {'sliding_attention': 256, 'full_attention':
512}`, FA4 indisponible.

## 2. Pourquoi 16 K demande presque autant que 32 K — la géométrie KV

Deux points mesurés (5,82 GiB @ 32 768 tok ; 5,25 GiB @ 16 384 tok) suffisent
à résoudre le système. Décomposition par famille de couches :

- couches **full-attention** : ~**37 Ko/tok**, coût linéaire dans le contexte ;
- couches **sliding** : ~**307 Ko/tok** jusqu'à une fenêtre ≥ 16 K, puis plat.

Autrement dit, sous ~16 K de contexte le coût est **~343 Ko/tok uniforme** —
c'est la fenêtre glissante à grosses têtes (head_dim 256 × nombreuses couches)
qui paie, pas le contexte lui-même. Réduire `max-model-len` ne réduit donc
presque pas l'exigence KV tant qu'on reste sous la fenêtre.

**La seule config bootable est ~8-10 K de contexte**, avec un pool KV total
d'environ **10 K tokens** (3,29 GiB / 343 Ko).

## 3. Le verdict contre le contrat du siège

| | FrogNano-4B (prod) | Gemma-4-12B (config max faisable) |
|---|---|---|
| Contexte servi | **32 768** | ~8-10 K (**÷4**) |
| Pool KV | **426 473 tok = 13,0 contextes pleins** | ~10 K tok = **1 contexte** |
| Motif horde N=16 (~1,5 K tok/appel = 24 K tok) | tient (mesuré 829 t/s) | **impossible** (24 K > 10 K) |
| KV fp8 | servi (SM89 à l'autre siège… non : fp8 servi ici via garde capa) | **interdit** (SM 8.6) |

Le motif horde est le cœur de l'architecture d'adoption du siège (fan-out
mini, portes mécaniques). Un moteur dont le pool KV ne tient pas UNE
conversation pleine n'est pas un candidat, quelle que soit sa fiabilité —
c'est pourquoi la batterie fiabilité n'a pas été exécutée : elle aurait
mesuré un chiffre sans valeur de décision. Même structure que le verdict 27B
sur GPU-2 (`qwen38_27b_gpu2`) : le fit tue avant la qualité.

**Ce qu'il faudrait pour le rouvrir** : une carte ≥ 24 Go (8,45 poids + 5,25
KV@16K + ~1,5 activations/graphes ≈ 15,2 GiB → confortable sur 24 Go), ou un
quant du même modèle à fenêtre glissante réduite. Sur po-2025 : clos.

## 4. Restaurations et preuves

- `gemma-eval` supprimé, délai de stabilisation 16 s respecté (règle du siège).
- FrogNano `docker start` → health 200 en **80 s** → **preuve par génération
  réelle** : `finish=stop`, `content='Paris'` (pas seulement `/health`).
- VRAM post-boot : **12 724 MiB** vs 14 564 MiB avant fenêtre — le drift
  non attribué (+1 215 MiB, WARN du cycle vigie) est reparti avec le boot.
  Nouveau nominal à confirmer au cycle suivant.
- Poids 7,87 Go conservés dans le cache HF local (Windows,
  `~/.cache/huggingface`) — pas de purge, le coût est nul et un futur siège
  24 Go pourrait les réutiliser.

## 5. Leçons transférables

1. **« Archi dans le registre » ≠ « servable au contrat »** : l'absence
   d'overlay était vraie et suffisante pour booter l'API, mais le fit KV se
   joue sur la géométrie des têtes, invisible dans le registre. Pour tout
   futur candidat : lire `head_dim` par famille de couches ET la fenêtre
   glissante AVANT de télécharger — deux lignes dans `config.json`.
2. **fp8 KV exige SM89+** sur le backend Triton — sur Ampere (SM 8.6), toute
   estimation de fit qui suppose KV fp8 est fausse d'un facteur 2.
3. **Un crash de session en pleine fenêtre moteur laisse la fenêtre
  ouverte** : aucune garde ne rend le siège pendant que personne ne pilote.
   La parade est le cron de vigie (5 h) — trop long pour une fenêtre de
   20 min. À considérer : annoncer aussi la durée max avant rollback
   automatique... reste un vœu sans acteur pour l'exécuter. Le point est
   consigné tel quel.

## Artefacts

| Fichier | Contenu |
|---|---|
| `.tmp/start_gemma_eval.sh` | lanceur tentative 1 (32K/util 0.85) |
| `.tmp/gemma_reliability.py` | batterie NON exécutée (R0-R4), réutilisable telle quelle sur un siège 24 Go |
| `.tmp/tts_corpus22.txt` / `tts_oracle22.txt` | corpus-piège et oracle (réf. FrogNano 13/14) |

GitHub : PR du même jour (docs). Watchlist : candidat n°1 descendu, Qwen3.5-9B
reprend la tête de file.
