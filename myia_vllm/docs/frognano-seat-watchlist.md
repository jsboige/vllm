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
> |---|---|---|---|---|
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

## Candidat n°1 — `Qwen/Qwen3.5-9B` (officiel, mars 2026)

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

## Candidat n°2 — Gemma 4-9B (Google, avril 2026)

- INT4 ≈ **10 Go** (18 Go en FP16), d'après la comparaison publique Gemma 4 / Llama 4 / Qwen 3.5.
- **À vérifier avant tout** : quel checkpoint INT4 exact (AWQ/compressed-tensors ?), et le statut
  de l'arch `gemma4` dans vLLM v0.32.0 — l'article de déploiement vLLM × Gemma 4 existe, le
  support semble acquis, mais **aucun quant W4A16 officiel n'est encore identifié** (le 26B-A4B
  MoE n'a PAS de w4a16 — dimensions d'experts trop petites, qualité perdue à 4 bits ; le 9B dense
  n'a pas cette excuse structurelle).
- Moins prioritaire que Qwen3.5-9B (pas de quant vérifiée, licence Gemma plus restrictive).

## Déjà évalués — fermés avec conditions de ré-ouverture

| Modèle | Verdict | Ré-ouvrir si |
|---|---|---|
| LFM3-1.7B-NVFP4 (LiquidAI) | Servable (greffe v0.32.0+#64959, 1,50× FrogNano à N=16) mais **thinking inline non séparable** — verbatim NON aux 3 niveaux, rédhibitoire pour la délégation | merge de vllm#64959 **et** un `--chat-template`/parser qui sépare le raisonnement |
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
