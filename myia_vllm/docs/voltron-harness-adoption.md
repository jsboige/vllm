# Harnais voltron — adoption flotte (po-2028, mandat user 18/11)

**Le produit** : une requête HTTP → une réponse **déjà fiabilisée**. La chaîne
worker (voltron-1.7B, po-2028, moteur local) + réparation dirigée (≤2 tours,
delta signé du gate — jamais la réponse) + second lecteur mini (frognano-4b de
la flotte, via hub claudish — étage `b`, 28/11) + coordinateur (swift-1.5-27b
via hub claudish, prompt sec) tourne **dans le service** ; chaque sortie est re-gatée
par le **contrat que l'appelant fournit**. L'appelant lit `ok`/`detail` — le
coût de vérification est déjà payé (critère d'adoption FrogNano : coût de
vérification ≪ coût de refaire soi-même).

**Héritage FrogNano** (po-2025, flambeau repris 18/11) : la règle de jugement
reste — **critère littéral + corpus local → `grep`, toujours**. Le harnais se
justifie là où grep ne peut pas : critère sémantique, rédaction cadrée,
contrat structuré. Et l'incitation qui convertit n'est pas l'économie de
tokens flotte mais la **préservation de la fenêtre de contexte de l'appelant**
et le **gain de temps** (le service gère réparation + escalade tout seul).

## 1. Le service

| | |
| --- | --- |
| URL | `http://127.0.0.1:5029` par défaut (po-2028, bind local). `VOLTRON_BIND` non-loopback = écoute LAN **avec clé entrante obligatoire** (§4ter) |
| Moteur | `voltron-harness` (docker, `--restart unless-stopped`, config fp8 validée : KV 159K tok, ~7,1/8 Gio VRAM ; **tier RAM retiré 24/11** — 4 Gio de shm pour 0 octet relu sur ~24 h, conteneur ~7 Gio → ~3 Gio) |
| Endpoints | `GET /health` · `GET /v1/capabilities` · `GET /openapi.json` (24/11 — découverte OpenAPI 3.1, sans `servers` : le chargeur d'outils ne montait pas le service, 404 mesurés 23/11) · `POST /v1/task` · `POST /v1/jobs` + `GET /v1/jobs/<id>` (reprise au restart serveur, 21/11) · `GET /v1/usage` (compteurs durables — l'instrument d'adoption) · **façade OpenAI 26/11** : `GET /v1/models` + `POST /v1/chat/completions` (JSON et SSE — §6c) · `OPTIONS` sur chaque route (204 + `Allow`, **aucun en-tête CORS** : service sans clé qui dépense des tokens hub, une page web ne doit pas pouvoir l'appeler) |
| Auto-guérison | engine muet → `docker start voltron-harness` (un seul partagé entre threads, puis ≤1/30 s pendant l'attente) + attente ≤240 s (boot mesuré 115-150 s ; un `docker start` bloqué ne fait plus renoncer — la politique de restart du conteneur ramène l'engine pendant l'attente ; `returncode`/`stderr` sont rapportés dans le résultat et journalisés seulement au changement d'erreur) |
| Démarrage | `pwsh -File myia_vllm/scripts/testing/start_voltron_service.ps1` (résout la clé hub en mémoire depuis `~/.claude.json`) |
| Config locale | `VOLTRON_HUB_URL` / `VOLTRON_JOBS_DIR` / `VOLTRON_USAGE_PATH` / `VOLTRON_DUO_MODEL` / `VOLTRON_BIND` / `VOLTRON_INBOUND_KEY` (env ; sur po-2028 via `D:\vllm-data\bench\v2_service.env`, hors dépôt — aucune adresse LAN ni chemin machine dans le code). Sans eux : `~/.voltron_harness/`, phase C désactivée ; `VOLTRON_DUO_MODEL` vide = étage `b` absent (§4bis) |
| Rollback | **arrêter d'abord le process python :5029**, puis `docker stop voltron-harness` — sinon le service relance son moteur ; aucune donnée perdue |
| Logs | `D:\vllm-data\bench\v2_server.log` · jobs persistés `D:\vllm-data\bench\v2_jobs\` |

Réponse type : `{"ok": true, "stage": "a"|"b"|"c", "answer": "...", "detail": "",
"turns": 2, "dt_s": 8.4}`. `stage=b` : le second lecteur mini a fini (§4bis) ;
`stage=c` signale que le coordinateur 27B a fini
la tâche (worker insuffisant) ; `ok=false` rend le **meilleur effort + le
détail du gate** — un échec est actionnable, pas un aveuglement.
**Coupures d'engine (24/11)** : un résultat coupé porte `stage="engine-error"`
ou `"engine-down"` et **`transient: true`** — l'appelant peut re-POSTer tel
quel (le service le fait déjà de lui-même, voir §3bis). Un refus HTTP de
l'engine (400/500) n'est PAS transitoire et n'est jamais rejoué.

## 2. Les quatre contrats (familles mesurées, banc `real_task_bench`)

### extract — extraction structurée verbatim

```json

POST /v1/task
{"type": "extract", "data": "<texte ≤20000 chars>",
 "fields": ["score", "acc", "duree_s"], "verbatim": true}

```

Gate : réponse = JSON avec **exactement** ces clés ; chaque valeur chaîne est
**sous-chaîne de la source** (porte verbatim FrogNano — 0 fabrication prouvable
mécaniquement). `verbatim:false` pour les valeurs reconstruites (nombres,
booléens).

### classify — classification avec preuve citée

```json

POST /v1/task
{"type": "classify", "data": "<fenêtre de log>", "classes": ["weight-shape", "engine-init", "..."],
 "class_definitions": {"weight-shape": "erreur de dimension de tenseur", "engine-init": "démarrage moteur"}}

```

Gate : classe dans la taxonomie fournie ; `ligne_cle` recopiée **mot pour mot**
depuis la source (≥8 caractères — le seuil FrogNano de 15 rendait les lignes de
code courtes structurellement ingatables, queue stage c 17 % mesurée sur le
premier job d'adoption réel 20/11). La preuve voyage avec le verdict — pas de
classification non étayée.

`class_definitions` **optionnel** (axe consommateur 20/11) : un dictionnaire
`{classe: définition}` injecté dans le prompt de l'étape A, après la ligne de
taxonomie. Mesuré sur 6 cas discriminatifs : **4/6 juste avec vs 3/6 sans** ;
les définitions placées AVANT « Texte : » faisaient copier leur texte par
l'étape B (gate reject) — d'où leur placement après la taxonomie. **Limite
mesurée** : sur les déclarations de classe multi-lignes, le worker 1.7B choisit
par prior lexicale (une méthode nommée `Afficher()` → classe « affichage »
malgré la définition de « fondations ») — les définitions aident les cas courts,
elles ne remplacent pas le jugement ; l'appelant garde le tri final des cas
ambigus.

**Exécution (mesuré 20/11)** : 2 appels préremplis au worker — la classe, puis
la ligne qui la JUSTIFIE (ancre brute `LIGNE :`, copie directe, aucun
échappement JSON à réussir). Sur un prompt combiné, le 1.7B délibère en prose et
n'émet jamais le JSON ; prérempli, il complète mécaniquement : **stage a en
0,26-0,64 s** (avant : escalade coordinateur systématique à 21-36 s).

### numbers — rapport chiffre fidèle

```json

POST /v1/task
{"type": "numbers", "data": "<source>",
 "report_prompt": "Rédige un rapport d'une à deux phrases citant la mémoire GPU et la température.",
 "numbers": ["455", "44"]}

```

Gate : chaque nombre fourni apparaît (bornes digits) ; **aucun** nombre absent
de la source (anti-invention). L'appelant connaît ses chiffres clés — le
service garantit qu'ils sont cités et que rien n'est fabriqué.

### diff — rapport de divergence entre deux configs JSON (pivot-outil)

```json

POST /v1/task
{"type": "diff", "a": "{...config A...}", "b": "{...config B...}"}

```

**Le diff est un calcul** (leçon v2.1) : l'OUTIL calcule le diff de premier
niveau, le MODÈLE rédige le rapport (chaque clé divergente + ses deux valeurs).
Gate : chaque clé citée avec ses deux valeurs (valeurs sérialisées >60 chars
exemptées de citation — mention de clé + qualificatif de divergence) ; zéro
clé inventée.

## 3. Tâches longues en background

```json

POST /v1/jobs {"name": "triage-vigie", "tasks": [<task>, <task>, ...]}
→ {"job_id": "job-20261118T...-ab12cd", "total": 30}
GET /v1/jobs/job-20261118T...-ab12cd
→ {"status": "running", "done": 17, "total": 30, "results": [...]}

```

Le job s'exécute en tâche de fond du service **à concurrence 6** (moteur mesuré
N=64 = 3 673 t/s ; fumée 12 tâches : 12/12 stage a en <12 s), **persisté sur
disque après chaque tâche** (un redémarrage du serveur ne perd rien ; le `GET`
sert l'état en mémoire du service — le disque après un restart serveur). Cas d'usage : balayer 30 fenêtres de logs, trier une inbox, rapporter
une série de diffs — l'agent appelant lance en début de session et relit en
fin de session (contrat BG FrogNano : ~0 token pendant, livrable forme fixe).
**Reprise après restart serveur (21/11)** : la charge est persistée dès le POST
; au boot, un job `running` dont le thread est mort voit ses tâches restantes
**relancées** (les résultats déjà faits sont gardés, jamais re-exécutés — validé
live : kill à 6/12 → reprise 5/12 → 12/12, index 0-11 sans doublon). Une tâche
malformée (p.ex. un str dans la liste) devient un résultat d'erreur consultable
— elle ne gèle plus le lot (défaut mesuré 21/11 : le pool entier mourait via
`ex.map`). Les jobs antérieurs au 21/11 (charge non persistée) passent
`orphaned` — terminal honnête, re-POST conseillé.

**Garantie de reprise : au moins une fois, pas exactement une fois.** Si le
serveur meurt après l'exécution d'une tâche mais avant la persistance de son
résultat, cette tâche est **ré-exécutée** au boot. Le consommateur doit donc
fournir des tâches idempotentes ou dédoublonner sur l'index `task` ; une tâche
rejouée n'est jamais re-comptée dans `/v1/usage`. Le service ne livre pas
lui-même de résultat vers un destinataire externe : ce choix évite une double
livraison, au prix d'une possible double exécution locale.

## 3bis. Coupures d'engine (24/11) — le job survit à la panne

**Cause mesurée** : la garde anti-famine du commit hôte (`Guard-Commit-Famine`,
tâche Maintenance) recycle la VM WSL (`wsl --shutdown`, 20-23/11 : 1 à 4
tirs/jour). Le conteneur revient seul par sa politique de restart après **1 min
49 s à 2 min 06 s** (7 tirs) — un tir a pris **8 min 52 s** (23/11 12:50Z), au-delà
de l'attente de 240 s de l'auto-guérison. Les tâches lancées dans cette fenêtre
mouraient en `stage: error` ; en synchrone, la connexion se fermait sans réponse.

**Second cas, mesuré 24/11** : après un `docker kill` sur notre conteneur en
`--restart unless-stopped`, la politique de restart **n'a rien fait pendant 20
min** (événements `kill` puis `die 137`, aucun `restart`, `restartCount` 0).
Un conteneur arrêté ne revient donc **pas** seul : le service le relance.

**Comportement maintenant** :

- une coupure de transport (connexion refusée/reset, timeout, réponse tronquée)
  est taguée **`transient: true`**. Un refus HTTP de l'engine (400/500) n'est
  **pas** transitoire : il n'est jamais rejoué ;
- la tâche **attend le retour de l'engine puis est REJOUEE** (jobs : ≤3600 s,
  2 rejeux ; `/v1/task` synchrone : ≤120 s après les 240 s d'auto-guérison,
  plus les appels modèle déjà en cours). **Tant que le moteur est muet pendant
  une attente, son conteneur est relancé toutes les 30 s** (`docker start`,
  idempotent, un seul start partagé entre tous les threads, **y compris le
  premier start d'auto-guérison**) — un start unique émis pendant l'agonie du
  conteneur serait un no-op. Un refus de la CLI est rapporté dans `detail` et
  journalisé au changement d'erreur seulement. Pour une tâche longue,
  préférer un job : il n'est pas soumis au timeout HTTP de l'appelant ;
- attente épuisée : `engine_outage` sur le job — **les tâches restantes ne sont
  plus lancées tant que l'engine est muet** (résultat `engine-down`,
  `transient: true`, à re-POSTer), le job finalise quand même. Engine revenu :
  le drapeau tombe, le job reprend (chaque coupure a sa propre attente) ;
- `GET /v1/jobs/<id>` expose `waiting_engine` (tâches en attente du moteur),
  `engine_outages` (nombre de coupures subies) ;
- le compteur d'adoption compte une tâche rejouée **une seule fois**.
**Effet de bord connu** : pendant une coupure, les tâches restantes du job
attendent (elles ne partent pas en échec immédiat) — préférer un job à un appel
synchrone si l'engine est en reboot. Pour arrêter le moteur : **arrêter d'abord
le service**, sinon sa prochaine attente relance le conteneur.

**Validé en réel (24/11)** : job de sonde de 48 tâches, `docker kill` de
l'engine pendant le lot.

- version **avant** relance du conteneur : 42/48 faites avant le kill, les 6
  tâches en vol coupées (`RemoteDisconnected`), puis attendues et **rejouées**,
  **48/48 `ok`** — mais le moteur n'est revenu que par un `docker start`
  externe, ~20 min plus tard (sa politique de restart ne l'a pas fait) ;
- version **finale** (relance pendant l'attente), job `job-20261124T015015Z-91bbba`,
  kill à 01:50:19Z : 42/48 faites, 6 tâches en attente du moteur, puis
  **48/48 `ok` en 160,1 s** — conteneur relancé par le service seul, rejouées
  sans intervention, compteur d'adoption inchangé (5 723 → 5 723, sonde).

## 4. Mesures

| Étage | Score (vérité banc 40 tâches réelles) | Appels/tâche |
| --- | --- | --- |
| Solo voltron t0 | 10/40 = 25 % | 1 |
| Chaîne complète A→B→C (bench, engine-swap par phase) | **40/40 = 100 %** | 2,4 voltron + 0,53 sibling + 0,25 swift-27B |
| **Service A→C en direct (v4, 18/11 soir)** | **38/40 = 95 %** — contrat appelant **40/40** | 2,70 |

`D:\vllm-data\bench\service_mode_v{1..4}.json` (40 tâches réelles du siège,
contrats appelant → réponses évaluées contre la vérité-terrain du banc, qui
est PLUS FORTE que le contrat : valeur d'égalité, pas seulement verbatim).
L'arc des 4 passes de ce soir — chacune a corrigé un défaut réel :

| Passe | Vérité banc | Défaut corrigé |
| --- | --- | --- |
| v1 | 30/40 = 75 % | état initial (gate sur réponse brute, contrat extract sans sémantique) |
| v2 | 37/40 = 92,5 % | **gate sur le livrable nettoyé** (on certifie ce qu'on livre, pas le brouillon de raisonnement) + champ `instruction` du contrat extract |
| v3 | 34/40 = 85 % | contre-essai : amputer le format de l'instruction coûte 4 tâches — **l'ancre de forme fait partie de la sémantique** (liste vs dict, booléens vs « non ») |
| v4 | **38/40 = 95 %** | règle placeholder (« les <...> sont des formats, pas des valeurs ») + garde alphanum sur les nombres |

Les 2 résiduels v4 : un `"score": "84/120"` (string au lieu de l'entier —
sémantiquement juste, forme off) et un placeholder récalcitrant que la
réparation dirigée du banc ferme (json_eq à valeur d'égalité). **Le contrat
appelant est tenu à 40/40 sur les 4 passes** — un `ok=false` du service est
toujours accompagné du détail actionnable, jamais d'un échec muet.

La phase B du BANC (critique sibling 2xmerge) nécessitait un deuxième engine
1.7B — impossible en simultané sur la GPU 8 Gio (contrainte mesurée) : elle
reste un outil de mesure hors-ligne. L'étage `b` du SERVICE (28/11, §4bis) est
autre chose : un second LECTEUR pris sur la flotte (`frognano-4b`, po-2025, par
le hub), donc sans second engine local. Le service exécute A→B→C et **rend son
propre verdict** : `ok` + `detail` = l'appelant sait exactement quoi refaire
ou escalader.

## 4bis. Le duo : second lecteur pris sur la flotte (28/11, mandat user)

Mandat user (28/11 09:12Z) : « s'il est trop faible pour être utile, essayer de
caler un harnais sk-agent avec le modèle de po-2025, peut-être qu'à deux ils
seront meilleurs ». L'étage `b` met ce second modèle **dans la chaîne du
service** : quand le worker local et ses deux réparations échouent, le mini de
la flotte (`frognano-4b`, po-2025) relit le **prompt sec** de l'appelant — même
prompt que le coordinateur, même gate, `enable_thinking: false`, 400 jetons —
puis le 27B ne reprend que ce que le mini a aussi raté. Le mini se consomme
**par le hub claudish** (jamais l'endpoint vLLM direct de po-2025 : la clé de
transport du hub resterait sur le client).

Activation : `VOLTRON_DUO_MODEL=frognano-4b` dans
`D:\vllm-data\bench\v2_service.env` (hors dépôt) ; variable vide = chaîne a→c
d'avant. `VOLTRON_DUO_MAX_TOKENS` (400) et `VOLTRON_DUO_TIMEOUT_S` (120) règlent
le budget. Nouveau `stage: "b"`, et un compteur durable `by_stage` dans
`GET /v1/usage` (`{"a": {"n", "ok"}, "b": …}`) : c'est l'effet mesurable du duo
en trafic réel. Un échec du hub en `b` n'est jamais `transient` (le rejeu
redonnerait le même résultat) et retombe sur `c`.

**Mesure hors-ligne, tâche à tâche** (`duo_bench.py` + `duo_analyze.py`, mêmes
bancs gelés, un bras par modèle, porte = celle du banc — plus proche de la
vérité que la porte du service ; relevés dans
`D:\vllm-data\bench\duo_20261128\`) :

| Banc | voltron | frog | les deux | cascade gâtée a→b | plafond de l'union |
| --- | --- | --- | --- | --- | --- |
| Socle 120 (arith, extract, count, json, grounded, constraint, sort, transform) | 87 | 82 | 76 | **93/120** | 93 |
| Pack réel 40 (classify, fidelity, fail-extract, cfg-diff) | 18 | 28 | 14 | **32/40** | 32 |

La cascade en ordre inverse rend le même chiffre, et un routeur par type de
contrat n'apporte rien de plus : **pas de table de routage à maintenir**. Le
mini est plus fort que le local sur la classification réelle et l'extraction
(12/12 vs 7/12, 10/12 vs 3/12), le local sur la fidélité numérique (8/10 vs
5/10) — d'où la cascade, qui prend le premier qui passe le gate de l'appelant.
Accord des deux réponses : 79/120 au socle (76 justes) contre 6/40 au pack
(6 justes) ⇒ l'accord est fiable mais trop rare sur les tâches réelles pour
servir de règle ; la cascade reste la seule règle mesurée.

**Mesure au niveau du SERVICE** (28/11, 40 tâches réelles, `duo_service_eval.py`
— serveur patché chargé en processus, même moteur, même hub, compteur et jobs
en répertoire jetable, Docker interdit ; bras l'un après l'autre) :

| Bras | Service (`ok`) | Vérité banc | Étages | Appels moteur / mini / 27B | Somme des appels 27B |
| --- | --- | --- | --- | --- | --- |
| a→c (d'avant) | 40/40 | 32/40 | a 36, c 4 | 66 / 0 / 4 | 754 s |
| a→b→c (duo) | 40/40 | 32/40 | a 36, **b 3**, c 1 | 64 / 4 / **1** | 146 s |

Les 3 tâches reprises par `b` (2 classify, 1 diff) sont justes à l'oracle, et
`c` les avait aussi dans l'autre bras : **aucune perte, aucun court-circuit** —
le risque réel (un `b` qui passe le gate en étant faux et prive `c` de la tâche)
ne s'est pas matérialisé sur ce banc. La 4ᵉ tâche que `b` n'a pas close (un
rapport chiffré) revient au 27B, qui la résout. Coût : 4 appels mini (3,6 s
cumulés) contre 3 appels 27B évités (−608 s de temps de coordinateur sur ces
40 tâches ; une part de l'écart vient du cache de préfixe, le second bras
tournant après le premier). `duo` sans coordinateur (dérivé, non rejoué) :
39/40 tâches rentrées, 31 justes — le 27B gagne encore 1 tâche.

**La limite, mesurée, et le levier qui suit** : le second lecteur ne se
déclenche que là où la porte du service échoue, et cette porte est **bien plus
faible que la vérité** sur `extract` sans `verbatim` — elle ne vérifie que les
clés du JSON. Sur les 12 tâches `fail-extract` du pack, le service répond 12/12
`ok` et la vérité n'en valide que 6 : **6 erreurs de valeurs sont invisibles
pour la chaîne** (ni réparation, ni `b`, ni `c` ne peuvent les voir ni les
corriger). Le duo paye donc là où le gate refuse (classify à preuve
invérifiable, numbers, diff) et reste muet ailleurs. Le levier suivant n'est pas
un troisième modèle mais un **gate plus fort** : type attendu par champ,
`verbatim: true` quand l'appelant peut le déclarer, énumérations. Chaque point
de gate gagné est un point que la chaîne sait ensuite réparer.

## 4ter. Écoute LAN et clé entrante (28/11) — la garde passe avant l'écoute

Le hub claudish (`192.168.0.50`) ne peut pas joindre le loopback d'une autre
machine : sans écoute LAN, une entrée d'endpoint au hub ne servirait qu'un 502
(constat du propriétaire du hub, 28/11). L'écoute est donc ouverte — jamais nue.

| Réglage | Défaut | Effet |
| --- | --- | --- |
| `VOLTRON_BIND` | `127.0.0.1` | adresse d'écoute. Toute valeur non-loopback **exige** une clé : sans elle, `REFUS DE DEMARRAGE` + exit 1 — le service ne s'ouvre pas |
| `VOLTRON_INBOUND_KEY` | vide | clé entrante. Les appels distants la portent en `Authorization: Bearer <clé>` (convention OpenAI, ce que le hub sait déjà envoyer) ou en `X-Voltron-Key` ; comparaison `hmac.compare_digest` |

Règles fixées par `test_voltron_inbound.py` (6 tests, **preuve rouge 6/6** sur
le serveur d'avant le 28/11) :

- **loopback = toujours servi**, clé configurée ou non : les sondes de vigie du
  siège n'ont pas changé d'un octet ;
- `GET /health` reste ouvert même à distance (sonde de vivacité, aucun
  identifiant) ; toute autre route distante sans clé juste rend **401 sans lire
  le corps** — le moteur n'est jamais atteint (testé : zéro appel) ;
- la clé ne s'écrit jamais dans le dépôt : elle vit dans
  `D:\vllm-data\bench\v2_service.env` (hors dépôt) ou dans l'environnement du
  lanceur. La bannière de démarrage n'imprime que l'empreinte `sha256[:12]`,
  qui est exactement ce qu'on publie — la valeur ne sort pas du siège.

**Ordre tenu** : (1) la garde (code + tests) ; (2) **mesure du pare-feu** ;
(3) `VOLTRON_BIND` non-loopback + clé ; (4) l'annonce (adresse, port,
empreinte).

**Le geste élevé prévu s'est révélé inutile — mesuré le 28/11 10:19Z** : ce
siège porte déjà deux règles entrantes `Allow` pour l'interpréteur même du
service (`C:\Users\jsboi\miniconda3\envs\mcp-jupyter\python.exe`, TCP **port
quelconque**, `RemoteAddress: Any`, profils Private+Public), posées par un autre
usage de cet interpréteur. Aucune règle 5029 ne les restreint : ouvrir l'écoute
n'exige donc **aucune** fenêtre UAC. C'est aussi une limite, et elle est plus
large que ce service : tout processus de cet interpréteur est déjà joignable.
Constat, pas modification — rien n'a été touché au pare-feu.

**Mesures après bascule (28/11 10:19Z, `0.0.0.0:5029`)** : loopback sans clé
**200** (47 sondes, dont 30 d'affilée), adresse LAN sans clé **401**, `Bearer`
**200**, `X-Voltron-Key` **200**, `Bearer` faux **401**, `/health` distant
**200**, `POST /v1/task` distant sans clé **401**, génération réelle en loopback
`stage=a` en 0,7 s. **Non mesuré ici** : l'appel depuis une AUTRE machine (le
chemin local vers sa propre adresse LAN ne traverse pas le pare-feu) — demandé
au propriétaire du hub en même temps que l'annonce.

**Fausse piste, notée pour ne pas la relancer** : une première lecture de ce
relevé a vu un « 401 loopback ». Il n'y en a eu aucun — la ligne loopback du
relevé imprimait 200. L'échec venait du script de mesure : sa boucle
d'impression (`for name, st in rows`) réutilisait le nom `st` de la première
sonde, donc l'assertion finale comparait le statut de la **dernière** ligne
(`Bearer` faux = 401) à celui attendu du loopback. Les 47 sondes ont cherché
une anomalie qui n'existait pas.

## 5. Ce que le service REFUSE (limites vendues d'avance)

- **Verdicts et jugements** (décisions, merges, priorisations de fond) — règle
  flotte : le producteur n'est jamais son propre vérificateur, et un petit
  modèle ne juge pas.
- **Sorties non gatées** : pas d'endpoint « réponds à tout » — une réponse
  sans contrat vérifiable n'est pas livrable (héritage FrogNano : les classes
  non vérifiables sont refusées, pas vendues).
- **data > 20 000 caractères** (garde contexte 32K) — découper côté appelant.
- **Comptage/agrégation arithmétique** : les nombres sont RECITÉS (numbers),
  jamais calculés par le modèle — pour compter, l'appelant compte.
- La classification est vérifiée contre la **taxonomie de l'appelant** (classe
  ∈ liste + preuve verbatim) ; la justesse factuelle de la taxonomie elle-même
  reste à l'appelant.

## 6. Recettes prêtes à copier (le réflexe adoption)

**Début de session / tâche longue** : tout balayage >30 items à critère
sémantique (logs à classer, configs à comparer, chiffres à reciter fidèlement)
qui coûterait la fenêtre de contexte → `POST /v1/jobs` avec la liste, continuer
son travail, relire en fin de session. Chaque ligne du livrable porte déjà son
gate.

**Une tâche unique** : `POST /v1/task` (~5-30 s selon étage) — remplace
« je lis moi-même ces 200 lignes pour en extraire 3 champs ».

**Ce qu'on ne délègue toujours pas** : un verdict, un merge, une suppression,
un jugement de fond, un comptage. Le service **lit, recopie, classe avec
preuve et rédige sous contrat** ; l'appelant **juge et agit**.

## 6b. Driver « 0-token » (recette W1 — productivité de l'appelant)

Le coût d'adoption réel n'est pas l'appel, c'est le boilerplate. Une lane
n'a qu'à **coller ce bloc PowerShell** pour consommer sans dépenser de tokens
à réinventer la requête. Depuis n'importe quel agent sur **po-2028** :

```powershell
# === VOLTRON HARNESS — driver copiable (po-2028) ===
$SVC = "http://127.0.0.1:5029"
function VTask($type, $data, $extra) {
  $body = @{ type = $type; data = $data } + $extra | ConvertTo-Json -Depth 8 -Compress
  (Invoke-WebRequest -Uri "$SVC/v1/task" -Method POST -ContentType "application/json" `
    -Body $body -TimeoutSec 900).Content | ConvertFrom-Json
  # Coupure : rejeu borné à 120 s après l'auto-guérison, PLUS les appels en cours.
  # Pas de garantie de durée totale : pour une tâche longue, utiliser /v1/jobs.
}
# --- exemples (décommenter et adapter) ---
# VTask classify (Get-Content C:\log.txt -Raw) @{ classes = @("oom","engine-init","path-mangling") }
# VTask extract  (Get-Content C:\bench.json -Raw) @{ fields = @("score","acc"); verbatim = $false;
#   instruction = "la plus basse accuracy -> JSON {score,acc}" }
# VTask numbers  (Get-Content C:\metrics.txt -Raw) @{ numbers = @("455","44");
#   report_prompt = "Rapport une phrase citant mémoire GPU et température." }
```

Résultat : `$r.ok` (bool), `$r.stage` (`a` worker seul · `b` second lecteur
mini · `c` coordinateur 27B), `$r.answer` (le livrable **déjà gaté**), `$r.detail` (pourquoi pas si
`ok=false`), `$r.turns`, `$r.dt_s`. **C'est `answer` qu'on consomme, pas un
texte à re-lire** — le service a déjà payé la vérification.

**Sondes de santé** : ajouter l'en-tête `X-Voltron-Probe: 1` (sur `/v1/task`
comme sur `POST /v1/jobs`) pour que le trafic de test **ne gonfle pas le
compteur d'adoption** — le compteur est l'instrument du mandat, il ne doit
mesurer que les consommateurs réels.

**Tâche longue en fond** (le réflexe « je lance et j'oublie ») :

```powershell
$tasks = Get-ChildItem C:\logs\*.txt | ForEach-Object {
  @{ type = "classify"; data = (Get-Content $_.FullName -Raw);
     classes = @("oom","engine-init","path-mangling","benign-boot") } }
$body = @{ name = "triage-logs"; tasks = $tasks } | ConvertTo-Json -Depth 8 -Compress
$job = (Invoke-WebRequest -Uri "$SVC/v1/jobs" -Method POST -ContentType "application/json" `
  -Body $body -TimeoutSec 60).Content | ConvertFrom-Json
$job.job_id   # → stocker ; relire en fin de session :
# (Invoke-WebRequest "$SVC/v1/jobs/$($job.job_id)").Content | ConvertFrom-Json
```

Le job tourne **en fond du service**, persiste après chaque tâche : l'agent
peut fermer sa session, relire le lendemain, rien n'est perdu. **~0 token
pendant**, livrable forme fixe à la fin (contrat BG FrogNano). Depuis une
**autre machine**, remplacer `127.0.0.1` par l'IP po-2028 — mais le service
bind local : demander l'exposition hub au siège po-2028:vllm (§7).

## 6c. Façade OpenAI (26/11) — pour les clients qui ne savent qu'appeler un modèle

Beaucoup de clients ne parlent que `chat/completions` : SDK OpenAI, proxys,
présets sk-agent. Le service expose donc ces deux routes, **sans devenir un
chat** : une **tâche par appel**, et le résultat du harnais dans le contenu.

| Route | Réponse |
| --- | --- |
| `GET /v1/models` | `{"object": "list", "data": [{"id": "voltron-harness", …}]}` — un seul modèle, qui est **le harnais**, pas le 1.7B nu |
| `GET /v1/models/voltron-harness` | sa fiche ; tout autre id → **404** `model_not_found` (format d'erreur OpenAI) |
| `POST /v1/chat/completions` | `choices[0].message.content` = **le JSON du résultat** (`{ok, stage, answer, detail, turns, dt_s}`) ; `stream: true` → SSE (rôle, contenu, fin, `[DONE]`) |

La tâche se lit dans le **contenu du dernier message `user`** : l'objet JSON de
`POST /v1/task`, seul, dans un bloc ```` ```json ````, ou imbriqué dans du texte
(première `{` … dernière `}`). Messages `system`/assistant, historique et
paramètres d'échantillonnage sont **ignorés** (listés dans
`x_voltron.ignored_params`) : c'est le contrat de l'appelant qui décide, pas le
tirage. `x_voltron.kind` dit ce qui a été compris : `task`, `batch` (un tableau
JSON → refus actionnable renvoyant vers `/v1/jobs`), `invalid` (JSON cassé),
`help` (rien de reconnaissable → **carte d'emploi**, aucune tâche exécutée).

```python
from openai import OpenAI
c = OpenAI(base_url="http://127.0.0.1:5029/v1", api_key="local")  # clé non vérifiée : bind loopback
r = c.chat.completions.create(model="voltron-harness", messages=[{"role": "user", "content":
    '{"type": "extract", "data": "Rapport : temp 42, score 97", "fields": ["temp", "score"]}'}])
print(r.choices[0].message.content)   # -> {"ok": true, "stage": "a", "answer": "{...}", ...}
```

```bash
curl -s http://127.0.0.1:5029/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "voltron-harness",
  "messages": [{"role": "user", "content": "{\"type\": \"classify\", \"data\": \"...\", \"classes\": [\"oom\",\"benign\"]}"}]}'
```

Limites vendues d'avance : pas d'outils, pas d'image, pas de chat libre ; une
tâche par appel (un lot → `POST /v1/jobs`) ; `usage` à zéro (le service ne
facture pas de tokens, il en dépense côté hub) ; échec **dans** la tâche =
HTTP 200 + `ok: false` (lire `detail`), HTTP 400 seulement pour un corps
malformé (`messages` absent ou sans message `user`). Le compteur d'adoption
ne compte que les tâches réellement exécutées ; carte d'emploi et refus
(`help`/`batch`/`invalid`) exclus, `X-Voltron-Probe: 1` exempte tout.
**Le service reste en bind loopback** : une exposition via le hub claudish est
une question ouverte (posée sur `global` et à claudish-2c le 25/11), pas un
acquis — d'ici là, la façade sert les clients locaux de po-2028.

## 7. Feuille de route

1. ✅ Service HTTP + moteur persistant + jobs background (ce document).
2. Mesure service-mode 40 tâches (`service_mode_eval.py`) — chiffre publié au
   §4 au fil des runs. ✅ v4 : 95 % vérité banc, contrat 40/40.
2b. ✅ Compteur d'usage durable `GET /v1/usage` (19/11) — baseline adoption 0 à
   partir du 2026-11-19T05:50Z ; piège po-2025 « compteurs engine reset-boot »
   neutralisé (persistance disque atomique, survit serveur ET engine).
2c. ✅ Ancrage par préremplissage (20/11, commit `e66d607085`) : classify
   2-étapes stage a 0,26-0,64 s (escalade coordinateur systématique avant) ;
   seuil verbatim 15→8 ; extract/numbers livrent propre (extract reparsable) ;
   jobs ×6 concurrents ; `GET /` sert les capacités.
3. ✅ **Façade OpenAI livrée (26/11, §6c)** : `GET /v1/models` +
   `POST /v1/chat/completions` (JSON + SSE) — le prérequis technique d'un
   préset sk-agent ou d'un montage hub. **Reste la décision d'exposition** :
   le service bind loopback ; la question (a fournisseur non-chat · b façade
   livrée · c pas de place) est posée à po-2025:claudish / claudish-2c depuis
   le 25/11, sans réponse ⇒ pause explicite datée au cycle suivant, service
   inchangé sur loopback.
3b. Corrigé au passage (même commit) : `POST /v1/task` avec un corps non objet
   répond **400** (au lieu de fermer la connexion), et une tâche malformée
   devient un résultat `stage: "error"` — même garde que les jobs (21/11).
4. Coordination migration po-2025 (flambeau FrogNano) : consommateurs hérités,
   recettes compatibles.
5. Veille capacité : le moteur est surveillé par le cron vigie 6h du siège
   (santé + génération réelle, pas seulement /health).
6. ✅ **Première adoption réelle (20/11, complète à 01:46Z)** : claudish-cd
   (po-2028) — job de **5 586 tâches classify** (1/cellule des 436 carnets C#
   orphelins) : **5 558 ok = 99,5 %**, stages a=4 211 / c=1 375 (75 % local),
   ~65 tâches/min, 85 min de mur ×6 concurrents. Consommation réelle : colonne
   « Archetype (preuve) » dans 434 specs, `ligne_cle` citées verbatim dans les
   fiches. Qualité fine mesurée (spot-check consommateur) : exact sur
   l'inventaire et les cellules à marqueur ; ~60-75 % de précision fine
   (sur-déclenchement « exercice » sur cellules `def` de fondations) —
   **accélérateur de brouillon, pas verdict** (frontière vendue). Axe
   suivant LIVRÉ (20/11 soir) : `class_definitions` optionnel dans le contrat
   (§2) — 4/6 vs 3/6 sur cas discriminatifs, limite lexicale documentée.
   Verbatim
   consommateur : « à 0,3-0,6 s c'est un non-choix ». Compteur au 01:46Z :
   5 666 tâches / 4 jobs depuis la baseline 0 (19/11 05:50Z).
7. ✅ **Reprise des jobs au restart serveur (21/11)** — ferme le point faible
   « tâches longues en background » du mandat : la charge est persistée dès le
   POST, le boot relance les tâches restantes d'un job interrompu (résultats
   faits gardés, jamais re-exécutés) et attend l'engine ≤300 s si le restart
   partage la fenêtre (reboot hôte). Défect corrigé au passage : une tâche
   malformée gelait TOUT le lot (`ex.map` tué, job `running` à vie) — elle
   devient un résultat d'erreur consultable. Validé live kill/relance (12/12,
   index sans doublon) + test isolé 5 branches.
8. ✅ **Passe review PR #508 (22/11)** — durcissement suite CHANGES_REQUESTED
   ai-01 : persistance de job sérialisée (verrou dédié + tmp unique par
   écriture + fsync — l'ancien tmp partagé produisait PermissionError Windows
   dès 2 threads, 7/8 tués en hammer mesuré), échec de `_persist` ne casse plus
   le pool, compteur d'usage refuse d'écrire sur fichier illisible (l'historique
   d'adoption ne repart pas de zéro), reprise sans re-comptage, `jid` validé par
   regex avant lecture disque, bornes d'entrée (`diff` a/b, class_definitions,
   numbers liste, corps POST 2 Mo), bind du port AVANT la reprise (instance
   unique), IP LAN et chemins machine sortis du code (env), `stage=c` seulement
   si la phase C a tourné, tests commités (`test_voltron_recovery.py`, 5/5 à
   l'époque — dont le hammer N-threads rouge sur l'ancienne tête).
9. ✅ **Résilience aux coupures d'engine + découverte OpenAPI (24/11)** —
   §3bis : rejeu des tâches coupées avec attente du retour de l'engine (cause
   racine : la garde anti-famine du commit hôte recycle la VM WSL 1 à 4
   fois/jour ; retour 1 min 49 s–2 min 06 s, une fois 8 min 52 s), échec rapide
   des tâches restantes tant que l'engine est muet puis reprise du job,
   `transient: true` pour l'appelant, `docker start` bloqué toléré,
   `/openapi.json` + `OPTIONS` (sans CORS), sonde `X-Voltron-Probe` hors
   compteur d'adoption, logs UTF-8 (un print de rejeu levait UnicodeEncodeError
   sous console cp1252 → la coupure devenait « stage: error » au lieu d'être
   rejouée), `GET /v1/jobs/<id>` en instantané sous verrou (une clé ajoutée
   pendant la réponse fermait la connexion). **Correction du rouge « flake » du
   22/11 : c'était un vrai défaut** — la dernière écriture du job n'était pas
   protégée ; un `os.replace` refusé par Windows (destination tenue par un
   lecteur ou l'antivirus, PermissionError WinError 5, reproduit ~1 passage sur
   12) tuait le thread à la finalisation : `done` jamais sur disque, job fini
   relancé au boot suivant ; au boot, la même exception empêchait le serveur de
   démarrer ; et un compteur d'usage muet changeait une tâche RÉUSSIE en
   « stage: error ». Persistance : 6 essais (3,15 s cumulés), jamais d'exception,
   tmp de l'essai raté nettoyé, même garde sur le compteur d'usage et sur
   `POST /v1/jobs` (la connexion se fermait sans réponse si la première
   écriture du job était refusée). Tests : `test_voltron_outage.py` **11/11**,
   `test_voltron_recovery.py` **6/6** (8 passages) — **preuve rouge sur
   l'ancienne tête : 1/11 et 4/6**. Tier RAM retiré (§1) : −3,5 Gio de
   consommation conteneur, KV identique (159 248 tokens), mesuré après
   recréation. **Deux leçons d'instrumentation, mesurées 24/11** : (a) une
   suite de tests ne doit jamais toucher le moteur ni Docker du siège — le
   seul `subprocess.run` du serveur est remplacé par un garde qui hérite de
   `BaseException`, car les deux `except Exception` qui l'entourent avaleraient
   un `Exception` ordinaire ; sans ce garde, la suite de reprise a lancé le
   VRAI conteneur. (b) Lire un fichier de job pendant son remplacement atomique
   est **refusé par Windows** (~1 lecture sur 20 sous écriture continue), et un
   lecteur qui sonde fait échouer **0,2 à 10 % des remplacements** (0,2 % sur
   D:, 10 % dans `%TEMP%`) — c'est la cause du rouge intermittent restant après
   la réparation ci-dessus : côté service, 6 essais ; côté tests, relire.
   **Validé en réel sur le service redéployé** : job de 48 tâches, `docker kill`
   en plein vol, conteneur relancé par le service seul, **48/48 `ok` en 160,1 s**
   (§3bis).
10. ✅ **Suivi de revue #599 (24/11)** — un compteur `usage.json` valide en
   JSON mais non-objet (par exemple `[]`) est désormais traité comme illisible
   : le job finalise et l'historique n'est pas écrasé. Le premier `docker start`
   d'`ensure_engine` partage la même porte que l'attente (6 appels concurrents
   → 1 start), et son `returncode`/`stderr` devient un résultat consultable, sans
   journal répétitif. Garantie de reprise explicitée : **au moins une fois**, une
   tâche non persistée peut être ré-exécutée, sans double comptage ni double
   livraison (§3). Tests : `test_voltron_recovery.py` **7/7**, `test_voltron_outage.py`
   **12/12** ; les deux nouveaux scénarios étaient rouges sur `main` avant correctif.
11. ✅ **Étage b : le duo avec le mini de la flotte (28/11, mandat user)** —
   §4bis. Le second lecteur (`frognano-4b`, po-2025, par le hub) s'insère entre
   les réparations du worker et le coordinateur 27B, sur le prompt sec et derrière
   le même gate. Hors-ligne, la cascade gâtée atteint le plafond de l'union
   (socle 93/120, pack 32/40). Au niveau du service, sur 40 tâches réelles :
   même service (40/40) et même vérité banc (32/40), **3 appels de coordinateur
   sur 4 évités** (somme des appels 27B 754 s → 146 s), aucune tâche gagnée ni
   perdue. Activation `VOLTRON_DUO_MODEL=frognano-4b` (env, hors dépôt).
   Limite mesurée : le gate `extract` sans `verbatim` ne voit pas les erreurs de
   valeur (12/12 `ok` contre 6/12 à la vérité sur le pack) — le levier suivant
   est un gate plus fort, pas un troisième modèle. Tests : `test_voltron_duo.py`
   11/11 (preuve rouge 10/11 sur le serveur d'avant).
12. ✅ **Écoute LAN gardée par clé entrante (28/11)** — §4ter. Le prérequis
   nommé par le propriétaire du hub : `VOLTRON_BIND` hors loopback avec
   `VOLTRON_INBOUND_KEY`, garde du démarrage (refus sans clé), 401 distant sans
   lecture du corps, `/health` ouvert, `Bearer` ou `X-Voltron-Key`, empreinte
   `sha256[:12]` seule publiée. Tests : `test_voltron_inbound.py` 6/6 (preuve
   rouge 6/6 sur `main`). Reste le geste élevé (règle de pare-feu TCP 5029),
   puis l'annonce.
