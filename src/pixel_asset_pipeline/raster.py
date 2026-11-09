"""Deterministic raster preparation and independent asset validation."""

from collections import Counter
import math

from PIL import Image, ImageChops, ImageFilter, ImageOps


MIN_SIZE = 8
MAX_SIZE = 256
KINDS = {"character", "icon", "item"}


def _options(size, palette, limit, kind):
    if type(size) is not int or not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f"size must be an integer from {MIN_SIZE} to {MAX_SIZE}")
    if kind not in KINDS:
        raise ValueError("kind must be character, icon, or item")
    if not palette or len(palette) > 256:
        raise ValueError("palette must contain 1 to 256 RGB colors")
    for color in palette:
        if len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
            raise ValueError("palette colors must be RGB integers from 0 to 255")
    colors = list(dict.fromkeys(tuple(color) for color in palette))
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError("limit must be an integer from 1 to 256")
    return colors


def _isolated(image):
    alpha = image.getchannel("A").point(lambda a: 255 if a else 0)
    padded = ImageOps.expand(alpha, border=1)
    neighbors = padded.filter(ImageFilter.Kernel((3, 3), (1, 1, 1, 1, 0, 1, 1, 1, 1), scale=1))
    neighbors = neighbors.crop((1, 1, image.width + 1, image.height + 1))
    return ImageChops.multiply(alpha, ImageChops.invert(neighbors))


def _remove_isolated(image):
    image.putalpha(ImageChops.subtract(image.getchannel("A"), _isolated(image)))


def process(image: Image.Image, size: int, palette: list[tuple[int, int, int]],
            limit: int, kind: str, outline: tuple[int, int, int] | None = None) -> Image.Image:
    """Fit a transparent draft to a pixel canvas without guessing its background.

    Alpha is thresholded at 128; outlines are only added when explicitly requested.
    Colors nearest to the supplied palette are ranked by frequency when a
    smaller color limit is requested. Palette order breaks equal-distance ties.
    """
    colors = _options(size, palette, limit, kind)
    if outline is not None:
        outline = tuple(outline)
        if outline not in colors:
            raise ValueError("outline must be a supplied palette color")
    rgba = image.convert("RGBA")
    low, high = rgba.getchannel("A").getextrema()
    if high == 0:
        raise ValueError("draft is empty")
    if low == 255:
        raise ValueError("draft has no transparency; supply a transparent background")
    rgba.putalpha(rgba.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    _remove_isolated(rgba)
    bounds = rgba.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("draft has no connected visible foreground after cleanup")
    crop = rgba.crop(bounds)
    bottom = 2 if kind == "character" else 1
    border = 1 if outline is not None else 0
    available_width = size - 2 - 2 * border
    available_height = size - 1 - bottom - 2 * border
    scale = min(available_width / crop.width, available_height / crop.height)
    if scale >= 1:
        # Never resample a native-resolution draft by a fraction: keep it 1:1 or upscale by an integer.
        scale = math.floor(scale)
    width = max(1, min(available_width, round(crop.width * scale)))
    height = max(1, min(available_height, round(crop.height * scale)))
    crop = crop.resize((width, height), Image.Resampling.NEAREST)
    _remove_isolated(crop)
    bounds = crop.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("foreground disappears at the requested size")
    crop = crop.crop(bounds)

    def nearest(rgb, choices):
        return min(choices, key=lambda c: sum((a - b) ** 2 for a, b in zip(rgb, c)))

    pixels = [crop.getpixel((x, y)) for y in range(crop.height) for x in range(crop.width)]
    counts = Counter(pixel[:3] for pixel in pixels if pixel[3])
    mapping = {rgb: nearest(rgb, colors) for rgb in counts}
    usage = Counter()
    for rgb, count in counts.items():
        usage[mapping[rgb]] += count
    selected = sorted(usage, key=lambda c: (-usage[c], colors.index(c)))[:limit]
    if outline is not None and outline not in selected:
        selected = selected[:limit - 1] + [outline]
    mapping = {rgb: nearest(rgb, selected) for rgb in counts}
    crop.putdata([(*mapping[pixel[:3]], 255) if pixel[3] else (0, 0, 0, 0)
                  for pixel in pixels])
    if outline is not None:
        crop = ImageOps.expand(crop, border=1)
        alpha = crop.getchannel("A")
        contour = ImageChops.subtract(alpha.filter(ImageFilter.MaxFilter(3)), alpha)
        crop.paste((*outline, 255), mask=contour)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - crop.width) // 2
    y = size - bottom - crop.height if kind == "character" else (size - crop.height) // 2
    result.paste(crop, (x, y))
    return result


def validate(image: Image.Image, size: int, palette: list[tuple[int, int, int]],
             limit: int, kind: str) -> dict:
    """Inspect the supplied image as-is; never repair it during validation."""
    colors = _options(size, palette, limit, kind)
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    histogram = alpha.histogram()
    foreground = sum(histogram[1:])
    semi_alpha = sum(histogram[1:255])
    used = {pixel[:3] for _, pixel in rgba.getcolors(rgba.width * rgba.height) if pixel[3]}
    isolated = _isolated(rgba).histogram()[255]
    ratio = isolated / foreground if foreground else 0.0
    edge = foreground
    if rgba.width > 2 and rgba.height > 2:
        edge -= sum(alpha.crop((1, 1, rgba.width - 1, rgba.height - 1)).histogram()[1:])
    bounds = alpha.getbbox()
    checks = {
        "size": image.size == (size, size),
        "rgba": image.mode == "RGBA",
        "binary_alpha": semi_alpha == 0,
        "nonempty": foreground > 0,
        "transparency": histogram[0] > 0,
        "palette": used.issubset(set(colors)),
        "color_limit": len(used) <= limit,
        "isolated_ratio": ratio < 0.03,
        "clear_edges": edge == 0,
        "baseline": kind != "character" or (bounds is not None and bounds[3] == size - 2),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "width": image.width, "height": image.height, "mode": image.mode,
            "foreground_pixels": foreground, "transparent_pixels": histogram[0],
            "semi_alpha_pixels": semi_alpha, "color_count": len(used),
            "colors_outside_palette": len(used - set(colors)),
            "isolated_pixels": isolated, "isolated_ratio": ratio,
            "edge_pixels": edge, "visible_bounds": list(bounds) if bounds else None,
            "color_limit": limit, "kind": kind,
        },
    }
