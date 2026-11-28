# Tapis nb_coder ai-01 — cycle du 28/11 2026 (12:0x→13:0xZ)

Run vivant : `D:/vllm/.tmp/nbcoder/conveyor-20261128` (scheduler PID 9036, harnais épinglé
`D:/vllm/.tmp/mcps-sched` @ `e5b554e36ede`). Le harnais vit dans `jsboige-mcp-servers`
(`servers/sk-agent/harness/nb_coder`) ; ce journal ne porte que **les mesures du siège**.

## Ce que le cycle a mesuré

### 1. La file du tapis était VIDE — le feeder était mort depuis 5 jours

| Lecture | Valeur |
| --- | --- |
| `feeder/feeder.log` (lane-local) | dernière ligne **2026-11-23T19:35:03Z** ⇒ feeder arrêté |
| `conveyor-20261128/queue.jsonl` | **2 lignes** (#28880, MGS-24) |
| grains | #28880 `deferred` (quarantaine RELACHEE, `[CLAIMED]` DEEP de `myia-po-2028:CoursIA` depuis 06:12:53Z) · MGS-24 `deferred` · MGS-27 `withdrawn` |

Le « 0 grain produit » n'était donc pas un défaut du tapis : **personne ne le nourrissait**.
Le feeder mutualisé (`nb_coder_feeder.py`, dans l'arbre épinglé) n'était jamais lancé, et
`pending.jsonl` n'existait pas sur ce run.

### 2. MGS-24 : deux blocages distincts, dont un qui n'est pas de la lane

* **Occupation IMPLICIT** (`deferred-by-claim-implicit-occupation:#28852,#28861`, 9 `deferred`
  sur le run) : la jambe IMPLICIT du garde (`check_lane_claim.py:6127-6204`) **ne lit pas les
  chemins** — une PR ouverte d'une lane tierce qui référence l'issue occupe le grain
  **à toute date** (#26751), même si ses fichiers sont disjoints des `--paths`. Sur une issue
  de **lot**, une seule PR d'un autre grain gèle le lot entier. Rejeu de la commande du
  coordinateur : **`rc=3`** pour la lane, alors qu'il mesurait `rc=0` — même commande,
  écart signalé. Arbitrage du coordinateur (c0180, 28/11 12:33Z) : option (a) — croiser les
  fichiers de la PR occupante avec les `--paths`, **fail-closed** si la liste est illisible —
  **dispatché à `myia-ai-01:CoursIA-2`** ; **la lane vllm ne code rien de ce côté**.
  Le correctif côté harnais (park : occupation garée, lancement remboursé, drain borné) est
  `jsboige/jsboige-mcp-servers#1981` (tête `d3eae92`).
* **Plancher de capacité** (`held capacity-target`, 16 ticks) : `--ramp 4,6,8` ⇒
  `budget = max_active − max(len(active), gate.running)`. Porte **green**, `running = 5,0`
  (KV GPU 88,6 %, trafic de failover MiniMax) ⇒ `budget = 4 − 5 < 0` ⇒ **tous les grains
  retenus**, même si la file était pleine. C'est le comportement voulu : le ramp borne le
  **total** des requêtes moteur, le tapis ne consomme que le mou.

### 3. La réserve se reconstruit, elle ne se rejoue pas

`nb_coder_reserve.py --checkout D:/CoursIA --lane myia-ai-01:vllm --json reserve.json` →
`pool_a` (feuilles ouvertes, non livrées, non tenues) et `pool_b` (pli à déplier). Le
`pending.jsonl` se déduit du `pool_a` : `issue`, `notebook` (cible `-Rust.ipynb` du body),
`source_nb` (jumeau `-Python.ipynb`), `meta_from` (un `-Rust.ipynb` **déjà sur `origin/main`**
— exigé par le driver, `meta-from-not-found` sinon), `claim`, `max_stage` 5,
`repair_rounds` 3. **Schéma fermé** du loader (`ITEM_FIELDS`) : une clé inconnue est refusée
à la charge, pas au run. Le feeder revalide chaque ligne sur données vivantes avant de la
pousser (trap 5) : une ligne fausse est **supprimée**, jamais rejouée.

### 4. Mesures moteur du cycle (12:50→12:55Z)

`health 200` en 4,1 ms · `RC=0`, `StartedAt 2026-11-28T02:03:40Z` (aucun redémarrage) ·
3 conteneurs Up · VRAM 22 483 / 21 404 / 46 MiB (GPU 2 libre) · `/dev/shm` 33/63 Go (le tier
lui-même, pas d'orphelin) · 5 000 lignes de journal moteur, **OOM 0** · watchdog : 2 808 sondes
`OK`, derniers WEDGE en `fail 1/2` (attendu en prefill large) · préemptions **23,0, delta 0**
· **ratio de cache = 90,7 %** (`Σ cached_by_source{device,host,disk}` / `prefix_cache_queries`)
⇒ amortissement des préfixes intact · commit hôte **71,8 %** (275,3/383,5 Go, marge 108 Go) ·
élagueur du tier fs : âge **1 min**, tier 151,3 Go, cap 268,4 Go, 0 erreur, C: 15,3 % libre ·
G: sonde d'écriture **OK** · watchdog hôte : UP, `LastTaskResult 0`, 0 bloc non livré ·
nbaudit : `ok:true`, 0 échec consécutif (dernier passage 12:14:18Z).

### 5. Relance — le tapis est de nouveau nourri, et il attend la place (13:04→13:06Z)

Le harnais est épinglé sur `jsboige-mcp-servers` **`150c2e9`** (fusion de ms#1981, park de
l'occupation IMPLICITE). Épreuves rejouées **sur cet arbre** avant la relance : **1454 passés,
3 skips, 3 erreurs préexistantes** (`test_nb_coder_window_replay` — `semantic_kernel`
incompatible Python 3.14, sans rapport avec le park) et **12/12** sur les tests ciblés
(occupation / implicit / attempts / park).
Deux gestes appriss ce cycle, tous deux rejoués tels quels :

* **Le noyau Rust doit être chauffé une fois avec un budget long avant d'appeler le lanceur.**
  Le premier lancement a été refusé par sa propre garde (`Kernel didn't respond in 30 seconds`,
  `exit 3`, rien n'a démarré) ; chauffé à 180 s il répond en **16,7 s**, puis 6,3 s à la
  deuxième tentative. La garde est correcte, elle est fail-closed par construction.
* **`TaskStop` sur le shell ne tue pas le python** : un `nb_coder_scheduler` orphelin a survécu
  au premier arrêt ; l'arrêt se fait sur la **ligne de commande** (`Get-CimInstance` filtré sur
  `nb_coder_scheduler`, `Stop-Process` sur le PID vérifié), puis un recomptage.

État après relance : scheduler **PID 73332** (13:04:04Z) sur l'arbre `150c2e9`, feeder mutualisé
**PID 10492** (13:05:36Z, `--cap 4 --poll-s 60 --bound-s 259200`), file à **5 grains**
(#28880, #27133 MGS-24 génération 3, #27722, #28875, #28944), 0 en vol.
Le feeder a été essayé en **`--once` d'abord** (il a poussé #27722, inflight 1) puis laissé en
daemon ; il a poussé #28875 et #28944 dans le même cycle de 60 s. `drift-sweep 0 PRs`.

**Le tapis tient sur `gate-red`, et c'est la bonne raison** : `waiting > 0` sur deux sondes
consécutives (5 requêtes en file depuis 13:00Z, `kv_gpu_perc` 65-99 %, préemptions **delta 0**),
soit du trafic de failover réel. Le ramp `4,6,8` borne le **total** des requêtes moteur : le
tapis ne consomme que le mou, et il n'y en a pas à cet instant. Rien à forcer ; le gate
rouvrira seul.

## Amont (veille, 1 appel REST par artefact)

Les 10 artefacts du §5quinquies : **0 merge** dans le cycle. Seul mouvement : `#69444`
(levier de la porte « parked-load », mesuré par `josephkaiser` sur **notre 4090 exacte**) a
reçu un commentaire de `nl-alonso` (28/11 06:46:19Z) annonçant `#54703` (patch du
`scheduler.py`, validé sur H200/B200 pour Inkling-2-Mini et -Small) et `#70482` (test de
planificateur sur `main`) — **rien de fusionné**, donc rien à re-mesurer chez nous ; le
`PR gate` de notre #28991 a conclu `INCONCLUSIVE` (quota d'installation GitHub App épuisé,
exit 3) puis `STARVED` (constituants en file sans runner, exit anticipé #13363) : **ni l'un
ni l'autre n'est un défaut de la PR**.
