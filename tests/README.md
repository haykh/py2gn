# py2gn tests

The tests start Blender in background mode with factory settings, register the add-on from this checkout, compile functions and evaluate the generated node groups on synthetic geometry, then compare against independent reference values (plain-Python semantics, `statistics`, hand-computed geometry).

## Windows

```powershell
.\scripts\run_tests.ps1 -Blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

`-Blender` may be omitted when `BLENDER_BIN` is set or Blender is on `PATH`; otherwise the newest install under `C:\Program Files\Blender Foundation` is used.

## Linux

```sh
./scripts/run_tests.sh --blender /path/to/blender
```

Run one group with `-Feature <name>` (PowerShell) or `--feature <name>`. The scripts work from any directory; `tests/run_tests.py` can also be called directly with any Python.

| Group | Covers |
| --- | --- |
| `math` | Example value functions vs. the Python reference over random samples (evaluated as fields), interfaces, defaults, constant folding. |
| `fields` | Evaluate at Index, Evaluate on Domain, named attributes, Edge Vertices. |
| `geometry` | Set Position, Store Named Attribute, Join (ordering), Duplicate Elements, Extrude, Flip Faces, Capture, geometry switches, Points to Curves, Set Spline Cyclic, Curve to Mesh, Mesh to Points. |
| `queries` | Bezier Segment / Quadratic Bezier (vs. de Casteljau), Resample Curve, Domain Size, Attribute Statistic, Mesh to Curve, Reverse Curve, Spline Parameter, Is Spline Cyclic. |
| `cleanup` | Separate Geometry (face / point domains, both parts), Delete Geometry (domains, modes, selection on the domain, point clouds), Split Edges (all, selected, round trip with merge), Merge by Distance (ALL / CONNECTED, distance, selection), Remove Named Attribute (exact / wildcard), menu argument checking. |
| `errors` | Error messages and line numbers, cleanup after failures, foreign-group protection, link preservation on recompile. |
| `names` | The naming convention: `lang.py` ↔ compiler name table, alias forms, bare names are yours, hints, migration (exact rewrite, scoping, idempotence). |
| `inline` | `@gn.inline`: no groups created, values vs. reference, generic parameters, nested inlines, outputs, geometry, vector promotion, errors. |
| `boolean` | Mesh Bevel (edges / vertices, per-side offsets, segments, profile, selection, output fields, mode errors); Mesh Boolean: every operation × solver checked by volume, several operands, intersecting edges, argument errors. |
| `topology` | Corners of Vertex/Edge/Face, Face/Vertex of Corner, Edges of Corner, Offset Corner in Face vs. the mesh data; Mesh Circle, Instance on Points (rotation, scale, selection), Realize Instances; Index Switch (values, vectors, geometry, folding); named outputs. |
| `meta` | Compile-time Python: list/enumerate/zip loops, f-string names, comprehensions spread into calls, closures and lambdas, list methods, the wall.py k-gon pattern, error messages. |
| `params` | `gn.Param`: defaults, min/max, subtype, description per input type; constant-expression defaults; reset on recompile with links kept; inline defaults; validation errors. |
| `repeat` | `gn.Repeat` zones: field / value / vector / geometry state, iteration index, parameter and node-computed counts, nested zones, unrolled loops inside, body built once (node counts), vs. Python, errors. |
| `foreach` | `gn.ForEachElement` zones: per-element results as fields, generated geometry with fields, selection, single-value index inside, joined generations, errors. |
| `ui` | Registration, Compile File, the on-save watcher. |
