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

## 5. Guardrails carried over

- CoursIA repo = another workspace's infra: **ask, don't apply** — the pilot PR needs their GO;
  the driver never force-pushes, works on a fresh branch, one issue at a time.
- REST only on GitHub (GraphQL bucket is fleet-shared), `gh api user` checked before writes.
- No secrets in cells/commits; scratch stays in gitignored `.tmp/`.
- The verifier is a **different agent instance** from the builder, and it compares against the
  **source** (the issue spec + the notebook), never against the builder's claims.
