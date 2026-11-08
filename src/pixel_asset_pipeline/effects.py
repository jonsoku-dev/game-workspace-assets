"""Small original, palette-locked pixel effects drawn directly at native size."""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from .bundle import write_json
from .spec import read_object, rgb
from .sheet import export_sheet


def _request(path):
    data = read_object(path, {"preset", "size", "palette", "seed"})
    preset = data.get("preset")
    if not isinstance(preset, str) or preset not in {"pickup", "flame"}:
        raise ValueError("preset must be pickup or flame")
    size = data.get("size", 32)
    if type(size) is not int or not 16 <= size <= 64:
        raise ValueError("size must be an integer in 16..64")
    palette = data.get("palette")
    if not isinstance(palette, list) or not 3 <= len(palette) <= 8:
        raise ValueError("palette requires 3..8 distinct #RRGGBB colors, outer to hot core")
    colors = [(*rgb(color), 255) for color in palette]
    if len(set(colors)) != len(colors):
        raise ValueError("palette colors must be distinct")
    seed = data.get("seed", 0)
    if type(seed) is not int or not -(2**31) <= seed < 2**31:
        raise ValueError("seed must be a signed 32-bit integer")
    return preset, size, colors, seed


def _pickup(size, colors, seed):
    rng = random.Random(seed)
    rays = [(index * math.tau / 8 + rng.uniform(-0.12, 0.12), rng.uniform(0.85, 1.05))
            for index in range(8)]
    frames = []
    scale = size / 32
    center = size // 2
    for frame in range(10):
        image = Image.new("RGBA", (size, size))
        draw = ImageDraw.Draw(image)

        def point(x, y):
            return round(center + x * scale), round(center + y * scale)

        def diamond(x, y, radius, color):
            draw.polygon([point(x, y - radius), point(x + radius * 0.6, y),
                          point(x, y + radius), point(x - radius * 0.6, y)], fill=color)

        if frame < 2:
            diamond(0, 0, 1 + frame, colors[-1])
        elif frame < 9:
            age = frame - 2
            if age < 4:
                radius = 3 + age * 2
                vertices = [point(0, -radius), point(radius, 0),
                            point(0, radius), point(-radius, 0), point(0, -radius)]
                draw.line(vertices, fill=colors[min(age, len(colors) - 2)], width=1)
            if age < 2:
                diamond(0, 0, 4 - age, colors[-1])
                draw.line([point(-4, 0), point(4, 0)], fill=colors[-1])
            for index, (angle, speed) in enumerate(rays):
                radius = (4 + age * 1.45) * speed
                x, y = math.cos(angle) * radius, math.sin(angle) * radius
                if age < 5 or index % 2 == age % 2:
                    diamond(x, y, 2 if age < 3 else 0.6,
                            colors[-1] if age < 3 else colors[-2])
        frames.append(image)
    return frames


def _flame(size, colors, seed):
    rng = random.Random(seed)
    phase = rng.random() * math.tau
    ember_phases = [rng.random() for _ in range(3)]
    frames = []
    scale = size / 32
    center = size // 2
    for frame in range(12):
        image = Image.new("RGBA", (size, size))
        draw = ImageDraw.Draw(image)
        time = frame / 12
        wave = math.tau * time + phase

        def point(x, y):
            return round(center + x * scale), round(y * scale)

        sway = math.sin(wave) * 2
        # Three asymmetric tongues share a fixed base, so the silhouette breathes without drifting.
        outer = [(-7, 25), (-8, 21), (-6, 16), (-6 + sway, 11),
                 (-2, 15), (sway, 5 + math.sin(wave) * 2), (3, 12),
                 (5 + math.cos(wave), 10), (5, 16), (8, 20), (7, 25), (3, 27), (-3, 27)]
        middle = [(-5, 25), (-5, 21), (-3, 17), (-3, 20),
                  (sway * 0.5, 11 + math.sin(wave + 1) * 2),
                  (2, 18), (4, 16), (5, 22), (4, 26), (-3, 26)]
        core = [(-2, 25), (-3, 23), (-1, 20), (0, 17 + math.sin(wave + 2)),
                (1, 22), (2, 21), (3, 25), (1, 26)]
        for polygon, color in ((outer, colors[0]), (middle, colors[-2]), (core, colors[-1])):
            draw.polygon([point(x, y) for x, y in polygon], fill=color)
        for index, offset in enumerate(ember_phases):
            age = (time + offset) % 1
            if age < 0.8:
                x = (index - 1) * 4 + math.sin(wave + offset * math.tau)
                y = 17 - age * 16
                draw.point(point(x, y), fill=colors[-1] if age < 0.4 else colors[-2])
        frames.append(image)
    return frames


def produce(request_path: Path, stage: Path) -> dict:
    """Write a native RGBA sheet and preview; palette order runs outer to hot core."""
    preset, size, colors, seed = _request(request_path)
    frames = (_pickup if preset == "pickup" else _flame)(size, colors, seed)
    duration = 60 if preset == "pickup" else 80
    stage.mkdir(parents=True, exist_ok=True)
    exported = export_sheet(frames, [duration] * len(frames), [size // 2, size // 2],
                            preset == "flame", stage)
    report = {
        "schema_version": 1, "producer": "local-procedural", "preset": preset,
        "size": size, "seed": seed, "frame_count": len(frames),
        "duration_ms": duration * len(frames), "loop": preset == "flame",
        "palette": ["#%02x%02x%02x" % color[:3] for color in colors],
        "frame_checks": [{"rgba": frame.mode == "RGBA",
                          "binary_alpha": sum(frame.getchannel("A").histogram()[1:255]) == 0,
                          "palette": {pixel for _, pixel in frame.getcolors(size * size) if pixel[3]} <= set(colors),
                          "blank": frame.getbbox() is None} for frame in frames],
        "terminal_blank": frames[-1].getbbox() is None,
        "review": "Original procedural art; visual and engine acceptance are separate from format checks.",
    }
    report["passed"] = (all(check["rgba"] and check["binary_alpha"] and check["palette"]
                            for check in report["frame_checks"])
                        and (report["terminal_blank"] if preset == "pickup"
                             else not any(check["blank"] for check in report["frame_checks"])))
    if not report["passed"]:
        raise ValueError(f"{preset} effect failed frame validation")
    write_json(stage / "effect.json", report)
    return {**exported, "effect": "effect.json"}
