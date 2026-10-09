#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."  # the checkout is the parent of scripts/
uv venv .venv --python 3.13 --allow-existing
uv pip install --python .venv/bin/python -r requirements.txt
site="$(.venv/bin/python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
dirname "$(pwd)" > "$site/py2gn_dev.pth"
echo "Ready: .venv/bin/python"
