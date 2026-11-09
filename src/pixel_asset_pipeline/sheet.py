"""Lossless offline horizontal sprite sheets and composited viewing previews."""
from pathlib import Path

from PIL import Image, ImageDraw

from .bundle import gif_timeline, local_path, open_png, write_json
from .spec import read_object


FILES = {"sheet": "sheet.png", "metadata": "sheet.json", "preview": "preview.gif"}
MAX_FRAMES = 64
MAX_SIDE = 512
MAX_PIXELS = 16_777_216
MAX_GIF_HOLD_MS = 655_350


def export_sheet(frames: list[Image.Image], durations: list[int], pivot: tuple[int, int],
                 loop: bool, stage: Path) -> dict[str, str]:
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"frames requires 1..{MAX_FRAMES} images")
    if not isinstance(durations, list) or len(durations) != len(frames):
        raise ValueError("durations must match the frame count")
    if any(type(value) is not int or not 1 <= value <= 60_000 for value in durations):
        raise ValueError("duration_ms must be an integer in 1..60000")
    if type(loop) is not bool:
        raise ValueError("loop must be a boolean")
    if any(not isinstance(frame, Image.Image) or frame.mode != "RGBA" for frame in frames):
        raise ValueError("frames must be RGBA images")
    width, height = frames[0].size
    if not 1 <= width <= MAX_SIDE or not 1 <= height <= MAX_SIDE:
        raise ValueError(f"frame dimensions must be in 1..{MAX_SIDE}")
    if any(frame.size != (width, height) for frame in frames):
        raise ValueError("frames must have identical dimensions")
    if width * height * len(frames) > MAX_PIXELS:
        raise ValueError(f"sheet must contain at most {MAX_PIXELS} pixels")
    if (not isinstance(pivot, (tuple, list)) or len(pivot) != 2
            or any(type(value) is not int for value in pivot)
            or not 0 <= pivot[0] <= width or not 0 <= pivot[1] <= height):
        raise ValueError("pivot must contain two integer coordinates within the frame edges")

    sheet = Image.new("RGBA", (width * len(frames), height))
    rectangles = []
    for index, (frame, duration) in enumerate(zip(frames, durations)):
        sheet.paste(frame, (index * width, 0))
        rectangles.append({"rect": {"x": index * width, "y": 0, "w": width, "h": height},
                           "duration_ms": duration})
    sheet.save(stage / FILES["sheet"])
    with Image.open(stage / FILES["sheet"]) as saved:
        for index, frame in enumerate(frames):
            crop = saved.crop((index * width, 0, (index + 1) * width, height))
            if crop.tobytes() != frame.tobytes():
                raise ValueError("saved sheet failed exact frame reconstruction")
    write_json(stage / FILES["metadata"], {
        "schema_version": 1, "frames": rectangles,
        "pivot_px_from_top_left": list(pivot), "loop": loop,
    })

    background = Image.new("RGBA", (width, height), "#525c59")
    drawing = ImageDraw.Draw(background)
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            if (x // 4 + y // 4) % 2:
                drawing.rectangle((x, y, x + 3, y + 3), fill="#5d6863")
    views = [Image.alpha_composite(background, frame).convert("RGB") for frame in frames]
    # One palette for every pose prevents per-frame quantization from flickering.
    palette_strip = Image.new("RGB", sheet.size)
    for index, view in enumerate(views):
        palette_strip.paste(view, (index * width, 0))
    palette = palette_strip.quantize(colors=256, dither=Image.Dither.NONE)
    scale = min(6, max(1, 288 // max(width, height)))
    previews = [view.quantize(palette=palette, dither=Image.Dither.NONE).resize(
        (width * scale, height * scale), Image.Resampling.NEAREST) for view in views]
    # GIF stores centiseconds; sheet metadata remains the exact source timing.
    timeline = gif_timeline(durations)
    holds, hold_durations = [], []
    for preview, duration in ((previews[index], delay) for index, delay in timeline):
        if holds and preview.tobytes() == holds[-1].tobytes():
            # Pillow merges identical poses; cap preview-only holds to GIF's uint16 delay.
            hold_durations[-1] = min(MAX_GIF_HOLD_MS, hold_durations[-1] + duration)
        else:
            holds.append(preview)
            hold_durations.append(duration)
    holds[0].save(stage / FILES["preview"], save_all=True, append_images=holds[1:],
                     duration=hold_durations, disposal=2, optimize=False,
                     **({"loop": 0} if loop else {}))
    return dict(FILES)


def produce(request_path: Path, stage: Path) -> dict[str, str]:
    request = read_object(request_path, {"frames", "pivot_px_from_top_left", "loop"})
    entries = request.get("frames")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FRAMES:
        raise ValueError(f"frames requires 1..{MAX_FRAMES} frame objects")
    frames, durations = [], []
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {"path", "duration_ms"}
                or not isinstance(entry["path"], str) or not entry["path"].strip()):
            raise ValueError("each frame requires path and duration_ms")
        frames.append(open_png(local_path(request_path.parent, entry["path"]), max_pixels=MAX_SIDE ** 2).convert("RGBA"))
        durations.append(entry["duration_ms"])
    return export_sheet(frames, durations, request.get("pivot_px_from_top_left"),
                        request.get("loop"), stage)
