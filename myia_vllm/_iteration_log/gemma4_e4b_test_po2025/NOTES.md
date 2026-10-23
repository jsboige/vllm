# Test Gemma-4-E4B-it W4A16 — po-2025, 23/10 13:25→13:43 locale (fenêtre GO user)

## Mandat

User 23/10 : « bascule sur l'image latest pour faire des tests avec le nouveau
modèle 4B », après reboot hôte + demande de réarmement cron (les 2 crons
session-only avaient survécu — `CronList` vérifié, rien à recréer).

## Enquête d'identification (tout VERIFIÉ, pas SUPPOSÉ)

- **`vllm/vllm-openai:latest` == v0.32.0** : digest manifest identique
  (`sha256:befccf0e7e40…`, poussé 18/10 10:53Z par vllmbot, comparé au tag
  `v0.32.0`). Aucune release vLLM plus récente. L'image FrogNano en prod ÉTAIT
  déjà « latest » — la bascule d'image est un no-op digest-wise.
- **Aucun FrogNano nouveau** : `microsoft/FrogNano-4B-2609` — commits = README
  seul (02/10, 22/09), poids du 17/09 inchangés ; aucun « 2610 » nulle part
  (API HF author=microsoft + search global + presse). L'activité communautaire
  d'octobre est 100 % dérivée du 2609 (quants GGUF/MLX/PARO/ONNX + EXL3).
- **Lignée « heretic »** (richardyoung + saidutta69, 13-20/10) = ABLITERATION
  (Heretic v1.4/v2.0, KL 0.0046-0.0395, refus 99→12/100, aucune éval coding
  post-ablation) — **écartée** : zéro utilité pour un tier lecture flotte.
- **Autres 4B d'octobre** : `microsoft/UserRepGen-4B` (14/10) = générateur de
  représentation utilisateur, niche, pas un chat générique. Reste :
  **`google/gemma-4-E4B-it`** (famille gemma4, sortie juillet, remontée dans
  les actus via DiarizationLM-Gemma-4-E4B le 04/10) — instruct, Apache-2.0.
- **Support vLLM** : registry de NOTRE image v0.32.0 contient
  `Gemma4ForCausalLM`, `Gemma4ForConditionalGeneration` (l'arch du checkpoint),
  `Gemma4Unified…`, `Gemma4DSparkModel`, `Gemma4MTPModel` — natif, pas de
  nightly nécessaire.
- **Variante retenue** : `google/gemma-4-E4B-it-qat-w4a16-ct` — QAT officiel
  Google, compressed-tensors pack-quantized W4A16 (même famille Marlin que la
  prod), public (gated=false), 278 k downloads. **Seule E4B viable a priori
  sur 16 Go** : le BF16 intégral dépasse la carte.
- ⚠ **Le « E4B » est un 4B EFFECTIF mais un checkpoint de 8,61 Md de params**
  (embeddings per-layer + tour vision 16 couches + tour audio 12 couches +
  lm_head NON quantifiés, BF16) : 11,51 Go sur disque.

## Déroulé (3 boots, tout mesuré dans les logs moteur)

| Essai | Config | Résultat |
|---|---|---|
| 1 (13:25) | gpu-util 0.80, batch 8192, 32K | `ValueError: No available memory for the cache blocks` — 0 bloc KV |
| 2 (13:30) | gpu-util 0.85, batch 4096, 32K, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0` | KV dispo **−2,3 Gio** — poids **10,17 Gio** + socle ~6,1 Gio |
| 3 (13:38) | gpu-util 0.92, batch 1024, 16K, **`--enforce-eager`** | ✅ BOOT — KV dispo **+4,28 Gio** → **201 136 tok KV (12,28× à 16K/req)**, init 2,39 s |

Fait clé : le socle fixe hors poids passe de ~5,5-6 Gio à ~0,3 Gio quand on
retire les CUDA graphs — **la capture de graphs de ce modèle mm consomme
~5 Gio** (PIECEWISE 11 + FULL 2). Le batch (4096→1024) ne bougeait presque
rien (6,06→5,55 Gio) : c'était les graphs, pas les activations.

## Gates (RETRY 3, EAGER — débits NON comparables à une config graphs)

| Gate | Valeur | Référence FrogNano prod |
|---|---|---|
| health + served name | 200, `gemma-4-e4b` | idem |
| Capitale 1 mot | `Paris`, 2 tok, 2,83 s | ~0,3-0,5 s |
| Extraction JSON | exact (fence ```json autour), 40 tok, 2,4 s | nu (sans fence) |
| Phrase FR cohérente | ✅ 45 tok, 3,41 s | ✅ |
| Single-stream 256 tok | **15,5 t/s (EAGER)** | 40-75 t/s (graphs) |
| N=16 (64 tok/req) | **73,8 t/s agrégé (EAGER)**, 16/16 OK, 8 s | **1 073 t/s** (fp8 KV) |
| VRAM / temp | 15 358/16 384 MiB (94 %), 41 °C | 15 034 MiB, ~29-69 °C |

## Verdict

**Fonctionnellement sain, structurellement inadapté au tier mini de cette
carte.** L'arch gemma-4 + le quant W4A16-ct servent correctement sur stock
v0.32.0 (= latest) — c'est un datapoint de compatibilité réel pour la flotte.
Mais :

1. **Seule config qui tient en 16 Gio = eager** (les graphs n'entrent pas) →
   single 15,5 t/s, N=16 **73,8 t/s = 14,5× plus lent** que FrogNano.
2. L'écart est STRUCTUREL, pas du tuning : 10,12 Gio de poids (62 % de la
   carte) pour un « 4B effectif » qui est un 8,6 Md de checkpoint — les parties
   BF16 non quantifiables (tours vision/audio, embeddings per-layer, lm_head)
   pèsent plus que TOUT le moteur FrogNano NVFP4.
3. La KV est paradoxalement bonne (201K tok, 12,3×) — le modèle n'est pas
   limité par la fenêtre mais par le débit.

**Rollback exécuté 13:42:43 locale** (boot chaud, volume compile intact),
conformément au plan annoncé (ping 41, DM po-2028) : profil de test conservé
comme record, aucun changement prod.

## Perspectives (non testées, SUPPOSÉ)

- `gemma-4-E2B-it-qat-w4a16-ct` (2B effectif, ~moitié des params) : pourrait
  entrer AVEC graphs — mais ce n'est plus un « 4B », hors mandat du jour.
- La famille gemma-4 sur une carte 24 Go (ai-01 GPU 2 en fenêtre dédiée,
  à demander) : les graphs rentreraient, débit à re-mesurer.
- MTP gemma-4 (`Gemma4MTPModel` au registry) : non exploré.

## Artefacts

- Profil : `myia_vllm/configs/docker/profiles/mini-gemma4-e4b-po2025-test.yml`
  (l'en-tête porte l'historique des 3 essais + le verdict).
- Cache HF : `~/.cache/huggingface/hub/models--google--gemma-4-E4B-it-qat-w4a16-ct`
  (snapshot `6cd26aaa…`, 10,75 Gio) — conservé (C: 792 Go libres), à supprimer
  si l'espace devient critique (fichiers nommés, jamais de rm -rf).
- Volume compile `vllm-compile-cache-gemma4e4b-v0320` : ne contient que le
  eager-run (aucune compilation de graphs) — inerte.
