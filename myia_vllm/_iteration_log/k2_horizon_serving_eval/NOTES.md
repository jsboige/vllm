# K2-Horizon-MoVA-36B-A4B — éval de service (2026-09-22, fenêtre ~18:28→20:0xZ, GO user)

**Question** : K2-Horizon (36B MoE MoVA, qualité agentique supérieure : Terminal-Bench 58.6 vs 32.6) peut-il remplacer le MoE Qwen3.6 en prod, via un des 3 quants communautaires INT4 ?

**Réponse courte : NON aujourd'hui.** Aucune des 3 voies n'est exploitable : l'une est morte sur CUDA par design (XPU-only), la fork cyankiwi **sert correctement mais décode 15× trop lentement** (sous enforce-eager, handicap MoE-amplifié). La ligne reste ouverte côté qualité — le checkpoint est sain — mais exige soit le merge d'un support CUDA upstream, soit le plugin Siladrim adapté TP=2.

## Les 3 voies (toutes vérifiées au source, pas au ouï-dire)

### Voie 1 — overlay v0.30.0 + PR #56637 : MORTE sur CUDA
- PR propre (2 fichiers, +230/−54, `k2_horizon.py` inchangé entre base et v0.30.0 → apply file-for-file propre). Image `vllm-openai-v0300-s56637:v1`.
- **Mais** : le guard (k2_horizon.py:~744 dans l'image) exige `isinstance(method.kernel, XPUwNa16LinearKernel)` — le support GPTQ MoVA quantifié du PR est **Intel XPU uniquement** (l'auteur urakozz sert sur Arc Pro B70). `NotImplementedError` déterministe au boot sur CUDA, quels que soient sym/desc_act du checkpoint.
- Checkpoints concernés (tous deux téléchargés, cache jesse, inutilisables sur cette voie) : urakozz AutoRound GS-64 (22,3 G), Siladrim GPTQModel GS-128 (21,8 G).
- Profil `medium-k2-horizon-gptq.yml` conservé comme documentation du mort.

### Voie 2 — fork cyankiwi `k2-mova-quant-v-experts` : SERVE mais décodage inutilisable
- Implémentation CUDA-native vérifiée au source (chemin `fused_experts` W4A16 standard, compressed-tensors → `MarlinExperts` confirmé au boot, méthode `pack_quantized_v_experts`, aucune gate XPU).
- Image `vllm-openai-v0290-cyankiwi-k2:v1` = base v0.29.0 locale (`aa542864b00a`) + fork via wheel précompilé épinglé `d2906091` (ancêtre v0.30.0, ère torch identique). Fork installé = `0.1.dev1+g46485cf57.precompiled`.
- Checkpoint `cyankiwi/K2-Horizon-MoVA-36B-A4B-AWQ-INT4` (24,27 G vérifiés, 7 shards, calibration STEM+Agentic).
- **3 échecs de boot avant succès, tous diagnostiqués** :
  1. Crash déterministe dans `aot_compile`→dynamo fullgraph_capture : le forward du fork atteint `with_nvml_context` (`platforms/cuda.py:194`, nvmlInit/nvmlShutdown) — incompatible avec la capture dynamo. **Fix : `--enforce-eager`.**
  2. `ValueError` KV : 131072 tokens exigent 6,0 GiB, disponibles < 6 à gpu-util 0.70. **Fix : `--max-model-len 65536`** (gpu-util inchangé — règle un-changement-à-la-fois, boot-OOM GPU 0).
  3. (Ces deux fixes = profil `medium-k2-horizon-cyankiwi.yml` final.)
- **Boot sain, batterie 8/11 PASS** :
  - PASS : smoke 0,62 s · **canary 3 prompts sains ratio4g=0,00** · tools `get_weather({"city":"Lyon"})` 3,8 s · prefill-30k **3 392 tok/s** · survie ×2 · concurrent-N16 112→123 tok/s agg (0 échec).
  - FAIL (3) : prefill-95k **structurel** (cap 65536) ; thinking = réponse CORRECTE (391 trouvé) mais champ `reasoning` vide — calibration kwarg/parser (`reasoning_effort` via chat_template_kwargs, format `<ifm|think>` non scindé) — à re-regarder, pas un défaut modèle ; **single-stream 6-8 t/s** (prod : 120) = eager × MoE.
- **Verdict perf** : même en créditant un facteur 2-3× de récupération compile/cudagraphs, le plafond serait ~15-25 t/s single — un ordre de grandeur sous le MoE. La cause plausible : kernels v_experts non optimisés (Marlin experts OK au chargement, mais le path MoVA eager + sans graphs tue le décodage).

### Voie 3 — plugin Siladrim (`stefanskiasan/k2-horizon-vllm`, v0.28.0) : non tentée
CUDA/Ada prouvé (L40S : 69 t/s single, 1 020 t/s N=32, int4 KV, 314K contexte) MAIS **TP=1 seul démontré** — notre cas (2×24 GB, checkpoint 21,8 G) exige TP=2. Non tentée dans cette fenêtre.

### Voie 4 — quant maison (recette `quantize_k2_horizon.py`) : dimensionnée le soir même, NE TIENT PAS à 0.70
Seule voie servable par le vLLM **stock** : notre ignore-list garde `self_attn.v_experts` en BF16, et le stock
v0.30.0 n'accepte que ça — `compute_mova_v_sparse` (`k2_horizon.py:812`) fait `torch.stack([expert.weight ...])`
à chaque forward, donc exige un `.weight` non quantifié (un `ColumnParallelLinear` compressed-tensors n'a que
`weight_packed`). Dimensionnement lu dans les en-têtes safetensors du BF16 (`de2d2efb`, 69,75 GiB, lecture seule) :

| Catégorie | BF16 | W4A16 (GS128) |
|---|---:|---:|
| experts MoE (quantifiés) | 49,93 GiB | 12,87 GiB |
| **attn.v_experts MoVA (ignorés, BF16)** | **14,06 GiB** | **14,06 GiB** |
| autres proj. attention (quantifiées) | 3,06 | 0,79 |
| lm_head + embed (ignorés) | 2,40 | 2,40 |
| MLP denses, routers, norms | 0,29 | 0,10 |
| **Total** | 69,75 | **~30,2 GiB → ~15,1 GiB/GPU en TP=2** |

Budget à gpu-util 0.70 : ~16,8 GiB/GPU, activations + KV compris → **KV quasi nul**. (Le quant cyankiwi, 24,3 G
avec v_experts quantifiés, plafonnait déjà à <6 GiB de KV → 65K.) Issues possibles, toutes coûteuses :
(a) éval à gpu-util 0.85 (précédent : profil Ornith FP8, éval seule) mais une adoption prod exigerait 0.85 sur
le GPU 0 partagé avec le bureau, à rebours du calibrage anti-boot-OOM ; (b) quantifier aussi les v_experts →
retour au besoin d'un kernel CUDA non-stock (aujourd'hui : le fork cyankiwi, eager) — notre quant n'apporterait
alors rien de plus que celle de cyankiwi ; (c) attendre l'upstream. SUPPOSÉ, non mesuré : le `torch.stack` par
forward recopie ~0,16 GiB de v_experts par couche et par GPU à chaque pas (~7 GiB de trafic sur 45 couches
MoVA), un plafond de décodage propre à l'implémentation stock.
Checkpoints du harnais de reprise : ~0,17 Go par couche dense, **~1,6 Go par couche MoE** (weight BF16
fake-quantifié + scale + zp) → **~72 Go de disque** pour un run complet (WSL : 257 Go libres).

### Harnais de reprise (checkpoint par couche) — VALIDÉ 22/09 nuit, critère révisé

Prérequis de la règle ferme « checkpoint obligatoire avant tout job > 1-2 h » (user 15/09) pour un run complet
(~49 couches, ≥ 10 h). Trois runs de 7 couches, 8 échantillons de calibration, GPU 2 :

- **test1** : interrompu après la couche 4, **repris** par injection des couches 0-4 depuis le checkpoint
  (`RESUME: injected packed params for 780 modules across 5 layers`, après le correctif d'adressage au module
  feuille `95f2c1c061`), couches 5-6 recalculées ;
- **test2** et **test3** : deux runs frais, mêmes arguments.

**Le critère « bit-exact » était mal posé.** Le premier verdict (`VERIFY_RESULT=DIFFER`, test1 vs test2)
montrait des écarts dès les couches 0-2, calculées à neuf dans les deux runs : GPTQ sur GPU n'est pas
déterministe d'un run à l'autre. Les entiers (zero-points) sont identiques partout ; seuls les poids BF16
fake-quantifiés diffèrent. Le bon critère est donc : **l'écart reprise-vs-frais doit rester dans le bruit
frais-vs-frais**, en particulier sur les couches recalculées après la reprise (5-6).

| Couche | frais vs frais : éléments ≠ / L1 rel. | reprise vs frais : éléments ≠ / L1 rel. |
|---|---|---|
| L0 (dense) | 0,149 % / 1,32e-3 | 0,154 % / 1,38e-3 |
| L1 (dense) | 1,342 % / 6,54e-3 | 1,266 % / 6,27e-3 |
| L2 (dense) | 1,571 % / 1,07e-2 | 1,557 % / 1,06e-2 |
| L3 (MoE) | 9,086 % / 5,82e-2 | 9,066 % / 5,81e-2 |
| L4 (MoE) | 7,969 % / 5,13e-2 | 7,988 % / 5,14e-2 |
| **L5 (MoE, après reprise)** | 10,015 % / 6,42e-2 | **9,967 % / 6,39e-2** |
| **L6 (MoE, après reprise)** | 10,286 % / 6,61e-2 | **10,279 % / 6,61e-2** |

Mots entiers différents : 0 % partout, dans les deux comparaisons. **Un run repris est indiscernable d'un run
frais** : le harnais de reprise est bon pour un run long. Ce que ce tableau montre aussi : deux quantifications
fraîches du même modèle diffèrent de ~10 % des éléments par couche MoE (L1 rel. ~6 %) avec 8 échantillons — une
propriété de la calibration elle-même, pas du harnais ; l'effet sur la qualité se mesure au bench, pas ici.
Coût : ~1 h 26 pour 7 couches (couche MoE ~21 min). Checkpoints de test conservés (3 × 6,5 Go, WSL
`~/k2-ckpt-test{1,2,3}`), GPU 2 rendue (45 MiB).

Cela ferme le volet « harnais » de la question Q3 ; le volet de fond (la quant maison ne tient pas à 0.70,
voir Voie 4) reste à l'arbitrage user.

## A/B (bench petits prompts, même soirée)
- Baseline prod MoE (chaud) : N=1 61,7 · N=4 186,4 · N=8 390,6 · N=16 **762,4 t/s**
- K2 fork eager : N=16 **112-123 t/s** (batterie), single 6-8. Comparaison biaisée par eager — mais l'ordre de grandeur écarte tout retournement.

## Suivi
- Le jour où un support CUDA des v_experts quantifiés atterrit upstream (ou le PR #56637 gagne un kernel CUDA), la voie overlay redevient la recette (tout est prêt : image, profil, checkpoints, batterie).
- Siladrim plugin TP=2 : question à poser à l'auteur (issue) si la ligne redevient prioritaire.
- Le bug nvml/dynamo du fork mérite un signalement à cyankiwi (leurs instructions de la model card ne mentionnent pas eager).

## Artefacts
- Profils : `medium-k2-horizon-gptq.yml` (voie morte), `medium-k2-horizon-cyankiwi.yml` (voie fork, fonctionnelle eager/65K)
- Images : `vllm-openai-v0300-s56637:v1`, `vllm-openai-v0290-cyankiwi-k2:v1` (35 G)
- Checkpoints cache jesse : urakozz 22,3 G · Siladrim 21,8 G · cyankiwi 24,3 G (~68 G total)
- Batterie : `k2_horizon_eval/validate_k2.py` (12 gates adaptées, kwargs reasoning_effort)

## Decision (2026-09-23): parked

User decision on registry Q3, option (b): the in-house W4A16 quant is **not run**. With the
MoVA `v_experts` kept in BF16 (the only form stock vLLM serves, `k2_horizon.py:812`) it needs
~15.1 GiB/GPU at TP=2 against ~16.8 GiB of budget at gpu-util 0.70, leaving almost no KV;
raising gpu-util to 0.85 for an eval was the rejected option (a). Re-open on the first
upstream CUDA path for quantized `v_experts`. Everything listed under Artefacts is kept,
plus the validated resume harness and the three test checkpoints (`~/k2-ckpt-test{1,2,3}`).
