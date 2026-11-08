"""Portable six-action atlases from authored PNG poses and local pixelfx exports."""
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw

from .bundle import open_png, write_json
from .spec import read_object

ACTIONS = {"idle": True, "walk": True, "run": True,
           "attack": False, "jump": False, "hurt": False}
MAX_PIXELS = 16_777_216


def local_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("source paths must be nonempty relative paths")
    path = (root / value).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("source paths must stay within the request directory")
    if path.stat().st_size > 16_777_216:
        raise ValueError("source exceeds 16 MiB")
    return path


def point(value, size, label):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) is not int or not 0 <= v <= bound for v, bound in zip(value, size))):
        raise ValueError(f"{label} requires integer coordinates within the cell edges")
    return list(value)


def duration(value):
    if type(value) is not int or not 1 <= value <= 60000:
        raise ValueError("duration_ms must be an integer in 1..60000")
    return value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_effect(event, root, index, stage, pixel_budget=MAX_PIXELS):
    paths = {key: local_path(root, event.get(key))
             for key in ("sheet", "metadata", "license", "notice")}
    if paths["metadata"].stat().st_size > 1_048_576:
        raise ValueError("effect metadata exceeds 1 MiB")
    data = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("meta"), dict):
        raise ValueError("effect requires Aseprite metadata with meta.pixelfx")
    fx = data["meta"].get("pixelfx")
    entries = data.get("frames")
    if not isinstance(fx, dict) or not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise ValueError("effect requires 1..256 Aseprite frames and meta.pixelfx")
    image = open_png(paths["sheet"], max_pixels=MAX_PIXELS).convert("RGBA")
    size = fx.get("frameSize")
    if (not isinstance(size, list) or len(size) != 2
            or any(type(v) is not int or not 1 <= v <= 512 for v in size)):
        raise ValueError("pixelfx frameSize requires two dimensions in 1..512")
    if size[0] * size[1] * len(entries) > pixel_budget:
        raise ValueError("effect frames exceed pixel budget")
    pivot = point(fx.get("pivot"), size, "pixelfx pivot")
    frames, crops = [], []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("rotated") is not False or entry.get("trimmed") is not False:
            raise ValueError("rotated or trimmed effect frames are unsupported")
        rect = entry.get("frame")
        if (not isinstance(rect, dict) or set(rect) != {"x", "y", "w", "h"}
                or any(type(v) is not int for v in rect.values())
                or [rect["w"], rect["h"]] != size or min(rect["x"], rect["y"]) < 0
                or rect["x"] + rect["w"] > image.width or rect["y"] + rect["h"] > image.height):
            raise ValueError("effect frame rectangle is outside its sheet or mismatches frameSize")
        frames.append({"rect": rect, "duration_ms": duration(entry.get("duration"))})
        crops.append(image.crop((rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"])))
    if type(fx.get("frames")) is not int or fx["frames"] != len(frames) or type(fx.get("loop")) is not bool:
        raise ValueError("pixelfx frames/loop metadata must match the exported frames")
    files = {key: f"effect-{index}{suffix}" for key, suffix in
             (("sheet", ".png"), ("metadata", ".json"), ("license", "-LICENSE"), ("notice", "-NOTICE"))}
    for key in ("sheet", "license", "notice"):
        if paths[key].stat().st_size > 16_777_216:
            raise ValueError("effect source exceeds 16 MiB")
        if key in ("license", "notice") and not paths[key].read_text(encoding="utf-8").strip():
            raise ValueError("effect license and NOTICE must contain text")
        shutil.copyfile(paths[key], stage / files[key])
    data["meta"]["image"] = files["sheet"]
    write_json(stage / files["metadata"], data)
    return {**files, "pivot_px_from_top_left": pivot, "frames": frames,
            "duration_ms": sum(f["duration_ms"] for f in frames),
            "source": {key: {"path": event[key], "sha256": digest(path)} for key, path in paths.items()}}, crops, size


def frame_at(frames, elapsed, loop=False):
    total = sum(f["duration_ms"] for f in frames)
    elapsed = elapsed % total if loop else min(elapsed, total - 1)
    for index, frame in enumerate(frames):
        elapsed -= frame["duration_ms"]
        if elapsed < 0:
            return index
    return len(frames) - 1


def preview(actions, poses, events, effects, size, stage):
    # Include effect extents so a contact outside the actor silhouette stays visible.
    left, top, right, bottom = 0, 0, size[0], size[1]
    for event, crops in zip(events, effects):
        x, y = (a - b for a, b in zip(event["at_px"], event["effect_anchor_px"]))
        left, top = min(left, x), min(top, y)
        right, bottom = max(right, x + crops[0].width), max(bottom, y + crops[0].height)
    canvas_size = right - left, bottom - top + 12
    views, times = [], []
    for name, action in actions.items():
        active = [(e, c) for e, c in zip(events, effects) if e["action"] == name]
        end = max([action["duration_ms"]] + [e["start_ms"] + e["duration_ms"] for e, _ in active])
        cycles = (end + action["duration_ms"] - 1) // action["duration_ms"] if action["loop"] else 1
        # Reject unrepresentable tiny-loop tails before enumerating repeated contacts.
        if cycles * len(action["frames"]) > 2048:
            raise ValueError("composite preview exceeds frame budget")
        boundaries = {0, end}
        t = 0
        for _ in range(cycles):
            for frame in action["frames"]:
                t += frame["duration_ms"]
                boundaries.add(min(t, end))
        for e, _ in active:
            contact = e["start_ms"]
            for _ in range(cycles):
                if contact >= end:
                    break
                boundaries.add(contact)
                t = contact
                cutoff = min(end, contact + action["duration_ms"]) if action["loop"] else end
                for frame in e["frames"]:
                    t += frame["duration_ms"]
                    if t > cutoff:
                        break
                    boundaries.add(t)
                if len(boundaries) > 2048:
                    raise ValueError("composite preview exceeds frame budget")
                contact += action["duration_ms"]
        ordered = sorted(boundaries)
        for start, stop in zip(ordered, ordered[1:]):
            view = Image.new("RGBA", canvas_size, "#525c59")
            view.alpha_composite(poses[name][frame_at(action["frames"], start, action["loop"])], (-left, 12 - top))
            for e, crops in active:
                elapsed = start - e["start_ms"]
                if elapsed >= 0 and action["loop"]:
                    elapsed %= action["duration_ms"]
                if 0 <= elapsed < e["duration_ms"]:
                    x, y = (a - b for a, b in zip(e["at_px"], e["effect_anchor_px"]))
                    view.alpha_composite(crops[frame_at(e["frames"], elapsed)], (x - left, y - top + 12))
            ImageDraw.Draw(view).text((2, 0), name, fill="white")
            if len(views) >= 2048:
                raise ValueError("composite preview exceeds frame budget")
            views.append(view.convert("RGB"))
            times.append(max(10, ((stop - start + 5) // 10) * 10))
            if len(views) * canvas_size[0] * canvas_size[1] > 67_108_864:
                raise ValueError("composite preview exceeds pixel budget")
    scale = min(4, max(1, 288 // max(canvas_size)))
    # Adaptive palettes retain effect colors absent from the opening idle pose.
    images = [v.quantize(colors=256, dither=Image.Dither.NONE).resize(
        (v.width * scale, v.height * scale), Image.Resampling.NEAREST) for v in views]
    images[0].save(stage / "preview.gif", save_all=True, append_images=images[1:],
                   duration=times, loop=0, disposal=2, optimize=False)


def produce(request_path: Path, stage: Path):
    if request_path.stat().st_size > 1_048_576:
        raise ValueError("action-set request exceeds 1 MiB")
    request = read_object(request_path, {"cell_size", "pivot_px_from_top_left", "actions", "events"})
    size = request.get("cell_size")
    if (not isinstance(size, list) or len(size) != 2
            or any(type(v) is not int or not 1 <= v <= 512 for v in size)):
        raise ValueError("cell_size requires two dimensions in 1..512")
    pivot = point(request.get("pivot_px_from_top_left"), size, "pivot")
    entries = request.get("actions")
    if not isinstance(entries, dict) or set(entries) != set(ACTIONS):
        raise ValueError("actions must contain exactly idle, walk, run, attack, jump, hurt")
    actions, poses = {}, {}
    columns = 0
    for name, looping in ACTIONS.items():
        action = entries[name]
        if not isinstance(action, dict) or set(action) != {"loop", "frames"} or action["loop"] is not looping:
            raise ValueError(f"{name} requires loop={looping} and frames")
        frames = action["frames"]
        if not isinstance(frames, list) or not 1 <= len(frames) <= 64:
            raise ValueError("each action requires 1..64 frames")
        columns = max(columns, len(frames))
        if columns * size[0] * size[1] * 6 > MAX_PIXELS:
            raise ValueError("atlas exceeds pixel budget")
        output_frames, images = [], []
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict) or set(frame) != {"path", "duration_ms"}:
                raise ValueError("each frame requires path and duration_ms")
            path = local_path(request_path.parent, frame["path"])
            image = open_png(path, max_pixels=size[0] * size[1]).convert("RGBA")
            if image.size != tuple(size):
                raise ValueError("all authored frames must match cell_size")
            images.append(image)
            output_frames.append({"rect": {"x": index * size[0], "y": len(actions) * size[1], "w": size[0], "h": size[1]},
                                  "duration_ms": duration(frame["duration_ms"]),
                                  "source": {"path": frame["path"], "sha256": digest(path)}})
        actions[name] = {"loop": looping, "duration_ms": sum(f["duration_ms"] for f in output_frames), "frames": output_frames}
        if actions[name]["duration_ms"] > 120000:
            raise ValueError("action duration exceeds 120000 ms")
        poses[name] = images
    atlas = Image.new("RGBA", (columns * size[0], 6 * size[1]))
    for row, name in enumerate(ACTIONS):
        for col, image in enumerate(poses[name]):
            atlas.paste(image, (col * size[0], row * size[1]))
    atlas.save(stage / "atlas.png")
    events, effects, credits = [], [], []
    effect_pixels = 0
    files = {"atlas": "atlas.png", "metadata": "action-set.json", "preview": "preview.gif", "credits": "credits.json"}
    source_events = request.get("events", [])
    if not isinstance(source_events, list) or len(source_events) > 8:
        raise ValueError("events requires at most 8 entries")
    for index, event in enumerate(source_events):
        allowed = {"action", "frame", "sheet", "metadata", "license", "notice", "attribution", "at_px", "effect_anchor_px"}
        if not isinstance(event, dict) or event.keys() - allowed:
            raise ValueError("invalid effect event fields")
        name, frame = event.get("action"), event.get("frame")
        if not isinstance(name, str) or name not in actions or type(frame) is not int or not 0 <= frame < len(actions[name]["frames"]):
            raise ValueError("event requires an existing action and zero-based contact frame")
        attribution = event.get("attribution", "")
        if not isinstance(attribution, str) or len(attribution) > 4096:
            raise ValueError("attribution must be text of at most 4096 characters")
        record, crops, effect_size = load_effect(event, request_path.parent, index, stage, MAX_PIXELS - effect_pixels)
        effect_pixels += sum(c.width * c.height for c in crops)
        if effect_pixels > MAX_PIXELS:
            raise ValueError("effect frames exceed pixel budget")
        record.update(action=name, frame=frame,
                      start_ms=sum(f["duration_ms"] for f in actions[name]["frames"][:frame]),
                      at_px=point(event.get("at_px", pivot), size, "at_px"),
                      effect_anchor_px=point(event.get("effect_anchor_px", record["pivot_px_from_top_left"]), effect_size, "effect_anchor_px"))
        if record["duration_ms"] > 120000:
            raise ValueError("effect duration exceeds 120000 ms")
        events.append(record)
        effects.append(crops)
        for key in ("sheet", "metadata", "license", "notice"):
            files[f"effect_{index}_{key}"] = record[key]
        credits.append({"event": index, "license": record["license"], "notice": record["notice"], "attribution": attribution, "source": record["source"]})
    write_json(stage / "action-set.json", {"schema_version": 1, "origin": "local-authored-poses", "cell_size": size,
               "pivot_px_from_top_left": pivot, "actions": actions, "events": events,
               "preview": {"timing": "GIF centiseconds rounded; exact milliseconds in metadata", "effects": "composited; newest contact replaces prior instance",
                           "scope": "one action traversal plus initial effect tail; loops retrigger within that window",
                           "visual_review": "pending"}})
    write_json(stage / "credits.json", {"schema_version": 1, "effects": credits})
    preview(actions, poses, events, effects, size, stage)
    return files
