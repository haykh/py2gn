"""Example py2gn functions.

Each top-level ``def`` becomes a Geometry Nodes group of the same name.
Parameters become input sockets (float by default; int, bool, gn.tVec, gn.tGeometry),
defaults become socket defaults, and the return value(s) become outputs:
a tuple of names gives named outputs, or ``return gn.Outputs(a=..., b=...)`` names them.
Built-ins live in the ``gn`` namespace; bare names are your own functions and groups.
"""

import py2gn.lang as gn


def smoothstep(x: float, edge0: float = 0.0, edge1: float = 1.0) -> float:
    """Hermite smoothstep."""
    t = gn.Clamp((x - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def ripple(p: gn.tVec, freq: float = 4.0, amp: float = 0.2, falloff: float = 1.5):
    r = gn.Length(gn.tVec(p.x, p.y, 0))
    h = amp * gn.Sin(gn.Tau * freq * r) * gn.Exp(-falloff * r)
    offset = gn.tVec(0, 0, h)
    return offset, h


def polar(p: gn.tVec):
    r = gn.Sqrt(p.x**2 + p.y**2)
    return gn.Outputs(radius=r, angle=gn.Atan2(p.y, p.x), inside=r < 1 and p.z >= 0)


def fbm_like(p: gn.tVec, gain: float = 0.5):
    # unrolled loop + calling another compiled function
    s = 0.0
    amp = 1.0
    for i in range(4):
        s += amp * smoothstep(gn.Sin(p.x * 2**i) * gn.Cos(p.y * 2**i), -1, 1)
        amp *= gain
    return s


def piecewise(x: float, k: float = 2.0):
    if x < 0:
        y = -x * k
    elif x < 1:
        y = x * x
    else:
        y = 1 + gn.Log(x)
    return y


def neighbor_delta(step: int = 1):
    """Vector from each point to the point `step` indices ahead."""
    return gn.EvaluateAtIndex(gn.Position, gn.Index + step) - gn.Position


def face_avg_offset(strength: float = 1.0):
    # point context: EvaluateOnDomain(Position, "FACE") = mean of the adjacent face centres
    return (gn.EvaluateOnDomain(gn.Position, "FACE") - gn.Position) * strength


def solidify(mesh: gn.tGeometry, thickness: float = 0.1) -> gn.tGeometry:
    # geometry is just another value: each call returns a new geometry
    inner = gn.FlipFaces(mesh)
    outer, _top, side = gn.ExtrudeMesh(mesh, offset=gn.Normal, scale=thickness, individual=False)
    outer = gn.StoreNamedAttribute(outer, "side", side, domain="FACE")
    return gn.JoinGeometry(inner, outer)


def flatten_above_top(mesh: gn.tGeometry, gap: float = 0.5, up: gn.tVec = gn.tVec(0, 0, 1)) -> gn.tGeometry:
    # Attribute Statistic gives single values: move every point to the plane `gap` above the highest one
    zmax = gn.AttributeStatistic(mesh, gn.Position.z, "max")
    return gn.SetPosition(mesh, offset=up * (gap + zmax - gn.Position.z))
