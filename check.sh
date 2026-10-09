#!/usr/bin/env sh
# Lint, type-check and optionally compile py2gn function files.
#   ./check.sh scripts/my_funcs.py [--compile]
set -eu
root="$(cd "$(dirname "$0")" && pwd)"
compile=0
files=""
for a in "$@"; do
  if [ "$a" = "--compile" ]; then compile=1; else files="$files $(cd "$(dirname "$a")" && pwd)/$(basename "$a")"; fi
done
status=0
echo "== ruff";    "$root/.venv/bin/ruff" check $files || status=1
echo "== pyrefly"; (cd "$root" && .venv/bin/pyrefly check $files --output-format min-text) || status=1
if [ "$compile" = 1 ]; then
  echo "== compile"
  out="$("${BLENDER_BIN:-blender}" --background --factory-startup --quiet --python-exit-code 2 \
    --python "$root/tools/compile_check.py" -- $files 2>&1)" || status=1
  printf '%s\n' "$out" | grep -E ': (ok|error): ' || true
fi
[ "$status" = 0 ] && echo OK || echo FAILED
exit $status
