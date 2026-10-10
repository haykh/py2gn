#!/usr/bin/env sh
# Regenerate the README's checklist of Geometry Nodes (tools/node_checklist.py in a background Blender).
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
"${BLENDER_BIN:-blender}" --background --factory-startup --quiet --python-exit-code 1 \
  --python "$root/tools/node_checklist.py" 2>&1 | grep 'node checklist' || true
