"""Materialize v0.34.0 tiering sources + tierpin race fix + fs admission filter.

Self-contained, deterministic port (same pattern as ../overlay_v0340_tierpin/port.py):

1. read the exact v0.34.0 sources from the fork's tag object ``TAG``;
2. apply the tierpin anchors (copied verbatim from overlay_v0340_tierpin/port.py)
   and REFUSE to continue unless the result is byte-identical to the files
   that overlay ships (= the files serving production, sha256 fba881f0... and
   93110d5f... on 2026-11-21) -- so this overlay can never drift from, or
   silently revert, the race fix;
3. apply the fs admission anchors (jsboige/vllm#198 Phase 1a, ported from
   ../overlay_v0320_fsadmit, PR #202) on top of tiering/manager.py;
4. write vllm/v1/kv_offload/{cpu,tiering}/manager.py next to this script and
   PATCH.diff (admission delta, diffed against the tierpin file).

Every anchor must match exactly once; the result is compiled before writing.

Usage (from anywhere inside the repo checkout):
    python -X utf8 port.py           # (re)write the materialized files
    python -X utf8 port.py --check   # exit 1 if the committed files differ
"""

import difflib
import hashlib
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TIERPIN = HERE.parent / "overlay_v0340_tierpin"
TAG = "0c57b4195da4a6b69a7725908e428053e51e51b8"
BASE = "vllm/v1/kv_offload/"

# --- 1. tierpin race fix (verbatim from overlay_v0340_tierpin/port.py) --------

TIERPIN_CPU = [
    ('        req_context: ReqContext,\n    ) -> PrepareStoreOutput | None:\n        keys = list(keys)',
     '        req_context: ReqContext,\n        *,\n        extra_protected: Collection[OffloadKey] = (),\n    ) -> PrepareStoreOutput | None:\n        keys = list(keys)'),
    ('            protected = set(keys)\n',
     '            protected = set(keys)\n            protected.update(extra_protected)\n'),
]
TIERPIN_TIERING = [
    ('        self._request_load_sources: dict[str, dict[OffloadKey, CacheHitSource]] = {}\n',
     '        self._request_load_sources: dict[str, dict[OffloadKey, CacheHitSource]] = {}\n        # A later synchronous promotion must not evict an unpinned HIT.\n        self._step_hit_keys: set[OffloadKey] = set()\n'),
    ('        if primary_hit is LookupResult.HIT:\n            return LookupResult.HIT\n',
     '        if primary_hit is LookupResult.HIT:\n            self._step_hit_keys.add(key)\n            return LookupResult.HIT\n'),
    ('        primary_write_result = self.primary_tier.prepare_write([key], req_context)\n',
     '        primary_write_result = self.primary_tier.prepare_write(\n            [key], req_context, extra_protected=self._step_hit_keys\n        )\n'),
    ('        self._processed_jobs_this_step = False\n\n        self._flush_pending_promotions()',
     '        self._processed_jobs_this_step = False\n        self._step_hit_keys.clear()\n\n        self._flush_pending_promotions()'),
    ('        self._request_load_sources.clear()\n',
     '        self._request_load_sources.clear()\n        self._step_hit_keys.clear()\n'),
    ('        gate = self._processed_jobs_this_step\n        self._processed_jobs_this_step = True\n',
     '        gate = self._processed_jobs_this_step\n        # Off-thread polls run under the same manager lock and must not\n        # carry their lookup hits over into the next scheduler step.\n        step_hits = self._step_hit_keys\n        self._step_hit_keys = step_hits.copy()\n        self._processed_jobs_this_step = True\n'),
    ('        finally:\n            self._processed_jobs_this_step = gate\n',
     '        finally:\n            self._processed_jobs_this_step = gate\n            self._step_hit_keys = step_hits\n'),
]

# --- 2. fs admission filter (#198 Phase 1a) -----------------------------------

ADMIT_HEADER = '''\
   it is cascaded to ALL secondary tiers
   [myia fs-admit overlay, issue #198] ...except chunks refused by the
   frequency admission filter for STORAGE (fs/SSD) tiers: a chunk is
   cascaded there only once it has been found in the primary tier at least
   MYIA_FS_ADMIT_MIN_HITS times (default 2, 0 = upstream write-through).
   A refused cascade only costs a recompute later, never wrong output.
2. Primary tier is the gateway'''

ADMIT_MODULE = '''\
_TIER_POLL_JOIN_TIMEOUT_S = 5.0

# --- myia fs-admission overlay (jsboige/vllm#198, Phase 1a) ---------------
# Upstream tiering is write-through: every primary-tier store is cascaded to
# every secondary tier. On our production workload this pushed 427.5 GB to
# the fs tier in 8.9 h of which only 9.3% was ever read back (v0.32.0,
# measured 2026-10-25), and again 560.4 GB written vs 25.3 GB read back
# (4.5%) on v0.34.0 without this filter (2026-11-20/21). Cascades to STORAGE
# tiers are therefore frequency-gated, after NVIDIA Dynamo's disk-offload
# filter (DYN_KVBM_DISABLE_DISK_OFFLOAD_FILTER is off by default there:
# CPU->disk only for blocks with frequency >= 2) and SGLang HiCache's
# write_through_selective. See the overlay README for the full design.
#
# Both switches are read once per TieringOffloadingManager construction, so a
# change needs a container recreate (like MYIA_FS_TOUCH in lru_fs_tier.py).
_FS_ADMIT_ENV_MIN_HITS = "MYIA_FS_ADMIT_MIN_HITS"
_FS_ADMIT_ENV_GDN_LATEST = "MYIA_FS_ADMIT_GDN_LATEST"
# Upper bound on admission bookkeeping entries (hit counters + admitted-key
# set, together). At the measured ~10^5 distinct chunk keys/day this leaves
# days of headroom; overflowing clears both structures, which only biases
# admission toward FEWER fs writes (a refused store costs a recompute, never
# wrong output), so an unbounded dict is traded for a hard memory ceiling.
_FS_ADMIT_TRACKER_MAX = 250_000


def _read_fs_admit_min_hits() -> int:
    """MYIA_FS_ADMIT_MIN_HITS, default 2. 0 disables the filter (rollback)."""
    raw = os.environ.get(_FS_ADMIT_ENV_MIN_HITS, "2")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "fs admission: %s=%r is not an int, using the default 2",
            _FS_ADMIT_ENV_MIN_HITS,
            raw,
        )
        return 2
    if value < 0:
        logger.warning(
            "fs admission: %s=%d is negative, treating as 0 (disabled)",
            _FS_ADMIT_ENV_MIN_HITS,
            value,
        )
        return 0
    return value


def _read_fs_admit_gdn_latest() -> bool:
    """MYIA_FS_ADMIT_GDN_LATEST, default off (the rule is a stub, see
    _gdn_latest_allows)."""
    return os.environ.get(_FS_ADMIT_ENV_GDN_LATEST, "0").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )
'''

ADMIT_INIT = '''\
        self.secondary_tiers = secondary_tiers or []

        # myia fs-admission overlay (issue #198): frequency-gated cascades to
        # STORAGE (fs/SSD) tiers. 0 disables the gate entirely and restores
        # upstream write-through for every tier. The counters below are
        # content-addressed facts, deliberately NOT cleared by reset_cache()
        # (secondary tiers keep their data across resets too).
        self._fs_admit_min_hits = _read_fs_admit_min_hits()
        # Number of times each key was found ready (HIT) in the primary tier
        # by a lookup() walk. The storing request's own walk sees MISS/absent,
        # so the count starts accruing with the FIRST REUSING request.
        self._fs_admit_hits: dict[OffloadKey, int] = {}
        # Keys already written (or queued) to at least one STORAGE tier by
        # this filter. Prevents repeat cascade submissions after a threshold
        # crossing; complete_store() still re-admits them so pruned-and-
        # recomputed content re-persists.
        self._fs_admitted_keys: set[OffloadKey] = set()
        self._fs_admit_gdn_latest = _read_fs_admit_gdn_latest()
        if self._fs_admit_min_hits > 0:
            logger.info(
                "fs admission: cascades to STORAGE tiers require >= %d "
                "primary-tier lookup hit(s) (%s=0 restores write-through)",
                self._fs_admit_min_hits,
                _FS_ADMIT_ENV_MIN_HITS,
            )
        if self._fs_admit_gdn_latest:
            logger.warning(
                "fs admission: %s is set, but the GDN latest-state rule is "
                "a documented no-op stub at this layer (no conversation-chain "
                "identity reaches the tiering manager). Frequency admission "
                "alone applies. See _gdn_latest_allows() and the overlay "
                "README for where the rule belongs.",
                _FS_ADMIT_ENV_GDN_LATEST,
            )

        self._job_id_counter: int = 0
'''

ADMIT_METHODS = '''\
                detector.stats,
            )

    # --- myia fs-admission overlay (issue #198, Phase 1a) ------------------

    def _record_fs_admit_hit(
        self,
        key: OffloadKey,
        req_context: ReqContext,
        exclude_tier_idx: int | None = None,
    ) -> None:
        """Count one upper-tier sighting of ``key`` and admit on crossing.

        Called on every primary-tier (RAM) lookup() HIT -- the canonical
        "found in an upper tier" event; the prepare_load() that follows the
        same HIT is the same use, not a second one, and is not counted
        again. Secondary-tier (fs) hits are not counted either: a chunk
        already on disk needs no disk admission.

        When the count reaches the threshold, the chunk is cascaded to the
        STORAGE tiers immediately, from inside this lookup: write-through
        only cascades at store time, and a chunk that stays hot in the
        primary tier forever (a stable socle) is never re-stored, so a
        store-time-only gate would never persist it -- after every restart
        the socle would stop reaching the fs entirely.

        ``exclude_tier_idx`` is the origin tier of a ParentManager lookup
        (a tier serving an external request); the crossing cascade skips it,
        as lookup() itself does.
        """
        if self._fs_admit_min_hits <= 0:
            return
        count = self._fs_admit_hits.get(key, 0) + 1
        self._fs_admit_hits[key] = count
        if count == self._fs_admit_min_hits:
            self._cascade_key_to_storage_tiers(key, req_context, exclude_tier_idx)
        self._check_fs_admit_overflow()

    def _cascade_key_to_storage_tiers(
        self,
        key: OffloadKey,
        req_context: ReqContext,
        exclude_tier_idx: int | None = None,
    ) -> None:
        """Admission threshold just crossed while ``key`` is resident and
        ready in the primary tier: cascade it now to every STORAGE tier.

        No existence probe first: the real fs tier's lookup() is
        asynchronous (a fresh probe returns RETRY), so probing would defer
        this write to a re-store that may never come for a chunk that stays
        hot in the primary tier. The fs tier's store path is idempotent
        (content-addressed file, temp + os.replace; our TouchOnHitFsTier
        additionally skips the rewrite of an existing file), so the worst
        case of submitting unconditionally is one redundant submission per
        key per process lifetime (e.g. a socle that survived a restart on
        disk and re-crossed).

        Same create_store_job() + submit_store() pair as the write-through
        cascade in complete_store(), under the same manager lock. A crossing
        reached from the tier-poll thread (ParentManager fan-out, P2P tiers
        only -- none in our deployment) is covered by the SecondaryTierManager
        contract: any tier can be reached from that thread.
        """
        if key in self._fs_admitted_keys:
            return
        if self._fs_admit_gdn_latest and not self._gdn_latest_allows(
            key, req_context
        ):
            return
        submitted = False
        for tier_idx, tier in enumerate(self.secondary_tiers):
            if tier_idx == exclude_tier_idx:
                continue
            if tier.medium is not Medium.STORAGE:
                continue
            if not self._should_store_to_tier(tier, 1):
                continue
            job_metadata = self.create_store_job([key], req_context, tier_idx)
            tier.submit_store(job_metadata)
            submitted = True
        if submitted:
            self._fs_admitted_keys.add(key)
        self._check_fs_admit_overflow()

    def _filter_fs_admitted(
        self, keys: Collection[OffloadKey], req_context: ReqContext
    ) -> list[OffloadKey]:
        """Return the subset of ``keys`` admitted to a STORAGE tier.

        Keys already in _fs_admitted_keys pass unconditionally: membership
        means admission was earned before, and the re-cascade this allows is
        what re-persists hot content after the external pruner deleted its
        fs file (the fs tier's write path is idempotent, content-addressed).
        """
        admitted: list[OffloadKey] = []
        for key in keys:
            if self._fs_admit_gdn_latest and not self._gdn_latest_allows(
                key, req_context
            ):
                continue
            if key in self._fs_admitted_keys:
                admitted.append(key)
            elif self._fs_admit_hits.get(key, 0) >= self._fs_admit_min_hits:
                self._fs_admitted_keys.add(key)
                admitted.append(key)
        self._check_fs_admit_overflow()
        return admitted

    def _check_fs_admit_overflow(self) -> None:
        if len(self._fs_admit_hits) > _FS_ADMIT_TRACKER_MAX:
            self._fs_admit_hits.clear()
            self._fs_admitted_keys.clear()
            logger.warning(
                "fs admission: tracker exceeded %d entries, cleared -- "
                "admission is temporarily more conservative (fewer fs "
                "writes) until counters rebuild",
                _FS_ADMIT_TRACKER_MAX,
            )

    def _gdn_latest_allows(
        self, key: OffloadKey, req_context: ReqContext
    ) -> bool:
        """STUB (issue #198, Phase 1b): GDN latest-state rule -- NOT
        IMPLEMENTED at this layer, by design.

        Intended semantics: a Gated DeltaNet state snapshot of a
        conversation must not be cascaded to fs once a newer snapshot of
        the same chain supersedes it. Deciding supersession needs two facts
        the tiering manager does not have:

        1. Which KV group indices are GDN state groups. The group index is
           recoverable from the key (get_offload_group_idx), but the
           group-index -> attention-type mapping lives in OffloadingConfig
           / the scheduler-side connector, never here.
        2. Conversation-chain identity. Keys are opaque content hashes:
           two snapshots of one conversation cannot be related at this
           layer, and ReqContext carries only req_id plus per-request
           token positions, not which prior request a prompt continues.

        The rule therefore belongs where both facts exist -- the
        scheduler-side offloading connector (upstream's planned
        TieringAdmissionPolicy, RFC vllm#51240 / PR vllm#60000) or Phase 2's
        branch-point checkpoints (issue #198). Until then this stub returns
        True (no exclusion): frequency admission alone applies, and
        MYIA_FS_ADMIT_GDN_LATEST only logs that the rule was requested.
        """
        return True

    @override
    def lookup(
'''

ADMIT_TIERING = [
    ('   it is cascaded to ALL secondary tiers\n2. Primary tier is the gateway', ADMIT_HEADER),
    ('import threading\nimport time\n', 'import os\nimport threading\nimport time\n'),
    ('    LookupResult,\n    OffloadingEvent,\n', '    LookupResult,\n    Medium,\n    OffloadingEvent,\n'),
    ('_TIER_POLL_JOIN_TIMEOUT_S = 5.0\n', ADMIT_MODULE),
    ('        self.secondary_tiers = secondary_tiers or []\n\n        self._job_id_counter: int = 0\n', ADMIT_INIT),
    ('                detector.stats,\n            )\n\n    @override\n    def lookup(\n', ADMIT_METHODS),
    ('            self._step_hit_keys.add(key)\n            return LookupResult.HIT\n',
     '            self._step_hit_keys.add(key)\n'
     '            self._record_fs_admit_hit(key, req_context, exclude_tier_idx)\n'
     '            return LookupResult.HIT\n'),
    ('            for tier_idx, tier in enumerate(self.secondary_tiers):\n'
     '                if not self._should_store_to_tier(tier, len(keys)):\n'
     '                    continue\n'
     '                job_metadata = self.create_store_job(keys, req_context, tier_idx)\n'
     '                tier.submit_store(job_metadata)\n',
     '            # [myia fs-admit overlay, issue #198] STORAGE tiers receive only\n'
     '            # the admitted subset: chunks never found in an upper tier are\n'
     '            # skipped (a refused store costs a recompute later, never wrong\n'
     '            # output). Other media keep upstream write-through.\n'
     '            for tier_idx, tier in enumerate(self.secondary_tiers):\n'
     '                if not self._should_store_to_tier(tier, len(keys)):\n'
     '                    continue\n'
     '                tier_keys: Collection[OffloadKey] = keys\n'
     '                if self._fs_admit_min_hits > 0 and tier.medium is Medium.STORAGE:\n'
     '                    tier_keys = self._filter_fs_admitted(keys, req_context)\n'
     '                    if not tier_keys:\n'
     '                        continue\n'
     '                job_metadata = self.create_store_job(tier_keys, req_context, tier_idx)\n'
     '                tier.submit_store(job_metadata)\n'),
]


def _show(path: str) -> str:
    out = subprocess.check_output(["git", "-C", str(HERE), "show", f"{TAG}:{path}"])
    return out.decode("utf-8")


def _apply(path: str, text: str, changes) -> str:
    for before, after in changes:
        if text.count(before) != 1:
            raise ValueError(f"Expected one anchor in {path}: {before!r}")
        text = text.replace(before, after)
    compile(text, path, "exec")
    return text


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build() -> dict[str, str]:
    cpu_path = BASE + "cpu/manager.py"
    tiering_path = BASE + "tiering/manager.py"
    cpu = _apply(cpu_path, _show(cpu_path), TIERPIN_CPU)
    tierpin = _apply(tiering_path, _show(tiering_path), TIERPIN_TIERING)
    # Composition guard: the tierpin layer must equal what production serves.
    for rel, text in ((cpu_path, cpu), (tiering_path, tierpin)):
        shipped = (TIERPIN / rel).read_text(encoding="utf-8")
        if shipped != text:
            raise SystemExit(
                f"tierpin layer of {rel} differs from overlay_v0340_tierpin "
                f"({_sha(text)[:12]} vs {_sha(shipped)[:12]}); refusing to port"
            )
    admitted = _apply(tiering_path, tierpin, ADMIT_TIERING)
    patch = "".join(
        difflib.unified_diff(
            tierpin.splitlines(keepends=True),
            admitted.splitlines(keepends=True),
            fromfile="a/" + tiering_path + " (overlay_v0340_tierpin)",
            tofile="b/" + tiering_path + " (overlay_v0340_fsadmit)",
        )
    )
    return {cpu_path: cpu, tiering_path: admitted, "PATCH.diff": patch}


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale = []
    for rel, text in build().items():
        target = HERE / rel
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == text:
            continue
        if check:
            stale.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {rel} sha256={_sha(text)[:12]}")
    if check:
        if stale:
            print("STALE: " + ", ".join(stale))
            return 1
        print("materialized files match port.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
