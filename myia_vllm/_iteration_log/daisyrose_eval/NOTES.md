# DaisyRose-27B-W4A16-HGPTQ — qualification du chargeur (20/11/2026)

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

## Prochaine étape

1. ~~Vérifier la taille téléchargée.~~ Fait, voir ci-dessus.
2. Demander un créneau GPU 2 à CoursIA (le GPU 2 leur appartient).
3. Banc : conteneur `vllm-openai-v0340-tierpin:v1` (ou stock v0.34.0) sur GPU 2 seul
   (`CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=2` : `--gpus device=2` n'isole plus
   depuis le 30/10), `--trust-remote-code`, `--enforce-eager`, 32K, NVFP4 KV, pas de MTP.
   Mêmes prompts de qualité que Swift (harnais `qwen38_27b_gpu2/quality_27b.py`), en paires.
4. Critère : DaisyRose ne devient candidate à une fenêtre TP=2 que si elle bat Swift sur les
   tâches à paires appariées. Sinon, la fiche se ferme ici.
