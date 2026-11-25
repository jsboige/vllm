# Lane po-2023:vllm — instructions du siège embeddings

> Siège inauguré le 2026-10-20 (mandat user) après la panne matérielle de po-2026
> (HS 09/10). Prédécesseur : [`po2026-embeddings.md`](po2026-embeddings.md) — ses
> doctrines vigie et son runbook restent la référence technique.

## Identité

- **Ce siège** (`myia_vllm/` du clone `D:\Dev\vllm`) = poste de travail de la lane
  **embeddings de la flotte** sur le fork `jsboige/vllm`. Siblings vllm :
  `myia-ai-01` (prod Swift-1.5-27B), `myia-po-2025` (FrogNano + hub).
- **Runtime de service** : depuis le cutover IIS du 2026-10-14 00:50Z, la chaîne
  entière tourne sur po-2023 — IIS ARR local → sidecar `:8004`
  (`embedding-proxy-logger`) → vLLM `:8005` (`qwen3_4b_awq_embedding_server`).
- **Machine bi-GPU** : GPU 0 = RTX 3080 Ti interne 16 Go (embedder, pinné via
  `device_ids: ['0']` + `CUDA_DEVICE_ORDER=PCI_BUS_ID`, PR #118) ; GPU 1 = RTX 3090
  externe 24 Go, **occupé par une autre lane — ne jamais y toucher**. Au déploiement :
  vérifier que nvidia-smi index 0 = le 3080 Ti libre.

## Surveillance (mission première)

- **Cron 5 h à :17** (mandat user 2026-10-20, continuité du mandat po-2026 d'octobre),
  session-only : CronList d'abord, ré-armement idempotent, jamais de doublon.
- Spec : skill `/surveillance-embeddings` (écrit pour po-2026 — traduire les chemins,
  cf. « Chemins du siège » ci-dessous ; les pièges et le rôle vigie restent intégralement valables).
- **Rapports → dashboard workspace `vllm`** (tag `DONE`). Le workspace `Embeddings`
  portait le fil po-2026 ; bascule à l'inauguration po-2023.
- Clé de test : `D:\Production\Embeddings\compose\.env` (`VLLM_API_KEY`) — jamais
  affichée ni postée. Contrat stable vérifié chaque cycle : POST réel public →
  **dims 2560**.

## Non-négociables (héritées po-2026)

1. `https://embeddings.myia.io` + modèle `qwen3-4b-awq-embedding` + dims 2560 stables —
   tout changement = réindexation flotte (6,2M+ points).
2. Clés uniquement dans les `.env` gitignored — jamais dans un commit, dashboard ou DM.
3. Jamais de suppression sans preuve de préservation ; jamais de restart Docker
   automatisé sans cadre user (co-locataires sur po-2023 : claudish-proxy, comfyui,
   stacks TTS/whisper, searxng…).
4. Un chiffre cité est mesuré, avec sa source ; qualifier VERIFIÉ / RAPPORTE / SUPPOSÉ.
5. Commits conventionnels ; PR vers `jsboige/vllm` ; ne jamais pousser vers `upstream`.
6. Convention flotte : écrire **po-2023/po-2024** (jamais po-203/po-204).

## Chemins du siège (po-2023)

- `.env` prod : `D:\Production\Embeddings\compose\.env` (`VLLM_API_KEY`,
  `HUGGING_FACE_HUB_TOKEN`).
- `QDRANT_API_KEY` (baromètre double) : dans `C:\Users\jsboi\.roo-state-manager\.env`
  (le `.env` du MCP RSM — validée 200 le 20/10 ; `D:\Dev\roo-extensions\.env` porte
  une copie stale, 401).
- Compose actif : profil repo `configs/docker/profiles/embeddings-qwen3-4b-awq-po2026.yml`
  (nom historique conservé), lancé avec `--env-file` vers le `.env` prod ci-dessus.
- Sidecar : script `D:\Production\Embeddings\scripts\embedding-proxy-logger.py`,
  logs `D:\Production\Embeddings\logs\capture-20261013\` (jsonl vidé à chaque restart
  du sidecar — copier avant restart si préservation nécessaire).
- Gouverneur thermique : **ABSENT de ce siège** (ni schtask ni undervolt migrés ;
  runbook po-2026 = procédure prête). Vigie : alerte >85 °C (registre Q-P2023-1).
- Qdrant prod : `https://qdrant.myia.io` + LAN `http://192.168.0.47:6333` (distant .47).

## Avant tout redémarrage de l'embedder : contrôle de VRAM (2026-11-25, c177, complété c178)

GPU 0 est occupé par des conteneurs d'autres lanes, **pas par le bureau Windows** :
mesuré au c178 (25/11 ~19:50Z, compteurs perf `GPUProcessMemory`) — `dwm`,
`explorer`, Edge et VSCode tiennent l'iGPU Intel et le 3090, et **120 MiB seulement**
côté Windows sur GPU 0 ; tout le reste (15 556 MiB) est attribué à `vmwp`, c'est-à-dire
aux allocations des conteneurs dans la VM WSL — dont **`comfyui-qwen`, vérifié sur cette
carte par son propre journal** (`Device: cuda:0 NVIDIA GeForce RTX 3080 Ti Laptop GPU`,
conteneur démarré 23/11 01:30Z). Le moteur refuse de démarrer si la carte est trop
pleine — règle lue dans le code v0.23.0 (`vllm/v1/worker/utils.py:405`) :
**mémoire libre ≥ `gpu-memory-utilization × total` à l'init** (≥ 12,3 GiB à 0,75),
sinon `ValueError: Free memory on device ... is less than desired GPU memory
utilization` et le conteneur crash-loop. Soit **≤ ~4 Go tenus par des tiers**.

- Contrôle, moteur tournant : `nvidia-smi --query-gpu=index,memory.used,memory.free
  --format=csv` → GPU 0 `memory.used` ≤ ~10,3 Go (moteur ≈ 6,7 Go + ≤ 4 Go de tiers).
- Au-delà : **ne pas redémarrer** ; faire libérer la carte par la lane propriétaire
  d'abord (régleur GPU : `myia-ai-01:CoursIA-2` ; locataires : po-2023:CoursIA).
- Monter `--gpu-memory-utilization` n'aide pas (l'exigence de mémoire libre monte) ;
  la baisser rend le KV négatif (besoin propre du moteur ≈ 9,2 GiB). Le « pallier
  0,90 » du profil ne vaut que pour de la mémoire étrangère arrivant pendant le profil.
- Mesuré le 25/11 (c177 14:56Z et c178 19:50Z) : **15 671 MiB occupés, 503 libres**,
  ~9 Go de tiers résidents ⇒ embedder non redémarrable tant que le niveau reste là
  (signalement global + CoursIA, question au registre du siège).
- **Qui les tient** (c178 ; journaux des conteneurs lus, aucun geste) :
  `comfyui-qwen` = **VERIFIÉ** sur GPU 0 (`Device: cuda:0 NVIDIA GeForce RTX 3080 Ti
  Laptop GPU`, `Total VRAM 16384 MB`, démarré 23/11 01:30Z — cause probable de
  l'incident du 04/11, « ~11 Go de contexts étrangers », traité alors en arrêtant ce
  conteneur) ; `tts-api` = SUPPOSÉ même carte ; `comfyui-video` = **VERIFIÉ** sur le
  3090 malgré `CUDA_VISIBLE_DEVICES=0,1`. Cause de configuration : `comfyui-qwen` et
  `tts-api` portent `CUDA_VISIBLE_DEVICES=1` **sans** `CUDA_DEVICE_ORDER=PCI_BUS_ID`,
  et l'ordre CUDA par défaut est FASTEST_FIRST (le 3090 prend l'index 0, l'index 1
  désigne donc la 3080 Ti) ; sous WSL2 `device_ids`/`--gpus` ne restreint pas
  l'énumération. Correctif chez leur lane : poser `CUDA_DEVICE_ORDER=PCI_BUS_ID` sur
  les deux premiers, retirer GPU 0 de `comfyui-video`.
- **Portée de la règle** : elle vaut pour un redémarrage de l'**embedder seul**, VM
  Docker debout. Un redémarrage de la VM (Docker Desktop, `wsl --shutdown`) vide la
  carte mais coupe tous les conteneurs ; l'embedder repart alors en concurrence avec
  ses locataires — sans le correctif ci-dessus, c'est une course, pas une garantie.

## Fix keep-alive sidecar (2026-10-20, PR #134)

Les `ServerDisconnectedError` dans les logs du sidecar (9 111 du 13 au 20/10,
uniquement au call site du forward amont) ont deux causes :

- **98 % = fenêtres mortes vLLM** : Docker publie `:8005` dès le start du
  conteneur alors que l'APIServer vLLM n'écoute qu'après boot complet (~2-3 min).
  Chaque requête IIS dans la fenêtre = accept-then-close → 500 consommateur.
  Corrélé 1:1 aux 11 boots vLLM de la semaine (15/10 ×3 : 5 622 erreurs 13-14h ;
  incident disque 19/10 22h : 3 092 ; reboot user 20/10 : 231). Baromètre Qdrant
  (2 547 977 → 2 593 672 pts sur la période) : les retries indexateurs ont tout
  comblé, zéro perte.
- **~2 % = course keep-alive** : uvicorn ferme ses connexions idle pendant que
  le pool `ClientSession` du sidecar les réutilise (~25/j de bruit de fond).

Fix déployé 20/10 13:05Z : `TCPConnector(force_close=True)` (connexion fraîche
par requête, localhost) + retry 1× sur `ServerDisconnectedError` (PR #134,
script repo = script prod, monté read-only dans le conteneur). Les fenêtres
mortes réelles restent des erreurs légitimes après épuisement du retry —
signature normale d'un boot vLLM sous trafic, pas une régression. Capture jsonl
préservée avant restart : `embedding_requests.pre-fix-20261020T1500Z.jsonl`.

## Gaps de migration (consignés au registre du siège)

1. Gouverneur thermique non migré (Q-P2023-1) — surveillance manuelle à chaque cycle.
2. HF token vide dans le conteneur courant (Q-P2023-3, bénin — cache local) — à la
   prochaine re-création : `--env-file D:\Production\Embeddings\compose\.env`.

Baselines d'inauguration (2026-10-20 01:20Z) : warm 176 ms · roo_tasks 2 547 977 pts ·
ws 65 coll. / 7 090 135 pts · cadence sidecar ~175 req/min.
