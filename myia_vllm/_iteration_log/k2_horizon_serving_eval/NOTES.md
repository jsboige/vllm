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
