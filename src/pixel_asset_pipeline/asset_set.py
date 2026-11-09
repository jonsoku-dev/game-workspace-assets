"""Bounded local comparison of build bundles, with no generation or resampling."""

import json
import math
from pathlib import Path
import stat

from PIL import Image, ImageDraw

from .bundle import png_bytes, read_once, sha256, write_json
from .raster import MAX_SIZE, validate
from .spec import nonempty, read_object, rgb


FILES = {"contact_sheet": "contact-sheet.png", "manifest": "manifest.json"}


def _file(path, limit):
    # Follow local aliases, but reject devices and pipes before opening inputs.
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("comparison input must be a bounded regular file")
    return path


def _relative(request_path, value):
    value = nonempty(value, "path")
    if Path(value).is_absolute():
        raise ValueError("comparison paths must be relative to the request")
    return request_path.parent / value


_SOURCES = {}  # reset per produce(); every input is read once, then decoded and hashed from those bytes


def _json(path, fields):
    path = _file(path, 131072)
    return read_object(path, fields, read_once(path, _SOURCES, 131072))


def _hash(path):
    return sha256(read_once(path, _SOURCES, 32 * 1024 * 1024))


def _png(path):
    path = _file(path, 4 * 1024 * 1024)
    return png_bytes(read_once(path, _SOURCES, 4 * 1024 * 1024), max_pixels=MAX_SIZE ** 2)


def produce(request_path: Path, stage: Path) -> dict:
    _SOURCES.clear()
    """Render native-scale pairs at the same pivot, plus a nearest 4x view."""
    request = _json(request_path, {"name", "assets"})
    name = nonempty(request.get("name"), "name")
    if len(name) > 80:
        raise ValueError("comparison name exceeds 80 characters")
    assets = request.get("assets")
    if not isinstance(assets, list) or not 2 <= len(assets) <= 12:
        raise ValueError("comparison requires 2..12 assets")
    rows, records, identifiers = [], [], set()
    for entry in assets:
        if not isinstance(entry, dict) or entry.keys() - {"id", "label", "bundle", "reference"}:
            raise ValueError("invalid comparison asset fields")
        identifier, label = nonempty(entry.get("id"), "id"), nonempty(entry.get("label"), "label")
        if identifier in identifiers or len(identifier) > 64 or len(label) > 80:
            raise ValueError("comparison IDs must be unique and labels bounded")
        identifiers.add(identifier)
        bundle = _relative(request_path, entry.get("bundle"))
        paths = {key: _file(bundle / filename, limit) for key, filename, limit in (
            ("sprite", "asset.png", 4 * 1024 * 1024), ("source", "draft.png", 32 * 1024 * 1024),
            ("metadata", "metadata.json", 131072), ("validation", "validation.json", 131072))}
        metadata = _json(paths["metadata"], {"request", "origin", "generation_prompt", "style_reference_used", "import", "visual_review"})
        spec = metadata.get("request")
        if (not isinstance(spec, dict) or not isinstance(spec.get("palette"), list)
                or not 1 <= len(spec["palette"]) <= 256 or not isinstance(spec.get("kind"), str)):
            raise ValueError("bundle metadata requires a request and palette")
        image = _png(paths["sprite"])
        report = validate(image, spec.get("size"), [rgb(c) for c in spec["palette"]], spec.get("limit"), spec.get("kind"))
        # Build validation reports are deliberately unversioned; inspect their current pixels instead.
        stored = json.loads(read_once(paths["validation"], _SOURCES, 131072))
        if not isinstance(stored, dict) or stored != report or not report["passed"]:
            raise ValueError("bundle validation does not match its current sprite")
        origin = metadata.get("origin")
        if not isinstance(origin, str) or origin not in {"codex-imagegen", "local-draft"}:
            raise ValueError("bundle requires a supported declared origin")
        size, kind = spec["size"], spec["kind"]
        expected = [size / 2, size - 2 if kind == "character" else size / 2]
        import_info = metadata.get("import")
        if not isinstance(import_info, dict) or import_info.get("filter") != "nearest" or import_info.get("pivot_px_from_top_left") != expected:
            raise ValueError("bundle pivot or filter does not match its request")
        pair = [(image, expected)]
        record = {"id": identifier, "label": label, "bundle": entry["bundle"], "declared_origin": origin,
                  "style_reference_used": metadata.get("style_reference_used"),
                  "sha256": {key: _hash(path) for key, path in paths.items()},
                  "pivot_px_from_top_left": expected, "size": size, "validation": report, "visual_review": "pending"}
        if "reference" in entry:
            reference = entry["reference"]
            if not isinstance(reference, dict) or set(reference) != {"path", "provenance"}:
                raise ValueError("reference requires path and provenance")
            provenance = nonempty(reference["provenance"], "reference provenance")
            if len(provenance) > 160:
                raise ValueError("reference provenance exceeds 160 characters")
            path = _relative(request_path, reference["path"])
            exemplar = _png(path)
            if exemplar.size != image.size or exemplar.mode != "RGBA" or not exemplar.getchannel("A").getbbox():
                raise ValueError("reference must be nonempty RGBA at the bundle's native size")
            pair.append((exemplar, expected))
            record["reference"] = {**reference, "sha256": _hash(path), "role": "local-comparison-only"}
        rows.append((label, pair))
        records.append(record)
    extent = max(math.ceil(max(p[0].width, p[0].height)) for _, pair in rows for p in pair)
    cell, row_height = extent + 8, extent * 4 + 40
    sheet = Image.new("RGB", (max(640, cell * 10 + 20), row_height * len(rows) + 30), "#ddd9cf")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), name + " | bundle / local reference | 1x and 4x", fill="#222222")
    for index, (label, pair) in enumerate(rows):
        y = 30 + index * row_height
        draw.text((8, y), label, fill="#222222")
        for column, scale in enumerate((1, 4)):
            for side, (sprite, pivot) in enumerate(pair):
                x = 10 + column * (cell * 2 + 10) + side * cell * scale
                top = y + 22
                # A common pivot within each pair keeps feet/centers aligned without fitting silhouettes.
                anchor = (x + cell * scale // 2, top + (extent - 2 if records[index]["validation"]["metrics"]["kind"] == "character" else extent // 2) * scale)
                enlarged = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
                sheet.paste(enlarged, (round(anchor[0] - pivot[0] * scale), round(anchor[1] - pivot[1] * scale)), enlarged)
    sheet.save(stage / FILES["contact_sheet"])
    sources = [record["sha256"]["source"] for record in records]
    write_json(stage / FILES["manifest"], {"schema_version": 1, "name": name, "request_sha256": _hash(request_path),
               "scales": [1, 4], "filter": "nearest", "visual_review": "pending", "assets": records,
               "distinct_source_count": len(set(sources)), "generation_executed": False,
               "reference_policy": "local exemplars; same-atlas references do not demonstrate independent generation"})
    return FILES.copy()
