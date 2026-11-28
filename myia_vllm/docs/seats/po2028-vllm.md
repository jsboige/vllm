# Siège po-2028 — lane vllm (vllm-c2)

**Inauguré le 2026-11-17** (mandat user en session). 3ᵉ worker sibling du workspace vllm
après po-2025 (FrogNano) et po-2026 (Embeddings). Coordination : dashboard
**workspace-vllm** (rendez-vous unique) ; même machine = messages de session
(RooSync réservé cross-machine).

## Identité

- Session : `vllm-c2` sur po-2028 (Windows 11, Docker 29.9.3 + WSL2 Ubuntu).
- Clone **partagé** `d:/dev/vllm` avec la lane claudish-72 (harnais nb_coder) :
  checkout principal et worktrees de `d:/dev/vllm/.tmp/` sont au driver seul (HEAD
  détaché au 27/11 : état de repos du driver, `wrong_branch` y est normal). **Les
  commits du siège vivent exclusivement dans des worktrees dédiés
  `d:/dev/wt-po2028-vllm-*`** — jamais de `switch -c` sur le checkout principal : les
  passes du driver sont déclenchées par événement, sans fenêtre coordonnable
  (arbitrage claudish-72 du 17/11).
- Données hors repo : `D:\vllm-data\` (modèles, cache HF, artefacts d'éval).

## Matériel (mesuré 17/11/2026, ne pas réétablir ; pilote et CPU : 27/11)

| Élément | Valeur |
|---|---|
| GPU | **RTX 3070 Ti Laptop, 8 192 MiB** (Ampere SM86, driver 621.24 le 17/11, **621.40 depuis le 27/11 17:47Z**) |
| CPU | **i7-12700H, 20 threads** — partagé avec toutes les lanes de la machine et les runners CI |
| KV dtype dispo | fp8 (précédent po-2025 sur SM86) ; **nvfp4 KV hors jeu** (Ada+) |
| Disques | D: 1 431 Go libres / C: 353 Go libres |
| Runtime | Docker 29.9.3 (server) + WSL2 (Ubuntu, docker-desktop Running) |

**Avertissements machine (transmis par claudish-72, 17/11)** : (a) bugcheck organique
**0x116** le 21/10, famille non diagnostiquée (dumps en attente de fenêtre UAC user) —
un crash pendant une éval GPU se rapproche d'abord de cette famille avant d'incriminer
la charge ; (b) gels machine 05-07/11 (BugcheckCode=0) = famine WSL CPU/RAM, pas GPU —
vérifier la marge commit hôte (< 85 %) avant tout boot lourd.

## Mission

1. **Vigie 6h** (cron session-only `17 */6`, à :17 UTC, re-armé chaque cycle ; son ID
   change à chaque ré-armement — `CronList` fait foi) : propreté du checkout partagé,
   GPU (temp × charge croisés), disques, inbox `myia-po-2028:vllm`, dashboards global +
   workspace-vllm, [DONE] en clôture. Ce siège n'a PAS la prod ai-01 — les gates
   Docker/watchdog//dev/shm de la spec ai-01 (`.claude/commands/vllm-surveillance.md`)
   sont hors périmètre ici.
2. **Service voltron** : moteur + façade sur ce siège (état servi ci-dessous).
3. **Promotion du harnais** (mandat user du 18/11) : le faire adopter par les autres
   lanes. Livré : presets sk-agent `voltron-*` (PR #627), façade OpenAI (PR #617),
   en-tête `X-Voltron-Caller` (PR #618), banc commun (#628), banc en régime
   `--thinking` / `--max-tokens` / `--strip-thinking` (PR #629), étage `b` en
   cascade (PR #646), écoute LAN gardée par une clé entrante (PR #647).

## Service voltron — état servi (2026-11-27)

- **Modèle servi depuis le 2026-11-27 21:49:48Z : `Akahsizrr/voltron-1.1-mini`**
  (finetune LFM3-1.7B BF16), noms servis `voltron-1.1-mini` et `voltron-1-mini`
  (alias, pour que les instruments existants ne cassent pas). Avant :
  `Akahsizrr/voltron-1-mini` (1.0), du 17/11 au 27/11.
- Moteur : conteneur `voltron-harness`, `127.0.0.1:5028` → 8000, image
  `vllm/vllm-openai@sha256:b6d1cfc60cce1f6405d37ea77645a36a46065230fb643abc2eeb93a5dc8fb79b`
  (vLLM `v0.34.0rc1.dev672+g8ca766326`), modèle monté en lecture seule depuis
  `D:\vllm-data\models\voltron-1.1-mini`. **La source de vérité des options de
  lancement est `myia_vllm/scripts/testing/start_voltron_service.ps1`** — elles se
  relèvent dans le script, jamais ne se reconstruisent de mémoire (boot raté du 26/11
  16:31Z : `--kv-cache-memory` oublié).
- Serveur : `myia_vllm/scripts/testing/voltron_harness_server.py` sur le port 5029,
  lancé par le même script. **Écoute `0.0.0.0:5029` depuis le 2026-11-28 10:19Z**
  (variable `VOLTRON_BIND` ; par défaut `127.0.0.1`, sans clé ni CORS en boucle
  locale). Un bind hors loopback **exige** `VOLTRON_INBOUND_KEY` : sans elle le
  démarrage est **refusé** (exit 1), et un appel distant sans clé reçoit **401 sans
  que son corps soit lu**. La clé passe en `Authorization: Bearer <clé>` ou
  `X-Voltron-Key` (comparaison en temps constant) ; la bannière du serveur ne montre
  que l'empreinte `sha256[:12]`, jamais la valeur. `/health` reste ouvert (vivacité
  seule, aucun contenu). Il prouve le moteur par **une génération d'un jeton** (pas
  par `/health` seul) et relance seul un moteur arrêté (`docker start`) ou qui
  répond sans générer (`docker restart`, jamais pendant les 240 s qui suivent son
  démarrage).
- Boot mesuré sur 1.1 : premier démarrage ≈4 min (21:45:51Z → 21:49:48Z : chargement
  des poids par le montage 9P 64 s, `torch.compile` à froid 33,8 s, capture des graphes
  4 s) ; redémarrage à chaud 1 min 24 s (21:50:39Z → 21:52:03Z).
- KV : **111 542 jetons (3,40× la fenêtre de 32 768)**, contre 159 248 (4,86×) sur 1.0 —
  voir pourquoi ci-dessous.

## Câbler un client distant (2026-11-28)

Le hub claudish ne peut pas joindre le loopback d'une autre machine ; son
propriétaire a nommé le prérequis (écoute LAN **avec** garde de clé), livré le 28/11.

- **Adresse : `http://192.168.0.54:5029`** (Ethernet, **DHCP** : bail de 24 h). Le
  siège porte aussi un Wi-Fi sur le même sous-réseau : une bascule d'interface change
  l'adresse sans redémarrage. L'adresse est relevée à chaque cycle de vigie et
  réannoncée si elle change — **ne pas la coder en dur sans cette réserve**.
- **Authentification** : `Authorization: Bearer <clé>` (ce qu'un proxy sait déjà
  envoyer) ou `X-Voltron-Key`. `/health` seul est ouvert. La valeur vit hors dépôt
  (`D:\vllm-data\bench\v2_service.env`) et se transmet par message à destruction
  automatique ; seul son empreinte `sha256[:12]` se publie.
- **Ce que le service accepte** :

  | Appel | Usage |
  |---|---|
  | `POST /v1/task` | contrat natif : une tâche gatée (`classify`, `extract`, `numbers`, `diff`, …) |
  | `POST /v1/jobs` | lot en arrière-plan, persisté et repris au redémarrage |
  | `POST /v1/chat/completions` | façade OpenAI — **une tâche par appel** : l'objet JSON de `/v1/task` dans le contenu du dernier message `user` ; `choices[0].message.content` = JSON du résultat |
  | `GET /v1/models` | un seul id : `voltron-harness` |
  | `GET /health`, `GET /v1/capabilities`, `GET /openapi.json` | vivacité, contrat humain, contrat machine |

  **La façade n'est pas un chat libre** : le service n'a jamais livré de texte non
  gaté, et un message sans tâche reconnaissable reçoit la carte d'emploi. Un routeur
  qui lui enverrait du dialogue général n'obtiendra pas de conversation.
- **Qui répond** (`stage` du résultat) : `a` = modèle local ; `b` = second lecteur
  `frognano-4b` du hub, appelé seulement si le gate de `a` échoue ; `c` =
  coordinateur du hub, seulement si `b` échoue aussi. Les étages `b` et `c` passent
  par le hub : ils coûtent un appel vers lui, mesuré à 4 pour 40 tâches.
- **Usage** : un appel marqué `X-Voltron-Probe: 1` est exclu du compteur
  d'adoption ; tout le reste compte dans `GET /v1/usage`.
- **Retour arrière de l'écoute** : retirer `VOLTRON_BIND` (ou le remettre à
  `127.0.0.1`) puis redémarrer le seul serveur — le moteur ne bouge pas.

## Mesure 1.0 → 1.1 (2026-11-27, même soir, même instrument)

Driver : `D:\vllm-data\bench\seat-po2028\bench_ab_voltron11.py` ; relevés dans
`D:\vllm-data\bench\voltron11_swap_20261127\` (`summary_v10ctl.json`,
`summary_v11.json`).

| Mesure | 1.0 (contrôle, 21:29→21:40Z) | 1.1 (21:53→22:09Z) |
|---|---|---|
| Socle 120 tâches, sans réflexion | 88/120 | 87/120 |
| Pack réel 40, sans réflexion | 16/40 | 18/40 |
| Pack réel 40, réflexion 2 048 + strip | 30/40, 11 troncatures | 33/40, 4 troncatures |
| Décode mono-flux, passage le plus rapide (256 jetons) | 2,652 s → 96,5 tok/s | 2,658 s → 96,3 tok/s |

- **Précision** : 1.1 n'est en dessous nulle part. Socle : un seul écart (arithmétique
  4 → 3), les sept autres catégories identiques. Pack avec réflexion : +3 tâches sur
  **un** passage de 40 (la veille, 1.0 donnait 29 puis 30) et surtout 4 réponses
  tronquées contre 11 au même plafond de jetons. Tendance sur un seul passage, pas une
  preuve.
- **Changement de forme des extractions** (10 échantillons sur 1.1, 27/11 : 1 à 22:20Z, 9 à 22:34Z) : à deux champs, 1.0 rendait des chaînes (`{"temperature": "46", "memoire": "7 Go"}`) et 1.1 rend des **nombres** (`{"temperature": 46, "memoire": 7}`), sur deux formulations différentes ; à un seul champ (`data` « memoire 7 Go »), 1.1 rend une liste (`{"memoire": ["Memoire 7 Go"]}`) — 1.0 n'a pas été mesuré sur cette entrée. Reproductible sur 3 passages chacun, pas un accident d'échantillon. Le socle ne le voit pas (extraction verbatim 15/15 aux deux versions) ; un consommateur qui attend une chaîne avec unité doit convertir.
- **Vitesse : parité, mesurée le 27/11 à 22:26→22:29Z sur hôte dégagé.** Le décode de la
  colonne 1.1 lu à 21:53Z (48,4 tok/s) était **invalide** : un rendu `gource` en 4K d'une
  autre lane tournait dans la VM WSL depuis 21:52:12Z, 31 s avant la batterie (933 % de
  CPU plus `ffmpeg` 265 %, charge 27,7 pour 20 threads) ; le contrôle 1.0 l'a précédée.
  Ce rendu terminé (vers 22:23Z), la même mesure refaite donne **85,5 tok/s en médiane de
  3** (80,8 / 93,8 / 85,5) puis 82,4 en médiane de 9 — les trois premières passes de ce
  second essai tombent sous une rafale (49,7 / 50,0 / 61,0) et les trois dernières
  consécutives donnent **96,0 / 94,3 / 96,3**. Le statisticien robuste est le passage le
  plus rapide : une charge étrangère ne peut que ralentir. **1.1 = 2,658 s pour 256
  jetons (96,3 tok/s), 1.0 = 2,652 s (96,5 tok/s) : écart 0,2 %. Aucun coût de vitesse.**
  Mon attente « ≈81 tok/s » était un mauvais raisonnement, corrigé : détacher la tête coûte
  de la **mémoire** (0,49 Gio), pas de la bande passante par jeton — les octets du `lm_head`
  sont lus une fois par pas dans les deux cas.
- **Verdict (critère annoncé) : 1.1 reste.** Socle 87 contre 88 et pack réel 18 contre 16
  (bruit), décode à parité, et **4 réponses tronquées au lieu de 11** avec réflexion. Le
  prix est la **capacité KV : 111 542 jetons au lieu de 159 248** (3,40× au lieu de 4,86×
  la fenêtre de 32K) — à savoir avant un job à plusieurs flux longs ; le retour arrière
  reste armé (`voltron-harness-10` conservé arrêté).
- Relevés du verdict : `summary_v11quiet.json` (22:27:47Z) et, hors du dossier de batterie
  (le sondeur de décode écrit à côté de lui), `D:\vllm-data\bench\ab_decode_v11quiet9-decode.json`
  (22:28:48Z) ; charge échantillonnée toutes les 5 s dans `D:\vllm-data\bench\voltron11_swap_20261127\loadavg_during_v11quiet.log` (72 relevés, sha12 `9dba64de4f1e`) — `gource` = 0 du début à la fin, `ffmpeg` présent 22:27:48→22:28:26Z et à 22:33:49Z, charge 1 min 6,2-6,7 puis une rafale à 13,6 sur le second essai).
- **Ce qui change entre les deux checkpoints** (`config.json` lus côte à côte) : même
  architecture (24 couches, mêmes `layer_types`, 2 048 caché, 7 680 intermédiaire,
  16 têtes / 4 KV, vocabulaire 128 000) ; 1.1 **détache la tête**
  (`tie_word_embeddings: false`) : +0,49 Gio au chargement (3,36 → 3,85 Gio, mesuré).
  La KV réservée est réduite d'autant (`--kv-cache-memory` 1 750 432 666 →
  1 226 144 666 octets) pour garder l'empreinte validée sur 1.0 sur une carte de 8 Gio.

**Retour arrière sur 1.0** (non exécuté à ce jour ; chaque geste vérifié séparément
lors de l'échange) :

1. Arrêter le serveur :5029 **d'abord** — sinon il relance le moteur par `docker start`.
2. `docker stop voltron-harness`, `docker rm voltron-harness`,
   `docker rename voltron-harness-10 voltron-harness`, `docker start voltron-harness`.
   Le conteneur 1.0 est conservé arrêté sous le nom `voltron-harness-10`.
3. Revenir au lanceur d'avant la MAJ (montage `voltron-1-mini`,
   `--kv-cache-memory 1750432666`, nom servi unique).
4. Retirer `VOLTRON_ENGINE_MODEL=voltron-1.1-mini` de
   `D:\vllm-data\bench\v2_service.env` (hors dépôt), puis relancer le serveur par le
   script. Sans ce retrait, le serveur sonde un nom que le moteur 1.0 ne sert pas.

## Incident du 27/11 — partition GPU de la VM WSL perdue

- **17:47Z** : mise à jour du pilote NVIDIA 621.24 → 621.40 par l'installeur officiel.
  Toute (ré)installation du pilote invalide la partition GPU des VM WSL déjà
  démarrées. Le moteur a continué de répondre `/health` 200 pendant 3 h 20.
- **21:08:22Z** : première génération réelle → `torch.AcceleratorError: CUDA error:
  unknown error`, requête en 500, l'API server s'arrête lui-même.
- **Remède mesuré : `wsl --shutdown`** (21:20:46Z), rien d'autre. `docker start` et
  `docker restart` échouent au hook prestart (`nvidia-container-cli: initialization
  error: WSL environment detected but no adapters were found`).
- **`RestartCount=0` ne prouve rien** : la politique `unless-stopped` a tiré 0,71 s
  après la sortie et a échoué ; le compteur ne compte que les relances réussies.
- **`/health` 200 n'est pas une preuve de vivacité.** Corrigé dans le serveur (PR #617,
  `9783f5c223`) : une génération d'un jeton. Essai réel le même soir : moteur arrêté,
  tâche déposée, réponse juste en 94,2 s.
- `wsl --shutdown` arrête tout le travail WSL des autres lanes : préavis dans le même
  cycle, et ne jamais promettre de relancer ce qui n'est pas à ce siège.

## Non-négociables

- Tout **boot moteur = fenêtre annoncée sur workspace-vllm AVANT lancement** —
  mécanisme de droit de veto des lanes voisines (leçon ai-01 01/11).
- Offload tier : **toujours non pinné** (`VLLM_WSL2_ENABLE_PIN_MEMORY=0`) — pin=1
  falsifié sur WSL2 (ai-01, ×2 mesurés).
- Clone partagé : invariants claudish-72 — sticky intouchable, `wt/` intouchables,
  zéro rebase/reset, checkout principal rendu à la sticky, working tree propre.
- Heures UTC suffixées Z (`(Get-Date).ToUniversalTime()`) ; GitHub en REST uniquement
  (seau GraphQL flotte partagé) ; jamais de clé en clair.
- Un chiffre cité est **mesuré**, avec sa source ; qualifier VERIFIÉ / RAPPORTE /
  SUPPOSÉ.
- **Avant toute mesure de débit** : `wsl -d Ubuntu -- cat /proc/loadavg`. Une mesure
  prise sous la charge d'une autre lane ne se compare à rien (27/11).

## Chemins

| Quoi | Où |
|---|---|
| Chemin d'exécution du service :5029 | `d:/dev/wt-po2028-vllm-duo` (PR #646 + #647, depuis le 28/11 10:19Z ; avant : `…-facade`, PR #617) — ne se retire jamais sans relancer le service depuis un autre chemin |
| Autres worktrees du siège | `…-abench` (PR #629), `…-attrib` (PR #618), `…-skagent` (PR #627) |
| Modèles | `D:\vllm-data\models\` (`voltron-1-mini`, `voltron-1.1-mini`) |
| Instruments et relevés | `D:\vllm-data\bench\seat-po2028\` (hors worktree : un instrument qui ne vit que dans un worktree meurt avec lui) |
| Mémoire du siège | `~/.claude/projects/d--dev-vllm/memory/` (MEMORY.md + fiches) |
| Dashboards | workspace-vllm (principal), global (escalade flotte) |
