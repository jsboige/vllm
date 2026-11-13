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
2. `notebook-coder` agent entry in sk-agent config — **roo-extensions adds it** (ask via dashboard,
   spec = §3.1; same flow as #4712).
3. Pilot issue agreed with the CoursIA coordinator (their repo, their review load) — sandbox branch
   first, PR only when the coordinator and the user GO.
4. Capacity-gate call wired (after the 24 h probe observation started 13/11 21:13Z).

## 5. Guardrails carried over

- CoursIA repo = another workspace's infra: **ask, don't apply** — the pilot PR needs their GO;
  the driver never force-pushes, works on a fresh branch, one issue at a time.
- REST only on GitHub (GraphQL bucket is fleet-shared), `gh api user` checked before writes.
- No secrets in cells/commits; scratch stays in gitignored `.tmp/`.
- The verifier is a **different agent instance** from the builder, and it compares against the
  **source** (the issue spec + the notebook), never against the builder's claims.
