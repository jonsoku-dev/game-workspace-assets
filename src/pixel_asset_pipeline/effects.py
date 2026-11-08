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
    if not isinstance(preset, str) or preset not in PRESETS:
        raise ValueError("preset must be one of: " + ", ".join(PRESETS))
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


# Timing is authored per cue; the final hold is a transparent resolved state.
PRESETS = {
    "pickup": ([60] * 10, "event", "collection committed", 3),
    "flame": ([80] * 12, "event", "active fire; stop when extinguished", 0),
    "step": ([30, 40, 50, 60, 60, 80], "ground", "foot contacts ground while moving", 1),
    "land": ([30, 40, 50, 60, 70, 80, 90, 100], "ground", "airborne actor contacts ground", 1),
    "slash": ([40, 30, 30, 40, 50, 60, 70, 80], "event", "right-facing attack active frame", 2),
    "impact": ([30, 40, 40, 50, 60, 70, 80, 100], "event", "hit or damage confirmed at contact", 1),
    "confirm": ([50, 50, 60, 80, 140, 100, 80, 100], "event", "UI action or progression committed", 4),
    "deny": ([40, 40, 40, 40, 50, 100, 100, 100], "event", "UI action rejected or interaction unavailable", 5),
}


def _feedback(preset, size, colors, seed):
    rng = random.Random(seed)
    rays = [(i * math.tau / 8 + rng.uniform(-0.1, 0.1), rng.uniform(0.85, 1.05))
            for i in range(8)]
    frames = []
    scale = size / 32
    ground = preset in {"step", "land"}
    origin = (size // 2, round(size * 0.8125) if ground else size // 2)
    for frame in range(len(PRESETS[preset][0])):
        image = Image.new("RGBA", (size, size))
        draw = ImageDraw.Draw(image)

        def point(x, y):
            return round(origin[0] + x * scale), round(origin[1] + y * scale)

        def line(points, color, width=1):
            draw.line([point(x, y) for x, y in points], fill=color,
                      width=max(1, round(width * scale)))

        if frame == len(PRESETS[preset][0]) - 1:
            frames.append(image)
            continue
        if ground:
            strong = preset == "land"
            spread = (3 + frame * 1.7) if strong else (2 + frame * 0.8)
            if frame < 3:
                line([(-spread, 0), (spread, 0)], colors[-1 if frame == 0 else 0])
            for i, (angle, speed) in enumerate(rays[:6 if strong else 3]):
                side = -1 if i % 2 else 1
                x = side * (spread + i * 0.45) * speed
                y = -math.sin((frame + 1) / (7 if strong else 5) * math.pi) * (3 + i % 3 if strong else 1.8)
                radius = (2 if strong and frame < 3 else 1) if frame < 4 else 0
                draw.rectangle([point(x - radius, y - radius), point(x + radius, y)],
                               fill=colors[-2 if frame < 3 else 0])
        elif preset == "slash":
            # Right-facing crescent sweeps down; detached sparks continue beyond the blade.
            if frame < 5:
                end = -55 + frame * 32
                start = max(-85, end - 90)
                arc = [(math.cos(math.radians(a)) * 11, math.sin(math.radians(a)) * 11)
                       for a in range(start, min(86, end + 1), 5)]
                line(arc, colors[0], 3)
                line(arc[-12:], colors[-1], 1)
            for i, (angle, speed) in enumerate(rays[:4]):
                if frame >= 2 and (frame < 5 or i % 2 == frame % 2):
                    x = 6 + (frame - 2) * speed + i
                    y = (i - 1.5) * (1 + (frame - 2) * 0.8)
                    line([(x, y), (x + 1, y - 1)], colors[-2])
        elif preset == "impact":
            if frame < 3:
                radius = 3 + frame * 2
                star = [(math.cos(i * math.pi / 8) * (radius if i % 2 == 0 else radius / 3),
                         math.sin(i * math.pi / 8) * (radius if i % 2 == 0 else radius / 3))
                        for i in range(16)]
                draw.polygon([point(x, y) for x, y in star], fill=colors[-1])
            for i, (angle, speed) in enumerate(rays):
                if frame < 5 or i % 2 == frame % 2:
                    radius = (3 + frame * 1.55) * speed
                    line([(math.cos(angle) * radius, math.sin(angle) * radius),
                          (math.cos(angle) * (radius + 2), math.sin(angle) * (radius + 2))],
                         colors[-2 if frame < 3 else 0])
        elif preset == "confirm":
            path = [(-7, 0), (-3, 4), (7, -6)]
            if frame == 0:
                line([path[0], (-5, 2)], colors[-1], 2)
            elif frame == 1:
                line(path[:2], colors[-1], 2)
            else:
                line(path, colors[-1 if frame < 5 else -2], 2)
            if 2 <= frame < 5:
                for x, y in [(-9, -6), (9, 5)]:
                    line([(x, y - 1), (x, y + 1)], colors[0])
                    line([(x - 1, y), (x + 1, y)], colors[0])
        else:  # Rejection shakes, then holds a readable X without a success sparkle.
            offset = (-2, 2, -1, 1, 0, 0, 0)[frame]
            color = colors[-1 if frame < 5 else -2]
            line([(-5 + offset, -5), (5 + offset, 5)], color, 2)
            line([(5 + offset, -5), (-5 + offset, 5)], color, 2)
        frames.append(image)
    return frames


def produce(request_path: Path, stage: Path) -> dict:
    """Write a native RGBA sheet and preview; palette order runs outer to hot core."""
    preset, size, colors, seed = _request(request_path)
    durations, anchor, trigger, reduced_frame = PRESETS[preset]
    frames = (_pickup(size, colors, seed) if preset == "pickup" else
              _flame(size, colors, seed) if preset == "flame" else
              _feedback(preset, size, colors, seed))
    pivot = [size // 2, round(size * 0.8125) if anchor == "ground" else size // 2]
    stage.mkdir(parents=True, exist_ok=True)
    exported = export_sheet(frames, durations, pivot,
                            preset == "flame", stage)
    report = {
        "schema_version": 1, "producer": "local-procedural", "preset": preset,
        "size": size, "seed": seed, "frame_count": len(frames),
        "duration_ms": sum(durations), "loop": preset == "flame",
        "timing_ms": durations, "pivot_px_from_top_left": pivot,
        "anchor": anchor, "trigger_intent": trigger, "reduced_motion_frame": reduced_frame,
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
                        and (report["terminal_blank"] if preset != "flame"
                             else not any(check["blank"] for check in report["frame_checks"])))
    if not report["passed"]:
        raise ValueError(f"{preset} effect failed frame validation")
    write_json(stage / "effect.json", report)
    return {**exported, "effect": "effect.json"}
