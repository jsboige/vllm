# Run vLLM unit tests on this host — no venv, no GPU

Snapshot of the harness used on 2026-11-27 to run the `vllm#63551` rework tests (see
`myia_vllm/_iteration_log/v0320_fstier/NOTES.md`, section `27/11`). The Windows host has no
Python environment with vllm, and no `--gpus` container started that day (broken GPU prestart
hook), so the tests ran **inside the vLLM image, CPU-only**.

## Recipe

1. Pick an image whose commit is the parent of the branch under test — here
   `vllm/vllm-openai:nightly-647a76866b4559a74e27d1c6b55fbffe85c07ce4` (vllm 0.34.0rc1.dev1133,
   Python 3.14). The production image `vllm-openai-v0340-fsadmit:v1` does **not** work: its API is
   older than current `main` (no `StoreTrigger`, no `vllm/v1/kv_hints/`).
2. `build_stage.sh <base_commit> <stage_dir>` builds two overlay trees from git blobs — `patched/`
   at `HEAD` and `base/` at `<base_commit>` — containing only the `.py` files that differ between
   the image's commit and `<base_commit>` (597 files on 2026-11-27), plus a reduced test tree.
   `<stage_dir>` must be an **absolute POSIX** path (`/d/...`); a `D:/...` value silently lands
   under `<worktree>/.tmp/D:/...`.
3. `docker run --rm -v <stage>:/stage:ro -v <logdir>:/logs --entrypoint bash <image> \
   /stage/run_tests.sh <patched|base> <logname> <pytest targets...>`, with
   `MSYS_NO_PATHCONV=1` **on the docker arguments only** (else `/stage` is rewritten to a Git
   path). No `--gpus`.
4. Read `<logdir>/<logname>.log`: it records the overlay count and the `sha256` of the installed
   and the staged `tiering/manager.py` — they must be equal, and the two variants must differ only
   by the patched files.

## What this proves, and what it does not

- It proves the branch's **Python** logic against the image's compiled extensions, and that an
  unpatched run reproduces the failure. Always run both variants: a patched-only run says nothing.
- It is **not** the upstream CI: the evidence comes from the image's build of `647a76866`, not from
  a build of current `main`, and nothing compiled was rebuilt.

## Observing the test run itself

`run_tests.sh` copies only the tests named by the caller's targeting; upstream suites that need
the root `tests/conftest.py` fixtures (`vllm_runner`) will error out — identically on both variants,
which is how you tell a harness gap from a regression.
