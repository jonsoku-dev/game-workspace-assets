"""Versioned asset requests and reusable game art profiles."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .raster import MAX_SIZE, MIN_SIZE


PRESETS = {"character": (48, 16), "icon": (24, 12), "item": (32, 24)}
DEFAULT_PALETTE = (
    "#212333 #433844 #714d46 #976450 #c36643 #d69875 #f6dfae #fff1d0 "
    "#33463d #64754b #99aa69 #cad58d #2e4b56 #487178 #6aa99c #b1d3bc "
    "#42445b #566480 #929bb0 #cabfbd #986141 #bd8646 #e5ad57 #f8ce81"
).split()
STYLE_FIELDS = {"palette", "style", "view", "outline"}


def read_object(path, allowed):
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError(f"{path.name} requires schema_version 1")
    unknown = data.keys() - allowed - {"schema_version"}
    if unknown:
        raise ValueError(f"unknown field(s) in {path.name}: {', '.join(sorted(unknown))}")
    return data


def rgb(color):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("colors must use #RRGGBB")
    return tuple(bytes.fromhex(color[1:]))


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} requires nonempty text")
    return value.strip()


@dataclass(frozen=True)
class Request:
    kind: str
    prompt: str
    size: int
    limit: int
    palette: list
    style: str
    view: str
    outline: str | None

    @classmethod
    def load(cls, path: Path):
        request = read_object(path, STYLE_FIELDS | {"kind", "prompt", "size", "max_colors", "profile"})
        profile = {}
        if "profile" in request:
            profile_path = path.parent / nonempty(request["profile"], "profile")
            profile = read_object(profile_path, STYLE_FIELDS)
        fields = {**profile, **request}
        kind = fields.get("kind")
        if not isinstance(kind, str) or kind not in PRESETS:
            raise ValueError("kind must be character, icon or item")
        default_size, cap = PRESETS[kind]
        size = fields.get("size", default_size)
        limit = fields.get("max_colors", cap)
        if type(size) is not int or not MIN_SIZE <= size <= MAX_SIZE:
            raise ValueError(f"size must be an integer in {MIN_SIZE}..{MAX_SIZE}")
        if type(limit) is not int or not 1 <= limit <= cap:
            raise ValueError(f"max_colors for {kind} must be an integer in 1..{cap}")
        palette = fields.get("palette", DEFAULT_PALETTE)
        if not isinstance(palette, list) or not 1 <= len(palette) <= 256:
            raise ValueError("palette requires 1..256 hex colors")
        for color in palette:
            rgb(color)
        palette = list(dict.fromkeys(c.lower() for c in palette))
        outline = fields.get("outline")
        if outline is not None:
            rgb(outline)
            outline = outline.lower()
            if outline not in palette:
                raise ValueError("outline must occur in the palette")
        return cls(kind, nonempty(fields.get("prompt"), "prompt"), size, limit, palette,
                   nonempty(fields.get("style", "Bold hand-placed pixel clusters, upper-left light"), "style"),
                   nonempty(fields.get("view", "front three-quarter"), "view"), outline)

    def raster_args(self):
        return self.size, [rgb(c) for c in self.palette], self.limit, self.kind

    def art_direction(self, has_reference=False):
        return (f"One standalone {self.kind} sprite: {self.prompt}\n"
                f"STYLE: {self.style}\nVIEW: {self.view}\n"
                f"OUTLINE: {self.outline or 'clean selective dark contour'}, readable at {self.size}px. "
                f"Use at most {self.limit} colors from {' '.join(self.palette)}.\n"
                "BACKGROUND: actual transparency. Keep the whole subject inside the box; the attached "
                "layout is a placement guide only. Omit the box and baseline from the artwork. "
                "No letters, logos, red cross symbols, dithering, particles, or ground shadow."
                + (" Image 1 is the placement guide. Match Image 2 for the scale of pixel clusters, "
                   "head-to-body ratio, outline weight, and shape language; draw the requested subject."
                   if has_reference else ""))
