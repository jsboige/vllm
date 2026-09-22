# v0.29.0 → v0.30.0 image bump (2026-09-22, GO user) — **PROMOTED**

- previous image: `vllm/vllm-openai:v0.29.0` (digest `sha256:aa542864b00a…`, promoted 2026-09-11)
- new image: `vllm/vllm-openai:v0.30.0` (image ID `8a69ffad015f`, 30.7 GB; tag published 2026-09-22T02:15Z, GitHub release 05:20Z)
- profile changes (exactly three): `image:`, compile-cache mount `…-v0300`, volume declaration. `…-v0290` and `…-v0280` volumes kept intact for rollback.
- rollback: restore the three lines to v0.29.0 + the `…-v0290` volume, then `down && up -d --env-file`.

## Why (user GO 2026-09-22)

v0.30.0 (762 commits) carries for us: #56908 (V2 runner tolerates missing pinned memory
— the WSL2/UVA gate family we clear with `VLLM_WSL2_ENABLE_PIN_MEMORY=1`), #51700 (FULL
CUDA graphs under V2), #55133 (Qwen3 DSpark padded-vocab fix — unblocks the DSpark
re-evaluation). The two Qwen3.6/GDN perf PRs previously watched (#52676, #52789) were
verified **already ancestors of v0.29.0** via `compare` — nothing new from them here.

## Window

Announced 11:25Z (machine dashboard) · baseline bench 11:30Z · `down` 11:41Z ·
engine `StartedAt 11:42:47Z` · **healthy ~11:47Z** (~4.5 min boot on the fresh
`…-v0300` compile-cache volume) · compose `up -d` returned once sidecars'
`service_healthy` resolved.

## Post-boot state (all carried over)

- **`Using V2 Model Runner`** — the pin-memory gate held, no UVA error (the 09-09 failure mode is gone)
- `prefix_match_unit=16`, `mamba_ssm_cache_dtype=float16` (fp16 warning present, user value wins), batch 8192 / seqs 16, `performance_mode interactivity`, TQ k8v4 — all applied
- **KV cache: 934,660 tokens** — byte-identical to v0.29.0; max concurrency 3.57× at 262K
- VRAM **GPU 0 19,344 / GPU 1 18,294 MiB** (v0.29.0: 19,127 / 18,296 — same ballpark)
- New in v0.30.0: the boot log now suggests explicit `--kv-cache-memory` values (actual CUDA-graph pool 0.18 GiB vs 0.81 estimated). **Not acted on** — recorded as a future gpu-util lever.

## Battery — 13/13 PASS (11:47:57Z)

| Gate | Result |
|---|---|
| smoke | 0.41 s |
| vision | 4/4 couleurs |
| tool-calling | `get_weather({"city":"Lyon"})` 0.5 s |
| thinking | 1 956 car reasoning, finish=stop |
| preserve_thinking | OK |
| prefill-30k | 31 417 tok en 3.9 s → **8 089 tok/s** + survie |
| prefill-95k | 101 838 tok en 13.9 s → **7 345 tok/s** + survie |
| prefill-235k | 253 503 tok en 44.7 s → **5 673 tok/s** + survie |
| concurrent N=16 ×2 | 386 → **507 tok/s** au repeat (prefix cache actif) |

**FORCING (batch (4096, 8192])**: 6 requêtes concurrentes de 4 618 prompt tokens (27 708 total) en 1.1 s, toutes 200 — forwards au-dessus de 4096 formés, **0** signature `Workspace is locked|turboquant_attn.*Error|EngineDead|out of memory|Traceback` sur tout le segment.

## Bench A/B same-window (same script, same prompts, temp 0)

| N | v0.29.0 (avant, 11:30Z) | v0.30.0 passe 1 | passe 2 | passe 3 |
|---:|---:|---:|---:|---:|
| 1 | 50.3 | 64.6 | 91.2 | 94.0 |
| 2 | 86.1 | 91.2 | 129.3 | 128.5 |
| 4 | 172.7 | 163.5 | 226.1 | 222.3 |
| 8 | 327.0 | 328.4 | 438.6 | 455.2 |
| 12 | 513.7 | 479.3 | 660.9 | 654.9 |
| 16 | **678.1** | 609.6 | **847.0** | **834.1** |

**La passe 1 est la taxe de warm-up JIT** (pattern documenté : premiers forwards post-boot systématiquement lents — le bench baseline tournait sur un moteur chaud depuis des heures, la passe 1 sur un moteur fraîchement booté). Passes 2-3, moteur chaud : **N=16 834-847 vs 678,1 → +23-25 %**, mieux à **tous** les N. Aucune régression une fois chaud.

Cross-day caution: the all-time same-machine record remains 869.5 (09-11, v0.29.0) — this
window's machine state is its own baseline; the +23-25 % claim is strictly same-window.

## Verdict: **PROMOTED** (2026-09-22)

13/13 gates, FORCING clean, error scan 0, config byte-identical, warm A/B better at every N.
Watch items for the next cycles: V2 + #51700 FULL cudagraphs is new territory — treat this
as a correctness clearance, not a soak (same stance as the 09-11 promotion). DSpark re-eval
now unblocked on two counts (V2 runner + #55133).
