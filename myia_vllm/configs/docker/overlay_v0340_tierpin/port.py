"""Materialize exact v0.34.0 source plus the local tiering fix, without touching main."""
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parent / 'swift-v0340-overlay'
tag = '0c57b4195da4a6b69a7725908e428053e51e51b8'

def port(relative, changes):
    path = 'vllm/v1/kv_offload/' + relative
    original = subprocess.check_output(['git', '-C', str(root.parent.parent), 'show', f'{tag}:{path}']).decode('utf-8')
    updated = original
    for before, after in changes:
        if updated.count(before) != 1:
            raise ValueError(f'Expected one anchor in {path}: {before!r}')
        updated = updated.replace(before, after)
    compile(updated, path, 'exec')
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8', newline='\n') as f:
        f.write(updated)

port('cpu/manager.py', [
    ('        req_context: ReqContext,\n    ) -> PrepareStoreOutput | None:\n        keys = list(keys)',
     '        req_context: ReqContext,\n        *,\n        extra_protected: Collection[OffloadKey] = (),\n    ) -> PrepareStoreOutput | None:\n        keys = list(keys)'),
    ('            protected = set(keys)\n',
     '            protected = set(keys)\n            protected.update(extra_protected)\n'),
])
port('tiering/manager.py', [
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
])
