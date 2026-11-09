"""Schema-version-2 parametric assembly requests: validation without Blender.

An assembly is a hierarchy of named parametric parts and pivots in meters (Blender Z-up),
each part with a library material that is baked to PBR textures, optional rigid
animations on parts or pivots, LOD ratios and quality budgets. The Blender worker builds
it; this module only admits well-formed, bounded requests.
"""
import math
import re

SHAPES = {
    "box": {"size_m"},
    "cylinder": {"radius_m", "depth_m"},
    "tube": {"outer_radius_m", "inner_radius_m", "depth_m"},
    "saw_blade": {"radius_m", "thickness_m", "teeth", "tooth_depth_m", "bore_radius_m"},
    "extrude": {"profile_m", "depth_m"},
    "arc": {"inner_radius_m", "outer_radius_m", "depth_m", "start_deg", "end_deg"},
    "lathe": {"profile_m"},
}
OPTIONAL_SHAPE = {"segments"}
PART_KEYS = {"id", "shape", "material", "parent", "position_m", "rotation_deg", "bevel_m", "free",
             "exploded_offset_m"}
MATERIAL_KEYS = {"base", "metallic", "roughness", "wear", "edge", "grain", "grain_scale", "emission",
                 "emission_strength", "dirt"}
GRAINS = {"none", "noise", "brushed", "cast"}
TOP_KEYS = {"schema_version", "name", "materials", "parts", "pivots", "animations", "lod_ratios", "budget",
            "expected_size_m", "texel_density_px_per_m", "bake_samples"}
IDENT = re.compile(r"[a-z][a-z0-9_]{0,47}")
FPS = 30  # animation sampling rate used by the Blender worker and glTF export
MAX_SPIN_DEG_PER_FRAME = 120
LIMITS = {"parts": 64, "pivots": 32, "animations": 16, "keys": 64, "profile": 128}


def _number(value, label, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be a number from {low} to {high}")
    return float(value)


def _vector(value, label, low=-50, high=50, size=3):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must be a list of {size} numbers")
    return [_number(v, label, low, high) for v in value]


def _color(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"{label} must be #RRGGBB")
    return value.lower()


def _ident(value, label):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError(f"{label} must match [a-z][a-z0-9_]* (max 48)")
    return value


def _material(name, spec):
    if not isinstance(spec, dict) or spec.keys() - MATERIAL_KEYS or "base" not in spec:
        raise ValueError(f"material {name}: needs base and may set {', '.join(sorted(MATERIAL_KEYS - {'base'}))}")
    out = {"base": _color(spec["base"], f"{name}.base"),
           "metallic": _number(spec.get("metallic", 0.0), f"{name}.metallic", 0, 1),
           "roughness": _number(spec.get("roughness", 0.5), f"{name}.roughness", 0.02, 1),
           "wear": _number(spec.get("wear", 0.0), f"{name}.wear", 0, 1),
           "dirt": _number(spec.get("dirt", 0.0), f"{name}.dirt", 0, 1),
           "grain": spec.get("grain", "noise"),
           "grain_scale": _number(spec.get("grain_scale", 40), f"{name}.grain_scale", 1, 2000),
           "emission_strength": _number(spec.get("emission_strength", 0.0), f"{name}.emission_strength", 0, 50)}
    if out["grain"] not in GRAINS:
        raise ValueError(f"material {name}: grain must be one of {sorted(GRAINS)}")
    out["edge"] = _color(spec.get("edge", "#9aa3a6"), f"{name}.edge")
    if "emission" in spec:
        out["emission"] = _color(spec["emission"], f"{name}.emission")
    return out


def _profile(value, label, closed_min=3):
    if not isinstance(value, list) or not closed_min <= len(value) <= LIMITS["profile"]:
        raise ValueError(f"{label} must list {closed_min}..{LIMITS['profile']} points")
    points = [tuple(_vector(p, label, -50, 50, 2)) for p in value]
    if len(set(points)) != len(points):
        raise ValueError(f"{label} repeats a point")
    return [list(p) for p in points]


def _shape(part):
    shape, label = part["shape"], f"part {part['id']}"
    params = {}
    for key in SHAPES[shape]:
        if key not in part:
            raise ValueError(f"{label}: {shape} needs {key}")
    if shape == "box":
        params["size_m"] = _vector(part["size_m"], f"{label}.size_m", 0.001, 50)
    elif shape == "cylinder":
        params.update(radius_m=_number(part["radius_m"], f"{label}.radius_m", 0.0005, 25),
                      depth_m=_number(part["depth_m"], f"{label}.depth_m", 0.0005, 50))
    elif shape == "tube":
        params.update(outer_radius_m=_number(part["outer_radius_m"], f"{label}.outer_radius_m", 0.001, 25),
                      inner_radius_m=_number(part["inner_radius_m"], f"{label}.inner_radius_m", 0.0005, 25),
                      depth_m=_number(part["depth_m"], f"{label}.depth_m", 0.0005, 50))
        if params["inner_radius_m"] >= params["outer_radius_m"]:
            raise ValueError(f"{label}: inner_radius_m must be smaller than outer_radius_m")
    elif shape == "saw_blade":
        params.update(radius_m=_number(part["radius_m"], f"{label}.radius_m", 0.01, 10),
                      thickness_m=_number(part["thickness_m"], f"{label}.thickness_m", 0.0005, 1),
                      tooth_depth_m=_number(part["tooth_depth_m"], f"{label}.tooth_depth_m", 0.0005, 1),
                      bore_radius_m=_number(part["bore_radius_m"], f"{label}.bore_radius_m", 0.0005, 5))
        teeth = part["teeth"]
        if type(teeth) is not int or not 6 <= teeth <= 240:
            raise ValueError(f"{label}: teeth must be an integer from 6 to 240")
        params["teeth"] = teeth
        if not params["bore_radius_m"] < params["radius_m"] - params["tooth_depth_m"]:
            raise ValueError(f"{label}: bore must fit inside the tooth root")
    elif shape == "extrude":
        params.update(profile_m=_profile(part["profile_m"], f"{label}.profile_m"),
                      depth_m=_number(part["depth_m"], f"{label}.depth_m", 0.0005, 50))
    elif shape == "arc":
        params.update(inner_radius_m=_number(part["inner_radius_m"], f"{label}.inner_radius_m", 0.0005, 25),
                      outer_radius_m=_number(part["outer_radius_m"], f"{label}.outer_radius_m", 0.001, 25),
                      depth_m=_number(part["depth_m"], f"{label}.depth_m", 0.0005, 50),
                      start_deg=_number(part["start_deg"], f"{label}.start_deg", -360, 360),
                      end_deg=_number(part["end_deg"], f"{label}.end_deg", -360, 360))
        if params["inner_radius_m"] >= params["outer_radius_m"]:
            raise ValueError(f"{label}: inner_radius_m must be smaller than outer_radius_m")
        if not 1 <= params["end_deg"] - params["start_deg"] <= 359:
            raise ValueError(f"{label}: arc span (end_deg - start_deg) must be 1..359 degrees")
    elif shape == "lathe":
        params["profile_m"] = _profile(part["profile_m"], f"{label}.profile_m", 2)
        if any(r < 0 for r, _ in params["profile_m"]):
            raise ValueError(f"{label}: lathe radii must be non-negative")
    segments = part.get("segments", 48 if shape in ("cylinder", "tube", "arc", "lathe") else 0)
    if shape in ("cylinder", "tube", "arc", "lathe"):
        if type(segments) is not int or not 6 <= segments <= 256:
            raise ValueError(f"{label}: segments must be an integer from 6 to 256")
        params["segments"] = segments
    elif "segments" in part:
        raise ValueError(f"{label}: segments applies to round shapes only")
    return params


def _animation(item, targets):
    if not isinstance(item, dict) or item.keys() - {"name", "target", "loop", "spin", "keys", "interpolation"}:
        raise ValueError("animations take name, target, loop and either spin or keys")
    name = _ident(item.get("name"), "animation name")
    target = item.get("target")
    if target not in targets:
        raise ValueError(f"animation {name}: target must name a part or pivot")
    loop = item.get("loop", False)
    if type(loop) is not bool:
        raise ValueError(f"animation {name}: loop must be boolean")
    interpolation = item.get("interpolation", "linear")
    if interpolation not in ("linear", "smooth"):
        raise ValueError(f"animation {name}: interpolation must be linear or smooth")
    if ("spin" in item) == ("keys" in item):
        raise ValueError(f"animation {name}: choose spin or keys")
    out = {"name": name, "target": target, "loop": loop, "interpolation": interpolation}
    if "spin" in item:
        spin = item["spin"]
        if not isinstance(spin, dict) or set(spin) != {"axis", "rpm", "duration_s"} or spin["axis"] not in ("x", "y", "z"):
            raise ValueError(f"animation {name}: spin is {{axis: x|y|z, rpm, duration_s}}")
        out["spin"] = {"axis": spin["axis"], "rpm": _number(spin["rpm"], f"{name}.rpm", -6000, 6000),
                       "duration_s": _number(spin["duration_s"], f"{name}.duration_s", 0.05, 60)}
        if out["spin"]["rpm"] == 0:
            raise ValueError(f"animation {name}: rpm must be nonzero")
        per_frame = abs(out["spin"]["rpm"]) * 360 / 60 / FPS
        if per_frame > MAX_SPIN_DEG_PER_FRAME:
            raise ValueError(f"animation {name}: {out['spin']['rpm']:g} rpm turns {per_frame:.0f} deg per {FPS} fps frame; "
                             f"above {MAX_SPIN_DEG_PER_FRAME} deg the spin reads as stopped or backwards. "
                             f"Use at most {MAX_SPIN_DEG_PER_FRAME * FPS * 60 / 360:.0f} rpm and sell speed with blur or sparks")
        turns = out["spin"]["rpm"] * out["spin"]["duration_s"] / 60
        if loop and abs(turns - round(turns)) > 1e-6:
            raise ValueError(f"animation {name}: a looping spin must make whole turns "
                             f"(rpm x duration_s / 60 = {turns:.4f}); adjust duration_s")
        return out
    keys = item["keys"]
    if not isinstance(keys, list) or not 2 <= len(keys) <= LIMITS["keys"]:
        raise ValueError(f"animation {name}: keys must list 2..{LIMITS['keys']} poses")
    parsed, last = [], -1.0
    for key in keys:
        if not isinstance(key, dict) or "t" not in key or key.keys() - {"t", "position_m", "rotation_deg"} \
                or not key.keys() & {"position_m", "rotation_deg"}:
            raise ValueError(f"animation {name}: each key is {{t, position_m?, rotation_deg?}}")
        t = _number(key["t"], f"{name}.t", 0, 60)
        if t <= last:
            raise ValueError(f"animation {name}: key times must increase")
        last = t
        entry = {"t": t}
        if "position_m" in key:
            entry["position_m"] = _vector(key["position_m"], f"{name}.position_m")
        if "rotation_deg" in key:
            entry["rotation_deg"] = _vector(key["rotation_deg"], f"{name}.rotation_deg", -3600, 3600)
        parsed.append(entry)
    channels = [set(k) - {"t"} for k in parsed]
    if any(c != channels[0] for c in channels):
        raise ValueError(f"animation {name}: every key must set the same channels")
    out["keys"] = parsed
    return out


def validate(spec):
    """Return a normalised schema-version-2 assembly or raise ValueError with the first problem."""
    if not isinstance(spec, dict) or spec.get("schema_version") != 2 or type(spec.get("schema_version")) is not int:
        raise ValueError("Expected schema_version 2 assembly object")
    if spec.keys() - TOP_KEYS:
        raise ValueError("Unknown assembly keys: " + ", ".join(sorted(spec.keys() - TOP_KEYS)))
    if not isinstance(spec.get("name"), str) or not spec["name"].strip():
        raise ValueError("Name required")
    materials = spec.get("materials")
    if not isinstance(materials, dict) or not 1 <= len(materials) <= 32:
        raise ValueError("materials must define 1..32 named materials")
    library = {_ident(name, "material name"): _material(name, value) for name, value in materials.items()}
    pivots = spec.get("pivots", [])
    parts = spec.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= LIMITS["parts"]:
        raise ValueError(f"parts must list 1..{LIMITS['parts']} parts")
    if not isinstance(pivots, list) or len(pivots) > LIMITS["pivots"]:
        raise ValueError(f"pivots must list at most {LIMITS['pivots']} pivots")
    nodes, order = {}, []
    for pivot in pivots:
        if not isinstance(pivot, dict) or pivot.keys() - {"id", "parent", "position_m", "rotation_deg"}:
            raise ValueError("pivots take id, parent, position_m and rotation_deg")
        ident = _ident(pivot.get("id"), "pivot id")
        if ident in nodes:
            raise ValueError(f"duplicate id {ident}")
        nodes[ident] = {"id": ident, "kind": "pivot", "parent": pivot.get("parent"),
                        "position_m": _vector(pivot.get("position_m", [0, 0, 0]), f"{ident}.position_m"),
                        "rotation_deg": _vector(pivot.get("rotation_deg", [0, 0, 0]), f"{ident}.rotation_deg", -360, 360)}
        order.append(ident)
    for part in parts:
        if not isinstance(part, dict) or part.get("shape") not in SHAPES:
            raise ValueError(f"each part needs a shape from {sorted(SHAPES)}")
        extra = part.keys() - PART_KEYS - SHAPES[part["shape"]] - OPTIONAL_SHAPE
        if extra:
            raise ValueError(f"part {part.get('id')}: unknown keys {sorted(extra)}")
        ident = _ident(part.get("id"), "part id")
        if ident in nodes:
            raise ValueError(f"duplicate id {ident}")
        if part.get("material") not in library:
            raise ValueError(f"part {ident}: material must name a defined material")
        free = part.get("free", False)
        if type(free) is not bool:
            raise ValueError(f"part {ident}: free must be boolean")
        nodes[ident] = {"id": ident, "kind": "part", "shape": part["shape"], "material": part["material"],
                        "parent": part.get("parent"), "free": free,
                        "position_m": _vector(part.get("position_m", [0, 0, 0]), f"{ident}.position_m"),
                        "rotation_deg": _vector(part.get("rotation_deg", [0, 0, 0]), f"{ident}.rotation_deg", -360, 360),
                        "bevel_m": _number(part.get("bevel_m", 0.0), f"{ident}.bevel_m", 0, 0.5),
                        "exploded_offset_m": _vector(part.get("exploded_offset_m", [0, 0, 0]), f"{ident}.exploded_offset_m"),
                        **_shape(part)}
        order.append(ident)
    for ident in order:
        parent = nodes[ident]["parent"]
        if parent is not None and parent not in nodes:
            raise ValueError(f"{ident}: parent must name a part or pivot")
    for ident in order:  # reject cycles through pivots declared before their parents
        seen, current = set(), ident
        while current is not None:
            if current in seen:
                raise ValueError(f"{ident}: parent cycle")
            seen.add(current)
            current = nodes[current]["parent"]
    animations = spec.get("animations", [])
    if not isinstance(animations, list) or len(animations) > LIMITS["animations"]:
        raise ValueError(f"animations must list at most {LIMITS['animations']} entries")
    parsed_animations = [_animation(item, nodes) for item in animations]
    if len({a["name"] for a in parsed_animations}) != len(parsed_animations):
        raise ValueError("animation names must be unique")
    lods = spec.get("lod_ratios", [])
    if not isinstance(lods, list) or len(lods) > 3:
        raise ValueError("lod_ratios lists at most 3 decimation ratios")
    lods = [_number(r, "lod ratio", 0.05, 0.95) for r in lods]
    if lods != sorted(lods, reverse=True) or len(set(lods)) != len(lods):
        raise ValueError("lod_ratios must strictly decrease")
    budget = spec.get("budget", {})
    if not isinstance(budget, dict) or budget.keys() - {"triangles", "texture_px"}:
        raise ValueError("budget takes triangles and texture_px")
    triangles = budget.get("triangles", 60000)
    texture_px = budget.get("texture_px", 1024)
    if type(triangles) is not int or not 100 <= triangles <= 500000:
        raise ValueError("budget.triangles must be an integer from 100 to 500000")
    if texture_px not in (128, 256, 512, 1024, 2048):
        raise ValueError("budget.texture_px must be 128, 256, 512, 1024 or 2048")
    density = spec.get("texel_density_px_per_m", 512)
    if type(density) is not int or not 32 <= density <= 4096:
        raise ValueError("texel_density_px_per_m must be an integer from 32 to 4096")
    samples = spec.get("bake_samples", 16)
    if type(samples) is not int or not 1 <= samples <= 256:
        raise ValueError("bake_samples must be an integer from 1 to 256")
    expected = spec.get("expected_size_m")
    if expected is not None:
        expected = _vector(expected, "expected_size_m", 0.001, 100)
    return {"schema_version": 2, "name": spec["name"].strip(), "materials": library,
            "nodes": [nodes[i] for i in order], "animations": parsed_animations, "lod_ratios": lods,
            "budget": {"triangles": triangles, "texture_px": texture_px}, "expected_size_m": expected,
            "texel_density_px_per_m": density, "bake_samples": samples}
