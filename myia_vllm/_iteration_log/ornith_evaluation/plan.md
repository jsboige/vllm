# Ornith-1.0-35B evaluation — candidate swap for Qwen3.6-35B-A3B

> Working/continuity doc for the 12h-cron task: evaluate switching prod from
> `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` to **DeepReinforce `Ornith-1.0-35B`**
> (agentic-coding RL fine-tune). Paced one crank/session. State here + memory
> `[[project-ornith-evaluation]]`. **Prod is NOT touched without local benchmarks
> + user/ai-01 sign-off** (outward-facing change).
> Started 2026-07-01 (user jsboige asked to look at the opportunity).

## TL;DR verdict so far (session 1, 2026-07-01) — STRONG CANDIDATE, verify before switch
Architecturally a **drop-in** for our stack; vendor claims big agentic-coding gains over the very Qwen3.6 we run. Worth a serious local eval. NOT a switch-now (vendor benchmarks unverified; base is 3.5 not 3.6 → must check non-coding regression).

## Ground truth — config.json (VERIFIED via raw fetch)
- `architectures: ["Qwen3_5MoeForConditionalGeneration"]` — **IDENTICAL vLLM class to our prod model.**
- `model_type: qwen3_5_moe`, 40 layers, **256 experts / 8 per tok** → MoE **A3B (~3B active)**. Same as Qwen3.6-35B-A3B.
- Hybrid attn: 30 `linear_attention` (GatedDeltaNet) + 10 `full_attention` (interval 4). Same hybrid split.
- `max_position_embeddings: 262144` (262K). `vision_config` present (`qwen3_5_moe_vision`, depth 27) → **vision preserved**.
- `mtp_num_hidden_layers: 1` (MTP heads present — but MTP+AWQ = 0% accept, known dead end for us).
- `vocab_size: 248320` (BIGGER than standard Qwen3.6 ~151k → different tokenizer → **fresh compile cache, verify chat template**).
- `transformers_version: 5.8.1` (needs transformers>=5.x — our image already handles this).

## Model card facts (VERIFIED via raw README)
- **License: MIT** (permissive ✓).
- **Thinking mode: YES** — emits `<think>…</think>`, `--reasoning-parser qwen3` ✓ (matches our setup).
- **Tool calling: `qwen3_xml`** recommended for vLLM (card). NOTE: our prod uses `qwen3_coder` (SGLang col uses qwen3_coder). → **verify which parser works on this checkpoint.**
- **Base: post-trained on Qwen 3.5** (35B extends Qwen3.5-35B) with "self-scaffolding RL" for agentic coding. → base is **3.5, NOT 3.6**.
- Sampling: temp 0.6, top_p 0.95, top_k 20 ✓ (≈ our defaults).
- Family: 9B-Dense, 31B-Dense, **35B-MoE (this one)**, 397B-MoE. 35B-MoE billed as "lightweight, single-GPU-capable".
- Released ~2026-06-26 (very fresh).

## Vendor benchmarks (Ornith-35B | Qwen3.5-35B | **Qwen3.6-35B = our prod**) — coding only
| Bench | Ornith | 3.5 | **3.6 (ours)** | Δ vs ours |
|---|---:|---:|---:|---:|
| Terminal-Bench 2.1 (Terminus-2) | 64.2 | 41.4 | **52.5** | **+11.7** |
| Terminal-Bench 2.1 (Claude Code) | 62.8 | 38.9 | **49.2** | **+13.6** |
| SWE-bench Verified | 75.6 | 70 | **73.4** | +2.2 |
| SWE-bench Pro | 50.4 | 44.6 | **49.5** | +0.9 |
| SWE-bench Multilingual | 69.3 | 60.3 | **67.2** | +2.1 |
| NL2Repo | 34.6 | 20.5 | **29.4** | +5.2 |
| Claw-eval Avg | 69.8 | 65.4 | **68.7** | +1.1 |
| SWE Atlas QnA/RF/TW | 37.1/29.7/27.8 | 13.2/10.2/9.8 | **15.5/11.4/13.3** | ~2–2.5× |
**Coding is our primary workload** (Roo/Claude Code routing, students, multi-agent orchestration) → the agentic Terminal-Bench/Claude-Code gains are the most relevant. But card shows **NO non-coding benches** (vision/math/general/multilingual) → must check ourselves.

## Quants available (RE-VERIFIED S2 2026-07-02 via HF API search)
- **✅ CHOSEN: `cyankiwi/Ornith-1.0-35B-AWQ-INT4`** (2851 dl) — **EXACT same recipe as our prod model** (same quantizer as `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`): `compressed-tensors` / `pack-quantized`, **int4 group_size=32 asym**, vision blocks in ignore-list (kept BF16), same `Qwen3_5MoeForConditionalGeneration`. **24.47 GB total → ~12.2 GB/GPU on TP=2** (≈ prod's ~11 GiB; delta = bigger 248320-vocab embeddings). Marlin MoE will engage as today. VERIFIED via raw config.json.
- **FP8 OFFICIAL**: `deepreinforce-ai/Ornith-1.0-35B-FP8` exists (33K dl — better provenance than the protoLabsAI third-party noted in S1). 35.7 GB → ~17.9 GB/GPU on TP=2: boots, but KV headroom collapses vs today's 2M tokens → NOT the path for prod parity. Also `cyankiwi/Ornith-1.0-35B-AWQ-FP8` (W4A16-style FP8 variant).
- **S1 correction**: `LeaderboardModel1/Ornith-1.0-35B-AutoRound-W4A16` is **GONE/renamed** (HF returns "Invalid username"; only a `-Tuning` variant remains, 558 dl). The S1 note "no compressed-tensors AWQ-group32 like cyankiwi's" is now WRONG — cyankiwi published exactly that. No self-quant needed.
- Rest: GGUF (official + bartowski), NVFP4 (useless on Ada sm89), MLX, misc uncensored forks — all irrelevant for us.

## S2 compat findings (2026-07-02, all VERIFIED on raw files)
- **Chat template: byte-identical to prod Qwen3.6's except 4 lines.** Sole diff = thinking-history handling: Ornith **always re-injects `<think>` reasoning into multi-turn history** (unconditional), where Qwen3.6 has the `preserve_thinking` conditional. Consequences: (a) our server-side `--default-chat-template-kwargs '{"preserve_thinking":true}'` becomes inert-but-harmless (var simply unused); (b) per-request opt-out `preserve_thinking:false` will NOT work on Ornith; (c) multi-turn prompts slightly longer (all reasoning retained) → marginal KV pressure, negligible at 2M tokens.
- **Tool-call wire format: IDENTICAL** — `<tool_call>\n<function=name>\n<parameter=key>…</parameter>\n</function>\n</tool_call>` (same block, byte-identical section). → **keep `--tool-call-parser qwen3_coder`** (the card's `qwen3_xml` suggestion parses the same XML family; no reason to deviate from prod parity). `--reasoning-parser qwen3` unchanged.
- **Genesis/TQ compat: SUPPOSED-good** (same class, same 30+10 hybrid layout, same expert count → same vLLM code paths Genesis patches). Real proof = S3 boot + continuation-prefill test. Fresh compile cache mandatory (bigger vocab).
- **Prefetch DONE (2026-07-02)**: `cyankiwi/Ornith-1.0-35B-AWQ-INT4` fully cached in the prod WSL HF cache (`hub/models--cyankiwi--Ornith-1.0-35B-AWQ-INT4`, 5/5 safetensors shards, 22.79 GiB, VERIFIED). → S3 boot is network-free; the container will resolve the model id straight from cache. Gotcha: image CLI is `hf download` (old `huggingface-cli download` removed).

## Fit assessment
**PRO (drop-in):** same vLLM class → Genesis-TQ (P22/P38 continuation-prefill fix), TurboQuant k8v4, EP=2, Marlin MoE, vision, thinking — all *should* apply unchanged. MoE A3B → same speed/VRAM/262K-context profile (no dense-model perf cliff). MIT. Beats our 3.6 on coding (vendor-claimed). Sampling defaults align.
**CON / verify:** (1) base 3.5 not 3.6 → possible non-coding/vision/multilingual regression (card hides those). (2) vendor benches unverified ("self-improving RL" hype → verify locally). (3) no AWQ-group32 quant (need AutoRound W4A16 / FP8 / self-quant). (4) bigger vocab + MTP + different fine-tune → fresh compile, verify Genesis/TQ + chat template + tool parser. (5) tool parser qwen3_xml vs our qwen3_coder. (6) GPU for A/B: 35B-MoE needs TP=2 (=prod GPUs 0,1); GPU 2 alone (24GB) is tight for 35B-4bit (~19GB + KV) — card claims single-GPU but risky; GPU 2 also earmarked for CoursIA trainings.

## Eval plan (future cranks — one per session)
- [x] **S1 (2026-07-01)**: research + arch/card/quant verification + verdict. Working doc + memory + cron armed. Prod state confirmed up post-outage. **DEFERRED 2026-07-01 (user "tester plus tard")**: tracking issue [roo-extensions#2716](https://github.com/jsboige/roo-extensions/issues/2716) created, cron `43c8f5f3` DELETED. Resume from #2716 when user wants active pacing.
- [x] **S2 (2026-07-02)**: quant path DECIDED = `cyankiwi/Ornith-1.0-35B-AWQ-INT4` (same recipe as prod — see "Quants" + "S2 compat findings" above). Chat template ≅ prod (4-line diff, thinking-history always-on), tool XML identical → keep qwen3_coder. Prefetch into prod HF cache launched. Cron re-armed `b7e8f117` (12h at :37) after brief 07-01 deferral; tracker = roo-extensions#2716.
- [~] **S3 (2026-07-02, IN PROGRESS — user GO "tenter de remplacer la prod, même archi 0,1, GPU 2 libre")**: prod cutover attempts on GPUs 0,1 with full Genesis-TQ stack, profile `medium-ornith-genesis-tq.yml` (serves BOTH `ornith-1.0-35b` + alias `qwen3.6-35b-a3b` so no client changes; fresh compile-cache volume).
  - **Attempt 1 (cyankiwi/Ornith-1.0-35B-AWQ-INT4): FAILED at boot 02:23Z** — `AssertionError: Only symmetric quantization is supported for MoE` (both workers). ROOT CAUSE: that quant = compressed-tensors pack-quantized int4 g32 **sym=False**; vLLM's compressed-tensors MoE loader is symmetric-only. **S2's "EXACT same recipe as prod" was WRONG**: prod Qwen3.6 quant is legacy **AWQ GEMM format** (`quant_method: awq`, `zero_point: true`) loaded via AWQ-Marlin which DOES accept asymmetric. Same author ≠ same format — always diff `quant_method`/format, not just bits/group/ignore-list. (CLAUDE.md's "AWQ 4-bit (compressed-tensors/pack-quantized)" description of prod is also wrong — config.json says quant_method: awq.) Rolled back to Qwen3.6 immediately (~15 min outage total).
  - **Attempt 2 (cyburn/Ornith-1.0-35B-int4-AutoRound, default Genesis flags): FAILED at boot 02:36Z** — GPTQ-Marlin path WAS taken (`Using MarlinLinearKernel for GPTQMarlinLinearMethod` on both workers) but `create_weights` died: `ValueError … output_size_per_partition = 32 is not divisible by min_thread_n = 64`. A 64-wide quantized projection (SUPPOSED: GDN beta/alpha in_proj — cyburn's `block_name_to_quantize: model.language_model.layers` quantizes EVERYTHING incl. tiny layers that prod's ignore-list skips) splits to 32/rank at TP=2, under Marlin's tile floor. Quant details: sym=True int4 **group_size=128** (coarser than prod's 32 — quality check needed at S4), packing `auto_round:auto_gptq`, vision BF16, 20.5 GB → ~10.2 GB/GPU. Prefetched 5/5 shards.
  - **Attempt 3 (same quant + `GENESIS_ENABLE_P87=1` + `GENESIS_ENABLE_P91=1`): ✅ SUCCESS 02:48Z — ORNITH IS SERVING PROD.** P87 = Marlin sub-tile output pad-on-load (backport vllm#40361, exact fix for the 32<64 crash; boot log confirms `[Genesis P87] padded output dim 32 -> 64 (tile=64)` — a single 64-wide layer, as hypothesized). P91 = AutoRound row-parallel group cdiv + group-aware `start_idx` (backport vllm#39460; fixes SILENT dequant corruption when `input_size_per_partition % group_size != 0` at TP>1 — we are exactly AutoRound g128 + TP=2, enabled proactively). VERIFIED at boot:
    - **MoE kernel: `Using 'MARLIN' WNA16 MoE backend`** — NO Triton moe_wna16 fallback → 2026-03-03 GPTQ cliff avoided. EP=2 active (128/256 experts/GPU, linear placement).
    - **KV cache: 2,434,565 tokens** (+20% vs Qwen3.6's 2.03M — AutoRound g128 weights are lighter: 9.65 GiB/GPU vs ~11). Load 72s from cache.
    - `quantization=inc` auto-detected (AutoRound/Intel Neural Compressor loader) → GPTQMarlinLinearMethod.
  - **Smoke gates (02:5xZ): 7/7 PASS** — models(both names) / simple 3.0s "OK" / thinking reasoning_len=1118 + "391" / tool call get_weather{city:Paris} qwen3_coder / vision "red" 0.8s / **58,415-token continuation-prefill needle BLUE-7742 found in 34.6s (the 2026-05-06 TQ killer, ~14 chunks at batch 4096)** / decode 116.6 tok/s single-user thinking-off (−3% vs v2g ~120, within ±5% threshold).
  - Watchdog sidecar up 02:57Z. 1h stability monitor armed (v2f idle regression fired at +55min — watch window covers it).
  - ~~STATUS: prod = Ornith serving~~ → **ROLLED BACK to Qwen3.6 same day (see S4/S5 below).**
- [x] **S4-light (2026-07-02, executed same session at user request "benchmarks légers")**: sequential harness (1-2 requests in flight of 16 slots), 150-sample subsets, **same-item comparison** vs Qwen3.6's full-run results on identical indexes:
  | Bench (150 same items) | Ornith | Qwen3.6 | Δ |
  |---|---|---|---|
  | GSM8K | 87.3% | 88.0% | −0.7 (noise) |
  | IFEval strict | 86.7% | 90.0% | **−3.3** |
  | MMStar (vision) | 49.3% | 54.0% | **−4.7** |
  | Tool-calling (12 scen.) | 83.3% | 83.3% | = (same 2 intelligent refusals) |
  | Decode single | 116.6 tok/s | ~120 | −3% |
  | KV cache | **2.43M** | 2.03M | **+20%** |
  - **Behavioral findings**: (a) Ornith **IGNORES `/no_think`** (still reasons ~1K chars — verified; Qwen3.x honors it) → any client relying on the marker + tight max_tokens breaks (LLMService.ts:502 synthesis path; synthesis currently disabled #788). (b) Ornith thinks MUCH longer by default (~3-5K chars even for trivial condensation tasks): with max_tokens=800 → `finish=length`, **content EMPTY** — this pattern would have broken utility clients. (c) **Dashboard condensation VERIFIED OK** (exact-shape test 35KB/15.9K tokens/max 12000/enable_thinking:false → stop, 17s): immune because `OPENAI_BASE_URL=localhost` routes to `chat_template_kwargs`. User's "condensations ne marchent plus" report = the S3 maintenance-window outages (02:20–02:57Z), verified no failing requests post-boot.
  - Repetition bench (qwen-instruct) killed mid-run by the rollback decision — not needed for the verdict.
- [x] **S5 DECISION (2026-07-02, user: "si les résultats sont moins bons on rollback non?")**: **REJECT for the generalist prod slot → ROLLED BACK to Qwen3.6 Genesis-TQ v2g.** Rationale: measured regressions on instruction-following (−3.3) and vision (−4.7, below even the 3.5 base) + `/no_think` incompatibility + heavy-thinking latency/empty-content risk on utility clients, while the headline coding gains (vendor Terminal-Bench +13.6) were NOT locally verifiable without an agentic harness. KV +20% and tool parity don't offset a generalist-role regression (OWUI multi-tenant, students, vision, condensation).
  - **Retained for the future ("coding-specialist split" option)**: profile `medium-ornith-genesis-tq.yml` (P87+P91 boot recipe proven), cyburn quant cached in prod HF cache, S4 coding benches only if a dedicated coding endpoint is ever wanted.
  - Smoke gate script ready: `smoke_test.py` (models/chat/thinking/tool/vision/30K-continuation-prefill-needle/decode-speed).
- [ ] **S4**: benchmark vs current 3.6 with OUR harness: coding (have students/agentic proxy), GSM8K, IFEval, MMStar, MME, tool-calling accuracy, repetition 4gram/TTR, decode tok/s, N=16 concurrent agg, KV cache size. Side-by-side table.
- [ ] **S5**: decide. If win (or coding-win with acceptable non-coding) → **propose to user + ai-01** before any prod cutover. Document rejection if it loses (cemetery entry).
- [ ] On delivery (deployed OR rejected-with-doc): report DONE both dashboards → CronList → CronDelete → memory DONE.

## Decision thresholds (mirror the TurboQuant migration plan style)
- **Switch** if: coding ≥ current (expected) AND non-coding regression ≤ ~2 pts on GSM8K/IFEval/MMStar/MME AND decode/concurrent within ~5% AND Genesis-TQ + vision + tool calling all work AND KV capacity preserved.
- **Reject** if: any of vision broken / tool calling broken / >5 pt non-coding regression / decode -10% / Genesis-TQ incompatible / boot crash.
- **Coding-specialist split option**: if Ornith wins coding but regresses general/vision, consider Ornith as a *second* coding endpoint (GPU 2, 9B/31B dense variant?) rather than replacing the 3.6 generalist on 0,1. Keep 3.6 as the vision/general default.

## Sources
- Model: https://huggingface.co/deepreinforce-ai/Ornith-1.0-35B (config.json + README verified raw)
- Quants: https://huggingface.co/models?other=base_model:quantized:deepreinforce-ai/Ornith-1.0-35B
- GitHub: https://github.com/deepreinforce-ai/Ornith-1 (9B/31B dense, 35B/397B MoE; Gemma4 + Qwen3.5 backbones)
- Reddit r/LocalLLaMA release thread; xhinker Medium "Runs Like 3B, Thinks Like 27B"
- Our prod baseline: CLAUDE.md "Qwen3.6-35B-A3B Deployment" + MEMORY.md `[[project-genesis-tq-batch-ceiling]]`
