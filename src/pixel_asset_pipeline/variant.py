"""Exact-pixel equipment variants; never resize or recolor the approved base."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from .bundle import open_png, write_json
from .raster import MAX_SIZE, validate
from .spec import nonempty, read_object, rgb


def _pair(value, label):
    if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value):
        raise ValueError(f"{label} requires two integers")
    return value


def _rect(value, size, label):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) is not int for v in value)):
        raise ValueError(f"{label} requires four integers")
    left, top, right, bottom = value
    if not 0 <= left < right <= size or not 0 <= top < bottom <= size:
        raise ValueError(f"{label} must be a nonempty rectangle inside the canvas")
    return value


def _inside(x, y, rect):
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]


def _path(request_path, value, label):
    name = nonempty(value, label)
    if Path(name).is_absolute():
        raise ValueError(f"{label} requires a relative local filename")
    return request_path.parent / name


def produce(request_path: Path, stage: Path) -> dict[str, str]:
    """Compose an overlay at anchor + offset, both in top-left canvas pixels."""
    request = read_object(request_path, {
        "base", "base_metadata", "equipment", "anchor", "offset", "allowed_region", "allowed_occlusion",
    })
    base_path = _path(request_path, request.get("base"), "base")
    metadata_path = _path(request_path, request.get("base_metadata"), "base_metadata")
    base = open_png(base_path, max_pixels=MAX_SIZE ** 2)
    with metadata_path.open(encoding="utf-8") as file:
        metadata = json.load(file)
    if not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 1:
        raise ValueError("base metadata requires schema_version 1")
    spec = metadata.get("request")
    if not isinstance(spec, dict) or spec.get("kind") != "character":
        raise ValueError("base metadata requires a character request")
    size, limit, palette = spec.get("size"), spec.get("limit"), spec.get("palette")
    if not isinstance(palette, list):
        raise ValueError("base metadata requires a palette")
    palette = [rgb(color) for color in palette]
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError("base character color limit must be in 1..16")
    report = validate(base, size, palette, limit, "character")
    if not report["passed"]:
        raise ValueError("base fails character validation")
    import_settings = metadata.get("import")
    if not isinstance(import_settings, dict) or import_settings.get("filter") != "nearest":
        raise ValueError("base metadata requires import settings")
    pivot = import_settings.get("pivot_px_from_top_left")
    if (not isinstance(pivot, list) or len(pivot) != 2
            or any(type(v) not in (int, float) for v in pivot)
            or pivot != [size / 2, size - 2]):
        raise ValueError("base metadata must retain the centered foot pivot")
    result = base.copy()
    equipment_path = None
    changed = []
    region = None
    if "equipment" in request:
        equipment_path = _path(request_path, request["equipment"], "equipment")
        equipment = open_png(equipment_path, max_pixels=size * size)
        if equipment.mode != "RGBA" or not equipment.getchannel("A").getbbox():
            raise ValueError("equipment requires nonempty RGBA pixels")
        anchor = _pair(request.get("anchor"), "anchor")
        if any(v < 0 or v >= size for v in anchor):
            raise ValueError("anchor must be inside the canvas")
        offset = _pair(request.get("offset"), "offset")
        region = _rect(request.get("allowed_region"), size, "allowed_region")
        occlusion = request.get("allowed_occlusion")
        if not isinstance(occlusion, list):
            raise ValueError("allowed_occlusion requires a list of rectangles")
        occlusion = [_rect(rect, size, "allowed_occlusion") for rect in occlusion]
        approved = {pixel[:3] for _, pixel in base.getcolors(size * size) if pixel[3]}
        origin = [a + b for a, b in zip(anchor, offset)]
        if (origin[0] < 0 or origin[1] < 0 or origin[0] + equipment.width > size
                or origin[1] + equipment.height > size):
            raise ValueError("equipment canvas clips the base canvas")
        for sy in range(equipment.height):
            for sx in range(equipment.width):
                pixel = equipment.getpixel((sx, sy))
                if pixel[3] not in (0, 255):
                    raise ValueError("equipment requires binary alpha")
                if not pixel[3]:
                    continue
                if pixel[:3] not in approved:
                    raise ValueError("equipment color is outside the approved base palette")
                x, y = origin[0] + sx, origin[1] + sy
                if not 0 < x < size - 1 or not 0 < y < size - 1:
                    raise ValueError("equipment clips the canvas or touches its edge")
                if not _inside(x, y, region):
                    raise ValueError("equipment is outside allowed_region")
                previous = base.getpixel((x, y))
                if previous[3] and not any(_inside(x, y, rect) for rect in occlusion):
                    raise ValueError("equipment occludes base outside allowed_occlusion")
                if previous != pixel:
                    if y >= size - 3:
                        raise ValueError("equipment changes the foot baseline")
                    result.putpixel((x, y), pixel)
                    changed.append((x, y))
        if not changed:
            raise ValueError("equipment makes no visible change")
    elif request.keys() & {"anchor", "offset", "allowed_region", "allowed_occlusion"}:
        raise ValueError("placement fields require equipment")
    report = validate(result, size, palette, limit, "character")
    unchanged = all(result.getpixel((x, y)) == base.getpixel((x, y))
                    for y in range(size) for x in range(size)
                    if region is None or not _inside(x, y, region))
    baseline = result.crop((0, size - 3, size, size)).tobytes() == base.crop((0, size - 3, size, size)).tobytes()
    report["schema_version"] = 1
    report["checks"].update({"base_pixels_outside_authorized_region": unchanged, "foot_pixels_unchanged": baseline})
    report["metrics"]["changed_pixels"] = len(changed)
    report["passed"] = all(report["checks"].values())
    if not report["passed"]:
        raise ValueError("equipment variant fails validation")
    stage.mkdir(parents=True, exist_ok=True)
    result.save(stage / "asset.png")
    result.resize((size * 8, size * 8), Image.Resampling.NEAREST).save(stage / "preview.png")
    write_json(stage / "validation.json", report)
    write_json(stage / "metadata.json", {
        "schema_version": 1, "request": spec, "variant_request": request,
        "origin": "local-equipment-overlay" if equipment_path else "approved-base-copy",
        "base_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "equipment_sha256": hashlib.sha256(equipment_path.read_bytes()).hexdigest() if equipment_path else None,
        "base_visible_bounds": report["metrics"]["visible_bounds"] if not equipment_path else list(base.getchannel("A").getbbox()),
        "import": metadata["import"], "visual_review": "pending",
    })
    return {"asset": "asset.png", "preview": "preview.png", "metadata": "metadata.json", "validation": "validation.json"}
