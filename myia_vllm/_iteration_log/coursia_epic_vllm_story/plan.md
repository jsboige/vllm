# CoursIA Epic #4427 — chapitre "fork vLLM" (instance #5)

> Working/continuity doc for the multi-session, 12h-cron task: write & publish the
> vLLM fork's hosting story into the CoursIA Epic **#4427** ("MAJ des séries par les
> agents depuis leur workspace/expérience — gouvernance ai-01").
> Cron job: **cebc222b** (every 12h :23, session-only, auto-expires 7 days).
> State lives here + in memory `[[project-coursia-epic-vllm-story]]`.

## Epic #4427 governance pipeline (MUST follow, in order)
1. **Proposition** — post approach + plan rédactionnel on CoursIA dashboard (workspace) [+ optional mission journal].
2. **User validation BEFORE writing** — present plan to sponsor (jsboige). NO speculative redaction.
3. **Worktree dédié** — branch `docs/<sujet>` in the CoursIA repo (D:\CoursIA), isolated from Lean/notebook work branches.
4. **Écriture progressive** — milestones on dashboard; FR-first; pedagogical; CATALOG-STATUS markers UNCHANGED.
5. **PR atomique** — one verifiable subject per PR (G.4); review + merge by ai-01.
6. **Coordination** — scope boundaries decided by ai-01; NO coordination files in the CoursIA repo (dashboard only → my working draft stays in the vllm workspace, i.e. THIS file).

Existing instances: #1 Claw-Systems (Hermes, #4428), #2 Qdrant (#4432), #3 Playwright-OWUI (#4433), #4 Claudish (#4445). Ours = the **vLLM serving backend** that hosts the course's local LLMs.

## STATE TRACKER (update every session)
- [x] Cron armed (cebc222b, 12h)
- [x] Read Epic #4427 (body, 0 comments) + GenAI structure (README/INDEX)
- [x] Git archaeology of the fork (timeline below)
- [x] **User validated** (2026-06-28): placement = `GenAI/Texte/`, format = récit markdown FR-first
- [x] Proposition posted to CoursIA dashboard (PROPOSAL+ASK @ai-01) 2026-06-28 — awaiting ai-01 bless of placement/scope before touching the CoursIA repo
- [x] **Full récit draft written** (2026-06-29, cron fire #2) — `recit-draft.md` in THIS folder, vllm-side, 7 sections FR-first ~repo-chapter length. Section 6 batch-ceiling claim corrected against verified memory (P28 not P72; candidate fix `GENESIS_PREALLOC_TOKEN_BUDGET=8192` is NOT runtime-validated → "4096 reste le plafond effectif"). No secrets/API keys. Sandermage Genesis credited.
- [x] **Proposition RE-SURFACED 2026-06-29** — the original (06-28) was archived without summary by the CoursIA dashboard's FALLBACK TRUNCATION at 05:11Z (vLLM itself was down during the outage → condensation connection-error → 11 msgs dumped to `archive/workspace-CoursIA-2026-06-29T05-11-38-fallback.md`). ai-01 never registered it (not in dashboard "Plans Rédactionnels"). Re-posted concise PROPOSAL+ASK @ai-01 now that vLLM+cluster are back.
- [x] **ai-01 GO received 2026-06-29 10:05Z** (msg `msg-20260629T080509-0b07d6`). Decisions: placement = **`GenAI/Texte/LLMs-Locaux-Serving/`** (dedicated subfolder, the alternative I offered — NOT loose in Texte/ root); instance #5 CONFIRMED, tracker issue **#4601** `[#4427] Doc vLLM` opened (journal there, mirror siblings); GO worktree `docs/vllm-story` + 1 atomic PR → ai-01 reviews/merges. **HARD guardrails**: FR-first · CATALOG-STATUS byte-identical to main (don't regen) · 0 secrets, genericize endpoints/IPs/hostnames/ports to placeholders · Sandermage credited (author+source+date) · no emojis · rebase fresh on origin/main · ping ai-01 at PR ready.
- Sibling format (mirror Claudish #4445 = closest analog): subfolder with `README.md` chapeau (title+tagline, breadcrumb `[← Texte](../README.md)`, bold intro, `> **Sources**` blockquote, "Pourquoi", ecosystem table, Documentation table, "Leçon fondatrice", italic footer) + `docs/*.md` narrative + optional `configs/*.example`. Path: `D:\CoursIA\MyIA.AI.Notebooks\GenAI\Texte\LLMs-Locaux-Serving\`.
- [x] Draft genericized (line 25 endpoint → `*.<domaine-interne>` / `https://<endpoint-medium>/v1`, port dropped). Only 1 sensitive line existed.
- [x] **Worktree `docs/vllm-story`** (D:\CoursIA, off fresh origin/main `6e4cff3e8`, 0 ahead/behind) → wrote `README.md` chapeau (mirrors Claudish) + `docs/journal-de-bord.md` (7-section récit). Only the new subfolder is untracked → catalog/COURSE_CATALOG/Texte-README byte-identical to main (verified `git status --porcelain`). Commit `86866c6b6` (2 files, 169 insertions, Co-Authored-By trailer).
- [x] **Atomic PR opened 2026-06-29: [jsboige/CoursIA#4602](https://github.com/jsboige/CoursIA/pull/4602)** → ai-01 pinged 3 ways: (a) reply on GO thread `msg-20260629T083111-xa2xiw`, (b) CoursIA workspace dashboard append w/ @ai-01 mention, (c) tracker #4601 comment `issuecomment-4830471153`. vllm workspace dashboard INFO note posted.
- [x] **MERGED 2026-06-29: PR #4602 squash-merged into `main`.** Files live on origin/main (verified `git ls-tree -r`). CI all green (Gitleaks, Catalog Guard/Drift, Docs Link Check, CodeQL, Regression Guard). Review = NanoClaw LGTM (2 reviews 82s apart = TOCTOU cron duplicate, single effective verdict; external sources verified real). **2 non-blocking nits** noted, not fixed (PR merged with them): (1) §5 "saturait vers 5" = 5 concurrent USERS not 5 tok/s (1-word clarif possible as optional follow-up — offered to ai-01); (2) Sandermage repo renamed `genesis-vllm-patches → sndr_core_engine` (URL redirects, link live).
- [x] **FINALIZED 2026-06-29**: [DONE] on both dashboards (CoursIA + vllm), tracker #4601 DONE comment `issuecomment-4831673453`, ai-01 ACK reply `msg-20260629T105542-bm8asa`. **CronDelete cebc222b done.** Memory marked DONE. Worktree cleanup pending below.

## ✅ TASK COMPLETE (2026-06-29)
Instance #5 of Epic #4427 delivered, merged, reported. Cron deleted. Only open thread: optional 1-word §5 clarification (awaiting ai-01 nod, non-blocking). #4601 closure is ai-01's governance call.

## Proposed placement (PENDING user/ai-01 confirmation)
**Recommendation: `MyIA.AI.Notebooks/GenAI/Texte/`** — Texte already covers "LLMs locaux + patterns de production", and our endpoint literally serves the course's local model (`qwen3.6-35b-a3b` at `api.medium.text-generation-webui.myia.io`, used by the Texte local-LLM notebooks + Roo/Claude Code integration). A narrative chapter on self-hosting production LLMs slots in cleanly.
Alternatives: `00-GenAI-Environment/` (infra/ops) · `Vibe-Coding/` (backend behind local coding assistants) · new `Infrastructure/` subfolder. ai-01 arbitrates final scope.

## Proposed format (PENDING)
**Recommendation: narrative markdown chapter (FR-first)** — matches the other Epic instances' README-style additions; the deliverable is literally "une histoire". Optional companion notebook later (connect to the live local endpoint + a mini benchmark).

## Proposed narrative outline (the "story")
1. **Le décor** — 3× RTX 4090 (72 GB), objectif : endpoints OpenAI-compat auto-hébergés pour la classe + Roo/Claude Code via reverse proxy `*.text-generation-webui.myia.io`.
2. **Origines & incident** — fork vLLM (2025-05), missions Roo 1-20, l'incident APT (2025-09) + récupération sécurité, grid-search (chunked_only_safe, ×3.22 KV cache).
3. **La valse des modèles** — Coder-Next (PP=3 bubbles, 5 tok/s) → GLM-4.7-Flash (3.3×) → Qwen3.5 → Qwen3.6-35B-A3B ; GPU 2 vision : ZwZ-8B → OmniCoder-9B. Le cimetière des rejetés (Dense 27B, GPTQ-Int4, BNB NF4, distill v2, NVFP4-sur-Ada).
4. **Les batailles d'ingénierie** — quantization (AWQ/GPTQ/FP8/NVFP4), KV cache (FP8 → TurboQuant ×6.3), CUDA graphs vs enforce-eager (3-4×), Marlin MoE OOM (gpu-util 0.85), sampling anti-répétition (presence_penalty 1.5).
5. **La saga TurboQuant → Genesis** — pourquoi (multi-user long-context = KV capacity), upstream bloqué (#41726/#40798), Option B downstream (Sandermage Genesis P22/P38), la nuit v2a→v2g (FlashInfer sampler trap), promotion baseline.
6. **Les impasses documentées** — spec-decode DFlash+MTP (4 attempts/4 crashes, 2 upstream datapoints postés), plafond batch 4096 (couplage buffer P28), discipline verify-before-propagating.
7. **Ce que ça enseigne** — un endpoint LLM de prod auto-hébergé = arbitrage permanent débit/contexte/qualité/VRAM ; documenter les échecs vaut autant que les succès ; contribuer upstream + adopter un patch tree downstream.

## Git archaeology timeline (raw material — 110 commits on myia_vllm, 2025-05 → 2026-06)
- 2025-05-04 fork base (upstream vLLM)
- 2025-08-05 commit-history archeology index (forensic)
- 2025-09-30 **Post-APT consolidation** — security recovery + architecture cleanup
- 2025-10-22 grid-search: chunked_only_safe **×3.22 KV cache**; 4 permanent guides (deploy/optim/troubleshoot/maintenance)
- 2025-10-26 Missions 16-20: Qwen3-VL-32B vision research, reorg → myia_vllm
- 2026-02-03 consolidate myia-vllm → myia_vllm + FP8 missions
- 2026-02-04 **Qwen3-Coder-Next** (Mission 22) — PP=3 pipeline bubbles, 5-6 tok/s → rejected
- 2026-02-05 **GLM-4.7-Flash** replaces Coder-Next, **3.3× throughput**
- 2026-02-09 llama.cpp vs vLLM A/B; micro/mini GPU-2 profiles
- 2026-02-16 **ZwZ-8B** vision (GPU 2), archive GLM-4.6V
- 2026-02-25 **Qwen3.5-35B-A3B MoE** production (Dense 27B rejected)
- 2026-03-03 **GPTQ-Int4 rejected** (missing RTX 4090 kernel autotune)
- 2026-03-08..22 sampling calibration (presence_penalty, 8 OWUI profiles)
- 2026-03-18 Orpheus 3B FR TTS; ZwZ shared-GPU
- 2026-03-25..28 **OmniCoder-9B** (GPU 2) replaces ZwZ (MME 1258.5, MMStar 58.5%)
- 2026-04-17 **Qwen3.6-35B-A3B MoE** (from 3.5)
- 2026-04-18 quality benchmarks (GSM8K 87.6, IFEval 87.6, MMStar 55.7, tool 83.3%)
- 2026-04-19 shm_broadcast deadlock workaround (--gdn-prefill-backend triton)
- 2026-04-24 **shm_broadcast PyCFunction patch** (vllm#35104); DFlash empirical eval
- 2026-04-30 archive OmniCoder → **free GPU 2 for CoursIA trainings**
- 2026-05-06 **27B Dense + TurboQuant K8V4 cutover → rollback** (all 3 thresholds tripped); MoE+TQ crash (#41726)
- 2026-05-16 **Genesis Option B** build; v2a→v2d→v2e→v2f(rollback)→**v2g PASS** (VLLM_USE_FLASHINFER_SAMPLER=0) — one night
- 2026-05-17 **promote Genesis-TQ v2g baseline** (×6.3 KV, N=16 → 829 tok/s)
- 2026-05-18 retire DFlash + MTP (4 attempts/4 crashes); upstream datapoints posted
- 2026-05-26 watchdog tuning + batch-ceiling doc
- 2026-06-24 batch 8192 attempt → **revert** (P28 buffer coupling; verify-before-propagating lesson)

## Sources to mine when writing
- d:\vllm\CLAUDE.md (full deployment history, per-model specs, benchmarks)
- MEMORY.md + topic files (project_*.md): turboquant, genesis batch ceiling, dflash, spec-dec retired, qwen36 benchmarks
- d:\vllm\myia_vllm\_iteration_log\ (genesis_tq_night_log.md, dflash_v2g_attempt{1,2,3}, fp8_mtp_attempt4)
- archives/2026/ (the rejected configs)
- git log -- myia_vllm (dates, commit messages)
