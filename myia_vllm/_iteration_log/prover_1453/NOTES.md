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
