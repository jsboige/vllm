# Notebook audit on the local model through sk-agent — pilots 1-2 (2026-09-22)

User mandate (22/09 ~21:00Z): scale the use of the local Qwen3.6 through sk-agent with a
dedicated, tooled agent (desktop-commander, jupyter-papermill, searxng) able to run
scheduled audits like the ones Hermes and NanoClaw run on CoursIA — at about half of our
capacity, with a light harness — and answer how it should be scheduled, what to do about
timeouts, whether it becomes a turnkey pre-audit service for the bots, and whether an
ad-hoc loop with claims is the right shape. If the audit is conclusive, part of the fleet
could move to corrective mode.

Context found on GitHub:

- **CoursIA #17073** — the campaign: 1343 notebooks, one issue per series
  (`[Audit #17073] Série …`, checklist + `paths:` claims), Hermes (po-2026, cron :35) and
  NanoClaw (ai-01, cron :05), one notebook per hour each (48/day for both). Organs
  (`scripts/notebook_tools/check_*.py`, 6 mandatory) run before any finding. The bots'
  own **"Inventaire capacités manquantes"** (20/09 23:09Z and 23:17Z comments) lists what
  they lack: (1) a runtime to execute the organs, (2) a kernel to execute notebooks,
  (3) figure rendering, (4) GraphQL quota. NanoClaw still wrote "artefact organes ai-01
  toujours absent de #17073" on every 22/09 cycle.
- **roo-extensions #2404** — umbrella "Haiku-task offloading via vLLM qwen3.6"; its
  Track C is exactly this pattern (scheduled task → script → `sk-agent.call_agent` →
  result file), acceptance ≥3 scheduled CoursIA tasks. Stale since 09-07.
- **roo-extensions #1748** (sk-agent tooling uplift: "21/25 agents have no tool, no
  file/exec MCP"), #1587 (review exec tier), #3408 (capability profiles, closed).

## What was built

| Piece | Where | Note |
|---|---|---|
| Agent `notebook-auditor` | local `sk_agent_config.json` (gitignored — holds inline keys); sanitized copy `nb_audit/agent_entry.example.json` | Qwen3.6 (vision+thinking), MCPs `desktop_commander` (npx `@wonderwhy-er/desktop-commander`, risk `exec`, caps shell+repo_read), `jupyter_papermill` (mcp-jupyter conda env, risk `exec`, cap repl), `searxng`; memory off; system prompt = `auditor_system_prompt.md` |
| Driver | `myia_vllm/scripts/adoption/nb_audit/nb_audit_driver.py` | notebook view (cells with ids, outputs clipped, figures extracted), series context, 6-organ pass, stages A/B/C, mechanical validation, ledger, resume, crash isolation |
| Prompt | `myia_vllm/scripts/adoption/nb_audit/auditor_system_prompt.md` | 4 passes (prose↔outputs, exercises, structure, series), 2 rounds, 4-field finding format, #17073 classes and exclusions, read-only on GitHub |
| One-shot CLI | `myia_vllm/scripts/adoption/nb_audit/sk_call.py` | `call_agent` smoke tests |

Audit checkout: `d:/dev/CoursIA-skaudit` (own clone, other lanes' clones untouched).
Everything is **dry**: nothing written to GitHub, findings land in local JSON.

## Pilot 1 — single call, tools optional (21:21→21:31Z, 11 notebooks, concurrency 4)

The 11 notebooks are the last ones the bots audited on 22/09 (Z3-08/09/10, Sudoku-07,
rl_11, GT-16d/16e/18b/19/21/24; 25 bot findings as reference).

- 9/11 parsed; 2 **empty responses** (Z3-08, Z3-10). Zero tool calls on both, so not the
  Semantic Kernel 5-round auto-invoke cap.
- **The model did not verify**: 12 tool calls in total, all on one notebook; on the other
  8 it wrote "les dénombrements … sont exacts" without executing anything.
- The validator rejected 3 findings that were **exact matches of bot findings**
  (GT-16d double-counted chains, GT-24 A3 misclassification, Sudoku-07 template
  placeholder): cell cited by index instead of id, markdown `*`/`` ` `` dropped by the
  model, extract attributed to the neighbouring cell. Fixed: index→id resolution,
  emphasis-insensitive matching, attribution repaired when the verbatim text lives in
  exactly another cell (`relocated-to`).
- A fixed script path in the prompt made concurrent audits overwrite each other's check
  script. Fixed: one work directory per notebook.

## Pilot 2 — the harness executes the checks (21:41→21:57Z, concurrency 6)

Stage A: read + candidates + one Python script per checkable claim. Stage B: the driver
runs the scripts (system Python: numpy, scipy, networkx, z3, pandas). Stage C: same
conversation (prefix-cached), the model keeps what the outputs confirm. One retry on an
empty answer.

| Notebook | Bots | Ours (valid) | Same defect as bots | Extras, my triage |
|---|---:|---:|---:|---|
| Z3-08 | 2 | 1 | 1 (deadline exercise inactive, V2: J0 ends at 6 < 7) | — |
| Z3-09 | 3 | 1 | 0 | "solution-leak" on a hint — likely FP |
| Z3-10 | 4 | 2 | 2 ("il manque le 4" false; ABC×D=DBC is `unsat`) | — |
| Sudoku-07 | 3 | 4 | 3 (exercise vs stub, template placeholder, summary 2.1 vs 3.30 ms) | "puzzle fourni déjà résolu" — input has 49 blanks: **likely TP** |
| rl_11 | 4 | 2 | 1 (≈0.909 threshold reading, same cells as bot F2) | trajectory reading vs seed-42 path — uncertain |
| GT-16d | 5 | 1 | 0 | exercise "unique max cycle" — likely FP |
| GT-16e | 1 | 0 | 0 | — |
| GT-18b | 0 | 2 | — | "couplés dans les deux sens" while `u1` has `0.0 * y`: **likely TP**; `2/delta` = the bot's own unfiled minor |
| GT-19 | 0 | 0 | — | clean on both sides, 2 values re-derived MATCH |
| GT-21 | 1 | 1 | 0 | LWSS (2,0) vs (0,-2) is a rotation — likely FP |
| GT-24 | 2 | 1 | 1 (A3 misclassification) | — |
| **Total** | **25** | **15** | **8 (32 % of bot findings)** | 2 likely TP, 2 debatable, 3 likely FP |

- 11/11 parsed, 20/21 verification scripts ran clean (the failure: `pulp` not installed).
  One empty stage-A answer (Z3-09) recovered by the retry.
- Precision against my reading: 10/15 likely true (8 shared + 2), 3/15 likely false.
  The campaign's own reference figure is ~60 % FP for an unassisted automatic auditor.
- Recall is concentrated where a script can decide: 5 of the 8 shared findings are
  verified computations. Misses are mostly structural (navigation links, headers after
  content, fabricated references) and multi-step re-derivations (rl_11 5-listen policy).
- Timing: stage A median 188 s (max 272), stage C median 48 s (max 170), per notebook
  median 230 s (max 398). 9 notebooks in 10.7 min at concurrency 6 ≈ **50 notebooks/h**
  against 2/h for both bots together.
- Prod stayed healthy under the load: health 200, RC=0, watchdog decode probes OK.

Caveats: 11 notebooks is a small sample; the bot findings are a reference, not ground
truth; the triage of extras is mine, from reading the cells.

### Re-run of GT-16d with the verification venv (22/09 ~22:10Z, one notebook, one run)

GT-16d was the notebook where pilot 2's V3 failed on the missing `pulp`. Re-run alone
with the venv: 217 s (A 154 s, C 61 s), 3/3 scripts clean, 2 valid findings, both
matching the bots — the chain double-counting (bot F2, confirmed by V3:
`matchings_bruts=10, receveurs_uniques=3`) and the |V|=30/100 experiments announced but
never run (part of bot F3). Pilot 2 had 0/5 on this notebook plus one likely FP. One run
on one notebook is not a measurement of the venv's effect — the model's sampling alone
could explain it — but the missing library is no longer a failure mode.

### Figures attached to stage A (22/09 ~22:15Z, rl_11 + Z3-08, concurrency 2)

The driver now sends the committed figures to the model's vision (sk-agent `attachment`
as a JSON list, notebook order, at most 4: the prod's `--limit-mm-per-prompt`), and names
them in the prompt as `<cell id>_<output n°>`. Both notebooks went through end to end:
2/2 parsed, 2/2 scripts clean, 1 valid finding each.

- rl_11 (2 figures): exercise 2 promises N*=1 at P=0.85, contradicted by the committed
  baselines — the same statement as bot F3 (the bot measured N*=5; our script compared
  N=0 and N=1). Pilot 2 had matched bot F2 on this notebook instead: two samples hit two
  different bot findings, which argues for the union of 2 runs per notebook.
- Z3-08 (1 figure): the "anatomy" table counts 6 domain bounds while `solve_jobshop` adds
  two per operation (12). Not in the bot audit; checked against the code: likely true,
  minor.
- No figure finding. Hermes had checked the rl_11 figure visually and found it
  consistent; the model's answer never mentions the figures, so this run does not show
  that it looked at them.
- **rl_11 stage A took 277.6 s** with 2 images, 22 s short of sk-agent's 300 s per-turn
  limit. Images make that limit tighter.

## Timeouts — the chain, measured

| Layer | Value | Effect |
|---|---|---|
| sk-agent model client | `AsyncOpenAI(timeout=300, max_retries=1)`, hardcoded (`sk_agent.py:456-461`, roo-extensions `cac965dcc5`) | one LLM turn > 300 s is cancelled and **silently regenerated once** |
| SK auto-invoke | 5 rounds (`DEFAULT_MAX_AUTO_INVOKE_ATTEMPTS`), then one final call without tools | not binding here (stage A has no tool call) |
| `max_tokens` | 16384 per turn (agent spec) | a turn whose reasoning uses it all returns empty content; the observed empty answers were not budget-bound (Z3-09: 127 s), cause open |
| `call_agent` | `timeout` 1500 s (driver) | per stage |
| MCP client | `timeout + 120` s (driver) | transport guard |

The binding one for scaling is the 300 s per turn: stage A already peaks at 272 s at
concurrency 6. At 8 streams it will start timing out. vLLM v0.30.0 accepts
`thinking_token_budget` (verified on prod; it ends reasoning after N tokens, and the model
continues in the content) but sk-agent has no passthrough. Two small sk-agent changes
would lift it: a per-model `request_timeout_s`, and `thinking_token_budget` in the agent
sampling spec. Owner = roo-extensions (sk-agent code); proposed on the global dashboard,
not patched here.

## Answers to the scheduling questions

**No Claude upstream per notebook.** The loop is the deterministic driver: it picks the
next notebook (series-issue checklists minus the local ledger), posts the `paths:` claim
itself, runs A/B/C, validates mechanically, records the result. The model never touches
GitHub. A Claude session (the 6 h surveillance cycle) supervises: it reads the ledger
counters, samples findings for precision, and handles anomalies. A generic prompt asking
the model to find its own state in the issue would spend the local model's weakest skill
(multi-step tool use, shown in pilot 1) on work that 20 lines of Python do exactly.

**Runner:** a user-level scheduled task (no elevation needed, but schtasks falls under the
UAC/dry-run rule: dry-run posted on the dashboard before registering), hourly, each run
auditing a batch of K notebooks at concurrency C and exiting. No long-lived process to
babysit. The ledger and the per-notebook JSON are the checkpoint: a killed batch resumes
at the next notebook (implemented: `parsed` records are skipped). A lock file prevents
overlapping batches.

**Capacity:** "half of our capacity" ≈ 8 concurrent streams of the N=16 envelope. At
concurrency 6 we measured ~50 notebooks/h; the whole catalogue is a day of machine time.
Going to 8 needs the per-turn timeout fix above.

**Turnkey pre-audit for Hermes/NanoClaw:** the value is in the driver, not in a bare
`call_agent`. Exposing only the agent (sk-agent streamable-http :8100 with its API key)
would hand the bots the model without the view, the organs, the executed checks and the
validation. The better contract is a **pre-audit record per notebook** (organ pass +
candidates + scripts + their outputs + validated findings) that the bot of that series
reads in its hourly cycle, then judges and posts under its usual protocol. That covers
gaps 1-3 of their inventory. The deterministic part (the 6-organ pass over the
catalogue) is exactly the "artefact organes ai-01" NanoClaw has been waiting for since
20/09. It costs no GPU and could ship first.

**Corrective mode:** not yet. A 32 % overlap with 3 likely FP in 15 is good enough to
pre-chew, not to repair unattended. The next measurement that would justify it: a
precision sample judged by the bots or the coordinator on a few hundred notebooks.

## Open items

- ~~Verification environment~~ done 22/09: dedicated venv
  `%LOCALAPPDATA%\nbaudit\verif-venv` (numpy, scipy, networkx, pandas, z3, matplotlib,
  sympy, pulp + CBC), picked by default through `--verif-python`; organs keep the system
  Python, which stays untouched.
- ~~Figures~~ sent since 22/09 (`--max-figures`, default 4). Whether the model actually
  checks them against the prose is not shown yet: needs a notebook with a known figure defect.
- Mechanical organ candidates seen in the misses: navigation "next →" pointing backwards
  (2 instances in Z3 already reported by the bots) — an organ, not an LLM finding.
- Recall: sample 2 runs per notebook and union the validated findings. We have the
  spare capacity for it.
- ~~Posting and claims on #17073 wait for the coordinator's arbitration~~ answered
  23/09: pre-audit records, see the next section.

## Readers' verdict (2026-09-23): (b) pre-audit records

Asked on the global dashboard (11:12Z) as the user requested. NanoClaw (11:17Z) and
ai-01:CoursIA (11:21Z) both chose **(b)**; Hermes had not answered at the time of writing.

- **Why not a third partition (a):** at 8/25 recall, a notebook "audited locally" would
  leave ~2/3 of the defects undetected and add ~1/3 of doubtful findings to the pool.
  CoursIA's `audit-reassessment.md` (HARD) already requires every automated finding to be
  re-verified before a fix. NanoClaw's condition for (a): raise recall first, e.g. few-shot
  on the 17 missed findings.
- **What the record buys the bots:** not reading time (their FULL READ is mandatory
  whatever they are given) but decision time: they judge on an executed argument
  instead of re-deriving by hand. NanoClaw has no Python at its seat, so the harness
  executing the script covers part of its real gap.
- **Record format (JSON per notebook):**
  - for each finding: cell id, verbatim extract, the **whole** verification script and its
    raw output;
  - the **fingerprint of the audited file** (sha256, commit, date). Without it the record
    goes stale at the next corrective push and fakes a divergence incident (#17167).
  - Never "verified by the harness" alone: a self-generated (script, output) pair can be
    self-consistent and wrong.
- **Where records land:** outside the CoursIA tree (CoursIA rule §A). They go to this
  `_iteration_log` or to a shared GDrive path, with at most a pointer per series on
  #17073. Findings reach GitHub only once a bot's FULL READ confirms them, under that
  bot's signature; the local auditor never posts.
- **Continuation criterion (CoursIA):** on the first 3 series, count the pre-audit
  findings confirmed by FULL READ, and the FULL READ time per notebook with and without
  a record. If confirmation stays around 1/3 and FULL READ does not get shorter, stop.

Driver changes on 23/09 (no model call needed; smoke-tested offline on a real CoursIA
notebook):
- each verification result keeps its full `code` and the size of the raw output
  (`output_chars`), since the stored output is only its tail;
- each record carries `fingerprint` {sha256, head, last_commit, last_commit_date, dirty};
- each finding gets `verif_ids`, resolved from its free-text `verification` field against
  the scripts that actually ran.

Still gated: the 300 s per-turn timeout (roo-extensions ticket, which the user must
approve in the roo-extensions registry), then the user's GO for a scheduled runner.

## Scheduled runner (2026-09-23): built, not armed

Hermes (12:05Z) chose (b) too, so all three readers agree. Hermes added two conditions,
both now met: the record keeps each script's **exit code and stderr apart from stdout**
(`rc`, `stdout_tail`, `stderr_tail`), because a script that dies quietly must not pass
for one that ran clean; and the fingerprint is a prerequisite. A script can only be
replayed against the fingerprinted HEAD.

User decision, 23/09: « OK pour les 2 si c'est bien cadré avec les consommateurs de ce
travail ». The two are the sk-agent timeout (roo-extensions #3797) and the runner.

`scripts/adoption/nb_audit/nb_audit_runner.py` runs one bounded batch per call. It:
- fast-forwards the read-only CoursIA clone (it refuses to run on a dirty clone);
- reads the checklists of the given #17073 series issues through `gh`, read-only
  (items with or without backticks);
- keeps the unchecked notebooks, in checklist order;
- skips any notebook whose current sha256 already has a published record;
- runs the driver in a per-run out dir, so the driver's resume cannot serve a stale
  record;
- scans each record for credential-like patterns, and withholds it on a hit;
- publishes the record to `<landing>/<issue>-<series>/` with an `index.json`: owner bot,
  fingerprint, verdict, counts.

A lock file (3 h staleness) prevents overlapping runs. `--dry-run` selects and prints,
and never calls the model. A dry run on 17107 (GameTheory, NanoClaw), 17239 (Sudoku,
Hermes) and 17357 (Lean, Hermes) picked 3 notebooks per series.

Still to settle with the readers before the first real run: how each bot reads the
landing dir, which notebooks come first (checklist order or its own queue), and how it
reports confirmed/rejected counts and FULL READ time for the stop criterion.
Concurrency stays at 4 until #3797 lifts the 300 s per-turn ceiling.

Raw outputs (per-notebook JSON, ledgers, run logs) were kept in the session scratchpad.
`ledger_pilot1.jsonl` and `ledger_pilot2.jsonl` are copied next to this file.
