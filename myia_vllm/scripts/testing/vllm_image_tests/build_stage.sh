#!/usr/bin/env bash
# Build two pure-Python overlay trees from the worktree, both as LF git blobs:
#   <stage>/patched/vllm/**  = HEAD            = <base> + the patch
#   <stage>/base/vllm/**     = <base>          = same files, WITHOUT the patch
# plus the test tree (minimal conftest chain, no 2046-line tests/conftest.py).
# The image carries vllm built from $NIGHTLY; overlaying exactly the files that
# changed between $NIGHTLY and <base> puts the image's compiled extensions under
# the branch's own pure-Python sources.
# Usage: build_stage.sh <stage_dir> <base_commit>
set -euo pipefail

WT=D:/vllm/.tmp/wt-63551
NIGHTLY=647a76866b4559a74e27d1c6b55fbffe85c07ce4
BASE="${1:?base commit}"
STAGE="${2:?stage dir}"

case "$STAGE" in /*) ;; *) STAGE="$WT/.tmp/$STAGE" ;; esac
mkdir -p "$STAGE/patched" "$STAGE/base" "$STAGE/tests"

git -C "$WT" diff --name-only --diff-filter=d "$NIGHTLY" "$BASE" -- vllm/ > "$STAGE/files.txt"
git -C "$WT" diff --name-only --diff-filter=D "$NIGHTLY" "$BASE" -- vllm/ > "$STAGE/deleted.txt"
echo "overlay files ($NIGHTLY..$BASE under vllm/): $(wc -l < "$STAGE/files.txt")"
echo "deleted between image and base (left stale in the image, harmless): $(wc -l < "$STAGE/deleted.txt")"
echo "non-.py among them: $(grep -vc '\.py$' "$STAGE/files.txt")"

extract_tree() { # $1 = commit, $2 = dest root
  local commit="$1" dest="$2" f
  while IFS= read -r f; do
    mkdir -p "$dest/$(dirname "$f")"
    git -C "$WT" show "$commit:$f" > "$dest/$f"
  done < "$STAGE/files.txt"
}

extract_tree HEAD "$STAGE/patched"
extract_tree "$BASE" "$STAGE/base"

echo "--- files that differ between base and patched overlays ---"
diff -rq "$STAGE/base/vllm" "$STAGE/patched/vllm" || true

mkdir -p "$STAGE/tests/tests/v1/kv_offload"
git -C "$WT" archive HEAD \
  tests/__init__.py tests/v1/__init__.py tests/v1/kv_offload/__init__.py \
  tests/v1/kv_offload/conftest.py tests/v1/kv_offload/tiering \
  | tar -x -C "$STAGE/tests"
cp "$WT/.tmp/stage/run_tests.sh" "$STAGE/run_tests.sh"
echo "--- staged test files: $(find "$STAGE/tests" -name 'test_*.py' | wc -l) ---"
