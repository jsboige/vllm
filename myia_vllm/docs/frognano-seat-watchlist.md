# Watchlist modèles — siège po-2025 (3080 Ti 16 Go, FrogNano-4B en prod)

Mandat user 03/11 matin : veille permanente sur d'éventuels modèles donnant de meilleures perfs
sur cette machine, **en vérifiant les quants disponibles**. Contrainte de siège : plafond
pratique ~**14,4 Go** de VRAM (16 384 MiB − marge desktop), moteur `:5003`, pool KV fp8.
Le user attend explicitement « un bon 9B » (décision pivot 29/10).

## `LiquidAI/LFM3-1.7B` — ❌ **écarté le 03/11 sur la fiabilité** (le plus rapide du siège, mais pas fiable seul)

> **Verdict mesuré le 03/11** (`_iteration_log/lfm3_reliability_po2025/NOTES.md`) :
> **il hallucine PLUS que FrogNano**, critère explicite du user → **pas d'onboarding**,
> FrogNano reste en prod. Contrôle apparié, même corpus 22 lignes, même session :
>
> | | rendues | réelles | couverture | délibération dans `content` |
> | --- | --- | --- | --- | --- |
> | FrogNano-4B | **13** | 13 | 13/14 | **0** |
> | LFM3-1.7B | 41 | 13 | 13/14 | **27** |
>
> **`enable_thinking:false` est COSMÉTIQUE sur ce checkpoint** : le template émet bien
> `<think></think>` vide, mais **le raisonnement fuit en clair dans `content`** dès que la
> tâche est difficile (`Wait, let us list exactly…`, re-listes abrégées `... temp=31C ...`,
> corpus re-dumpé annoté `-> include`). Le flag supprime l'enveloppe, pas le comportement.
> Sur 120 lignes avec `mt=4096` il atteint **42/42, 0 fabrication** — mais en recopiant
> **73 lignes hors-motif** (précision 37 % contre 100 % pour FrogNano), et le comportement
> **varie d'un run à l'autre**. Ce qui marche : piège d'hallucination → `AUCUNE` (correct),
> appel d'outil → `finish=tool_calls` bien formé.

Faits techniques vérifiés (conservés pour un successeur éventuel) :

- **`enable_thinking` est natif au template** (`chat_template.jinja` l. 3) — mécanisme Qwen,
  mais **sans effet réel sur la délibération** (voir verdict ci-dessus).
- **Le template rend les outils** (22 occurrences) au format `<tool_call>/<function=…>/<parameter=…>` ;
  `--tool-call-parser qwen3_coder` fonctionne.
- **Piège de service** : `--reasoning-parser deepseek_r1` + `enable_thinking:false` ⇒ **`content`
  vide**, tout part dans `reasoning` (le parser cherche un `</think>` qui n'arrive jamais).
  **Retirer le parser.**
- **Débit** : KV 408 734 (12,47× le contexte), 110,8 / 615,1 / 1 245,9 tok/s à N=1/8/16
  = 0,96× / 1,16× / **1,50× FrogNano**, 0 erreur/25, TTFT ≤ 0,43 s.
- Servable par l'overlay conservé `vllm-openai-v0320-lfm3:v1` (poids 3,3 GB sur le siège).

**Ré-ouvrable si** un template ultérieur rend `enable_thinking:false` réellement silencieux,
OU si le siège reçoit un trafic où le débit devient le facteur limitant — **et alors avec la
porte mécanique devant**, jamais en producteur direct.

## ❌ `axteam/gemma-4-12B-it-AWQ-4bit` — **INFaisable sur ce siège, testé le 03/11** (était candidat n°1)

> **Verdict mesuré le 03/11** (`_iteration_log/gemma4_12b_po2025/NOTES.md`, fenêtre GO user) :
> **le modèle ne tient pas sur la 3080 Ti 16 Go** — la fiabilité n'a même pas pu être mesurée.
> Trois configs, trois causes distinctes :
>
> | Config | Échec |
> | --- | --- |
> | util 0.85, 32K, KV fp16 | KV requis **5,82 GiB** > dispo **2,79 GiB** |
> | util 0.88, 32K, **KV fp8** | **FP8 KV interdit sur SM 8.6** (fp8e4nv exige SM89+ — la carte est Ampere) |
> | util 0.88, **16K**, KV fp16 | KV requis **5,25 GiB** > dispo **3,29 GiB** ; max estimé **10 240** |
>
> **La cause racine est la géométrie KV** : têtes hétérogènes `{sliding: 256, full: 512}` —
> les couches sliding coûtent **~307 Ko/tok** jusqu'à une fenêtre ≥ 16 K, les full ~37 Ko/tok,
> soit **~343 Ko/tok uniforme** sous la fenêtre (contre ~16 Ko/tok fp8 pour FrogNano). Réduire
> le contexte ne réduit presque pas l'exigence KV tant qu'on reste sous 16 K. Poids 8,45 GiB
> (l'estimation tenait) — c'est bien le KV qui tue.
>
> **Config max faisable : ~8-10 K de contexte, pool KV ~10 K tokens** = 1 conversation.
> Le motif horde N=16 (~24 K tokens) est impossible, le contexte est ÷4 vs FrogNano.
> **Ré-ouvrir sur une carte ≥ 24 Go** (8,45 + 5,25 + ~1,5 ≈ 15,2 GiB → confortable) —
> poids 7,87 Go conservés dans le cache HF du siège.
>
> **Leçon watchlist** : « archi dans le registre » ≠ « servable au contrat ». Avant tout
> téléchargement, lire `head_dim` par famille de couches ET la fenêtre glissante dans
> `config.json` — deux lignes qui auraient prédit l'échec sans fenêtre moteur.

Faits techniques vérifiés avant l'échec (conservés pour un successeur éventuel) :

- Base `google/gemma-4-12B-it`, **Apache-2.0**, **non gated**. Modifie le **2026-11-02** (tout neuf).
- Quant **`compressed-tensors` / `pack-quantized` W4A16** — exactement le format servi en prod sur
  Swift-1.5-27B, donc le chemin Marlin/WNA16 deja eprouve.
  `ignore` = `vision_embedder.patch_dense`, `embed_vision.embedding_projection`,
  `embed_audio.embedding_projection`, `lm_head` (BF16), c'est-a-dire la convention saine.
- **Archi servable par l'image stock** : `Gemma4UnifiedForConditionalGeneration` est enregistre
  dans `vllm/model_executor/models/registry.py:427` et `gemma4_unified.py` est dans l'arbre
  de v0.32.0. **Aucun overlay a construire** — ce qui distingue ce candidat de [[reference-lfm3-overlay-eval]]
  (overlay) et de Nanbeige (overlay).
- Config : 48 couches, hidden 3840, intermediate 15360, 16 tetes, hybrid
  `sliding_attention` + `full_attention` (1 couche pleine sur 6) — favorable au KV.
  **`max_position_embeddings` = 262 144** (contre 32 768 configures sur FrogNano).
- **Vision ET audio** (`image_token_id`, `audio_token_id`).

**ESTIME, non mesure** : fit VRAM ~9-10 Go (6-6,5 Go de poids W4A16 + embeddings BF16
262K x 3840 = ~1 Md de parametres, soit ~2 Go) sous le plafond de ~14,4 Go ⇒ ~4 Go pour le KV
et les activations. **A verifier par un boot reel**, pas a prendre pour acquis : c'est le point
qui a tue le 27B sur ce siege.

**RISQUE A PONDERER** : l'uploadeur `axteam` / WINSTECHNET_AX est **petit** (2 likes,
335 telechargements, compte de 7 jours). Les quants `RedHatAI` du candidat n°2 sont d'un
tiers bien plus etabli. Un mauvais quant est indetectable avant de l'avoir servi — prevoir
un A/B qualite contre le BF16 de base avant toute promotion, pas seulement un test de debit.

**Prochain geste si le user donne un GO** : fenetre de ~10 min, boot stock sur `:5024`,
gates verbatim d'abord, puis mesure de debit a N=1/8/16. Meme protocole que le 02/11 et le 03/11.

## `cyankiwi/Ornith-1.5-9B-AWQ-INT4` — ✅ **MESURÉ le 03/11 : tient sur le siège et bat FrogNano sur la classe servie** (arbitrage user)

> **Verdict mesuré** (`_iteration_log/ornith_15_9b_po2025/NOTES.md`, fenêtre GO user, `:5003`
> indisponible 8 min 30) — le modèle **boote et sert**, contrairement au 12B :
>
> | | FrogNano-4B (prod) | Ornith-1.5-9B |
> | --- | --- | --- |
> | Verbatim corpus-piège 22 lignes | 13/14 | **14/14** |
> | Bruit / fabrications (thinking off) | 0 / 0 | **0 / 0** |
> | Stabilité inter-runs | stable | **3/3 identiques** |
> | Débit N=16 | **829,1 tok/s** | 506,7 tok/s (**0,61×**) |
> | Pool KV | **426 473 tok** (13,0 ctx) | 122 523 tok (3,74 ctx) |
> | VRAM en service | 12 724 MiB | 12 530 MiB |
> | Boot | ~80 s | **260 s** |
>
> **`enable_thinking: false` est RÉEL ici** — il supprime les 40 lignes de bruit et tout le
> préambule de délibération sans perdre une ligne de l'oracle. C'est **l'inverse du cas LFM3**, où
> le flag était cosmétique.
>
> **Arbitrage user 03/11 : le thinking n'est pas un problème en soi.** Il ne vide pas `content`
> pour peu que `max_tokens` soit dimensionné pour absorber la délibération — c'est une **erreur de
> protocole de test** de conclure sur une réponse tronquée. Ce que le thinking coûte réellement,
> mesuré : ~40 lignes hors motif pour une couverture **inchangée à 14/14**, et des tokens en plus.
> Le flag reste une **option** pour l'appelant qui veut une sortie propre ; ce n'est **pas** une
> condition de service. Les épreuves doivent donc tourner **thinking actif par défaut**, avec un
> budget de tokens suffisant, et vérifier `content` non vide.
>
> **Comptage (R2)** : échoue comme tout le siège. **Outil (R4)** : `finish=tool_calls` bien formé.
>
> **Ce n'est pas un remplacement à somme nulle** : +1 ligne de rappel et le déterminisme contre
> **0,61× le débit** et **0,29× le pool KV**. Le siège est bâti comme tier horde (mandat 29/10) ;
> **la promotion est un arbitrage user, pas une décision de lane.** Poids 8,40 Go conservés.

**Pré-vérification géométrique PASSEÉE AVANT téléchargement** (leçon Gemma appliquée dès sa première heure) :

- `config.json` lu (`Qwen3_5ForConditionalGeneration`, `model_type: qwen3_5`) — **la famille exacte de
  Swift-1.5 en prod et d'OmniCoder-9B** (cyankiwi avait quantisé ce dernier) ⇒ **zéro overlay**.
- **KV-léger** : 32 couches dont **24 `linear_attention`** (état fixe, pas de KV par token) et **8
  `full_attention`** seulement, `head_dim 256` × **4 têtes KV** ⇒ **~32 Ko/tok fp16** (fp8 KV interdit
  SM 8.6) — la classe FrogNano, l'opposé de Gemma (~343 Ko/tok).
- **262 144 natif**, vision (ViT 27 couches), **MIT**, **MTP 1 couche** présent dans le checkpoint.
- Quant **pack-quantized W4A16 group 32** par **cyankiwi** — le quantiseur du Qwen3.6-35B-AWQ resté
  en prod des mois. Calibration « STEM and Agentic », version 26.05.01. Poids 8,99 Go (3 shards).
- Fit estimé (overhead mesuré chez Gemma 2,34 Gio) : util 0.88 ⇒ KV ~3,4 Gio ⇒ **~3 contextes pleins
  de 32K, horde N=16 tient**. Inconnue non bloquante : état GDN fp32 par séquence (`max_num_seqs`
  le plafonne), le boot chiffre.

**Ce que c'est** (carte éditeur, RAPPORTÉ) : Ornith-1.5 = self-improvement end-to-end (génération
de tâches + scaffolds + rollouts, RL) par ornith-ai, construit sur Ornith-1.0 lui-même développé
« on top of Qwen3.5 and Gemma4 » avec prétraining continu. Leur table : **Terminal-Bench 2.1
46,2/47 (Terminus-2/Claude Code) contre 21,3/18,9 pour Qwen3.5-9B base** — le fine-tune double la
base sur l'agentic, et passe Gemma-4-31B (42,1). Benchmarks éditeur non vérifiés localement —
la batterie fiabilité du siège tranche (réf. FrogNano 13/14, 0 bruit).

## Candidat rétrogradé — `Qwen/Qwen3.5-9B` (officiel, mars 2026) — **rejeté par le user 03/11 soir**

> **Décision user** : la base brute est « assez vieille » et dominée — leur propre table la met à
> **21,3/18,9 Terminal-Bench 2.1** là où le fine-tune Ornith fait 46,2/47. « On veut mieux que ça. »
> La ligne reste pour mémoire : deux quants W4A16 vérifiés (RedHatAI, sanskar003), fit ~10-11 Go,
> mais la valeur de la tranche 9B est dans ses fine-tunes (Ornith, OmniCoder), pas dans la base.

- **Ce que c'est** : dense 9B officiel Qwen, **vision incluse** (Image-Text-to-Text, ~10 B
  paramètres totaux avec l'encodeur), licence Apache-2.0, thinking `<think>`.
- **Quants vLLM-prêts VERIFIÉS** (compressed-tensors W4A16, servables par stock v0.32.0 —
  l'arch `qwen3_5` est en prod sur ai-01 depuis des mois) :
  - `RedHatAI/Qwen3.5-9B-quantized.w4a16` — carte avec commande `vllm serve` + `--reasoning-parser
    qwen3`, tag `vllm`, llm-compressor ;
  - `sanskar003/Qwen3.5-9B-AWQ` — AWQ W4A16 compressed-tensors, auto-décrit « for efficient
    inference with vLLM ».
- **Fit siège (ESTIMÉ, à vérifier au boot)** : poids W4A16 ≈ 5,5-6 Go + KV fp8 ~2 Go (32 K ctx,
  KV ~16 Ko/tok si la famille 3.5-9B suit le 27B) + activations/overhead ~2,5 Go ⇒ **~10-11 Go,
  sous le plafond** avec de la marge pour du NVFP4 KV.
- **Attente de perf** : OmniCoder-9B (finetune Qwen3.5-9B) faisait 96-107 t/s sur une 4090 ⇒
  **~60-75 t/s attendus en single-stream ici** (vs 115 FrogNano), mais qualité et vision en plus.
  La forme « horde » (N=8/16) reste le bon usage.
- **Précédent utile** : la fenêtre LFM3 (02/11) a validé la recette d'éval complète en ~8,5 min
  (overlay, boot, bench 3 niveaux, verdict, retour FrogNano) — réutilisable telle quelle.

## Candidat n°2 — Gemma 4-9B (Google, avril 2026) — **ré-ouvert 03/11 soir** (le 12B n'a PAS tenu en VRAM)

> **Mise a jour 03/11 soir** : la condition de ré-ouverture « si le 12B ne tient pas en VRAM » est
> **tombée** — le 12B est infaisable (géométrie KV, voir ci-dessus). MAIS l'échec du 12B transfère
> son soupçon au 9B : **vérifier `head_dim` et la fenêtre glissante dans le `config.json` du 9B
> AVANT tout téléchargement** — si la famille garde les têtes hétérogènes `{sliding: 256, full: 512}`
> et la fenêtre 16 K, le 9B paye le même ~343 Ko/tok uniforme (à 9/12 des couches près) et peut
> être infaisable aussi. Deux lignes de config à lire, zéro Go téléchargé.

- INT4 ≈ **10 Go** (18 Go en FP16), d'après la comparaison publique Gemma 4 / Llama 4 / Qwen 3.5.
- **À vérifier avant tout** : quel checkpoint INT4 exact (AWQ/compressed-tensors ?), et le statut
  de l'arch `gemma4` dans vLLM v0.32.0 — l'article de déploiement vLLM × Gemma 4 existe, le
  support semble acquis, mais **aucun quant W4A16 officiel n'est encore identifié** (le 26B-A4B
  MoE n'a PAS de w4a16 — dimensions d'experts trop petites, qualité perdue à 4 bits ; le 9B dense
  n'a pas cette excuse structurelle).
- Moins prioritaire que Qwen3.5-9B (pas de quant vérifiée, licence Gemma plus restrictive).

## Déjà évalués — fermés avec conditions de ré-ouverture

| Modèle | Verdict | Ré-ouvrir si |
| --- | --- | --- |
| Ornith-1.5-9B-AWQ (cyankiwi) | **Mesuré 03/11, tient** : verbatim **14/14** déterministe (×3) contre 13/14 pour FrogNano, mais **0,61× le débit** et **0,29× le KV**. Thinking actif = +40 lignes hors motif, couverture inchangée ⇒ coût de tokens, pas défaut (arbitrage user) | **adopté** le 03/11 (épopée #365) |
| LFM3-1.7B-NVFP4 (LiquidAI) | Servable (greffe v0.32.0+#64959, 1,50× FrogNano à N=16) mais **hallucine plus que FrogNano** (27 lignes de délibération vs 0 ; `enable_thinking:false` cosmétique) | template ultérieur réellement silencieux, ou trafic où le débit limite — **avec porte mécanique** |
| Gemma-4-12B-AWQ (axteam) | **Infaisable** (03/11) : géométrie KV ~343 Ko/tok sous fenêtre 16 K, fp8 KV interdit SM 8.6 | **carte ≥ 24 Go** (poids 7,87 Go conservés dans le cache HF du siège) |
| Nanbeige4.2-3B | 0,89× FrogNano à N=16 et KV 88 Ko/tok ⇒ perdant partout | une version KV compacte |
| Spark-X2.6-4B | dominé sur toutes les métriques (ligne close 24/10) | — |
| Qwen3.8-27B / Nanbeige 4.3-33B | ne passent pas (16 Go) — 33B reste une décision ai-01 | changement de siège |

## Protocole d'éval (recette LFM3, ~10 min par candidat)

1. `hf download` avec `HF_HUB_DISABLE_XET=1` (gotcha stub 9p, 3ᵉ occurrence mesurée), vérifier
   `du -sb`.
2. Profil dédié `mini-<modèle>.y` sur `:5023` (jamais toucher `:5003`), gpu-util ~0.90, KV fp8.
3. `bench_capacity.py --base http://localhost:5023/v1/chat/completions` : N=1/8/16, TTFT, KV,
   contexte. **Gates qualité** : verbatim 3 niveaux (le piège LFM3), sonde thinking, tool parser.
4. Critère de promotion : **verbatim d'abord** (c'est la classe servie), qualité/debit ensuite.
5. Retour FrogNano vérifié par génération réelle + `docker stats`.

Toute fenêtre moteur sur ce siège = annonce dashboard avant + GO user (règle en vigueur).
