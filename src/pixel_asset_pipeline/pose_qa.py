"""Pose-sequence motion QA for painted or pixel key poses on a shared canvas.

Measures what a viewer sees between consecutive exposures instead of counting frames:
tool-tip travel per step, overshoot past the rest pose after contact, floor penetration,
tool length drift, planted-foot skating and silhouette pops. Large tip jumps get an
in-between plan with target tip positions and a timing split that keeps the total
duration and the contact start fixed. Measurements never grant artistic approval.
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .action_set import local_path
from .bundle import open_png, write_json
from .spec import read_object

FILES = {"report": "pose-qa.json", "trail": "tip-trail.png", "breakdowns": "breakdowns.json"}
MAX_CANVAS = 4096
DEFAULTS = {
    "max_step_body": 0.6,        # tip travel per exposure, in body heights
    "overshoot_body": 0.25,      # how far past the rest pose the tip may swing back after contact
    "floor_tolerance_px": 4,
    "tool_length_spread": 0.10,  # (max - min) / median grip-to-tip length
    "skate_body": 0.05,          # planted-foot travel per step
    "min_iou": 0.2,              # silhouette overlap below this is reported as a pop
    "contact_exposure_ratio": 0.66,
}
SOCKETS = {"tip", "grip", "foot_front", "foot_back"}


def _point(value, canvas, label):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or not -canvas[i] <= v <= 2 * canvas[i]
                   for i, v in enumerate(value))):
        raise ValueError(f"{label} must be an [x, y] point near the canvas")
    return (float(value[0]), float(value[1]))


def load(path):
    path = Path(path)
    data = read_object(path, {"name", "canvas", "floor_y", "facing", "frames", "sequences", "thresholds"})
    root = path.parent
    canvas = data.get("canvas")
    if (not isinstance(canvas, list) or len(canvas) != 2
            or any(type(v) is not int or not 16 <= v <= MAX_CANVAS for v in canvas)):
        raise ValueError(f"canvas must be [width, height] within 16..{MAX_CANVAS}")
    floor = data.get("floor_y")
    if type(floor) is not int or not 0 < floor <= canvas[1]:
        raise ValueError("floor_y must be an integer row inside the canvas")
    if data.get("facing", "right") not in ("right", "left"):
        raise ValueError("facing must be right or left")
    thresholds = dict(DEFAULTS)
    overrides = data.get("thresholds", {})
    if not isinstance(overrides, dict) or overrides.keys() - DEFAULTS.keys():
        raise ValueError("unknown threshold")
    for key, value in overrides.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"threshold {key} must be a non-negative number")
        thresholds[key] = float(value)
    frames = {}
    if not isinstance(data.get("frames"), list) or not 2 <= len(data["frames"]) <= 64:
        raise ValueError("frames must list 2..64 key poses")
    for item in data["frames"]:
        if not isinstance(item, dict) or item.keys() - {"id", "image", "sockets", "foreshortened"}:
            raise ValueError("frame entries take id, image, sockets and foreshortened")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident or ident in frames:
            raise ValueError("frame ids must be unique nonempty strings")
        sockets = item.get("sockets", {})
        if not isinstance(sockets, dict) or sockets.keys() - SOCKETS or "tip" not in sockets:
            raise ValueError(f"{ident}: sockets need tip and may add grip, foot_front, foot_back")
        image = open_png(local_path(root, item.get("image")), MAX_CANVAS ** 2).convert("RGBA")
        if list(image.size) != canvas:
            raise ValueError(f"{ident}: image must use the shared {canvas[0]}x{canvas[1]} canvas")
        if type(item.get("foreshortened", False)) is not bool:
            raise ValueError(f"{ident}: foreshortened must be a boolean")
        frames[ident] = {"id": ident, "image": image, "foreshortened": item.get("foreshortened", False),
                         "sockets": {k: _point(v, canvas, f"{ident}.{k}") for k, v in sockets.items()}}
    sequences = data.get("sequences")
    if not isinstance(sequences, dict) or not 1 <= len(sequences) <= 16:
        raise ValueError("sequences must name 1..16 timed step lists")
    parsed = {}
    for name, sequence in sequences.items():
        if not isinstance(sequence, dict) or sequence.keys() - {"steps", "contact_step", "loop", "planted", "arc"}:
            raise ValueError(f"{name}: sequences take steps, contact_step, loop, planted and arc")
        steps = sequence.get("steps")
        if not isinstance(steps, list) or not 2 <= len(steps) <= 128:
            raise ValueError(f"{name}: steps must list 2..128 exposures")
        for step in steps:
            if (not isinstance(step, dict) or set(step) != {"frame", "ms"} or step["frame"] not in frames
                    or type(step["ms"]) is not int or not 1 <= step["ms"] <= 60000):
                raise ValueError(f"{name}: each step is {{frame, ms}} naming a known frame")
        contact = sequence.get("contact_step")
        if contact is not None and (type(contact) is not int or not 0 <= contact < len(steps)):
            raise ValueError(f"{name}: contact_step must index a step")
        if type(sequence.get("loop", False)) is not bool:
            raise ValueError(f"{name}: loop must be a boolean")
        planted = sequence.get("planted", [])
        if not isinstance(planted, list) or any(
                not isinstance(p, dict) or set(p) != {"from", "to", "feet"}
                or type(p["from"]) is not int or type(p["to"]) is not int or not 0 <= p["from"] < p["to"] < len(steps)
                or not isinstance(p["feet"], list) or not p["feet"] or set(p["feet"]) - {"front", "back"}
                for p in planted):
            raise ValueError(f"{name}: planted entries are {{from, to, feet:[front|back]}} step ranges")
        arc = sequence.get("arc", {})
        if not isinstance(arc, dict) or any(not k.isdigit() or int(k) >= len(steps) or v not in ("cw", "ccw")
                                            for k, v in arc.items()):
            raise ValueError(f"{name}: arc maps a step index to cw or ccw")
        parsed[name] = {"steps": steps, "contact_step": contact, "loop": sequence.get("loop", False),
                        "planted": planted, "arc": {int(k): v for k, v in arc.items()}}
    return {"name": data.get("name", path.stem), "canvas": canvas, "floor_y": floor,
            "facing": data.get("facing", "right"), "frames": frames, "sequences": parsed,
            "thresholds": thresholds}


def _mask(image):
    return image.getchannel("A").point(lambda a: 255 if a >= 32 else 0)


def _count(mask):
    return mask.histogram()[255]


def _profile(mask, axis):
    """Opaque pixel count per column (axis=0) or per row (axis=1)."""
    width, height = mask.size
    size = (width, 1) if axis == 0 else (1, height)
    scale = height if axis == 0 else width
    return [v * scale / 255 for v in mask.resize(size, Image.Resampling.BOX).tobytes()]


def body_height(mask):
    rows = _profile(mask, 1)
    total = sum(rows)
    if not total:
        raise ValueError("frame has no visible pixels")
    budget, top, shed = total * .002, 0, 0.0
    while shed + rows[top] <= budget:
        shed += rows[top]
        top += 1
    bottom, shed = len(rows), 0.0
    while shed + rows[bottom - 1] <= budget:
        shed += rows[bottom - 1]
        bottom -= 1
    return bottom - top


def ground_contacts(mask, floor_y, band, gap):
    """Clusters of opaque columns touching the floor band, left to right, as (x0, x1) spans."""
    strip = mask.crop((0, max(0, floor_y - band), mask.width, min(mask.height, floor_y + 2)))
    columns = _profile(strip, 0)
    spans, start, last = [], None, None
    for x, count in enumerate(columns):
        if count >= 1:
            if start is None or x - last > gap:
                if start is not None:
                    spans.append((start, last + 1))
                start = x
            last = x
    if start is not None:
        spans.append((start, last + 1))
    return spans


def _feet(frame, mask, floor_y, body, facing):
    sockets = frame["sockets"]
    if "foot_front" in sockets and "foot_back" in sockets:
        return {"front": sockets["foot_front"], "back": sockets["foot_back"], "source": "sockets"}
    band = max(2, round(body * .03))
    spans = ground_contacts(mask, floor_y, band, max(2, round(body * .02)))
    tip = sockets["tip"]
    if tip[1] >= floor_y - band - body * .05:
        # A tool resting on or sunk into the floor is not a foot.
        reach = body * .15
        spans = [s for s in spans if s[1] < tip[0] - reach or s[0] > tip[0] + reach]
    if not spans:
        return {"front": None, "back": None, "source": "floor-band"}
    centre = lambda span: ((span[0] + span[1]) / 2, float(floor_y))
    if len(spans) == 1:
        # One grounded foot, the other lifted; which one is resolved against the neighbouring pose.
        return {"front": None, "back": None, "single": centre(spans[0]), "source": "floor-band"}
    left, right = spans[0], spans[-1]
    back, front = (left, right) if facing == "right" else (right, left)
    return {"front": centre(front), "back": centre(back), "source": "floor-band"}


def _resolve(a, b):
    """Name a lone grounded foot by the nearer foot of the neighbouring pose."""
    if not a or not b:
        return None
    a, b = dict(a), dict(b)
    for one, other in ((a, b), (b, a)):
        if "single" in one and other.get("front") and other.get("back"):
            point = one.pop("single")
            side = "front" if math.dist(point, other["front"]) <= math.dist(point, other["back"]) else "back"
            one[side] = point
    if "single" in a or "single" in b:
        return None
    return a, b


def _iou(a, b):
    union = _count(ImageChops.lighter(a, b))
    return _count(ImageChops.darker(a, b)) / union if union else 1.0


def _breakdown(a, b, count, arc):
    """Target tip positions for `count` in-betweens from frame a to frame b."""
    tip_a, tip_b = a["sockets"]["tip"], b["sockets"]["tip"]
    targets = []
    if "grip" in a["sockets"] and "grip" in b["sockets"]:
        grip_a, grip_b = a["sockets"]["grip"], b["sockets"]["grip"]
        angle_a = math.atan2(tip_a[1] - grip_a[1], tip_a[0] - grip_a[0])
        angle_b = math.atan2(tip_b[1] - grip_b[1], tip_b[0] - grip_b[0])
        delta = (angle_b - angle_a + math.pi) % (2 * math.pi) - math.pi
        if arc == "cw" and delta < 0:
            delta += 2 * math.pi
        elif arc == "ccw" and delta > 0:
            delta -= 2 * math.pi
        length_a = math.dist(tip_a, grip_a)
        length_b = math.dist(tip_b, grip_b)
        for i in range(1, count + 1):
            t = i / (count + 1)
            grip = (grip_a[0] + (grip_b[0] - grip_a[0]) * t, grip_a[1] + (grip_b[1] - grip_a[1]) * t)
            angle, length = angle_a + delta * t, length_a + (length_b - length_a) * t
            targets.append({"tip": [round(grip[0] + math.cos(angle) * length), round(grip[1] + math.sin(angle) * length)],
                            "grip": [round(grip[0]), round(grip[1])],
                            "blade_angle_deg": round(math.degrees(angle), 1)})
        return targets, "arc-around-grip"
    for i in range(1, count + 1):
        t = i / (count + 1)
        targets.append({"tip": [round(tip_a[0] + (tip_b[0] - tip_a[0]) * t), round(tip_a[1] + (tip_b[1] - tip_a[1]) * t)]})
    return targets, "linear"


def assess(request):
    frames, floor_y, limits = request["frames"], request["floor_y"], request["thresholds"]
    masks = {ident: _mask(frame["image"]) for ident, frame in frames.items()}
    first = next(iter(frames))
    body = body_height(masks[first])
    findings, breakdowns, sequences = [], [], {}

    def finding(code, severity, sequence, where, message, **detail):
        findings.append({"code": code, "severity": severity, "sequence": sequence, "where": where,
                         "message": message, **detail})

    frame_metrics = {}
    for ident, frame in frames.items():
        box = masks[ident].getbbox()
        depth = box[3] - 1 - floor_y if box else 0
        frame_metrics[ident] = {"visible_bounds": list(box) if box else None, "below_floor_px": max(0, depth)}
        if depth > limits["floor_tolerance_px"]:
            finding("floor-penetration", "error", None, ident,
                    f"{ident}: 그림이 바닥선 아래로 {depth}px 내려갑니다. 공구·발을 바닥선(y={floor_y}) 위로 올리세요.",
                    depth_px=depth)
        sockets = frame["sockets"]
        if "grip" in sockets:
            frame_metrics[ident]["tool_length_px"] = round(math.dist(sockets["grip"], sockets["tip"]), 1)
    lengths = [m["tool_length_px"] for i, m in frame_metrics.items()
               if "tool_length_px" in m and not frames[i]["foreshortened"]]
    tool = None
    if len(lengths) >= 2:
        median = sorted(lengths)[len(lengths) // 2]
        spread = (max(lengths) - min(lengths)) / median
        tool = {"median_px": median, "spread": round(spread, 3)}
        if spread > limits["tool_length_spread"]:
            shortest = min((m["tool_length_px"], i) for i, m in frame_metrics.items() if "tool_length_px" in m
                           and not frames[i]["foreshortened"])
            longest = max((m["tool_length_px"], i) for i, m in frame_metrics.items() if "tool_length_px" in m
                          and not frames[i]["foreshortened"])
            finding("tool-length-drift", "error", None, f"{shortest[1]}..{longest[1]}",
                    f"공구 길이가 포즈마다 {spread:.0%} 달라집니다 ({shortest[0]:.0f}px {shortest[1]} ~ {longest[0]:.0f}px {longest[1]}). "
                    f"원근으로 짧아진 포즈는 foreshortened로 표시하고, 나머지는 손잡이~끝 길이를 {median:.0f}px에 맞추세요.",
                    spread=round(spread, 3))

    for name, sequence in request["sequences"].items():
        steps = sequence["steps"]
        order = list(range(len(steps)))
        pairs = list(zip(order, order[1:]))
        if sequence["loop"] and steps[-1]["frame"] != steps[0]["frame"]:
            pairs.append((len(steps) - 1, 0))
        planted = {}
        for span in sequence["planted"]:
            for i in range(span["from"], span["to"]):
                planted.setdefault(i, set()).update(span["feet"])
        feet = {i: _feet(frames[s["frame"]], masks[s["frame"]], floor_y, body, request["facing"])
                for i, s in enumerate(steps)}
        rows = []
        for i, j in pairs:
            a, b = frames[steps[i]["frame"]], frames[steps[j]["frame"]]
            travel = math.dist(a["sockets"]["tip"], b["sockets"]["tip"])
            row = {"from_step": i, "to_step": j, "from": a["id"], "to": b["id"], "hold_ms": steps[i]["ms"],
                   "tip_travel_px": round(travel, 1), "tip_travel_body": round(travel / body, 3),
                   "tip_speed_px_per_ms": round(travel / steps[i]["ms"], 2),
                   "silhouette_iou": round(_iou(masks[a["id"]], masks[b["id"]]), 3)}
            pair = _resolve(feet[i], feet[j])
            if pair:
                feet_i, feet_j = pair
                row["ground_shift_px"] = {k: round(math.dist(feet_i[k], feet_j[k]), 1) for k in ("front", "back")
                                          if feet_i[k] and feet_j[k]}
                for foot in sorted(planted.get(i, set())):
                    if feet_i[foot] and not feet_j[foot]:
                        finding("foot-lift", "error", name, f"step {i}->{j}",
                                f"{a['id']}→{b['id']}: 고정해야 할 {foot} 발이 바닥에서 떨어집니다. 발바닥을 바닥선(y={floor_y})에 붙여 그리세요.")
                for foot, shift in row["ground_shift_px"].items():
                    if shift / body <= limits["skate_body"]:
                        continue
                    if foot in planted.get(i, set()):
                        finding("foot-skate", "error", name, f"step {i}->{j}",
                                f"{a['id']}→{b['id']}: 고정된 {foot} 발이 {shift:.0f}px 미끄러집니다. "
                                "같은 바닥 위치에 발을 다시 그리거나 고정 구간을 고치세요.", shift_px=shift)
                    else:
                        finding("ground-contact-shift", "warning", name, f"step {i}->{j}",
                                f"{a['id']}→{b['id']}: {foot} 발 접지점이 {shift:.0f}px 이동합니다. 발을 딛는 동작이 아니면 planted로 고정하세요.",
                                shift_px=shift)
            if row["silhouette_iou"] < limits["min_iou"]:
                finding("silhouette-pop", "warning", name, f"step {i}->{j}",
                        f"{a['id']}→{b['id']}: 실루엣 겹침이 {row['silhouette_iou']:.2f}로 화면이 튑니다.",
                        iou=row["silhouette_iou"])
            if row["tip_travel_body"] > limits["max_step_body"]:
                count = math.ceil(row["tip_travel_body"] / limits["max_step_body"]) - 1
                targets, method = _breakdown(a, b, count, sequence["arc"].get(i))
                # In-betweens take time from the outgoing hold, so later step start times stay fixed.
                share = [steps[i]["ms"] // (count + 1)] * (count + 1)
                share[0] += steps[i]["ms"] - sum(share)
                plan = {"sequence": name, "after_step": i, "from": a["id"], "to": b["id"], "count": count,
                        "method": method, "timing_ms": share,
                        "inbetweens": [dict(t, ms=ms) for t, ms in zip(targets, share[1:])]}
                breakdowns.append(plan)
                row["needs_inbetweens"] = count
                finding("tip-jump", "error", name, f"step {i}->{j}",
                        f"{a['id']}→{b['id']}: 칼끝이 한 노출에 몸높이의 {row['tip_travel_body']:.2f}배({travel:.0f}px) 이동합니다. "
                        f"중간 포즈 {count}장을 breakdowns.json의 목표 좌표로 그리세요.",
                        travel_body=row["tip_travel_body"], inbetweens=count)
            rows.append(row)
        contact = sequence["contact_step"]
        overshoot = None
        if contact is not None:
            path = list(range(contact, len(steps))) + ([0] if sequence["loop"] and steps[-1]["frame"] != steps[0]["frame"] else [])
            rest = frames[steps[path[-1]]["frame"]]["sockets"]["tip"]
            tips = [frames[steps[k]["frame"]]["sockets"]["tip"] for k in path]
            overshoot = {}
            for axis, label in ((1, "vertical"), (0, "horizontal")):
                values = [t[axis] for t in tips]
                turn = next((k for k in range(1, len(values) - 1)
                             if (values[k] - values[k - 1]) * (values[k + 1] - values[k]) < 0), None)
                if turn is None:
                    continue
                approach = math.copysign(1, rest[axis] - values[turn])
                worst = max(((values[k] - rest[axis]) * approach, k) for k in range(turn + 1, len(values) - 1)) \
                    if turn + 1 < len(values) - 1 else (0.0, None)
                overshoot[label] = round(worst[0], 1)
                if worst[1] is not None and worst[0] > limits["overshoot_body"] * body:
                    step = path[worst[1]]
                    finding("post-contact-reversal", "error", name, f"step {step}",
                            f"{steps[step]['frame']}: 접촉 뒤 칼끝이 대기 위치를 {worst[0]:.0f}px 지나쳐 반대로 돌아갑니다 ({label}). "
                            "두 번째 휘두르기로 읽히므로 회수 포즈는 칼끝이 후속 위치와 대기 위치 사이에 머물게 그리세요.",
                            overshoot_px=round(worst[0], 1), axis=label)
            ms = [s["ms"] for s in steps]
            median_ms = sorted(ms)[len(ms) // 2]
            if steps[contact]["ms"] < limits["contact_exposure_ratio"] * median_ms:
                finding("contact-exposure", "warning", name, f"step {contact}",
                        f"접촉 포즈 노출이 {steps[contact]['ms']}ms로 다른 단계(중앙값 {median_ms}ms)보다 짧아 타격이 읽히기 어렵습니다.",
                        ms=steps[contact]["ms"])
        sequences[name] = {"duration_ms": sum(s["ms"] for s in steps), "transitions": rows,
                           "post_contact_overshoot_px": overshoot,
                           "feet": {i: f for i, f in feet.items() if f}}
    errors = [f for f in findings if f["severity"] == "error"]
    return {"schema_version": 1, "name": request["name"], "passed": not errors,
            "body_height_px": body, "floor_y": floor_y, "thresholds": limits, "tool_length": tool,
            "frames": frame_metrics, "sequences": sequences, "findings": findings,
            "breakdown_count": sum(b["count"] for b in breakdowns),
            "visual_review": "pending", "artistic_acceptance": "pending"}, breakdowns


def render_trail(request, report, breakdowns, path, size=1024):
    """Onion skin of each sequence with tip path, floor, rest height and planned in-betweens."""
    canvas = request["canvas"]
    scale = size / max(canvas)
    names = list(request["sequences"])
    width, height = round(canvas[0] * scale), round(canvas[1] * scale)
    sheet = Image.new("RGB", (width * len(names), height + 40), "#17242b")
    draw = ImageDraw.Draw(sheet)
    flagged = {(f["sequence"], f["where"]) for f in report["findings"] if f["severity"] == "error"}
    for column, name in enumerate(names):
        steps = request["sequences"][name]["steps"]
        ox = column * width
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for frame in dict.fromkeys(s["frame"] for s in steps):
            ghost = request["frames"][frame]["image"].resize((width, height), Image.Resampling.BILINEAR)
            alpha = ghost.getchannel("A").point(lambda a: a // 4)
            tint = Image.new("RGBA", (width, height), (225, 232, 236, 0))
            tint.putalpha(alpha)
            layer.alpha_composite(tint)
        sheet.paste(layer, (ox, 40), layer)
        floor = 40 + request["floor_y"] * scale
        draw.line((ox, floor, ox + width, floor), fill="#6f8a93", width=2)
        tips = [request["frames"][s["frame"]]["sockets"]["tip"] for s in steps]
        if request["sequences"][name]["loop"] and steps[-1]["frame"] != steps[0]["frame"]:
            tips.append(tips[0])
        rest = 40 + tips[-1][1] * scale
        draw.line((ox, rest, ox + width, rest), fill="#355058", width=1)
        for k, (p, q) in enumerate(zip(tips, tips[1:])):
            bad = (name, f"step {k}->{(k + 1) % len(steps) if k + 1 >= len(steps) else k + 1}") in flagged
            draw.line((ox + p[0] * scale, 40 + p[1] * scale, ox + q[0] * scale, 40 + q[1] * scale),
                      fill="#ff5a4e" if bad else "#f2a33a", width=3)
        for k, p in enumerate(tips[:len(steps)]):
            x, y = ox + p[0] * scale, 40 + p[1] * scale
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#f1e9da")
            draw.text((x + 7, y - 7), str(k), fill="#f1e9da")
        for plan in breakdowns:
            if plan["sequence"] != name:
                continue
            for target in plan["inbetweens"]:
                x, y = ox + target["tip"][0] * scale, 40 + target["tip"][1] * scale
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline="#9dd9c5", width=2)
        errors = sum(1 for f in report["findings"] if f["sequence"] == name and f["severity"] == "error")
        draw.text((ox + 10, 12), f"{name}  errors {errors}  body {report['body_height_px']}px", fill="#f1e9da")
    sheet.save(path)


def produce(request_path, stage):
    request = load(Path(request_path))
    report, breakdowns = assess(request)
    write_json(stage / FILES["report"], report)
    write_json(stage / FILES["breakdowns"], {"schema_version": 1, "plans": breakdowns})
    render_trail(request, report, breakdowns, stage / FILES["trail"])
    return FILES


def summary(stage):
    return json.loads((Path(stage) / FILES["report"]).read_text())
