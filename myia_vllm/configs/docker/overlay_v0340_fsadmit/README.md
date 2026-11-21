# overlay_v0340_fsadmit — fs KV tier write admission on v0.34.0 (issue jsboige/vllm#198, Phase 1a)

**Status: built for evaluation, NOT deployed.** Deploying means a user GO, a
window announced on the `global` dashboard first, and one engine recreate
(see “Deployment proposal”). Nothing here changes a file that production
loads today: the profile still defaults to `vllm-openai-v0340-tierpin:v1`.

## Why this exists: production lost the filter on 2026-11-09

The admission filter was written for v0.32.0 (`overlay_v0320_fsadmit/`,
PR #202) and served in production on top of the tierpin overlay. On
**2026-11-09 00:19Z**, prod went back to `vllm-openai-v0320-tierpin:v1` after
the MTP A/B window, an image that does not carry the filter. The v0.34.0 bump
of 2026-11-19 (`overlay_v0340_tierpin/`) ported only the race fix. Since
then, the fs tier has been back on upstream write-through.

Measured on the running engine since its 2026-11-20 14:14:21Z boot:

| Signal | Value |
| --- | --- |
| `kv_offload_tiering_write_bytes_total{tier="1:TouchOnHitFsTier"}` | **560.4 GB** |
| `kv_offload_store_bytes_total` (GPU→RAM) | 548.5 GB (≈ equal: every RAM store cascades) |
| fs read back | 25.3 GB (**4.5 %**) |
| real file births, 30 min window ~03:20Z on 2026-11-21 | 989 files / 26.83 GB (attention 10.96 GB, GDN 15.87 GB) ≈ **54 GB/h** |
| cruise with the filter on, 2026-10-26 | 5.0 GB/h |

The `lru_fs_tier.py` skip-rewrite (bind-mounted, image-independent) is still
active. Only the admission gate is gone.

## What it does

Same design as `overlay_v0320_fsadmit/README.md`, which remains the
reference for the rationale: prior art in Dynamo KVBM's disk-offload filter
and SGLang HiCache's `write_through_selective`, the “hit” semantics, the
no-probe crossing, and the GDN latest-state stub. Summary:

- A chunk is cascaded to a **STORAGE-medium** secondary tier (fs/SSD) only
  once it has been **found (lookup HIT) in the primary (RAM) tier at least N
  times**, where N = `MYIA_FS_ADMIT_MIN_HITS`, default 2. The storing
  request's own walk sees MISS, so counting starts with the first *reusing*
  request: one-shot content never reaches the disk.
- On the Nth hit the chunk is cascaded **from inside `lookup()`**. A chunk
  that stays hot in RAM is never re-stored, so a store-time-only gate would
  never persist it.
- `complete_store()` sends STORAGE tiers only the admitted subset of the
  keys: a counter at N or above, or already admitted.
- The RAM tier and every non-STORAGE secondary tier keep exact upstream
  behaviour.
- A refused store costs a recompute later, never wrong output: the same
  contract as a pruned fs file under `kv_load_failure_policy=recompute`.

The production fs tier is in scope. `TouchOnHitFsTier` (`myia_vllm/kv_tier/lru_fs_tier.py`)
subclasses `FileSystemTierManager`, which declares
`medium = Medium.STORAGE` (v0.34.0 `tiering/fs/manager.py:107`).

## Files, and how the two patches compose

| File | Content |
| --- | --- |
| `port.py` | Anchor-based, deterministic port from the fork's v0.34.0 tag object `0c57b4195da4a6b69a7725908e428053e51e51b8` (byte-identical to the stock `cf5b2fdd…` image files, see `_iteration_log/v0340_bump/NOTES.md`). It applies the tierpin anchors first, verbatim from the tierpin port. It **refuses to continue** unless the intermediate result is byte-identical to `../overlay_v0340_tierpin/vllm/v1/kv_offload/{cpu,tiering}/manager.py`. Only then does it apply the admission anchors. Each anchor must match exactly once. `--check` exits 1 if the committed files are stale. |
| `vllm/v1/kv_offload/cpu/manager.py` | **Byte-identical** to `overlay_v0340_tierpin` (`93110d5f…`): the `extra_protected` half of the race fix. |
| `vllm/v1/kv_offload/tiering/manager.py` | tierpin (`fba881f0…`) + admission filter = `ea197bf3…`. |
| `PATCH.diff` | Diff **against the tierpin file**, so it shows only the fsadmit delta. |
| `Dockerfile` | `FROM` the same stock v0.34.0 digest as production; it copies both modules, runs `py_compile`, and a build-time assert fails the build unless `_step_hit_keys` (tiering), `extra_protected` (cpu) **and** `_record_fs_admit_hit` / `_filter_fs_admitted` are present. |
| `tests/` | `test_fs_admission.py` (9 tests), `test_step_hit_protection.py` (the tierpin race regression, copied from `overlay_v0320_tierpin/tests/`), `run_tests.sh`. |

Regenerate: `python -X utf8 port.py`; verify: `python -X utf8 port.py --check`.

### file:line evidence (patched `tiering/manager.py`, 1677 lines)

| Change | Where |
| --- | --- |
| Header principle 1 amended | `manager.py:12-16` |
| Env readers, tracker cap 250 000 | `manager.py:95-151` |
| Init state (`_fs_admit_min_hits`, `_fs_admit_hits`, `_fs_admitted_keys`, GDN flag, logs) | `manager.py:365-397` |
| Methods `_record_fs_admit_hit`, `_cascade_key_to_storage_tiers`, `_filter_fs_admitted`, overflow, GDN stub | `manager.py:801-944` |
| Hit counting, right after the tierpin `self._step_hit_keys.add(key)` | `manager.py:995` |
| `complete_store()` STORAGE gate | `manager.py:1319-1332` |

## What differs from the v0.32 port

The v0.34.0 tiering manager is not the v0.32 one: there are 738 diff lines
between the two tierpin files. The admission logic is unchanged. The
differences that touched it:

1. **ParentManager fan-out.** v0.34 lets a secondary tier issue lookups on
   behalf of an external request through
   `_SecondaryTierFacingParent.lookup` → `lookup(..., exclude_tier_idx=origin)`
   (`manager.py:312`). Such a lookup still counts as a primary-tier
   sighting. The crossing cascade now takes the same `exclude_tier_idx` and
   **skips the origin tier**, exactly as `lookup()` itself does: the tier
   that asked must not be written back into. A key whose only STORAGE tier
   was the origin is not marked admitted, so a later store re-evaluates it
   from the persistent counter. Two new tests cover this.
2. **Tier-poll thread.** v0.34 polls tiers that set
   `tolerates_off_thread_polling` from a background thread, under the
   manager's `threading.Lock`. Only P2P sets it upstream, and our deployment
   has no P2P tier. A crossing reached from that thread follows the base
   contract (“any tier can be reached from there via ParentManager
   fan-out”) and uses the same `create_store_job` + `submit_store` pair as
   the write-through cascade.
3. **`bp_detector` property.** v0.34 reads `tier.bp_detector`, a property
   over `_bp_detector`. `_should_store_to_tier(tier, 1)` gates the crossing
   exactly as before, and it is evaluated before the filter in
   `complete_store`, in the same order as the v0.32 overlay.
4. **`Medium` import** comes from `vllm.v1.kv_offload.base` (the import
   block moved).
5. **Tier indexing at construction** (`_tier_index`): tests must pass every
   tier to the constructor instead of appending later. This changes test
   scaffolding only.

Deliberately **not** filtered, the same choice as v0.32:

- `_cascade_existing_chunks_to_request_level_tiers` / `_flush_pending_cascades`
  (v0.34 parks HIT_PENDING keys in `pending_cascade_keys`). That path serves
  only tiers whose `on_new_request` returns `OffloadPolicy.REQUEST_LEVEL`,
  and upstream only P2P does (`p2p/manager.py:478`). fs, obj, kvcr and
  example return the default `CHUNK_LEVEL`, and `lru_fs_tier.py` does not
  override it. A future STORAGE tier that opted into request-level policy
  would bypass the filter. None exists.
- `create_store_job` itself: P2P/external store jobs stay upstream.

## Config switches

| Variable | Default | Meaning |
| --- | --- | --- |
| `MYIA_FS_ADMIT_MIN_HITS` | `2` | Cascade to STORAGE tiers only after N or more primary-tier lookup hits. **`0` disables the filter and restores exact upstream write-through** (the rollback switch). Read once per manager construction, so a change needs a container recreate. A non-int value falls back to 2 and a negative one to 0, each with a log line. |
| `MYIA_FS_ADMIT_GDN_LATEST` | `0` | Documented no-op stub. Setting it only logs. |

**Profile passthrough today: NONE.** `profiles/medium-swift15-27b-fstier.yml`
sets no `MYIA_FS_ADMIT_*` variable, so on this image the default **2**
applies, and `MYIA_FS_ADMIT_MIN_HITS=0` cannot be set from the shell alone.
This PR deliberately leaves the profile unchanged. Adding an `environment:`
line changes the engine's Compose config hash, so the next
`compose up -d` from the repository would recreate production. That change
belongs in the deployment window, together with the image switch (below).

## Deployment proposal (needs a user GO and an announced window)

```bash
# 1. Announce on the global dashboard (window, downtime ~5 min warm boot -- the
#    2026-11-18 v0.34 recreate took 23:51Z -> 23:55:20Z to a watchdog generation -- and rollback).
# 2. Recreate the engine only, on the new image:
VLLM_IMAGE_SWIFT15=vllm-openai-v0340-fsadmit:v1 \
  docker compose -f myia_vllm/configs/docker/profiles/medium-swift15-27b-fstier.yml \
  --env-file myia_vllm/.env up -d --no-deps vllm-medium-swift15-27b
# 3. Verify: boot log line "fs admission: cascades to STORAGE tiers require >= 2",
#    KV 793,516 unchanged, watchdog generation OK, then over the next hours:
#    rate(kv_offload_tiering_write_bytes_total{tier="1:TouchOnHitFsTier"}) falls
#    toward the ~5 GB/h cruise of 2026-10-26, while the disk-served prompt-token
#    share does not collapse (acceptance gate of issue #198).
```

The compile cache should carry over: the profile mounts
`vllm-compile-cache-swift15-27b-v0340` whatever the image, the base digest
is the same, and the only modules that differ are scheduler-side ones that
are not part of the traced model code. This is SUPPOSED, not measured. A
cold compile shows up as a 10-25 min boot, which is normal per the profile
header, not a hang.

Once validated, make it durable in one commit inside the same kind of
window: profile default image → `vllm-openai-v0340-fsadmit:v1`, plus
`- MYIA_FS_ADMIT_MIN_HITS=${MYIA_FS_ADMIT_MIN_HITS:-2}` in the engine
`environment:`. The hash then changes exactly when the container is
recreated anyway.

## Rollback

- **Image**: drop the variable and recreate. `docker compose … up -d --no-deps vllm-medium-swift15-27b`
  without `VLLM_IMAGE_SWIFT15` returns to the profile default
  `vllm-openai-v0340-tierpin:v1`, which is today's production image.
- **Filter only, same image**: recreate with
  `- MYIA_FS_ADMIT_MIN_HITS=0` in the engine `environment:`. Every added code
  path short-circuits and behaviour is upstream write-through. The upstream
  v0.34.0 suite in that mode reproduces the tierpin baseline exactly (record
  below).

## Tests

All tests run in throwaway CPU-only containers (`docker run --rm`, no
`--gpus`, `CUDA_VISIBLE_DEVICES=`), never against the production container.
`tests/run_tests.sh` has the host-side driver lines. The upstream tests come
from the same fork tag the port reads; see the runner header for the
extraction commands.

### Test run record (2026-11-21, image `vllm-openai-v0340-fsadmit:v1` = `69e76f2e5fa7`)

Build: the in-image asserts passed, and the sha256 of both installed
modules matches the committed files (`93110d5f…` cpu, `ea197bf3…`
tiering).

| Suite | fsadmit (default, N=2) | tierpin `be9b93d707c9` (prod) | stock v0.34.0 `cf5b2fdd…` |
| --- | --- | --- | --- |
| `test_fs_admission.py` | **9/9 pass** | 9/9 fail (no filter) | 9/9 fail |
| `test_step_hit_protection.py` (race regression, whole file) | **3/3 pass** | 3/3 pass | **3/3 fail** (race unfixed upstream) |

Upstream v0.34.0 `tests/v1/kv_offload` (1008 test items), compared per
test through JUnit XML against the tierpin baseline:

| Run | passed / skipped / failed / errors | Outcome differences vs tierpin baseline |
| --- | --- | --- |
| tierpin baseline | 955 / 15 / 0 / 38 | — |
| fsadmit, `MYIA_FS_ADMIT_MIN_HITS=0` (rollback) | 955 / 15 / 0 / 38 | **0** |
| fsadmit, default (N=2) | 954 / 15 / 1 / 38 | **1, expected**: `test_fs_tier.py::test_cascade_store_emits_fs_event_through_tiering_manager` (`assert 0 == 1` on the fs stored event). The test asserts that a **first** store reaches the fs tier, which is exactly what the filter removes. The v0.32 port had the same expected failure. |

The 38 errors are the same in all three runs and come from the test
environment, not from the code. They are fixtures defined in the top-level
`tests/conftest.py` (`default_vllm_config` ×32, `caplog_vllm` ×4,
`vllm_runner` ×2), which is not extracted because it pulls the whole
model-test stack. The tests affected are 36 in `cpu/test_gpu_worker.py` and
2 in `tiering/test_p2p_lifecycle_e2e.py` (a real engine through
`vllm_runner`). Neither touches the two modules this overlay changes.
