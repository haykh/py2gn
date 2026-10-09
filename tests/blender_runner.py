from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

FEATURE_MODULES = {
    "math": "tests.test_math",
    "fields": "tests.test_fields",
    "geometry": "tests.test_geometry",
    "queries": "tests.test_queries",
    "cleanup": "tests.test_cleanup",
    "errors": "tests.test_errors",
    "names": "tests.test_names",
    "inline": "tests.test_inline",
    "boolean": "tests.test_boolean",
    "topology": "tests.test_topology",
    "meta": "tests.test_meta",
    "params": "tests.test_params",
    "repeat": "tests.test_repeat",
    "ui": "tests.test_ui",
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-root", required=True)
    parser.add_argument("--feature", default="all")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--keep-artifacts", action="store_true")
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(args)


def main() -> int:
    args = _arguments()
    addon_root = Path(args.addon_root).resolve()
    if addon_root.name != "py2gn":
        raise RuntimeError(f"Expected add-on directory named 'py2gn', got {addon_root}")

    sys.path.insert(0, str(addon_root.parent))
    sys.path.insert(0, str(addon_root))
    os.environ["PY2GN_TEST_ARTIFACTS"] = str(Path(args.artifacts).resolve())
    os.environ["PY2GN_TEST_KEEP_ARTIFACTS"] = "1" if args.keep_artifacts else "0"

    import py2gn

    py2gn.register()

    selected = list(FEATURE_MODULES) if args.feature == "all" else [args.feature]
    unknown = set(selected) - set(FEATURE_MODULES)
    if unknown:
        raise ValueError(f"Unknown feature(s): {', '.join(sorted(unknown))}")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for feature in selected:
        suite.addTests(loader.loadTestsFromName(FEATURE_MODULES[feature]))

    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        py2gn.unregister()


if __name__ == "__main__":
    raise SystemExit(main())
