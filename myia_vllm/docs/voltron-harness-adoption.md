# Harnais voltron — adoption flotte (po-2028, mandat user 18/11)

**Le produit** : une requête HTTP → une réponse **déjà fiabilisée**. La chaîne
worker (voltron-1.7B, po-2028, moteur local) + réparation dirigée (≤2 tours,
delta signé du gate — jamais la réponse) + coordinateur (swift-1.5-27b via hub
claudish, prompt sec) tourne **dans le service** ; chaque sortie est re-gatée
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
| --- |---|
| URL | `http://127.0.0.1:5029` (po-2028, bind local machine) |
| Moteur | `voltron-harness` (docker, `--restart unless-stopped`, config fp8 validée : KV 159K tok, tier RAM 4 Gio, ~6,2/8 Gio VRAM) |
| Endpoints | `GET /health` · `GET /v1/capabilities` · `POST /v1/task` · `POST /v1/jobs` + `GET /v1/jobs/<id>` |
| Auto-guérison | engine muet → `docker start voltron-harness` + attente ≤240 s (boot mesuré 115-150 s) |
| Démarrage | `pwsh -File myia_vllm/scripts/testing/start_voltron_service.ps1` (résout la clé hub en mémoire depuis `~/.claude.json`) |
| Rollback | `docker stop voltron-harness` + kill du process python :5029 — aucune donnée perdue |
| Logs | `D:\vllm-data\bench\v2_server.log` · jobs persistés `D:\vllm-data\bench\v2_jobs\` |

Réponse type : `{"ok": true, "stage": "a"|"c", "answer": "...", "detail": "",
"turns": 2, "dt_s": 8.4}`. `stage=c` signale que le coordinateur 27B a fini
la tâche (worker insuffisant) ; `ok=false` rend le **meilleur effort + le
détail du gate** — un échec est actionnable, pas un aveuglement.

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
{"type": "classify", "data": "<fenêtre de log>", "classes": ["weight-shape", "engine-init", "..."]}

```

Gate : classe dans la taxonomie fournie ; `ligne_cle` recopiée **mot pour mot**
depuis la source (≥15 caractères). La preuve voyage avec le verdict — pas de
classification non étayée.

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

Le job s'exécute en tâche de fond du service, **persisté sur disque après
chaque tâche** (un redémarrage du serveur ne perd rien ; le `GET` relit le
disque). Cas d'usage : balayer 30 fenêtres de logs, trier une inbox, rapporter
une série de diffs — l'agent appelant lance en début de session et relit en
fin de session (contrat BG FrogNano : ~0 token pendant, livrable forme fixe).

## 4. Mesures

| Étage | Score (vérité banc 40 tâches réelles) | Appels/tâche |
| --- |---| --- |
| Solo voltron t0 | 10/40 = 25 % | 1 |
| Chaîne complète A→B→C (bench, engine-swap par phase) | **40/40 = 100 %** | 2,4 voltron + 0,53 sibling + 0,25 swift-27B |
| **Service A→C en direct (v4, 18/11 soir)** | **38/40 = 95 %** — contrat appelant **40/40** | 2,70 |

`D:\vllm-data\bench\service_mode_v{1..4}.json` (40 tâches réelles du siège,
contrats appelant → réponses évaluées contre la vérité-terrain du banc, qui
est PLUS FORTE que le contrat : valeur d'égalité, pas seulement verbatim).
L'arc des 4 passes de ce soir — chacune a corrigé un défaut réel :

| Passe | Vérité banc | Défaut corrigé |
| --- |---| --- |
| v1 | 30/40 = 75 % | état initial (gate sur réponse brute, contrat extract sans sémantique) |
| v2 | 37/40 = 92,5 % | **gate sur le livrable nettoyé** (on certifie ce qu'on livre, pas le brouillon de raisonnement) + champ `instruction` du contrat extract |
| v3 | 34/40 = 85 % | contre-essai : amputer le format de l'instruction coûte 4 tâches — **l'ancre de forme fait partie de la sémantique** (liste vs dict, booléens vs « non ») |
| v4 | **38/40 = 95 %** | règle placeholder (« les <...> sont des formats, pas des valeurs ») + garde alphanum sur les nombres |

Les 2 résiduels v4 : un `"score": "84/120"` (string au lieu de l'entier —
sémantiquement juste, forme off) et un placeholder récalcitrant que la
réparation dirigée du banc ferme (json_eq à valeur d'égalité). **Le contrat
appelant est tenu à 40/40 sur les 4 passes** — un `ok=false` du service est
toujours accompagné du détail actionnable, jamais d'un échec muet.

La phase B (critique sibling 2xmerge) nécessite un deuxième engine 1.7B —
impossible en simultané sur la GPU 8 Gio (contrainte mesurée) ; elle reste un
outil de mesure hors-ligne du banc. Le service exécute A→C et **rend son
propre verdict** : `ok` + `detail` = l'appelant sait exactement quoi refaire
ou escalader.

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

## 7. Feuille de route

1. ✅ Service HTTP + moteur persistant + jobs background (ce document).
2. Mesure service-mode 40 tâches (`service_mode_eval.py`) — chiffre publié au
   §4 au fil des runs.
3. Présets sk-agent voltron (si les lanes veulent un routage hub) — à demander
   au PO sk-agent le cas échéant.
4. Coordination migration po-2025 (flambeau FrogNano) : consommateurs hérités,
   recettes compatibles.
5. Veille capacité : le moteur est surveillé par le cron vigie 6h du siège
   (santé + génération réelle, pas seulement /health).
