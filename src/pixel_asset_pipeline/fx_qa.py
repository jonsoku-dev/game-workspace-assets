"""Emissive VFX readability QA against the surfaces and materials the effect plays on.

Cutting sparks, embers and impact flashes must read as the hottest thing in frame:
a near-white core, a luminance ramp above every surface they touch, and a hue that is
not camouflaged by same-coloured paint or rust. The report measures that on the real
layers, and a regraded preview shows the same particles mapped through a hot ramp.
"""
import colorsys
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .action_set import local_path
from .bundle import open_png, write_json
from .spec import read_object, rgb

FILES = {"report": "fx-qa.json", "comparison": "fx-comparison.png", "regraded": "emissive-regraded.png"}
DEFAULTS = {
    "core_luma": 0.9,          # a pixel this bright and this unsaturated counts as white-hot core
    "core_saturation": 0.35,
    "min_core_share": 0.01,    # of visible emissive pixels
    "luma_margin": 0.08,       # emissive p99 must clear each surface p99 by this much
    "hue_separation_deg": 18,
    "min_contrast": 0.15,      # mean luma lift of the composite inside the effect footprint
}
# White-hot core -> yellow -> orange -> deep red -> ember; positions are normalised intensity.
HOT_RAMP = [(1.0, (255, 252, 236)), (0.82, (255, 226, 140)), (0.6, (255, 170, 62)),
            (0.38, (238, 102, 30)), (0.18, (160, 44, 18)), (0.0, (70, 16, 10))]
# For scenes with orange/red paint or rust: tails stay amber-yellow (~45 deg) so they separate from it.
AMBER_RAMP = [(1.0, (255, 253, 242)), (0.82, (255, 241, 176)), (0.6, (255, 220, 92)),
              (0.38, (242, 190, 58)), (0.18, (176, 132, 30)), (0.0, (78, 54, 12))]


def ramp_for(surface_hues):
    """Pick the ramp whose tails are farthest from the surfaces' saturated hues."""
    if any(h is not None and (h <= 40 or h >= 340) for h in surface_hues):
        return "amber", AMBER_RAMP
    return "hot", HOT_RAMP


def _luma(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _visible(image, limit=200_000):
    """Visible (alpha >= 32) RGBA pixels, subsampled deterministically to at most `limit`."""
    data = image.tobytes()
    count = len(data) // 4
    stride = max(1, count // limit)
    return [data[i * 4:i * 4 + 4] for i in range(0, count, stride) if data[i * 4 + 3] >= 32]


def _quantile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _hue_stats(pixels):
    """Circular mean hue (degrees) of saturated pixels, or None."""
    x = y = weight = 0.0
    for p in pixels:
        h, s, v = colorsys.rgb_to_hsv(p[0] / 255, p[1] / 255, p[2] / 255)
        if s >= .25 and v >= .2:
            x += math.cos(h * 2 * math.pi) * s
            y += math.sin(h * 2 * math.pi) * s
            weight += s
    if weight < 1e-6:
        return None
    return math.degrees(math.atan2(y, x)) % 360


def _hue_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def load(path):
    path = Path(path)
    data = read_object(path, {"name", "emissive", "surfaces", "thresholds"})
    root = path.parent
    thresholds = dict(DEFAULTS)
    overrides = data.get("thresholds", {})
    if not isinstance(overrides, dict) or overrides.keys() - DEFAULTS.keys():
        raise ValueError("unknown threshold")
    thresholds.update({k: float(v) for k, v in overrides.items()})
    emissive = data.get("emissive")
    if not isinstance(emissive, list) or not 1 <= len(emissive) <= 16:
        raise ValueError("emissive must list 1..16 transparent PNG layers or sheets")
    layers = [open_png(local_path(root, item)).convert("RGBA") for item in emissive]
    surfaces = []
    if not isinstance(data.get("surfaces"), list) or not 1 <= len(data["surfaces"]) <= 16:
        raise ValueError("surfaces must list 1..16 materials the effect plays on")
    for item in data["surfaces"]:
        if not isinstance(item, dict) or set(item) - {"name", "image", "color"} or ("image" in item) == ("color" in item):
            raise ValueError("each surface is {name, image} or {name, color}")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("surfaces need names")
        if "image" in item:
            image = open_png(local_path(root, item["image"])).convert("RGBA")
        else:
            image = Image.new("RGBA", (64, 64), (*rgb(item["color"]), 255))
        surfaces.append({"name": name, "image": image})
    return {"name": data.get("name", path.stem), "emissive": emissive, "layers": layers,
            "surfaces": surfaces, "thresholds": thresholds}


def _stack(layers):
    """Emissive layers side by side on one transparent strip (sheets keep their cells)."""
    width = sum(l.width for l in layers)
    height = max(l.height for l in layers)
    strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for layer in layers:
        strip.paste(layer, (x, 0))
        x += layer.width
    return strip


def regrade(layer, ramp=HOT_RAMP):
    """Map each emissive pixel's intensity through a hot ramp; the brightest ~15% become core."""
    pixels = _visible(layer)
    ceiling = max(_quantile([_luma(*p[:3]) for p in pixels], .99), 1e-3)
    out = layer.copy()
    data = bytearray(out.tobytes())
    for i in range(0, len(data), 4):
        if data[i + 3] < 8:
            continue
        t = min(1.0, (_luma(data[i], data[i + 1], data[i + 2]) / ceiling) ** 1.5 * 1.08)
        for (t1, c1), (t0, c0) in zip(ramp, ramp[1:]):
            if t >= t0:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 1
                data[i:i + 3] = bytes(round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
                break
    return Image.frombytes("RGBA", out.size, bytes(data))


def _patch(surface, size):
    """A native-resolution patch of the surface's opaque area, tiled up to `size`."""
    box = surface.getchannel("A").point(lambda a: 255 if a >= 200 else 0).getbbox() or (0, 0, *surface.size)
    region = surface.crop(box).convert("RGB")
    tiled = Image.new("RGB", size)
    for y in range(0, size[1], region.height):
        for x in range(0, size[0], region.width):
            tiled.paste(region, (x, y))
    if region.width >= size[0] and region.height >= size[1]:
        left, top = (region.width - size[0]) // 2, (region.height - size[1]) // 2
        tiled = region.crop((left, top, left + size[0], top + size[1]))
    return tiled


def _composite(surface, effect):
    """Additive (screen) composite of the effect over a same-size patch of the surface."""
    base = _patch(surface, effect.size)
    glow = Image.new("RGB", effect.size)
    glow.paste(effect.convert("RGB"), mask=effect.getchannel("A"))
    return ImageChops.screen(base, glow), base


def _measure(effect, surfaces, limits):
    pixels = _visible(effect)
    if not pixels:
        raise ValueError("emissive layers have no visible pixels")
    lumas = [_luma(*p[:3]) for p in pixels]
    core = sum(1 for p, l in zip(pixels, lumas)
               if l >= limits["core_luma"] and colorsys.rgb_to_hsv(*(c / 255 for c in p[:3]))[1] <= limits["core_saturation"])
    hue = _hue_stats(pixels)
    stats = {"visible_pixels_sampled": len(pixels), "core_share": round(core / len(pixels), 4),
             "luma_p50": round(_quantile(lumas, .5), 3), "luma_p99": round(_quantile(lumas, .99), 3),
             "hue_deg": None if hue is None else round(hue, 1), "surfaces": []}
    mask = effect.getchannel("A").point(lambda a: 255 if a >= 32 else 0)
    footprint = max(1, mask.histogram()[255])
    for surface in surfaces:
        spixels = _visible(surface["image"])
        slumas = [_luma(*p[:3]) for p in spixels]
        shue = _hue_stats(spixels)
        composite, base = _composite(surface["image"], effect)
        lift = 0.0
        cdata, bdata, mdata = composite.tobytes(), base.tobytes(), mask.tobytes()
        for i, m in enumerate(mdata):
            if m:
                lift += _luma(*cdata[i * 3:i * 3 + 3]) - _luma(*bdata[i * 3:i * 3 + 3])
        stats["surfaces"].append({"name": surface["name"], "luma_p99": round(_quantile(slumas, .99), 3),
                                  "luma_p90": round(_quantile(slumas, .9), 3),
                                  "hue_deg": None if shue is None else round(shue, 1),
                                  "hue_distance_deg": None if hue is None or shue is None else round(_hue_distance(hue, shue), 1),
                                  "composite_lift": round(lift / footprint, 3)})
    return stats


def _findings(stats, limits):
    findings = []
    if stats["core_share"] < limits["min_core_share"]:
        findings.append({"code": "no-hot-core", "severity": "error",
                         "message": f"흰색에 가까운 고온 심이 {stats['core_share']:.1%}뿐입니다. 입자 중심 15%를 거의 흰색(채도 0.35 이하, 밝기 0.9 이상)으로 올리세요."})
    for surface in stats["surfaces"]:
        if stats["luma_p99"] < surface["luma_p99"] + limits["luma_margin"]:
            findings.append({"code": "dimmer-than-surface", "severity": "error", "surface": surface["name"],
                             "message": f"불꽃의 가장 밝은 부분({stats['luma_p99']:.2f})이 {surface['name']}의 하이라이트({surface['luma_p99']:.2f})보다 충분히 밝지 않습니다."})
        if (surface["hue_distance_deg"] is not None and surface["hue_distance_deg"] < limits["hue_separation_deg"]
                and stats["luma_p50"] < surface["luma_p90"] + .15):
            findings.append({"code": "hue-camouflage", "severity": "error", "surface": surface["name"],
                             "message": f"불꽃 색상({stats['hue_deg']:.0f}°)이 {surface['name']}({surface['hue_deg']:.0f}°)과 {surface['hue_distance_deg']:.0f}°밖에 차이 나지 않고 더 밝지도 않아 재질에 묻힙니다."})
        if surface["composite_lift"] < limits["min_contrast"]:
            findings.append({"code": "low-contrast", "severity": "warning", "surface": surface["name"],
                             "message": f"{surface['name']} 위에 합성하면 효과 영역 밝기가 평균 {surface['composite_lift']:.2f}만 올라갑니다."})
    return findings


def _focus(layers, window=192):
    """Densest `window`-sized region across the emissive layers, so the comparison shows real particles."""
    best = (-1, 0, (0, 0, 1, 1))
    step = 8
    for index, layer in enumerate(layers):
        mask = layer.getchannel("A").point(lambda a: 255 if a >= 32 else 0)
        w, h = max(1, mask.width // step), max(1, mask.height // step)
        cells = list(mask.resize((w, h), Image.Resampling.BOX).tobytes())
        span_x, span_y = min(w, window // step), min(h, window // step)
        for y in range(0, h - span_y + 1):
            for x in range(0, w - span_x + 1):
                total = sum(sum(cells[(y + dy) * w + x:(y + dy) * w + x + span_x]) for dy in range(span_y))
                if total > best[0]:
                    best = (total, index, (x * step, y * step, (x + span_x) * step, (y + span_y) * step))
    return best[1], best[2]


def _comparison(layers, regraded, surfaces, path, side=360, label="regraded"):
    index, box = _focus(layers)
    pairs = (layers[index].crop(box), regraded[index].crop(box))
    scale = side / max(pairs[0].size)
    size = (max(1, round(pairs[0].width * scale)), max(1, round(pairs[0].height * scale)))
    sheet = Image.new("RGB", (size[0] * 2 + 30, (size[1] + 28) * len(surfaces) + 10), "#121a1f")
    draw = ImageDraw.Draw(sheet)
    for row, surface in enumerate(surfaces):
        y = 10 + row * (size[1] + 28)
        for column, effect in enumerate(pairs):
            composite, _ = _composite(surface["image"], effect)
            sheet.paste(composite.resize(size, Image.Resampling.LANCZOS), (10 + column * (size[0] + 10), y + 18))
            draw.text((10 + column * (size[0] + 10), y + 2),
                      f"{surface['name']} / {'original' if column == 0 else label + ' ramp'}", fill="#e9eff1")
    sheet.save(path)


def produce(request_path, stage):
    request = load(Path(request_path))
    limits = request["thresholds"]
    effect = _stack(request["layers"])
    stats = _measure(effect, request["surfaces"], limits)
    findings = _findings(stats, limits)
    ramp_name, ramp = ramp_for([surface["hue_deg"] for surface in stats["surfaces"]])
    regraded = [regrade(layer, ramp) for layer in request["layers"]]
    hot_stats = _measure(_stack(regraded), request["surfaces"], limits)
    _stack(regraded).save(stage / FILES["regraded"])
    _comparison(request["layers"], regraded, request["surfaces"], stage / FILES["comparison"], label=ramp_name)
    errors = [f for f in findings if f["severity"] == "error"]
    write_json(stage / FILES["report"], {
        "schema_version": 1, "name": request["name"], "passed": not errors, "thresholds": limits,
        "emissive": request["emissive"], "measured": stats, "findings": findings,
        "regraded_preview": {"measured": hot_stats, "remaining_findings": _findings(hot_stats, limits),
                             "ramp_name": ramp_name,
                             "ramp": [{"at": t, "color": "#%02x%02x%02x" % c} for t, c in ramp]},
        "visual_review": "pending", "artistic_acceptance": "pending"})
    return FILES
