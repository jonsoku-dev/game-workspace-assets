"""Offline pixel-grid articulation of an explicitly assigned approved master sprite.

The caller supplies visible part pixels and parent-before-child joint anchors;
this module neither segments anatomy nor invents occluded artwork.
"""
import colorsys
import hashlib
import io
import json
import math
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from .action_set import ACTIONS, digest, duration, local_path, point
from .bundle import open_png, write_json

ROLES = {'torso', 'head', 'arm_left', 'arm_right', 'leg_left', 'leg_right', 'weapon', 'accessory'}
MAX_PIXELS = 4_194_304


def pixel_data(image):
    return getattr(image, 'get_flattened_data', image.getdata)()


def vector(value, bound, label):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(v) is not int or abs(v) > bound for v in value)):
        raise ValueError(f'{label} requires two integers within +/-{bound}')
    return value


def defaults(parts):
    """Semantic role choreography: sway, stride, sprint, windup/strike, tuck, recoil."""
    poses = {
        'idle': [(0, 0, 0, 0), (4, -10, 0, 0), (0, 0, 0, 0), (-4, 10, 0, 0)],
        'walk': [(0, 24, -22, 0), (0, 0, 0, 0), (0, -24, 22, 0), (0, 0, 0, 0)],
        'run': [(10, 48, -42, -1), (15, -12, 12, -2), (10, -48, 42, -1), (15, 12, -12, -2)],
        'attack': [(-10, -50, 8, 0), (-16, -85, 15, 0), (18, 95, -12, 0), (8, 60, -6, 0), (0, 0, 0, 0)],
        'jump': [(-8, -20, 30, 1), (0, -65, 45, -3), (0, -80, 65, -6), (5, -30, 25, -3), (-8, 10, 30, 1)],
        'hurt': [(-18, -35, 18, 0), (-25, -60, 25, 0), (-12, -25, 10, 0), (0, 0, 0, 0)],
    }
    output = {}
    for name, sequence in poses.items():
        frames = []
        for body, arm, leg, rise in sequence:
            transforms = {}
            for part in parts:
                role = part['role']
                angle = {'torso': body, 'head': -body / 2, 'arm_left': arm,
                         'arm_right': -arm if name in ('walk', 'run') else arm / 2,
                         'leg_left': leg, 'leg_right': -leg if name in ('walk', 'run') else leg / 2}.get(role, 0)
                transforms[part['id']] = {'angle_deg': angle}
            frames.append({'duration_ms': 160 if name == 'idle' else 90 if name == 'run' else 120,
                           'root_offset_px': [0, rise], 'parts': transforms})
        output[name] = {'frames': frames}
    return output


def snapshot(path, limit, label, snapshots):
    key = path.resolve(strict=True)
    if key not in snapshots:
        with key.open('rb') as stream:
            snapshots[key] = stream.read(limit + 1)
    data = snapshots[key]
    if len(data) > limit:
        raise ValueError(label + ' exceeds byte limit')
    return data


def load_rig(request, root, master, snapshots=None):
    snapshots = {} if snapshots is None else snapshots
    rig = request.get('rig')
    if not isinstance(rig, dict) or set(rig) != {'parts'}:
        raise ValueError('rig requires parts')
    parts = rig['parts']
    if not isinstance(parts, list) or not 2 <= len(parts) <= 24:
        raise ValueError('rig requires 2..24 explicit parts')
    seen, assigned, result = set(), set(), []
    opaque = {(x, y) for y in range(master.height) for x in range(master.width) if master.getpixel((x, y))[3]}
    for part in parts:
        if (not isinstance(part, dict) or (set(part) - {'contact_px', 'joint_underlap'}) not in
                ({'id', 'role', 'parent', 'anchor_px', 'rect'}, {'id', 'role', 'parent', 'anchor_px', 'mask'})):
            raise ValueError('part requires id, role, parent, anchor_px and exactly rect or mask')
        pid, parent = part['id'], part['parent']
        if not isinstance(pid, str) or not pid.isidentifier() or len(pid) > 40 or pid in seen:
            raise ValueError('part ids must be unique identifiers of at most 40 characters')
        if not isinstance(part['role'], str) or part['role'] not in ROLES or (parent is not None and (not isinstance(parent, str) or parent not in seen)):
            raise ValueError('role must be supported; parent must precede child (no cycles)')
        anchor = point(part['anchor_px'], master.size, 'anchor_px')
        if 'contact_px' in part:
            point(part['contact_px'], master.size, 'contact_px')
        mask_pin = {}
        if 'rect' in part:
            rect = part['rect']
            if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
                    or min(rect) < 0 or min(rect[2:]) < 1
                    or rect[0] + rect[2] > master.width or rect[1] + rect[3] > master.height):
                raise ValueError('rect requires x,y,width,height inside master')
            x, y, w, h = rect
            pixels = {(a, b) for a, b in opaque if x <= a < x + w and y <= b < y + h}
        else:
            mask_bytes = snapshot(local_path(root, part['mask']), 16_777_216, 'mask', snapshots)
            mask = open_png(io.BytesIO(mask_bytes), max_pixels=128 ** 2)
            mask_pin = {'mask_sha256': hashlib.sha256(mask_bytes).hexdigest()}
            if mask.size != master.size or mask.mode not in ('1', 'L'):
                raise ValueError('mask must be a same-size binary grayscale PNG (0 or 255)')
            if not set(pixel_data(mask.convert('L'))) <= {0, 255}:
                raise ValueError('mask must be binary')
            pixels = {(x, y) for y in range(mask.height) for x in range(mask.width) if mask.getpixel((x, y))}
            if not pixels <= opaque:
                raise ValueError('mask assigns transparent master pixels')
        if not pixels or pixels & assigned:
            raise ValueError('parts must contain visible pixels and may not overlap')
        if 'joint_underlap' in part:
            support = part['joint_underlap']
            required = {'parent_px', 'child_px', 'radius_px', 'source_px'}
            if (parent is None or not isinstance(support, dict) or not required <= set(support) <= required | {'edge_px'}
                    or type(support['radius_px']) is not int or not 1 <= support['radius_px'] <= 6):
                raise ValueError('joint_underlap requires a parent, endpoint/source points and radius_px in 1..6')
            for key in ('parent_px', 'child_px', 'source_px', 'edge_px'):
                if key in support:
                    point(support[key], master.size, 'joint_underlap '+key)
            span = math.dist(support['parent_px'], support['child_px'])
            if not 0 < span <= 32:
                raise ValueError('joint_underlap rest endpoint span must be in (0,32] pixels')
            parent_pixels = next(p['pixels'] for p in result if p['id'] == parent)
            if any(tuple(support[key]) not in pixels | parent_pixels for key in ('source_px', 'edge_px') if key in support):
                raise ValueError('joint_underlap samples must be visible pixels owned by the child or parent')
        assigned |= pixels
        seen.add(pid)
        result.append({**part, **mask_pin, 'anchor_px': anchor, 'pixels': pixels})
    if assigned != opaque:
        raise ValueError('rig must assign every opaque master pixel exactly once')
    if not any(p['role'].startswith(('arm_', 'leg_')) for p in result):
        raise ValueError('rig needs at least one articulated arm or leg role')
    return result


def compose(a, b):
    ac, ass, ax, ay = a
    bc, bs, bx, by = b
    return ac * bc - ass * bs, ass * bc + ac * bs, ac * bx - ass * by + ax, ass * bx + ac * by + ay


def apply(matrix, x, y):
    c, s, tx, ty = matrix
    return c * x - s * y + tx, s * x + c * y + ty


def render(master, parts, frame):
    matrices, anchors, contacts, clipped = {}, {}, {}, 0
    canvas = Image.new('RGBA', master.size)
    for part in parts:
        transform = frame['parts'].get(part['id'], {})
        angle = math.radians(transform.get('angle_deg', 0))
        c, s = math.cos(angle), math.sin(angle)
        ax, ay = part['anchor_px']
        dx, dy = transform.get('offset_px', [0, 0])
        local = (c, s, ax - c * ax + s * ay + dx, ay - s * ax - c * ay + dy)
        parent = matrices[part['parent']] if part['parent'] else (1, 0, *frame['root_offset_px'])
        matrix = compose(parent, local)
        matrices[part['id']] = matrix
        anchors[part['id']] = [round(v, 3) for v in apply(matrix, ax, ay)]
        if 'contact_px' in part:
            contacts[part['id']] = [round(v, 3) for v in apply(matrix, *part['contact_px'])]
        # Inverse nearest sampling fills rotated pixels without introducing palette colors.
        corners = [apply(matrix, x + ox, y + oy) for x, y in part['pixels'] for ox, oy in ((-.5, -.5), (.5, .5))]
        left = math.floor(min(x for x, _ in corners)) - 1
        right = math.ceil(max(x for x, _ in corners)) + 1
        top = math.floor(min(y for _, y in corners)) - 1
        bottom = math.ceil(max(y for _, y in corners)) + 1
        c, s, tx, ty = matrix
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                sx, sy = round(c * (x - tx) + s * (y - ty)), round(-s * (x - tx) + c * (y - ty))
                if (sx, sy) in part['pixels']:
                    if 0 <= x < master.width and 0 <= y < master.height:
                        canvas.putpixel((x, y), master.getpixel((sx, sy)))
                    else:
                        clipped += 1
    underlay = Image.new('RGBA', master.size)
    underlaps, support_clipped = [], 0
    first = next(iter(matrices.values()))
    rigid = all(all(abs(a-b) <= 1e-9 for a, b in zip(first, matrix)) for matrix in matrices.values())
    for part in parts:
        if 'joint_underlap' not in part:
            continue
        spec = part['joint_underlap']
        start = apply(matrices[part['parent']], *spec['parent_px'])
        end = apply(matrices[part['id']], *spec['child_px'])
        if math.dist(start, end) > 64:
            raise ValueError('posed joint_underlap span exceeds 64 pixels; revise joint endpoints/transforms')
        radius = spec['radius_px']
        left = math.floor(min(start[0], end[0])-radius)
        top = math.floor(min(start[1], end[1])-radius)
        right = math.ceil(max(start[0], end[0])+radius)+1
        bottom = math.ceil(max(start[1], end[1])+radius)+1
        record = {'part': part['id'], 'active': not rigid,
                  'parent_endpoint_px': [round(v, 3) for v in start],
                  'child_endpoint_px': [round(v, 3) for v in end], 'radius_px': radius,
                  'source_px': spec['source_px'], 'edge_px': spec.get('edge_px'),
                  'drawn_pixels': 0, 'visible_support_pixels': 0, 'clipped_pixels': 0,
                  'region_xywh': [max(0, left), max(0, top),
                                  max(0, min(master.width, right)-max(0, left)),
                                  max(0, min(master.height, bottom)-max(0, top))]}
        if not rigid:
            sx, sy = spec['parent_px']
            rx, ry = spec['child_px'][0]-sx, spec['child_px'][1]-sy
            vx, vy = end[0]-start[0], end[1]-start[1]
            den = vx*vx+vy*vy
            angle = math.atan2(vy, vx)-math.atan2(ry, rx)
            co, si = math.cos(angle), math.sin(angle)
            for y in range(top, bottom):
                for x in range(left, right):
                    t = max(0, min(1, ((x-start[0])*vx+(y-start[1])*vy)/den)) if den else 0
                    ox, oy = x-start[0]-t*vx, y-start[1]-t*vy
                    distance = math.hypot(ox, oy)
                    if distance > radius:
                        continue
                    # Clip the authored patch to existing rest alpha; no inferred hidden anatomy.
                    source_x, source_y = round(sx+t*rx+co*ox+si*oy), round(sy+t*ry-si*ox+co*oy)
                    if not (0 <= source_x < master.width and 0 <= source_y < master.height
                            and master.getpixel((source_x, source_y))[3]):
                        continue
                    if not (0 <= x < master.width and 0 <= y < master.height):
                        record['clipped_pixels'] += 1
                        continue
                    sample = spec.get('edge_px', spec['source_px']) if distance > radius-1 else spec['source_px']
                    underlay.putpixel((x, y), master.getpixel(tuple(sample)))
                    record['drawn_pixels'] += 1
                    record['visible_support_pixels'] += not canvas.getpixel((x, y))[3]
        support_clipped += record['clipped_pixels']
        underlaps.append(record)
    canvas = Image.alpha_composite(underlay, canvas)
    for record in underlaps:
        x, y, w, h = record['region_xywh']
        components = foreground_components(canvas.crop((x, y, x+w, y+h))) if w and h else []
        for component in components:
            component['bounds_xywh'][0] += x
            component['bounds_xywh'][1] += y
        record['foreground_components'] = components
        record['sizeable_component_count'] = sum(c['area_px'] >= 4 for c in components)
    return canvas, {'clipped_part_pixels': clipped+support_clipped, 'clipped_underlap_pixels': support_clipped,
                    'anchors_px': anchors, 'contact_points_px': contacts, 'joint_underlaps': underlaps}


def frames_for(action, parts, size):
    if not isinstance(action, dict) or set(action) != {'frames'}:
        raise ValueError('action override requires frames')
    frames = action['frames']
    if not isinstance(frames, list) or not 2 <= len(frames) <= 32:
        raise ValueError('motion actions require 2..32 frames')
    ids = {p['id'] for p in parts}
    output = []
    for frame in frames:
        if not isinstance(frame, dict) or not {'duration_ms'} <= set(frame) <= {'duration_ms', 'parts', 'root_offset_px', 'contacts', 'hold'}:
            raise ValueError('invalid frame fields')
        duration(frame['duration_ms'])
        if 'hold' in frame and type(frame['hold']) is not bool:
            raise ValueError('hold must be boolean')
        transforms = frame.get('parts', {})
        if not isinstance(transforms, dict) or not set(transforms) <= ids:
            raise ValueError('frame parts must reference rig ids')
        for trans in transforms.values():
            if not isinstance(trans, dict) or not set(trans) <= {'angle_deg', 'offset_px'}:
                raise ValueError('part transform supports angle_deg and offset_px')
            angle = trans.get('angle_deg', 0)
            if type(angle) not in (int, float) or abs(angle) > 180 or not math.isfinite(angle):
                raise ValueError('angle_deg must be finite within +/-180')
            vector(trans.get('offset_px', [0, 0]), 32, 'offset_px')
        contacts = frame.get('contacts', {})
        if not isinstance(contacts, dict) or not set(contacts) <= ids:
            raise ValueError('contacts must reference rig ids')
        for target in contacts.values():
            point(target, size, 'contact target')
        output.append({**frame, 'parts': transforms,
                       'root_offset_px': vector(frame.get('root_offset_px', [0, 0]), 32, 'root_offset_px')})
    if sum(f['duration_ms'] for f in output) > 120000:
        raise ValueError('action duration exceeds 120000 ms')
    return output


def difference(a, b):
    return sum(p != q for p, q in zip(pixel_data(a), pixel_data(b)))


def foreground_components(image):
    remaining = {(x, y) for y in range(image.height) for x in range(image.width) if image.getpixel((x, y))[3]}
    components = []
    while remaining:
        pending, group = [next(iter(remaining))], set()
        while pending:
            xy = pending.pop()
            if xy not in remaining:
                continue
            remaining.remove(xy)
            group.add(xy)
            x, y = xy
            pending.extend((x+dx, y+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           if (dx or dy) and (x+dx, y+dy) in remaining)
        left, top = min(x for x, y in group), min(y for x, y in group)
        right, bottom = max(x for x, y in group)+1, max(y for x, y in group)+1
        components.append({'area_px': len(group), 'bounds_xywh': [left, top, right-left, bottom-top]})
    return sorted(components, key=lambda c: (-c['area_px'], c['bounds_xywh']))



def review_previews(master, parts, inspection, stage):
    """Show declared joints and measured contacts; no anatomical or artistic verdict."""
    colors = {p['id']: tuple(round(c * 255) for c in colorsys.hsv_to_rgb(i / len(parts), .45, 1))
              for i, p in enumerate(parts)}
    numbers = {p['id']: i + 1 for i, p in enumerate(parts)}
    scale = min(8, 512 // max(master.size))
    enlarged = master.copy()
    tint = Image.new('RGBA', master.size)
    ink = ImageDraw.Draw(tint)
    for part in parts:
        for xy in part['pixels']:
            ink.point(xy, fill=(*colors[part['id']], 105))
    enlarged = Image.alpha_composite(enlarged, tint).resize(
        (master.width * scale, master.height * scale), Image.Resampling.NEAREST)
    x0, y0 = max(160, master.width + 32), 48
    legend = x0 + enlarged.width + 24
    rig = Image.new('RGB', (legend + 390, max(enlarged.height + 88, len(parts) * 32 + 64)), '#20333d')
    draw = ImageDraw.Draw(rig)
    draw.text((16, 12), 'MASTER 1x', fill='white')
    draw.text((x0, 12), f'EXPLICIT RIG {scale}x / IDs match inspection.json', fill='white')
    rig.paste(master, (16, y0), master)
    rig.paste(enlarged, (x0, y0), enlarged)
    anchors = {p['id']: (x0 + p['anchor_px'][0] * scale, y0 + p['anchor_px'][1] * scale) for p in parts}
    for part in parts:
        if part['parent']:
            draw.line((anchors[part['parent']], anchors[part['id']]), fill='#c4d3dc', width=2)
    for part in parts:
        pid = part['id']
        x, y = anchors[pid]
        color = colors[pid]
        draw.ellipse((x-4, y-4, x+4, y+4), fill=color, outline='white')
        draw.text((x+6, y-10), str(numbers[pid]), fill=color, stroke_width=1, stroke_fill='#102029')
        if 'contact_px' in part:
            cx, cy = part['contact_px']
            cx, cy = x0 + cx * scale, y0 + cy * scale
            draw.rectangle((cx-4, cy-4, cx+4, cy+4), outline=color, width=2)
        if 'joint_underlap' in part:
            support = part['joint_underlap']
            endpoints = [(x0 + support[key][0]*scale, y0 + support[key][1]*scale)
                         for key in ('parent_px', 'child_px')]
            draw.line(endpoints, fill='#ffbd76', width=2)
        row = 48 + (numbers[pid] - 1) * 32
        draw.text((legend, row), f"{numbers[pid]} {pid}", fill=color)
        support_label = f" / underlap r{part['joint_underlap']['radius_px']}" if 'joint_underlap' in part else ''
        draw.text((legend, row+13), f"{part['role']} / parent: {part['parent'] or '-'}{support_label}", fill='#c4d3dc')
    draw.text((16, rig.height-22), 'Circles: joint anchors / squares: declared contact landmarks. No inferred bones or feet.', fill='#c4d3dc')
    rig.save(stage / 'rig.png')

    scale = min(4, max(1, 128 // max(master.size)))
    tile_w, tile_h = max(184, master.width * scale + 24), master.height * scale + 72
    columns = min(8, max(len(a['frames']) for a in inspection['actions'].values()))
    rows = sum(math.ceil(len(a['frames']) / columns) for a in inspection['actions'].values())
    headings = textwrap.wrap(
        'MOTION QA: all frames. T cyan cross = target; M amber circle = measured; IDs: rig.png. '
        'Only declared targets; errors are measurements, not IK or human acceptance. Full coordinates: inspection.json',
        width=max(20, columns * tile_w // 7))
    header_h = len(headings) * 14 + 12
    qa = Image.new('RGB', (columns * tile_w, rows * tile_h + header_h), '#20333d')
    draw = ImageDraw.Draw(qa)
    for i, line in enumerate(headings):
        draw.text((8, 6+i*14), line, fill='#c4d3dc')
    row = 0
    for name, action in inspection['actions'].items():
        for i, record in enumerate(action['frames']):
            x, y = i % columns * tile_w, (row + i // columns) * tile_h + header_h
            draw.text((x+6, y+4), f"{name}:{i} / {record['duration_ms']}ms", fill='white')
            image = open_png(stage / f'{name}-{i:02}.png').resize(
                (master.width * scale, master.height * scale), Image.Resampling.NEAREST)
            ox, oy = x + 12, y + 24
            qa.paste(image, (ox, oy), image)
            measurements = record['contact_measurements']
            for pid, contact in measurements.items():
                mx, my = (ox + contact['measured_px'][0] * scale, oy + contact['measured_px'][1] * scale)
                tx, ty = (ox + contact['target_px'][0] * scale, oy + contact['target_px'][1] * scale)
                # Off-cell contacts retain their exact coordinates in JSON, not a clamped marker.
                if all(0 <= v <= bound for v, bound in zip(contact['measured_px'], master.size)):
                    draw.line((mx, my, tx, ty), fill='#f0796c', width=2)
                    draw.ellipse((mx-3, my-3, mx+3, my+3), outline='#ffc565', width=2)
                draw.line((tx-4, ty, tx+4, ty), fill='#67e4ed', width=2)
                draw.line((tx, ty-4, tx, ty+4), fill='#67e4ed', width=2)
                draw.text((tx+5, ty-10), str(numbers[pid]), fill=colors[pid], stroke_width=1, stroke_fill='#102029')
            error = max((m['distance_px'] for m in measurements.values()), default=0)
            off_cell = sum(any(v < 0 or v > bound for v, bound in zip(m['measured_px'], master.size))
                           for m in measurements.values())
            footer = oy + master.height * scale + 5
            clipped = record['clipped_part_pixels']
            split = record['new_sizeable_components'] or (inspection['single_body_required'] and record['sizeable_component_count'] > 1)
            if clipped or split:
                draw.rectangle((x+2, y+2, x+tile_w-3, y+tile_h-3), outline='#ff8e7f', width=2)
            if split:
                for component in record['foreground_components']:
                    if component['area_px'] >= 4:
                        cx, cy, cw, ch = component['bounds_xywh']
                        draw.rectangle((ox+cx*scale, oy+cy*scale, ox+(cx+cw)*scale-1, oy+(cy+ch)*scale-1),
                                       outline='#ff8e7f', width=1)
            for joint in record['joint_underlaps']:
                jx, jy, jw, jh = joint['region_xywh']
                if jw and jh:
                    draw.rectangle((ox+jx*scale, oy+jy*scale, ox+(jx+jw)*scale-1, oy+(jy+jh)*scale-1),
                                   outline='#ffbd76' if joint['sizeable_component_count'] > 1 else '#8fb3c1')
                    draw.text((ox+jx*scale, oy+jy*scale), str(numbers[joint['part']]), fill='#ffbd76')
            draw.text((x+6, footer), f'CLIP {clipped} / contacts {len(measurements)}', fill='#ff8e7f' if clipped else '#afd7b2')
            draw.text((x+6, footer+14), f'max contact error {error:g}px' if measurements else 'No declared contact targets', fill='#ffbd76' if error else '#c4d3dc')
            detail = f'components {record["sizeable_component_count"]} / new {record["new_sizeable_components"]}'
            if off_cell:
                detail += f' / M off-cell {off_cell}'
            draw.text((x+6, footer+28), detail, fill='#ff8e7f' if split else '#c4d3dc')
        row += math.ceil(len(action['frames']) / columns)
    qa.save(stage / 'motion-qa.png')


class PoseQualityError(ValueError):
    """The requested rig and poses cannot produce distinguishable motion."""


def produce(request_path: Path, stage: Path, *, selected_actions=None, provisional_rig=False):
    snapshots = {}
    request_bytes = snapshot(request_path, 1_048_576, 'motion request', snapshots)
    request = json.loads(request_bytes.decode('utf-8'))
    if not isinstance(request, dict) or type(request.get('schema_version')) is not int or request['schema_version'] != 1:
        raise ValueError('motion request requires schema_version 1')
    unknown = request.keys() - {'schema_version', 'master', 'approved', 'rig', 'pivot_px_from_top_left', 'actions', 'extra_actions', 'single_body'}
    if unknown:
        raise ValueError('unknown field(s) in motion request: ' + ', '.join(sorted(unknown)))
    if request.get('approved') is not True and not (provisional_rig and request.get('approved') is False):
        raise ValueError('master requires explicit approved:true')
    single_body = request.get('single_body', False)
    if type(single_body) is not bool:
        raise ValueError('single_body must be boolean')
    source = local_path(request_path.parent, request.get('master'))
    source_bytes = snapshot(source, 16_777_216, 'master', snapshots)
    master = open_png(io.BytesIO(source_bytes), max_pixels=128 ** 2).convert('RGBA')
    if not 4 <= min(master.size) or max(master.size) > 128:
        raise ValueError('master dimensions must be in 4..128')
    if set(pixel_data(master.getchannel('A'))) != {0, 255}:
        raise ValueError('master requires both transparent and opaque pixels, with binary alpha')
    # Invisible RGB is not artwork; canonical transparent pixels make reconstruction exact.
    master.putdata([pixel if pixel[3] else (0, 0, 0, 0) for pixel in pixel_data(master)])
    pivot = point(request.get('pivot_px_from_top_left'), master.size, 'pivot')
    parts = load_rig(request, request_path.parent, master, snapshots)
    actions = defaults(parts)
    overrides = request.get('actions', {})
    if not isinstance(overrides, dict) or not set(overrides) <= set(ACTIONS):
        raise ValueError('actions overrides must use known action names')
    actions.update(overrides)
    extras = request.get('extra_actions', {})
    if not isinstance(extras, dict) or len(extras) > 26:
        raise ValueError('extra_actions requires at most 26 authored actions')
    loops = dict(ACTIONS)
    reserved = set(ACTIONS) | {'neutral', 'request', 'inspection', 'master', 'rig', 'rig_preview',
                               'motion_qa', 'rive_poses', 'action_set'}
    reserved.update(f'{name}_{index}' for name in (*ACTIONS, *extras) for index in range(32))
    for name, action in extras.items():
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or name in reserved:
            raise ValueError('extra action ids require 1..32 lowercase ASCII letters/digits/underscores, starting with a letter, and must not be reserved')
        if not isinstance(action, dict) or set(action) != {'loop', 'frames'} or type(action['loop']) is not bool:
            raise ValueError('extra actions require exactly loop (boolean) and frames')
        actions[name] = {'frames': action['frames']}
        loops[name] = action['loop']
    if selected_actions is not None:
        if not selected_actions or len(set(selected_actions)) != len(selected_actions) or set(selected_actions) - actions.keys():
            raise ValueError('selected actions must be distinct actions available in the motion request')
        actions = {name: actions[name] for name in selected_actions}
    frames = {name: frames_for(action, parts, master.size) for name, action in actions.items()}
    count = sum(len(value) for value in frames.values())
    wants_rive = bool(extras) or selected_actions is not None
    if wants_rive and count > 256:
        raise ValueError('extra actions exceed the 256-frame Rive manifest budget')
    if count * master.width * master.height > MAX_PIXELS or count * len(parts) * master.width * master.height > 33_554_432:
        raise ValueError('motion exceeds pixel/computation budget')
    neutral, _ = render(master, parts, {'parts': {}, 'root_offset_px': [0, 0]})
    if neutral.tobytes() != master.tobytes():
        raise ValueError('rig neutral reconstruction differs from master')
    rest_components = foreground_components(neutral)
    rest_sizeable = sum(c['area_px'] >= 4 for c in rest_components)
    neutral.save(stage / 'neutral.png')
    master.save(stage / 'master.png')
    files = {'neutral': 'neutral.png', 'request': 'action-set.request.json', 'inspection': 'inspection.json',
             'master': 'master.png', 'rig_preview': 'rig.png', 'motion_qa': 'motion-qa.png'}
    packed = {'schema_version': 1, 'cell_size': list(master.size), 'pivot_px_from_top_left': pivot, 'actions': {}, 'events': []}
    inspection = {'schema_version': 1, 'visual_review': 'unverified', 'artistic_acceptance': 'unverified',
                  'neutral_exact_visible_reconstruction': True, 'sampling': 'inverse-nearest-native-grid',
                  'single_body_required': single_body, 'component_min_area_px': 4,
                  'component_neighbors': 8, 'rest_foreground_components': rest_components,
                  'source': {'path': request['master'], 'sha256': hashlib.sha256(source_bytes).hexdigest(),
                             'request_sha256': hashlib.sha256(request_bytes).hexdigest()},
                  'rig': [{k: v for k, v in p.items() if k != 'pixels'} for p in parts],
                  'limitations': ['Visible cutout articulation only; hidden anatomy is not synthesized.',
                                  'Contacts are measured anchor targets, not inverse-kinematic constraints.',
                                  'Role choreography requires visual review for the supplied anatomy.'], 'actions': {}}
    palette = set(pixel_data(master))
    for name, action_frames in frames.items():
        images, records, entries, hashes = [], [], [], []
        for index, frame in enumerate(action_frames):
            image, record = render(master, parts, frame)
            if not set(pixel_data(image)) <= palette:
                raise ValueError('renderer introduced a color outside the master palette')
            filename = f'{name}-{index:02}.png'
            image.save(stage / filename)
            files[f'{name}_{index}'] = filename
            entries.append({'path': filename, 'duration_ms': frame['duration_ms']})
            components = foreground_components(image)
            sizeable = sum(c['area_px'] >= 4 for c in components)
            record.update({'foreground_components': components, 'sizeable_component_count': sizeable,
                           'new_sizeable_components': max(0, sizeable-rest_sizeable)})
            record.update({'duration_ms': frame['duration_ms'], 'authored_transform': frame, 'intentional_hold': frame.get('hold', False),
                           'contact_error_px': {pid: [round(a - b, 3) for a, b in zip(record['contact_points_px'].get(pid, record['anchors_px'][pid]), target)]
                                                for pid, target in frame.get('contacts', {}).items()}})
            record['contact_measurements'] = {
                pid: {'target_px': target,
                      'measured_px': record['contact_points_px'].get(pid, record['anchors_px'][pid]),
                      'delta_px': record['contact_error_px'][pid],
                      'distance_px': round(math.hypot(*record['contact_error_px'][pid]), 3),
                      'landmark': 'contact_px' if pid in record['contact_points_px'] else 'anchor_px'}
                for pid, target in frame.get('contacts', {}).items()}
            images.append(image)
            records.append(record)
            hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
        unique = len(set(hashes))
        if unique < 2:
            raise PoseQualityError(f'{name} has no visible articulation; revise rig/angles')
        packed['actions'][name] = {'loop': loops[name], 'frames': entries}
        inspection['actions'][name] = {'frames': records, 'unique_poses': unique,
                                       'duplicate_frames': [i for i, h in enumerate(hashes) if h in hashes[:i]],
                                       'unmarked_adjacent_duplicates': [i for i in range(1, len(hashes)) if hashes[i] == hashes[i-1] and not action_frames[i].get('hold', False)],
                                       'loop_seam_changed_pixels': difference(images[-1], images[0]) if loops[name] else None,
                                       'changed_pixels_from_neutral': [difference(image, neutral) for image in images]}
    signatures = {name: [digest(stage / entry['path']) for entry in action['frames']] for name, action in packed['actions'].items()}
    if len({tuple(value) for value in signatures.values()}) != len(actions):
        raise PoseQualityError('actions must have distinct visible pose sequences')
    inspection['single_body_passed'] = rest_sizeable <= 1 and all(
        f['sizeable_component_count'] <= 1 for a in inspection['actions'].values() for f in a['frames'])
    connectivity_failed = single_body and not inspection['single_body_passed']
    clipped = any(f['clipped_part_pixels'] for a in inspection['actions'].values() for f in a['frames'])
    inspection['passed'] = not clipped and not connectivity_failed
    inspection['technical_status'] = ('needs-clipping-and-connectivity-review' if clipped and connectivity_failed else
                                      'needs-connectivity-review' if connectivity_failed else
                                      'needs-clipping-review' if clipped else 'passed')
    inspection['rive_export_status'] = ('blocked-single-body' if connectivity_failed else 'blocked-clipping' if clipped else
                                      'ready' if wants_rive else 'not-requested')
    if provisional_rig:
        inspection['rig_status'] = 'provisional'
    inspection['limitations'].append('8-connected components detect splits, not anatomical continuity or natural motion.')
    if any('joint_underlap' in part for part in parts):
        inspection['limitations'].append('Joint underlaps are authored palette-sampled patches clipped to rest alpha, not recovered hidden artwork.')
    inspection['review_files'] = {key: files[key] for key in ('master', 'rig_preview', 'motion_qa')}
    review_previews(master, parts, inspection, stage)
    if wants_rive and inspection['passed']:
        files['rive_poses'] = 'rive-poses.json'
        write_json(stage / files['rive_poses'], packed)
    if ACTIONS.keys() <= packed['actions'].keys():
        packed = {**packed, 'actions': {name: packed['actions'][name] for name in ACTIONS}}
        write_json(stage / files['request'], packed)
    else:
        del files['request']
    write_json(stage / files['inspection'], inspection)
    return files
