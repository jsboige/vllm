# nbaudit → notebook-coder: issue → notebook → PR trajectory (groundwork)

**Date:** 2026-11-13 · **Status:** groundwork VERIFIED, nothing armed · **Mandate:** user 13/11 22:45Z
(« lire et exécuter des cellules… et en sortir des issues (fait aujourd'hui), mais aussi **écrire et exécuter**
des cellules… et en sortir des PRs »).

---

## 1. What nbaudit does today (baseline, verified)

`nb_audit_driver.py` drives the sk-agent preset `notebook-auditor` (model `qwen3.6-35b-a3b-audit`,
MCPs `open_terminal` + `jupyter_papermill` + `searxng`, caps `shell/repl/repo_read/web/vision/github_read`,
memory off, 1500 s budget per notebook) through a **deterministic 3-stage harness**:

- Stage A — model reads the notebook, writes verification scripts;
- Stage B — **the harness executes them** (dedicated venv `%LOCALAPPDATA%\nbaudit\verif-venv`);
- Stage C — model judges against real outputs.

Findings flow as pre-audit dossiers (DM attachments to NanoClaw/Hermes) that feed CoursIA audit
issues/comments. **The write path of jupyter-papermill is never used** — audit is read+execute only.
The runner already reads GitHub defensively (skips notebooks touched by the 50 most recent open PRs).

## 2. Verified tonight — the missing bricks exist (live proof, not inference)

1. **Notebook provisioning of this seat**: `check-deny-fallback.py --workspace vllm` → handshake OK,
   25 tools (rule #4340 — `NotebookEdit` deny, papermill is the only sanctioned path).
2. **Write + execute, end-to-end, with persisted outputs** (scratch `D:\vllm\.tmp\nb_writer_poc.ipynb`):
   `create_notebook` → `add_cell` (code) → `manage_kernel start` → `execute_on_kernel(mode=notebook_cell)`
   → `status ok`, stdout + execute_result **written back into the .ipynb** (2 outputs, sha256 recorded).
   This is exactly what a deliverable notebook in a PR needs: source **and** executed outputs.
   - ⚠ Tool gotcha: the legacy `execute_notebook_cell` returns `Kernel not found` for standalone
     kernels — **root cause verified in source**: `main.py` runs `initialize_kernel_tools` AND
     `initialize_execution_tools`, each building its OWN `KernelService` → two `JupyterManager`
     instances, each with an **instance-local in-memory** `_active_kernels` dict
     (`jupyter_manager.py:115`, raise at `:467`). A kernel started via `manage_kernel` (kernel_tools
     instance) is structurally invisible to the legacy tools (execution_tools instance). The
     consolidated `execute_on_kernel` shares kernel_tools' instance, hence works. **Always
     `execute_on_kernel`**; cleanup signalled to roo-extensions (13/11).
3. **Sandbox = kernel choice.** The kernel registry exposes **29 kernels including every CoursIA
   series venv** (`coursia-genai-audio`, `coursia-genai-video`, `python3-lean`, `search313`,
   `python313-tweety`, `smartcontracts`, …). Per-series isolation is a config line per series, not
   new infrastructure — the verif-venv discipline of nbaudit generalizes to "run Audio notebooks on
   the audio kernel".
4. **CoursIA PR conventions** (REST sample 13/11): branch `fix/<issue>-<slug>` /
   `feature/<issue>-<slug>`, title `Fix(notebooks,#NNNN): …` / `Docs(curriculum,#NNNN): …`, PRs by
   the main account, `gh pr create` via REST. The repo checkouts exist locally (`D:\CoursIA`,
   `D:\CoursIA-2` — kernel specs point into their `.tmp` venvs).
5. **sk-agent already has the surrounding cast**: agents `coder`/`coder-local`/`mini-coder-fix`, and
   PR-review conversations `pr-review-tier1/2/3` (incl. a synthetizer on `swift-1.5-27b-no-thinking`).
   The **review side of the trajectory exists today**; only the build-and-deliver side is missing.
6. Real sk-agent config lives at `d:/roo-extensions/mcps/internal/servers/sk-agent/sk_agent_config.json`
   (gitignored, inline keys) — **roo-extensions territory**: agent entries are added by them on our
   spec (same flow as the capacity-gate #4712 coordination).

## 3. Design — the issue→PR trajectory

**Principle kept from nbaudit: the harness is deterministic and owns the gestures; the model proposes,
never self-verifies, never touches GitHub directly.** (Producteur ≠ vérificateur — global rule.)

```
design issue (CoursIA, label/agreed)
   │  0. CLAIM      harness: REST read issue + comment claim (if coordinator flow requires)
   ▼
   │  1. PLAN       model turn: propose cell plan (JSON: cell list, series kernel, expected outputs)
   ▼
   │  2. BUILD      model writes cells via papermill (add_cell/update_cell);
   │                HARNESS executes each cell via execute_on_kernel on the SERIES kernel;
   │                pass/fail decided by the harness from real outputs — model never judges its own run
   ▼
   │  3. GATES      harness: the 6 nbaudit organs + nbformat validate + series-specific checks
   ▼
   │  4. VERIFY     independent reviewer: notebook-auditor instance re-derives the deliverable
   │                (read+execute path — its day job) and issues a verdict on the BUILT notebook
   ▼
   │  5. PR         harness only: branch fix/<issue>-<slug> → commit .ipynb (with outputs) → push
   │                → gh pr create (REST) → body: issue link, plan, gate results, verifier verdict,
   │                sk-agent conversation_id (the agentic trace)
   ▼
  PR reviewed by the existing pr-review conversations / CoursIA lanes
```

### 3.1 Agent variant delta (notebook-auditor → notebook-coder)

| Field | auditor (today) | coder (proposed) |
|---|---|---|
| id | `notebook-auditor` | `notebook-coder` |
| model | `qwen3.6-35b-a3b-audit` | same (Swift alias + audit sampling preset) |
| mcps | open_terminal, jupyter_papermill, searxng | **identical set** — no new MCP needed |
| capabilities | shell, repl, repo_read, web, vision, github_read | same (github stays READ for the model; the **harness** holds write) |
| memory | off | off (trace lives in conversation_id) |
| budget | 1500 s/notebook | ~2400 s/notebook (write path ≈ 1.5× audit turns; measure at pilot) |

The delta is essentially the **system prompt** (build-from-spec instead of audit) and the driver.

### 3.2 Driver (`nb_coder_driver.py`, reuse the audit skeleton)

Spawn sk-agent MCP stdio exactly as `nb_audit_driver.py` does (`SK_AGENT_CONFIG`, `read_timeout = budget + 120`).
New stages 1/2 above; stages 3-5 are plain Python (subprocess git/gh, papermill kernel calls).
Per-series kernel map at the top (`{"19451:Audio/": "coursia-genai-audio", …}`) — mirrors the runner's
series scoping.

### 3.3 Capacity discipline (ties into tonight's gate work)

The driver calls `swift_capacity_gate.py` before **each** notebook (exit 0 only) and defers on
yellow/red — this is precisely a "consumer armed after 24 h observation" of the gate rollout
(#4712). Build work is batchable, so red = come back next hourly slot; no in-flight kill needed.

### 3.2bis Mode création (`--source-nb`) — les grains de parité C# (vague 1, 17/11)

La vague 1 de specs CoursIA (#27099-#27116, notre part : SMT/Z3-API + GameTheory) porte des
carnets **à créer** : la cible `X-CSharp.ipynb` est absente d'origin/main, sa création EST la
livraison (politique 7 de #26070). Le driver historique est correction-only
(`copy2` de la cible depuis le worktree → `notebook-not-found` sinon — mesuré au source,
échec sec avant tout appel modèle). Le mode création le comble :

```powershell
python nb_coder_driver.py --issue 27099 `
  --notebook   MyIA.AI.Notebooks/SymbolicAI/SMT/Z3-API/Z3-10-Cryptarithmetic-CSharp.ipynb `
  --source-nb  MyIA.AI.Notebooks/SymbolicAI/SMT/Z3-API/Z3-10-Cryptarithmetic-Python.ipynb `
  --repo D:/CoursIA --agent notebook-coder --gate-mode block --kernel-override .net-csharp
```

- **Résolution** : cible absente + `--source-nb` présent → création (le jumeau Python devient
  la source de contexte) ; cible présente + `--source-nb` → `target-already-exists` (refus
  loud : une coquille opérateur corrigerait silencieusement le jumeau) ; cible absente sans
  `--source-nb` → verdict historique inchangé.
- **Stage 1** : `creation_prompt` — le modèle rend le PLAN du jumeau (une ligne par cellule :
  index, type, titre, rôle — **SANS les sources** ; une cellule du jumeau Python = une
  cellule du jumeau C#, même fil pédagogique), guidé par la table index/verbatim de l'issue.
- **Stage 2** : le harnais pose un squelette vide héritant de la **metadata canonique du
  plus proche jumeau C# de la série** (`*-CSharp.ipynb` : kernelspec + language_info .NET,
  jamais ceux du jumeau Python), puis `create_segments` réclame les sources **PAR TRANCHES
  de 8 cellules** (`2-build+0`, `2-build+8`, …) dans la même conversation — mesuré 17/11
  (#27099, passe à blanc) : la réponse mono-tour « tout le carnet » de 16 268 caractères
  n'a **jamais parsé** (budget de sortie dépassé sur ~29 cellules) ; `apply_create`
  assemble le tout en UNE écriture (même discipline que le write-mode json ;
  `--write-mode mcp` refusé en création). Cellules code : `execution_count: null`, zéro
  output au départ. Réponses non parsées : queue brute persistée
  (`stage1_raw_tail`/`stage2_raw_tail`, 3 000 car.) — la passe du 17/11 n'avait que
  `response_chars` pour deviner.
- **Boucle de réparation (`--repair-rounds`, défaut 2)** — mesuré 17/11 (#27099, passes
  3-4) : le modèle traduit des idiomes Python inexistants dans l'API .NET (`MkNe`,
  `Expr` là où `ArithExpr` est exigé). Les erreurs **réelles** du kernel (messages du
  compilateur, ligne + cause, extraits des outputs persistés) retournent au modèle dans
  la même conversation (`2.5-repair+N`) ; il ne rend que les cellules en échec (index
  inchangés) ; `apply_repairs` remplace leurs sources en une écriture et **réinitialise
  outputs et `execution_count`** (les sorties ne reviennent que de l'EXÉCUTION), kernel
  **frais** à chaque tour (une définition réparée peut changer la sémantique en aval),
  puis re-exécution complète. Passe 4 : round 0 → 6 cellules réparées, round 1 →
  **11/11 cellules OK, `execution_count` 1..11 séquentiels, verdict `gates-ok`** en
  7 appels modèle (~23 min).
- **Kernel cwd = dossier du carnet source** : sans lui `#load "Z3NativeLoader.cs"` meurt
  CS1504 (le fichier existe dans la série) et chaque cellule utilisant Z3 cascade CS0246 —
  mesuré #27099 passe 2 ; même correctif que #467 pour `import ict` (#27021).
- **Preuve structurelle** : `verify_structure_create` — même nombre de cellules que le
  jumeau + signature de types identique (code↔code, markdown↔markdown) + aucune cellule code
  vide + aucun output résiduel (les sorties doivent venir de l'EXÉCUTION).
- **Gate language-info** : comparé à la version canon .NET de la série, pas au jumeau
  Python (la parité porte sur les verdicts, pas sur la langue).
- **Kernel mort = échec** : `kernel-start-failed` — un kernel `.net-csharp` absent ne peut
  plus produire un `built-executed-ok` sans aucune cellule exécutée (le trou était réel).
- Tests offline : `test_nb_coder_create.py` (apply/skeleton, preuve structurelle, meta
  canonique, gate création, prompts, garde mcp, applicateur de réparation) — aucun moteur,
  aucun MCP, aucun GitHub. 18 verts avec les pins correction.

### 3.2ter Mode création depuis la spec (`--from-spec`) — carnet neuf sans jumeau (20/11)

Le mode `--source-nb` exige un **jumeau** (portages C#/Rust). Un carnet neuf d'une série
existante sur main — premier cas : CoursIA InformationTheory carnet 08, parent #27077 — n'en
a pas, et rendait `notebook-not-found`. `--from-spec` en fabrique un à partir de l'issue :

```powershell
python nb_coder_driver.py --issue <N> --from-spec `
  --notebook  MyIA.AI.Notebooks/<série>/<Nouveau-08>.ipynb `
  --meta-from MyIA.AI.Notebooks/<série>/<Existant-01>.ipynb `
  --repo D:/CoursIA --claim --lane ai-01:nb-coder --gate-mode block --max-stage 5
```

- **Contrat de spec** : section `## Plan des cellules` (niveau 2 à 4) contenant une table
  avec une colonne `Type` (`markdown`|`md`|`code`) et une colonne de contenu
  (`Contenu`/`Rôle`/`Attendu`). Colonnes `#` et `Titre` facultatives ; si `#` est présente,
  les index se suivent à partir de 0 ou de 1. Il faut au moins 3 lignes, la première et la
  dernière en markdown (titre, pied de provenance) et au moins une cellule code. Un pipe
  littéral s'écrit `\|`.
- **Refus fermé, AVANT la réservation** : `parse_spec_cells` nomme chaque défaut et rejette
  le plan entier → `refused-spec-plan-unusable`, sans commentaire `[CLAIMED]`, sans worktree
  et sans token. Un plan approximatif ne se révélerait qu'au vérificateur, une fois tout payé.
- **Jumeau de spec** : `spec_twin` écrit une cellule `[SPEC cellule i — type] titre` par
  ligne, sans sortie, dans le **out-dir** (`spec-twin-<N>.ipynb`), jamais dans le worktree,
  jamais commité. `verify_structure_create` et le prompt de stage 1
  (`spec_creation_prompt`) s'y réfèrent, avec le même contrat de plan léger.
- **Metadata** : kernelspec + language_info de `--meta-from` uniquement (rien d'autre n'en
  est lu) ; `kernel_source = meta-from-kernelspec`. Refus `meta-from-not-found` /
  `meta-from-no-kernelspec`. Cible déjà présente → `target-already-exists`.
- **Kernel cwd = dossier de la CIBLE** (créé si absent) : le jumeau vit hors série, son
  dossier ferait résoudre chaque chemin relatif hors de la série.
- **Vérificateur `--mode spec`** : la référence devient la spec de l'issue. La tâche
  « contenu perdu/inventé » est remplacée par : plan réalisé, attendus **affichés par des
  sorties réelles** et exacts, aucune source ou page que l'issue ne fournit pas, conventions.
  Les digests et diffs contre le jumeau sont omis (bruit pur). Le contrat JSON du verdict
  est inchangé.
- Gardes CLI : `--from-spec` exclut `--source-nb`, exige `--meta-from` et refuse
  `--write-mode mcp`. Tests : `test_nb_coder_spec.py` (26 pins), 7 mutations des gardes
  toutes tuées.
- File du scheduler : un grain de spec s'écrit
  `{"issue": N, "notebook": "...", "from_spec": true, "meta_from": "<carnet repo-relatif>"}`.
  `load_queue` applique les mêmes refus que le driver dès le chargement : `source_nb`
  exclu, `meta_from` exigé, `write_mode` `mcp` refusé, `meta_from` sans `from_spec` refusé,
  chemin repo-relatif `.ipynb` requis. Un grain de spec n'hérite jamais du `--source-nb`
  par défaut du scheduler. Tests : 10 dans `test_nb_coder_scheduler.py`, 6 mutations
  toutes tuées.

### 3.2quater Modèle par étape : spec / coder / vérificateur (#4831, 21/11)

Le modèle de chaque étape se choisit par paramètre, jamais en modifiant la source.
Ce port vient de la tranche `81ec3536` (roo-extensions#4831, jsboige-mcp-servers#1810)
et ajoute deux gardes propres à ce dépôt.

| Étape | Drapeau du driver | Défaut (env) | Ce qu'elle sert |
|---|---|---|---|
| spec (pré-mâchage, optionnel) | `--spec-model` + `--spec-mode run\|skip` | `NBCODER_SPEC_MODEL` / `NBCODER_SPEC_MODE` | le tour qui réécrit une issue grossière en issue détaillée |
| coder (plan, build, segments, réparations) | `--coder-model` | `NBCODER_CODER_MODEL` | chaque tour producteur |
| vérificateur (audit de l'étape 4) | `--verifier-model` (relayé à `nb_coder_verify.py --model`) | `NBCODER_VERIFIER_MODEL` | l'audit indépendant |

Sans valeur, chaque étape garde le modèle du préréglage `--agent` / `--verifier-agent`,
comme avant #4831. sk-agent valide la référence contre sa configuration (modèles activés
seulement). Le modèle déclaré est tracé dans `rec["models"]`, le modèle qui a réellement
servi le tour dans `calls[].model_used` et `verify.model_used`.

**Étape ½ SPEC.** `--spec-mode skip` (le défaut) est un choix **déclaré** par la lane
appelante, jamais une heuristique du harnais. Il est tracé sur le run :
`"spec": {"mode": "skip", "skipped": true, "declared": "--spec-mode skip", "issue_body_chars": N}`.
`--spec-mode run` exige `--spec-model` : sinon le driver refuse, avec le code de sortie 2
et le message `--spec-mode run requires --spec-model`. Le tour de spec réécrit l'issue
brute, avec son fil, les conventions et la vue du carnet, et le résultat devient le corps
d'issue de l'étape 1. Il est plafonné à 30 000 caractères et écrit dans
`<out-dir>/spec-<issue>.md`. La ligne du ledger porte `"spec": "run" | "skip"`. Un tour de
spec mort échoue bruyamment (`spec-<cause>`) au lieu de retomber sur l'issue brute :
sinon le coder brûlerait sa passe sur exactement l'échec que l'étape spec doit éviter.

**Gardes propres à ce dépôt** (refusées avant tout jeton, code de sortie 2) :
- `--spec-mode run` avec `--from-spec` : le plan de cellules gaté est lu dans le corps
  **brut** de l'issue, alors qu'un corps pré-mâché ferait diverger ce plan du prompt ;
- `--spec-mode run` avec `--revise-from` : une révision ne re-planifie rien, donc le tour
  de spec ne tournerait jamais (il faut déclarer `skip`).

`--source-nb` (portage) accepte `--spec-mode run` : son plan de création voit la spec.

**Correspondance difficulté → modèle** : c'est une consigne pour la lane appelante, qui
décide par passe ou par grain. Elle n'est jamais codée dans le harnais. Les identifiants
réels sont ceux de la configuration sk-agent du siège (ai-01 : `nb-minimax`, `glm-5.3`,
`swift-1.5-27b`).

| Difficulté | coder | vérificateur | spec |
|---|---|---|---|
| simple (corrections, prose) | swift | tier flash | skip |
| standard | MiniMax | GLM | skip, ou GLM si l'issue est vague |
| difficile (parité C# SMT/Z3…) | GLM, ou rôle Sonnet | GLM ou au-dessus | GLM ou Sonnet |
| très difficile | rôle Opus | au-dessus du coder | Sonnet/Opus |

Terrain mesuré (18/11) : les grains de parité C# SMT/Z3 sont au moins difficiles. Swift y
fait 0/7 (5× `built-execution-failed`, avec la même erreur régénérée trois tours de suite),
MiniMax 2/2 au vert sur la même classe.

**Scheduler.** Dans la file, les clés `coder_model` / `verifier_model` / `spec_model` /
`spec_mode` remplacent par grain les défauts du scheduler (drapeaux du même nom).
`--spec-mode` est toujours relayé, pour que le skip soit déclaré sur chaque ligne de
commande du driver.

```bash
# grain standard, issue assez détaillée : spec skip (déclaré, tracé)
python nb_coder_driver.py --issue 27106 --notebook Ser/Z3-10-CSharp.ipynb --repo D:/CoursIA \
    --lane myia-ai-01:vllm --coder-model nb-minimax --verifier-model glm-5.3 --spec-mode skip
# issue grossière : pré-mâchage GLM, puis code MiniMax
    ... --spec-mode run --spec-model glm-5.3 --coder-model nb-minimax
```

Tests : `test_nb_coder_step_models.py` (37). 26 mutations, toutes tuées, dont la garde de
Hermes remplacée par `if False:` et chaque branche de `run()` relue sur l'issue brute.

### 3.4 Agentic trace

- sk-agent `conversation_id` persists per notebook build → the PR body carries it;
- the committed `.ipynb` itself carries executed outputs (the artifact IS part of the trace);
- gate results + verifier verdict are JSON, pasted in the PR body and kept in the run record
  (`%LOCALAPPDATA%\nbaudit\` sibling dir) — same survivable-trace discipline as `last-result.json`
  (the 37 h silent-outage lesson: a deliverable's exit code hides a dead producer).

## 4. What must be built, in order

1. `nb_coder_driver.py` (stages 1-2-5 skeleton; gates reused from nbaudit organs) — **vllm repo**.

   **État 2026-11-14 (dispatch CoursIA 15:34Z, GO suite 17:00Z/corrigé 17:15Z)** : étapes
   **0-2 écrites** dans `myia_vllm/scripts/adoption/nb_coder/nb_coder_driver.py` (claim guard
   via `check_lane_claim.py` ; plan JSON ; build par le modèle via papermill, **exécution par
   le harnais** via `execute_on_kernel`, verdict mécanique sur sorties réelles ; noyau par
   série avec version des voisins ; gate capacité en mode warn jusqu'à la fin de
   l'observation 24 h ; trace JSON + ledger ; **dry par défaut, zéro écriture GitHub hors
   claim**). Les chemins des grains portent le préfixe `MyIA.AI.Notebooks/`. Passe à blanc
   grain 1 : **built-executed-ok** (4 passes, 4 défauts corrigés) ; passe à blanc grain 3
   (#18874, chemin exécution) : **built-executed-ok, C.2 prouvé** — 16/16 cellules exécutées,
   `execution_count` 1..16 strictement séquentiels, 0 erreur, 0 cellule dégénérée restante
   (5 éditions + 5 inserts markdown, édition minimale vérifiée). Stages 3-5 = incrément
   suivant ; **stage PR gelé sur Q188** (identité GitHub à arbitrer par le user — aucun push,
   préparation à blanc autorisée).

   **Leçons des quatre passes à blanc du 14/11** (chaque défaut est mesuré, pas supposé) :

   | # | Défaut trouvé | Correctif |
   |---|---|---|
   | 1 | `plan_prompt` coupait la vue du carnet à **20 000 caractères** sans le dire → le modèle a planifié « insérer en pied » **après la cellule 19** d'un carnet qui en compte 37, et a reconstruit 21 cellules (17 perdues, 12 sorties perdues) | `build_view` rend **toute** la vue (39 203 caractères ici) ; toute coupe est **déclarée** avec l'index des cellules restantes |
   | 2 | le build demandait au modèle de « réécrire l'intégralité du carnet » → reconstruction fidèle à ce qu'il avait vu, jamais à la source | le harnais **copie la source** (`shutil.copy2`, sorties incluses) et le modèle n'édite que les cellules du plan |
   | 3 | le verdict se contentait de « le fichier existe » → un carnet de 21 cellules était accepté | `verify_structure` : nombre de cellules, cellules non prévues **verbatim et dans l'ordre**, sorties préservées, édition réellement appliquée, **ancre d'insertion** (un `insert_after` doit atterrir juste après son ancre) |
   | 4 | **le MCP papermill perd les écritures concurrentes** : trois appels parallèles du modèle (`update_cell` 0, `update_cell` 36, `add_cell` 37) à 17:08:12 locale → chacun lit-modifie-écrit, les deux `update_cell` répondent « success » et sont **écrasés** par le `add_cell` (carnet final : 38 cellules, zéro édition) | mode d'écriture **`--write-mode json` (défaut)** : le modèle rend les sources complètes, le harnais applique en **une seule** lecture-modification-écriture (`apply_edits`, ids nbformat générés, round-trip canonique `json.dumps(indent=1)+"\n"` vérifié). `--write-mode mcp` conservé pour la démonstration de capacité |

   Conséquence pour roo-extensions : les outils d'écriture du MCP sont **sûrs en appel unique,
   pas en appels parallèles** — un `lock` par fichier (ou une sérialisation des appels d'un même
   agent) est nécessaire avant qu'un autre consommateur s'appuie dessus.

   **Leçons de la passe grain 3 du 14/11 soir (exécution de cellules, #18874)** :

   | # | Défaut trouvé AVANT la passe (lecture du code, corrigé préventivement) | Correctif |
   |---|---|---|
   | 5 | `apply_edits` ne savait ni **supprimer** une cellule ni **convertir son type** (bannière `print("="*60)` → titre markdown), alors que le schéma du plan le déclare (`geste: delete`) | `deletes[]` + `cell_type` optionnel par édition (conversion : pop/ajout `execution_count`/`outputs`), ordre canonique édits → deletes (desc) → inserts (ancre remappée `a − #(deletes<a) + 1`), **cohérent avec le `shift()` du vérificateur** — prouvé par 5/5 contrôles positifs/négatifs, non exercé par la passe live (le modèle a choisi éditions+inserts) |
   | 6 | `execute_cells` du plan = index **source**, exécutés sur le carnet **construit** → décalage dès la première insertion ; et exécuter seulement les cellules éditées casse sur l'état du noyau (une cellule exercice appelle `charger()` défini plus haut) | `--exec-mode auto` (défaut) : si le plan touche du code, le harnais exécute **toutes les cellules code du carnet construit, dans l'ordre** (Restart & Run All) — état-sûr et preuve C.2 native ; verdict `built-executed-counts-broken` si les `execution_count` ne sont pas 1..N |
   | 7 | Réponse vide du tour plan (**2ᵉ occurrence mesurée**, 303 s perdues) | le retry `RETRY_NOTE` existant a récupéré (4 299 chars au 2ᵉ essai) — mécanisme validé, pas de changement |

   Résultat grain 3 : **`built-executed-ok`** — 16/16 cellules exécutées sur `python3` (3.13.14,
   version des voisins), `execution_count` **1..16 strictement séquentiels**, 0 erreur, 0
   cellule dégénérée restante (critères de l'issue : ≥5 prints, ≤2 assignations, pas de `def`),
   47 cellules (42 + 5 inserts markdown), édition minimale vérifiée (5 éditions, cellules hors
   plan verbatim, outputs préservés). Durée ~15 min (plan 303 s vide + retry 415 s + build
   162 s + exécution 4,3 s). Tokens (bornes hautes fenêtre, hub partagé) : 2 047 775 prompt /
   65 702 génération.

   **Étape 4 — vérificateur indépendant (`nb_coder_verify.py`, 14/11 soir)** : producteur =
   `notebook-auditor` (Swift), vérificateur = `critic` (GLM-5.3 via hub) — **modèles réellement
   distincts**, session neuve, aucun outil, prompt = SOURCE + LIVRABLE + critères d'issue +
   les faits mécaniques du harnais étiquetés « affirmations à contre-vérifier ». Les vues ne
   montrent pas les sorties : une **annexe d'empreintes par cellule code** (n, types, bytes,
   sha1[:8]) comble ce trou — le vérificateur avait signalé la limite lui-même au premier
   passage. **Prouvé dans les deux sens** : `approve` sur le livrable grain 1 (0 constat,
   5 points vérifiés citant les 12 empreintes de sorties) et **`reject` sur le carnet tronqué
   de la passe 2** (4 constats majeurs/mineur : 17 cellules perdues, 12 sorties effacées avec
   preuve sha, provenance en mauvaise forme, caractère parasite). ~18 s et 30 881 tokens par
   passage. Exit du script : 0 approve / 1 reject / 2 erreur d'instrument — **jamais de lecture
   d'un `reject` comme un « zéro »** (attention : dans une commande pipée, le code de sortie lu
   est celui du tube, pas celui du script).

   **Garde d'origine du `--repo` (15/11, après un faux diagnostic rétracté)** : `check_lane_claim.py`
   infère le slug du dépôt depuis le remote `origin` de **son cwd** — un appel manuel depuis
   `d:/vllm` a rendu un verdict sur `jsboige/vllm#20250` (bon numéro, mauvais dépôt) ; le driver,
   lui, l'appelle avec `cwd=repo` et tous les contrôles de passe étaient corrects. Le driver
   **refuse désormais** un `--repo` dont l'`origin` n'est pas `jsboige/CoursIA`
   (`refused-foreign-origin`, `--allow-foreign-origin` pour déroger) et enregistre `repo_origin`
   dans la trace ; le `conversation_id` du build est persisté (`rec["conversation_id"]`) pour que
   le corps de PR porte la trace agentique. Piège d'instrument jumeau : `git remote -v | head -2`
   **n'est pas un inventaire** — `d:/CoursIA` porte deux remotes (`Arfi345`, puis `origin`) et la
   liste tronquée avait fait conclure à tort à un fork étranger ; lire `git remote get-url origin`.
2. `notebook-coder` agent entry in sk-agent config — **roo-extensions adds it** (ask via dashboard,
   spec = §3.1; same flow as #4712). *2026-11-14 : PR jsboige-mcp-servers#1760 en review — 4
   variantes seat-local (Swift gaté sur `qwen3.6-35b-a3b-nbcoder`), split GitHubPlugin/
   GitHubWritePlugin, CI verte ; application siège ai-01 attendue côté ai-01:roo-extensions.*
3. Pilot issue agreed with the CoursIA coordinator (their repo, their review load) — sandbox branch
   first, PR only when the coordinator and the user GO. *2026-11-14 : les 3 grains pilotes sont
   nommés dans CoursIA#26534 (2 gestes Epic-ref markdown sur #20250, 1 conversion print→display
   sur #18874 P3).*
4. Capacity-gate call wired (after the 24 h probe observation started 13/11 21:13Z).
   *Fin de l'observation ~14/11 21:13Z ; mode warn d'ici là, conformément au dispatch.*
5. **Capacity-aware scheduler** above the driver (`nb_coder_scheduler.py`, #468) — *livré
   17/11 : le maillon manquant du « remplissage intelligent » (mandat user 17/11 10:49Z).*

## 4bis. Scheduler `nb_coder_scheduler.py` — la boucle au-dessus du driver (#468)

Le driver gâte **par carnet** ; ce qui manquait pour remplir les batchs opportunistes était
la **boucle** : maintenir N grains en vol seulement quand la gate est verte, reprendre les
grains déférés par capacité, et monter un palier de ramp 2→3→4 **sur preuve mesurée**.
Le driver reste inchangé (sa gate `block` reste la deuxième ligne de défense).

**File d'entrée** (JSONL, un grain par ligne, champs fermés — tout champ inconnu est refusé) :

```json
{"issue":26997,"notebook":"MyIA.AI.Notebooks/…/X.ipynb"}
{"issue":26998,"notebook":"…","max_stage":2,"claim":true,"agent":"notebook-coder"}
```

Mêmes clés que les flags par-grain connus du driver (`max_stage`, `claim`, `fresh_worktree`,
`agent`, `intention`, `write_mode`, `exec_mode`, `kernel_override`, `verifier_agent`,
`timeout`, `max_tokens`, `allow_foreign_origin`) **+ les champs du mode création (17/11)** :
`source_nb` (jumeau Python repo-relatif — absent ⇒ le grain reste une correction, jamais
d'héritage d'un `source_nb` par défaut) et `repair_rounds`. Chemin `notebook` repo-relatif
obligatoire.

**File vague 1 (17/11)** — les 10 grains de notre part sont prêts et validés par
`load_queue` : `D:/vllm/.tmp/nbcoder/queue-wave1.jsonl` (digest `7a982c32ffb1`) —
SMT/Z3-API #27099-#27103 + GameTheory #27109-#27113, tous `source_nb` + `kernel_override
.net-csharp` + `max_stage 5` + `claim`. **Lancement armé après le merge des PR #469
(scheduler) et #471 (création)** — ramp 2→3→4 sur preuve, fenêtre annoncée sur `global`.

**Règles d'admission** (tick par `--poll-s`, 30 s par défaut) :

- lancement **uniquement sur gate green**, et tant que
  `max(len(en_vol_scheduler), gate.running) < max_active` — la cible de ramp borne le
  total de requêtes moteur, pas un compte privé de slots ;
- yellow/red/unknown **gèlent les nouveaux lancements** et ne touchent **jamais** un driver
  en vol (contrat d'admission debout : pas de kill en vol, pas de replay d'outil) ;
- fichier STOP (`<state-dir>/STOP`) = gel des lancements, enfants intacts ;
- verdict driver `deferred-by-capacity-gate` → grain **deferred** avec backoff
  `not_before` (croissant, plafonné), re-proposé plus tard sans re-claim dupliqué ;
- `--max-attempts` épuisé sur du déféré → **failed** terminal (jamais de boucle infinie).

**Ramp mesurée** (`--ramp 2,3,4`) : la promotion d'un palier exige `--ramp-min-done`
**runs servis** (3), zéro échec de run au-delà de `--ramp-max-failures`, et `--ramp-green-s`
de green **continu** (600 s ; un échantillon red/unknown relance la fenêtre, `dirty` le
garde comme preuve dans le rapport du palier). Un run servi est un achèvement propre **ou
un échec de contenu** : le moteur a servi toute la conversation et le harnais a jugé un
carnet qui n'a pas passé (`built-execution-failed`, `built-structure-mismatch`,
`built-executed-counts-broken`, `gates-failed:*`, `verify-reject`,
`stage1-unaddressable-creation-plan`, `refused-spec-plan-unusable`,
`stage2-short-segment:*` — `CONTENT_FAILURE_PREFIXES`, préfixe strict). Tout autre échec
(appel, timeout, sans réponse, crash, kernel, `verify-error`, verdict inconnu) reste un
**échec de run** et bloque. Les échecs comptés sont les grains échoués pendant le palier
et **encore** échoués (un grain relancé sur correctif sort de la preuve). Mesure fondatrice
(21/11) : un seul `built-execution-failed` sur CoursIA#27302 (parité C#) avait gelé le
tapis à son palier plancher 7 h, gate green sur 791/858 échantillons. L'événement
`failed` porte `failure_class` ; `ramp_history` porte `done`, `content_failed`, `failed`.
`--ramp-demote` redescend d'un palier sur red (les preuves repartent de zéro, les grains
en vol continuent). Tout palier franchi est archivé dans `ramp_history` (state.json) avec
ses compteurs — la montée se **prouve**, elle ne se déclare pas.

**Persistance** : `state.json` (statuts `pending/running/done/failed/deferred/withdrawn/
orphaned` + état de ramp) et `scheduler.jsonl` (un événement JSON par décision). Au
redémarrage, un grain `running` dont le driver est encore le processus lancé (même pid,
même create time, ligne de commande du driver) est **adopté** : suivi par pid, verdict lu
dans son `driver.log` à l'offset de la tentative. Tout autre grain `running` devient
**orphaned**, jamais relancé automatiquement (un doublon entrerait en collision sur
worktree, claim et PR) — la reprise est un geste opérateur explicite.

**Drivers détachés (`--detach-drivers`, défaut)** : mesure du 21/11 00:45Z, l'arrêt de la
tâche du planificateur (TaskStop) a tué les deux drivers en vol (MGS-25 à 1 464 s, MGS-28
à 283 s) — l'arrêt parcourt l'arbre de processus. Un enfant direct meurt quels que soient
ses drapeaux (plain, `CREATE_NEW_PROCESS_GROUP`, `CREATE_BREAKAWAY_FROM_JOB`) ; seul
l'enfant d'un intermédiaire déjà sorti survit. Chaque driver passe donc par
`nb_coder_detach.py`, qui le lance et sort aussitôt ; le planificateur le suit comme un
driver adopté et enregistre son create time (`driver_create_time`, identité plus forte que
la fenêtre de lancement). Conséquences : redémarrer le planificateur ne coûte plus les
grains en vol ; **arrêter le planificateur n'arrête plus les drivers** — pour en arrêter
un, tuer le pid de `state.json`. Sans psutil, ou si le lanceur échoue avant tout
lancement (`detach-failed`), le lancement attaché d'avant est utilisé ; un lanceur muet
60 s (`detach-timeout`) n'est jamais relancé et compte comme échec d'exécution.
`--no-detach-drivers` rétablit le lancement attaché.

**Commande** :

```powershell
python myia_vllm/scripts/adoption/nb_coder/nb_coder_scheduler.py `
  --queue grains.jsonl --state-dir D:/vllm/.tmp/nbcoder-sched `
  --repo D:/CoursIA --lane myia-ai-01:nb-coder --claim `
  --ramp 2,3,4 --gate-mode block
```

`--dry-run` journalise les commandes exactes sans rien spawner ; `--once` = une passe ;
`--watch` = reste vivant après drain ; `--max-launch N` borne les lancements de la session.
Tests offline : `test_nb_coder_scheduler.py` (fausse gate + faux driver, 14 cas — zéro
moteur, zéro écriture GitHub).

## 5. Guardrails carried over

- CoursIA repo = another workspace's infra: **ask, don't apply** — the pilot PR needs their GO;
  the driver never force-pushes, works on a fresh branch, one issue at a time.
- REST only on GitHub (GraphQL bucket is fleet-shared), `gh api user` checked before writes.
- No secrets in cells/commits; scratch stays in gitignored `.tmp/`.
- The verifier is a **different agent instance** from the builder, and it compares against the
  **source** (the issue spec + the notebook), never against the builder's claims.
