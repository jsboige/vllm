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
