"""Compile py2gn function files inside (background) Blender and report the result.

Run by check.ps1 / check.sh:
    blender --background --factory-startup --python tools/compile_check.py -- FILE [FILE ...]

Errors are printed as ``path:line: error: message`` (clickable in most terminals/IDEs);
the exit code is 1 if any file fails to compile.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    files = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root.parent))

    from py2gn.compiler import GNCompileError, gn_compile

    failed = 0
    for name in files:
        path = Path(name).resolve()
        try:
            groups = gn_compile(path.read_text(encoding="utf-8"))
        except GNCompileError as ex:
            print(f"{path}:{ex.lineno or 1}: error: {ex.msg}")
            failed += 1
            continue
        except SyntaxError as ex:
            print(f"{path}:{ex.lineno or 1}: error: SyntaxError: {ex.msg}")
            failed += 1
            continue
        for g in groups:
            sockets = [i for i in g.interface.items_tree if i.item_type == "SOCKET"]
            ins = ", ".join(i.name for i in sockets if i.in_out == "INPUT")
            outs = ", ".join(i.name for i in sockets if i.in_out == "OUTPUT")
            print(f"{path}: ok: {g.name}({ins}) -> {outs}  [{len(g.nodes)} nodes]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
