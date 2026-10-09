"""Plain-Python reference semantics of the language (used by tests)."""

from __future__ import annotations

import ast
import math
import types
from typing import Any

from .names import CONSTANTS, CONSTRUCTORS, MATH, SPECIAL, find_aliases
from .tables import CONSTS, fmod_floor, sign_of


def reference_namespace() -> dict[str, object]:
    """Namespace in which the same source runs as plain Python (mathutils.Vector for vec)."""
    from mathutils import Vector

    def _vec(*a):
        return Vector((a[0],) * 3) if len(a) == 1 else Vector(a)

    def _fract(x):
        return x - math.floor(x)

    def _clamp(x, lo=0.0, hi=1.0):
        return min(max(x, lo), hi)

    ns: dict[str, object] = dict(CONSTS)
    ns.update(
        vec=_vec,
        Vector=_vec,
        vec3=_vec,
        sin=math.sin,
        cos=math.cos,
        tan=math.tan,
        asin=math.asin,
        acos=math.acos,
        atan=math.atan,
        atan2=math.atan2,
        sinh=math.sinh,
        cosh=math.cosh,
        tanh=math.tanh,
        sqrt=math.sqrt,
        exp=math.exp,
        log=math.log,
        floor=math.floor,
        ceil=math.ceil,
        trunc=math.trunc,
        fract=_fract,
        sign=sign_of,
        radians=math.radians,
        degrees=math.degrees,
        clamp=_clamp,
        lerp=lambda a, b, t: a + (b - a) * t,
        outputs=lambda **kw: tuple(kw.values()) if len(kw) > 1 else next(iter(kw.values())),
        mix=lambda a, b, t: a + (b - a) * t,
        length=lambda v: v.length,
        dot=lambda a, b: a.dot(b),
        cross=lambda a, b: a.cross(b),
        normalize=lambda v: v.normalized(),
        distance=lambda a, b: (a - b).length,
        float=float,
        int=int,
        bool=bool,
        vec_t=Vector,
    )
    return ns


def reference_gn() -> types.SimpleNamespace:
    """The public ``gn`` namespace with plain-Python semantics (fields are not available)."""
    from mathutils import Vector

    ns = reference_namespace()
    extra = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "pow": pow,
        "fmod": math.fmod,
        "mod": fmod_floor,
        "inversesqrt": lambda x: 1.0 / math.sqrt(x),
    }
    attrs: dict[str, object] = {}
    for pub, internal in {**MATH, **CONSTRUCTORS, **SPECIAL, **CONSTANTS}.items():
        value = ns.get(internal, extra.get(internal))
        if value is not None:
            attrs[pub] = value
    attrs.update(tFloat=float, tInt=int, tBool=bool, tVec=ns["vec"], tGeometry=object)
    attrs["Vector"] = Vector
    attrs["inline"] = lambda fn: fn
    attrs["Param"] = lambda default=None, **_meta: default
    return types.SimpleNamespace(**attrs)


def reference_functions(src: str) -> dict[str, Any]:
    """Execute only the ``def``s of ``src`` with ``gn`` bound to the reference namespace.

    Imports and other top-level statements are skipped, mirroring what the compiler reads;
    the namespace is bound under every alias the file imports ``py2gn.lang`` as.
    """
    tree = ast.parse(src)
    aliases = find_aliases(tree)
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    gn = reference_gn()
    env: dict[str, Any] = {}
    for alias in aliases:
        head, *rest = alias.split(".")
        if not rest:
            env[head] = gn
        else:  # `import py2gn.lang` -> py2gn.lang.X
            env[head] = types.SimpleNamespace(lang=gn)
    exec(compile(tree, "<py2gn reference>", "exec"), env)  # noqa: S102 - by design
    return env
