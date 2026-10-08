# Lean prover passes on the local MoE (CoursIA #1453) — 2026-09-23

## Why

CoursIA's TASK of 22/09 23:01Z asked ai-01:vllm to serve small models (≤ 35B) on GPUs 0/1 for a
ping-pong with the multi-agent Lean prover. On 23/09 the user decided "on reste sur le MOE et on
le fait produire" (registry Q6), and GPU 2 stays with the training jobs. The proposal, posted on
the thread at 12:48Z, is therefore to run the prover **on the production MoE**
(`qwen3.6-35b-a3b`, :5002), in short bounded passes, one at a time. Serving extra small models is
the user's call (registry Q8). This is also the second background workload under roo-extensions
#2404, after the notebook auditor.

## Setup

- **Dedicated clone** `d:/dev/CoursIA-prover`: `git clone --local --no-checkout` from the
  audit clone (objects hard-linked, the audit clone left untouched), origin reset to GitHub, and
  sparse checkout of `MyIA.AI.Notebooks/SymbolicAI/Lean/agent_tests` and
  `MyIA.AI.Notebooks/GameTheory/game_theory_lean`. Neither `D:\CoursIA` nor the audit clone is
  used. The harness files are under a po-2024:CoursIA claim, so they are only read, never edited.
- **Lean**: toolchain `v4.32.1` pinned by `game_theory_lean`, already installed through elan.
  `lake exe cache get` cloned the dependencies and found every Mathlib artifact in the local cache
  (8,638 files decompressed, nothing downloaded): 5 min.
- **Python**: the existing conda env `coursia-ml-training` already has `agent-framework-openai`,
  `openai` 2.36 and `python-dotenv`.
- **Launcher** `myia_vllm/scripts/adoption/prover_1453/run_prover_local.sh`: reads
  `VLLM_API_KEY_MEDIUM` from `myia_vllm/.env` without printing it, and pins **every** role to the
  `local` provider. The last point matters: with `--provider local` alone, the coordinator and
  tactic agents still default to **openrouter** (see `run_prover_bg.py --help`), so a "local"
  run would silently call the cloud or fail on a missing key.

```bash
bash myia_vllm/scripts/adoption/prover_1453/run_prover_local.sh <demo_id> <max_iter> <timeout_s>
```

## Demo 0 (smoke), 17:08:59Z → 17:11:33Z

`run_prover_bg.py 0 --max-iter 3 --workflow-timeout 300`, all roles local, `director=none`.

- The launcher stubbed the approved proof of `_SmokeTest.lean` line 6 (`CALIBRATION_STUB`), sorry
  1 → 0, `RESULT_SUCCESS True`, 3 iterations, 1 attempt, 0 provider failure, **151.5 s**. The
  proof found was `exact Nat.zero_add n`. The approved proof was restored (`CALIBRATION_RESTORE`),
  `EXIT code=0`.
- The RUNBOOK quotes < 60 s for this demo. On the MoE, the agent cycle takes 151 s for a trivial
  one-liner: read it as a floor on cost per pass, not as a measure of proving ability.
- Trace: `agent_tests/prover/baselines/traces/multi_SMOKE_TEST_ZERO_ADD_local_1790183341.spans.jsonl`
  in the dedicated clone. The only local change is the harness knowledge base
  (`proof_knowledge.json` learned `0 + n = n`); nothing is committed to CoursIA.

## Target order (ai-01:CoursIA, 23/09) and the ad-hoc launcher

CoursIA's answer on the #1453 thread: `game_theory_lean` (1) first, since it is already in the
sparse checkout, then `decision_theory_lean` (2), then `knot_lean` (8). `conway_lean` comes
later, after its migration to v4.33.0 (#16341). Budget: at most one pass per hour on :5002,
so the notebook auditor keeps its share. Deliverable per pass, on the workspace-CoursIA
dashboard: target, sorry before/after, duration, provider per role, the proof as text on
success, and the trace path. A failure is reported too, as a measurement.

`count_code_sorry.py` gives one distinct code sorry in `game_theory_lean`:
`RepeatedGames/Folk.lean:544`, `folk_theorem_discounted`. The `_en` mirror carries the same
debt. The file itself marks it a STRETCH (Fudenberg–Maskin, several pages).

That sorry has **no DEMOS entry**, and the harness only targets DEMOS ids. Its files are only
read, so `run_prover_target.py` registers a transient entry in memory, built from the target
file (import block, statement, sorry line), and runs the unmodified `run_prover_bg.main`. The
launcher takes that mode when the first argument is `<file.lean>:<theorem>`:

```bash
bash myia_vllm/scripts/adoption/prover_1453/run_prover_local.sh d:/dev/CoursIA-prover/MyIA.AI.Notebooks/GameTheory/game_theory_lean/RepeatedGames/Folk.lean:folk_theorem_discounted 8 1800
```

The target file is backed up before a pass. A modified file is copied back from that backup,
never restored with `git checkout`.

## Pass 1 — `Folk.lean:folk_theorem_discounted` (2026-09-23, 23:00-23:35Z)

Every role was local and the budget was `max_iter 8, workflow_timeout 1800`.

| Field | Value |
|---|---|
| Result | failure, sorry 1 → 1, 2 iterations, 1 attempt |
| Duration | 2,073.6 s; stopped on the 1,800 s reasoning budget plus 219 s of build credited |
| Trace | `agent_tests/prover/baselines/traces/multi_ADHOC_FOLK_THEOREM_DISCOUNTED_local.json` (33 entries) and a `.spans.jsonl` next to it; local to the clone |

- **About 490 s were lost to an overlap.** The pass started at 23:00Z, together with the
  wrapper test of the notebook runner (7-9 concurrent requests, 300-400 tok/s aggregate,
  about 50 tok/s per stream). The coordinator's first thinking turn went past the harness's
  240 s client cap, and `PROVIDER_MAX_RETRIES["local"] = 1` allows one retry, so the turn
  ended in `APITimeoutError` after about 480 s. The engine was not stuck. From now on,
  prover passes start at **:30**, away from the runner's :05 slot.
- **Search ran without LeanExplore.** `LEANEXPLORE_API_KEY` is not set on ai-01; the main
  clone's `Lean/.env` does not carry it either. `search_mathlib_lemmas` therefore used only
  its built-in dictionary: 12 queries of 0.01 s each. It still surfaced
  `tsum_geometric_of_lt_one`.
- **All tactic attempts failed to build.** Five rewrites failed with 3 to 6 errors each,
  including two 1→2 decompositions. One LOST_PROGRESS veto fired (sorry 1→0 but one error
  outside the sorry). Every change was reverted.
- **Clone hygiene.** The harness's revert rewrote `Folk.lean` with CRLF endings; the content
  was identical (`diff --strip-trailing-cr` is empty), and the LF bytes were copied back from
  the backup. A leftover `Folk.lean.*.sandbox` was moved out of the tree.
  `proof_knowledge.json` carries one learned entry from the demo 0 smoke test (17:11Z),
  which is the harness's own store. Nothing is committed to CoursIA.

## Target triage after `game_theory_lean`

| Project | Toolchain / mathlib | Sorry sites | Verdict |
|---|---|---|---|
| `decision_theory_lean` | v4.33.0 / `db584cd` | 2, both in `Gittins/GittinsTheorem.lean:gittins_optimality` | skip |
| `knot_lean` | v4.33.0 / `db584cd` | `Lidman.lean:81` `unknotting_11n102_upper` (≤ 2) | **pass 2 candidate** |
| `knot_lean` | same | `Lidman.lean:98` (= 2) | out of reach |
| `knot_lean` | same | `Reidemeister.lean:1060` | out of reach |
| `knot_lean` | same | `Conway.lean:3260/3290` | vacuous |

Why each verdict:
- **`gittins_optimality`, skip.** One of its sorries is the *definition* of the value
  operator `V`. That makes the goal most likely `s ≥ s` for a single sorry term, so closing
  it would be a vacuous delta. This is assumed, not compiled. The file itself classifies the
  theorem as INTRINSIC, needing an MDP / optimal-stopping formalization.
- **`unknotting_11n102_upper`, pass 2 candidate.** It is a genuine target: two crossing
  changes plus an explicit `ReidemeisterEquiv` to the unknot, since `unknottingNumber` is
  `sInf {n | UnknottableIn n}`, closed by #15082. It is hard but not vacuous.
- **`Lidman.lean:98`, out of reach.** The lower bound needs Heegaard Floer theory.
- **`Reidemeister.lean:1060`, out of reach.** It is the full Reidemeister theorem.
- **`Conway.lean:3260/3290`, vacuous.** `IsSmoothlySlice` and `IsTopologicallySlice` are
  defined as `Prop := sorry`.

Both v4.33.0 projects share mathlib `db584cd`, so one cache serves them.
`decision_theory_lean` and `knot_lean` were added to the clone's sparse checkout. The
`knot_lean` prebuild (`lake exe cache get` + `lake build`) runs at BelowNormal priority so
it does not compete with the engine for CPU.

## The knot_lean prebuild took Docker Desktop down (2026-09-24)

The prebuild worked: it built 3,023 jobs and finished rc=0 at 01:51:39Z. It also cost a machine-wide
outage. BelowNormal priority caps CPU, not memory, and Lake has no `-j` flag, so the build ran
at full 32-thread parallelism on the Windows host.

| Time (UTC) | Host commit | Event |
|---|---|---|
| 23:31Z | 350.6 GB (88.8 %) | baseline |
| 23:39:56Z | — | prebuild starts |
| 00:11Z | 381.1 GB (96.6 %) | 0.5 GB free physical, 3,698 PageReads/s |
| 00:26:31Z | 385.9 GB (97.8 %) | peak |
| 00:26:10-40Z | — | `com.docker.backend.exe` and the Docker Desktop UI die with no shutdown lines, so every container stops, prod vLLM included |
| 01:23Z → 01:32:25Z | — | `Watchdog-Docker-Desktop-Distro` (hourly) sees the engine DOWN, waits its 8 min grace, relaunches Docker Desktop |
| 01:38:50Z | — | vLLM healthy again (watchdog v5 warm-up grace consumed) |

Sources: `reclaim-wsl-memory.log` (local time), `Docker/log/host/com.docker.backend.exe.log.*`
and `electron-2026-09-24.log` (UTC), and `watchdog-docker-desktop-20260924.log` (local time).
The timing correlation is verified. The mechanism, an allocation failure in the Go backend near
the commit limit, is assumed: no fatal message was captured.

The hourly pre-audit run at 01:05Z fell inside the outage and left one notebook unparsed. It was
retried and delivered at 02:05Z.

Rule going forward: the host's baseline commit is already 88-91 %, so a full Windows-side build
needs the commit checked first (below ~85 %). Prover passes are single-file `lake env lean`
checks and stay within budget.

## Passe 23 — armée le 07/10 (non lancée : marge hôte 88,4 % ≥ 85 %)

**Déclencheur** : fin de passe 22 = le candidat témoin `exact ⟨[0, 1], rfl, by decide⟩` a été
**invalidé** à la re-vérification offline (1500 s, `LEAN_EXIT=124`) : `failed to synthesize
Decidable (ReidemeisterEquiv …)` — **il n'existe pas d'instance `Decidable` sur ce Prop**, donc
un `by decide` nu ne peut pas clore le 3ᵉ composant. Note de cible corrigée par le coordinateur
le 07/10 12:25Z.

**Deux corrections portées dans le lanceur** (`scripts/adoption/prover_1453/run_pass23_unknotting_upper.sh`) :

1. **Forme de fermeture** : passer par l'**organe** — fournir le témoin à `verifyMoves`, clore
   l'équation **Bool** par `decide`/`rfl` (là c'est décidable), convertir par `verifyMoves_sound`
   (`ReidemeisterCombinatorial.lean:235`, contrat :264-268). Le `decide` ne porte QUE sur le
   calcul Bool, **jamais** sur le Prop.
2. **Budget de vérification relevé pour cette cible seule** : `LEAN_LAKE_BUILD_TIMEOUT_S=1800`
   — variable relue à **chaque** appel (`agent_tests/lean_server.py:106-124`, défaut 600),
   donc aucun changement global. Le harnais écrit lui-même la valeur retenue dans la trace
   (`timeout_s = budget`, propagation #18432). Justification de 1800 : en passe 22 l'élaboration
   du fichier courait **encore** > 1500 s (kill externe, LEAN_EXIT=124) **même** avec l'erreur de
   synthèse précoce à :112 — le coût dominant est l'évaluation kernel des littéraux concrets
   (`List.foldl Knot.changeCrossingAt knot_11n102 …` déplie le PD-code 11 croisements) : c'est
   **structurel**, pas un bug harnais. Tout verdict wall-clock à 600 s était donc perdu par
   construction sur cette cible.

**Gate de lancement** (consigne coordinateur 07/10 15:17Z) : marge commit hôte **< 85 %**
(lue à l'instant du lancement, **valeur écrite dans le post de lancement**), fenêtre **:30Z**
(claire du runner nbaudit :05Z). Mesurée à 88,4 % au 07/10 16:47Z → **gel**, pas de lancement.

**Workflow-timeout porté 4200 → 5400 s** : +1200 s de budget de vérification peuvent être
consommés 1 à 2 fois par passe, la passe 22 a déjà couru 6 334 s de mur.

## Passe 23 — EXÉCUTÉE le 08/10 (00:30Z → 03:19:54Z) : ÉCHEC, mais le blocage est NOMMÉ

**Résultat brut** (`pass23.log`, harnais `run_prover_target.py` → `run_prover_bg`) :

| Mesure | Valeur |
|---|---|
| Prébuild `+Knots.Lidman +Knots.Slice` | rc=0, 22:48:06Z → 23:39:33Z (~51 min) |
| Fenêtre :30Z | atteinte 00:30:00Z (attente 3027 s) |
| `RESULT` | **FAILED** — `Sorry: 2 -> 2`, `Total time: 8385.8s` (2 h 20) |
| `DELTA` / `ATTEMPTS` / `ITERATIONS` | 0 / 0 / 3 |
| `FREEZE_LOOP` / `CALIBRATION` / `SUCCESS` | False / False / False |
| `TRUE_PLACEHOLDER` avant/après | **0 / 0** (fichier et log) |
| Cible restaurée | **byte-identique** au backup `Lidman.lean.pre-pass23` (seul écart : LF→CRLF, corrigé) |

**Cause de l'abandon** : `Workflow reasoning-budget timeout (5400s reasoning; 0s build credited)`
— l'agent a consommé **tout** le budget de raisonnement sans émettre une seule tactique qui
compile (`ATTEMPTS 0`). Le garde-fou de régression a ensuite joué : build-aware sorry **3 > 2**
(1 `sorry` implicite via `apply?`/`exact?`/`solve_by_elim`) → `REGRESSED` → **retour à l'état
d'entrée** (#1453 iter-3 guard), puis `SAME_COUNT_ZERO_VERIFIED`. Le harnais n'a donc **rien
persisté**, ce qui est le comportement voulu.

### ⚠️ Le vrai livrable : le chemin de clôture désigné est INIMPLÉMENTABLE (vérifié au source)

L'agent a conclu de lui-même « **Blocage confirmé : le chemin `verifyMoves_sound` est mort** »
(~+2938 s). J'ai vérifié ce claim **au source**, et il est **exact sur le fond** :

- `ReidemeisterCombinatorial.lean:166-172` — `oneStepWitnesses` **retourne `[]`** (squelette
  assumé : « la liste exhaustive des successeurs à 1 mouvement n'est pas énumérée ici (PR2+) »).
- D'où `verifyMoves n d₁ d₂ ≡ decide (d₁ = d₂) || [].any …` = **`decide (d₁ = d₂)`**.
  L'organe ne certifie donc **que l'égalité réflexive** (n=0). Pour n=2 sur un diagramme
  distinct de `unknotDiagram`, il rend **`false` par construction**.
- `verifyMoves_sound` (:235) est **prouvé** — mais **vacuous** : son induction consomme
  `oneStepWitnesses_sound` (:231), elle-même triviale par `List.not_mem_nil` sur une liste vide.
  Les deux théorèmes sont vrais et sans contenu.

**Conséquence** : la forme de fermeture de la note corrigée (« fournir le témoin à `verifyMoves`,
clore l'équation Bool par `decide` ») est **inimplémentable** — le `decide` porterait sur
`false = true`. La prémisse du docstring de `Lidman.lean` (« ce `sorry` est résoluble en condition
par l'organe natif ») est **fausse pour le cas 2 changements** tant que `oneStepWitnesses = []`.

**Ce n'est donc pas un mur de recherche, c'est un trou de bibliothèque** : la passe 22 avait buté
sur l'absence d'instance `Decidable` sur le Prop ; la passe 23 montre que le repli sur l'organe
ne mène nulle part, l'organe étant incomplet. **Une 4ᵉ passe avec une meilleure note ne peut pas
aboutir** : le prérequis est d'implémenter l'énumération réelle des témoins à 1 mouvement
(le « mur PR2+ » documenté l.221-222), travail de bibliothèque distinct d'un run de harnais.

**Leçon (à mon endroit)** : la note corrigée venait du coordinateur et s'appuyait sur la
docstring ; je l'ai armée **sans lire la définition de `oneStepWitnesses`**. La docstring décrivait
l'intention, pas l'état du code. Vérifier l'organe au source **avant** d'en faire le chemin de
clôture d'une passe — la docstring n'est pas une preuve d'implantation.

---

## CLÔTURE (ai-01:CoursIA, 08/10 09:12Z, DM `msg-20261008T071253-h3y6wx`)

Le coordinateur **confirme le diagnostic sur main courant** : `oneStepWitnesses` retourne `[]`
(`ReidemeisterCombinatorial.lean:166-172`), donc `verifyMoves_sound` est **vacuous**. Décisions :

1. **Tâche bibliothèque ouverte : #19890** — énumération R1/R2/R3, soundness **non vacuous**,
   témoin positif `verifyMoves 1` sur deux diagrammes distincts.
2. **ARRÊTER les passes sur ce lemme.** Aucune branche ni PR ne le remplit aujourd'hui → une
   4ᵉ passe échouerait à l'identique. Le harnais n'a plus rien à moudre ici.
3. **Reprise** : le coordinateur **prévient ai-01:vllm au merge de #19890** (réouverture de la
   voie de clôture = `oneStepWitnesses` réellement énuméré).

**Statut de la lane vllm sur #1453 : EN ATTENTE de #19890 — aucune passe armée, aucun geste
programmé.** Le `sorry` de `Lidman.lean:112` reste en place, fichier intact (LF, restauré depuis
`Lidman.lean.pre-pass23`). Le résultat utile de la passe 23 n'est pas une preuve mais un
**diagnostic structurel** : le blocage est un trou de bibliothèque nommé, chiffré, et routé.

*Reconnaissance du coordinateur (verbatim) : « Ton diagnostic a lu le code et pas la docstring :
c'est exactement ce qu'il fallait. »*
