"""Exact-size opaque terrain tiles, independently checked without sprite fitting."""
from pathlib import Path

from PIL import Image

from .bundle import open_png, write_json, local_path
from .raster import MAX_SIZE, MIN_SIZE
from .spec import read_object, rgb, nonempty


def validate(image, size, palette, limit):
    """Measure seam contrast against interior contrast; this is not visual approval.

    Opposite edge pixels need not match. A seam fails when its mean RGB channel
    jump exceeds both 8 levels and twice the mean neighboring interior jump.
    """
    image = image.convert("RGBA")
    pixels = image.load()

    def jump(a, b):
        return sum(abs(a[c] - b[c]) for c in range(3)) / 3

    seams = {}
    for axis in ("x", "y"):
        width, height = image.size if axis == "x" else image.size[::-1]

        def pixel(x, y):
            return pixels[x, y] if axis == "x" else pixels[y, x]

        interior = sum(jump(pixel(x, y), pixel(x + 1, y))
                       for y in range(height) for x in range(width - 1)) / max(1, height * (width - 1))
        seam = sum(jump(pixel(width - 1, y), pixel(0, y)) for y in range(height)) / height
        threshold = max(8.0, 2 * interior)
        seams[axis] = {"seam_mean_channel_jump": seam, "interior_mean_channel_jump": interior,
                       "threshold": threshold, "passed": seam <= threshold}
    colors = {color[:3] for _, color in image.getcolors(image.width * image.height)}
    checks = {"exact_square_size": image.size == (size, size),
              "fully_opaque": image.getchannel("A").getextrema() == (255, 255),
              "palette": colors <= set(palette), "color_limit": len(colors) <= limit,
              "seam_heuristic": all(axis["passed"] for axis in seams.values())}
    return {"schema_version": 1, "passed": all(checks.values()), "checks": checks,
            "metrics": {"color_count": len(colors), "seams": seams},
            "edge_assessment": "contrast heuristic only; repeated motifs and perceptual seams require visual review",
            "visual_review": "pending", "engine_integration": "not_checked"}


def produce(request_path: Path, stage: Path) -> dict[str, str]:
    request = read_object(request_path, {"source", "size", "palette", "max_colors"})
    size = request.get("size")
    if type(size) is not int or not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f"tile size must be an integer in {MIN_SIZE}..{MAX_SIZE}")
    limit = request.get("max_colors", 12)
    if type(limit) is not int or not 1 <= limit <= 12:
        raise ValueError("tile max_colors must be an integer in 1..12")
    palette = request.get("palette")
    if not isinstance(palette, list) or not 1 <= len(palette) <= 12:
        raise ValueError("tile palette requires 1..12 hex colors")
    colors = [rgb(color) for color in palette]
    source = local_path(request_path.parent, nonempty(request.get("source"), "source"))
    image = open_png(source, max_pixels=size * size)
    if image.size != (size, size):
        raise ValueError("tile failed validation: exact_square_size")
    image = image.convert("RGBA")
    report = validate(image, size, colors, limit)
    if not report["passed"]:
        raise ValueError(f"tile failed validation: {report['checks']}")
    files = {"tile": "tile.png", "repeat_preview": "repeat.png",
             "metadata": "metadata.json", "validation": "validation.json"}
    image.info.clear()
    image.save(stage / files["tile"])
    repeat = Image.new("RGBA", (size * 3, size * 3))
    for y in range(3):
        for x in range(3):
            repeat.paste(image, (x * size, y * size))
    repeat.resize((size * 12, size * 12), Image.Resampling.NEAREST).save(stage / files["repeat_preview"])
    write_json(stage / files["validation"], report)
    write_json(stage / files["metadata"], {
        "schema_version": 1, "kind": "opaque-terrain-tile", "request": request,
        "origin": "local-source", "size": [size, size], "transform": "none",
        "preview": {"repeats": [3, 3], "zoom": 4, "sampling": "nearest"},
        "files": files, "visual_review": "pending", "engine_integration": "not_checked"})
    return files
