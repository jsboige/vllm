# DaisyRose-27B-W4A16-HGPTQ — chargeur qualifié, banc apparié, non retenue (20/11/2026)

Demande user du 19/11 11:35Z : « étudier l'opportunité de remplacer notre modèle Swift par
<https://huggingface.co/nchapman/DaisyRose-27B-W4A16-HGPTQ> », puis 11:41Z « réserver un test
sur la gpu2 ». Un premier créneau GPU 2 a été rendu sans test le 19/11, faute de poids en
cache et avec un chargeur non qualifié. Cette fiche lève le second préalable. Aucun
déploiement, aucun geste sur la production.

## Provenance

- Dépôt `nchapman/DaisyRose-27B-W4A16-HGPTQ`, révision **`9aef1a7d0402c57249cdc176b34f8e9482a65097`**
  (lastModified 2026-11-19T04:15:25Z), public, non gated, Apache-2.0.
- Base : `RadixArk/DaisyRose-27B` @ `293a7a2a…`, architecture `Qwen3_5ForConditionalGeneration`,
  `model_type: qwen3_5` (la même famille que Swift).
- 18 shards, **17 330 005 464 octets** (16,14 GiB ; 15,70 GiB texte seul). Correction du 20/11 :
  une première version de cette fiche portait 17 329 725 200, chiffre faux. La valeur
  ci-dessus est la somme des tailles LFS de l'arbre Hugging Face à la révision épinglée.
- Quantification : `compressed-tensors`, `pack-quantized`, W4 group 64 (backbone, MTP,
  vision), `lm_head` et `mtp.fc` en W8 g64 non tournés. Rotation de Hadamard en entrée
  (`transform_config`, bloc 64 ; bloc 16 pour `visual.*.mlp.linear_fc2`), appliquée en ligne
  au runtime (`CompressedTensorsLinearTransformMethod` / HadaCore).
- `config.json` porte `"auto_map": {"AutoConfig": "vllm_warp_quant.WarpQuantConfig"}` et le
  dépôt livre `vllm_warp_quant.py` (73 078 octets).

## Le README dit « zero-patch stock vLLM » : c'est faux pour notre image (MESURÉ)

Lu en lecture seule dans le conteneur de production (`vllm 0.34.0`, `compressed-tensors 0.17.0`),
fichier `vllm/model_executor/layers/quantization/compressed_tensors/transform/` :

| Lacune stock | Emplacement | Effet sur DaisyRose |
| --- | --- | --- |
| `assert bias is None` dans `apply` | `linear.py:161` | les couches de vision tournées ont un biais → assertion au premier forward vision |
| `NotImplementedError` si TP > 1 | `module.py:47` | **la config de prod (TP=2) ne peut pas charger ce checkpoint en stock** |

`vllm_warp_quant.py` existe précisément pour combler ces lacunes. Sa docstring le dit :
« Patches four upstream gaps when present in the active vLLM version ».

## Ce que fait le plugin (LU, pas exécuté)

- Chargé par `--trust-remote-code` via `auto_map` : `WarpQuantConfig.from_pretrained` appelle
  `register()`, puis `_install_subprocess_autoload()` qui copie le fichier dans
  `$TMP/warp_quant_vllm_boot_<uid>/`, y écrit un `sitecustomize.py` et **préfixe `PYTHONPATH`**
  pour que l'EngineCore et chaque worker GPU exécutent aussi `register()`.
- `register()` modifie à chaud quatre zones de vLLM :
  1. `CompressedTensorsLinearTransformMethod` : `apply` remplacé (biais ajouté après la GEMM),
     `_validate_tfm_schemes` remplacé (QKV de vision non fusionnée), `SharedWeightParameter`
     (chargeurs row/column), `HadamardTransform.__init__` et `forward`. **Le support TP > 1 passe
     par un `get_tensor_model_parallel_world_size = lambda: 1` temporaire pendant l'init**, plus
     un chemin « boundary-straddling » quand la tranche TP n'est pas multiple du bloc.
  2. experts MoE tournés (inerte ici, modèle dense) ;
  3. W2A16 (inerte ici, W4) ;
  4. PLE LUT4 de `Qwen4Exp` (inerte ici).
- Recherche de motifs à risque sur tout le fichier : **aucun** `subprocess`, `os.system`,
  `urllib`, `requests`, `socket`, `http`, `exec(`, `eval(`, `base64`. Écritures disque :
  seulement la copie et le `sitecustomize.py` sous le répertoire temporaire.

**Conséquence** : un test exécuterait du code tiers qui modifie l'intérieur de vLLM dans tous
ses processus. Pour le banc GPU 2 (conteneur isolé, `CUDA_VISIBLE_DEVICES=2`), le risque est
borné et le code a été lu à cette révision. **Pour la production, ce serait une décision user** :
le chemin TP=2 est un contournement non relu en amont, et il faudrait le vendoriser en overlay
épinglé (comme `overlay_v0340_tierpin`) plutôt que dépendre de `--trust-remote-code`.

## Ce que valent les chiffres de l'auteur

Ils mesurent la **fidélité au BF16 de base** (KL pondérée 0,1110 sur `probe-v4`, top-1 MTP
96,30 % isolé / 89,38 % E2E, top-1 vision 99,01 % / 95,03 %). Ils ne disent **rien de la
qualité face à Swift**, et aucun banc de tâche n'est publié (GSM8K, IFEval, tool calling). Une
perplexité **inférieure** au BF16 (−3,12 % ; −7,19 % sur le holdout) après une distillation KL
calibrée sur `data/calib-cascade-v1.jsonl` signale une évaluation non indépendante, pas un
modèle meilleur que sa base. ⇒ toute décision passe par **notre** banc, sur les mêmes
prompts que Swift.

## Tenue VRAM sur GPU 2 en TP=1 (CALCULÉ depuis des mesures antérieures, non mesuré sur DaisyRose)

Faits mesurés le 12/09 sur ce même emplacement (`qwen38_27b_gpu2/NOTES.md`) : taxe DXG 2,02 GiB,
plafond gpu-util ≈ 0,91, activations ~2,4 GiB, estimation cudagraph ~3,1 GiB. Avec des poids de
16,14 GiB, il resterait environ 0,2 GiB de KV avec les CUDA graphs. Sans eux
(`--enforce-eager`), il resterait environ 3,3 GiB. ⇒ **un banc de QUALITÉ seul est faisable en
`--enforce-eager`**, à contexte réduit (32K) et sans MTP. Le débit mesuré n'y vaudrait rien,
puisque l'enforce-eager coûte 3 à 4×. Une comparaison de débit avec Swift exige TP=2 sur
GPU 0/1, donc une fenêtre de production annoncée, et le plugin.

## Poids

Téléchargés hors du disque WSL : celui-ci porte le cache HF **et** le tier fs de production
(ext4 à 91 %, 88 Go libres le 20/11 ~05:0xZ). Le pruner borne le tier à « libre invité − 40 Go »,
donc 17 Go de poids y retireraient autant de rétention au cache de prod. Destination :
`C:\vllm_models\DaisyRose-27B-W4A16-HGPTQ` (C: 606 Go libres), à monter en lecture seule dans
le conteneur de banc. `HF_HUB_DISABLE_XET=1`, sans jeton, révision épinglée.

**Téléchargement vérifié (20/11 ~05:40Z, MESURÉ).** `hf download` rc=0. Les 35 fichiers de
l'arbre (API `tree/<révision>`) ont tous la taille publiée, 0 écart. Les **19 fichiers LFS**
(18 shards + `tokenizer.json`) ont tous leur SHA-256 égal à l'`oid` LFS publié, 0 écart. Script :
`.tmp/daisyrose/verify_sha.py` (brouillon, non versionné).

## Chargement à sec, sans GPU (20/11 05:39Z, MESURÉ)

Conteneur jetable `--rm --network none`, sans GPU, image `vllm-openai-v0340-tierpin:v1`, poids
montés en lecture seule, `AutoConfig.from_pretrained(..., trust_remote_code=True)` :

- la config se charge en `Qwen3_5Config`, `model_type qwen3_5`, `quant_method compressed-tensors` ;
- le plugin s'enregistre à l'import : `CompressedTensorsLinearTransformMethod.apply` vient de
  `transformers_modules.daisyrose.….vllm_warp_quant`, et `PYTHONPATH` vaut
  `/tmp/warp_quant_vllm_boot_0` (l'auto-chargement des sous-processus est posé).

Ce contrôle ne prouve ni le chargement des poids ni un forward : il élimine seulement une
panne de chargeur avant de consommer un créneau GPU 2.

## Banc qualité sur GPU 2 (20/11 06:36→07:51Z, MESURÉ) — verdict : ne remplace pas Swift

Créneau GPU 2 accordé par CoursIA-2 (06:00→08:00Z). Lanceur de la fenêtre :
[`bench_window.sh`](bench_window.sh), exécuté sous `CoursIA/scripts/ci/run_guarded.py`
(plafond 8 GiB, commit ≤ 90 %, réservation `myia-ai-01#gpu2` tenue puis rendue).

**Déroulé.**

- Une première tentative (06:31:59→06:33:36Z) s'est arrêtée avant tout lancement. La sonde
  d'isolation rendait `1 0000:72:00.0`, avec un domaine PCI à 4 chiffres (`nvidia-smi` en écrit
  8), et le motif ne reconnaissait pas cette forme. C'était un faux négatif : rien n'a démarré. Le
  motif a été corrigé et l'essai relancé à 06:36Z.
- Isolation prouvée : un seul device visible, pci `72:00.0`. Le contrôle de croissance de GPU 0
  pendant le boot n'a pas déclenché (22 580 → 22 591 MiB).
- Poids chargés en 139 s ; `Model loading took 15.93 GiB`. **KV GPU 67 795 tokens** à 32K, soit
  une concurrence max de 2,07×. GPU 2 occupé à 19 341 MiB. Sain à 06:44:41Z (5 min de boot).
- Le plugin `vllm_warp_quant` a tenu en TP=1 : **550 requêtes, 0 erreur**. Ce banc n'exerce ni
  le chemin TP > 1 du plugin ni la vision, donc la lacune `assert bias is None` des couches de
  vision n'a pas été testée.
- Swift a été mesuré **en parallèle sur la prod** (:5002, 2 workers par tâche, trafic réel),
  avec le même harnais `quality_27b.py`. DaisyRose tournait à 4 workers par tâche.
- Les quatre runs se sont arrêtés au budget (`rc=124`, voulu). Teardown à 07:51:01Z,
  observation `released` à 07:51:19Z, GPU 2 revenu à 98 MiB.

**Résultat apparié** (`paired_27b.py`, McNemar sur les items terminés des deux côtés ; le
script étiquette la référence « 3.6 », ici c'est Swift) :

| Tâche | Paires | DaisyRose | Swift | Δ (IC95) | Discordants D / S | McNemar |
| --- | ---: | ---: | ---: | --- | --- | --- |
| GSM8K | 405 | 89,1 % | 89,1 % | +0,0 pt (±3,0) | 10 / 10 | χ² 0,05, ns |
| IFEval (strict, toutes instructions) | 145 | 76,6 % | 78,6 % | −2,1 pts (±6,9) | 3 / 6 | χ² 0,44, ns |

Tokens générés en moyenne : GSM8K 331 (DaisyRose) contre 314 (Swift), IFEval 921 contre 875.
Aucun chiffre de débit n'est tiré de ce banc : DaisyRose tournait en `--enforce-eager` sur un
seul GPU, Swift en TP=2 sous trafic réel, donc les régimes ne sont pas comparables.

**Verdict.** Le critère fixé avant le banc n'est pas atteint : DaisyRose ne bat Swift sur
aucune des deux tâches appariées. Elle est à égalité sur GSM8K et légèrement derrière, de
façon non significative, sur IFEval. Côté coût, l'adoption exigerait un plugin tiers qui
modifie l'intérieur de vLLM dans tous ses processus, plus un chemin TP=2 non relu en amont.
**La fiche se ferme ici** : pas de fenêtre TP=2. Une réouverture demanderait un fait nouveau,
par exemple un banc de tâche publié qui montre un gain, ou un support amont sans plugin.

**Données brutes** (non versionnées, 1,8 Mo) : `D:\vllm_eval_results\daisyrose_20261120\`.
Ce dossier contient `daisyrose/` et `swift-ref/` (JSONL + journaux de run), `window.log` et
`tree.json`. Un `MANIFEST.sha256` les accompagne, vérifié identique à la source au moment de la
copie. Empreintes des JSONL :

- `daisyrose/gsm8k_results.jsonl` `87e302d6…`, `daisyrose/ifeval_results.jsonl` `68fd4eeb…`
- `swift-ref/gsm8k_results.jsonl` `85ac8308…`, `swift-ref/ifeval_results.jsonl` `3b5227ab…`

Les poids restent dans `C:\vllm_models\DaisyRose-27B-W4A16-HGPTQ` (16,14 GiB), hors du disque
WSL. On peut les supprimer si le user ne veut pas d'autre banc.
