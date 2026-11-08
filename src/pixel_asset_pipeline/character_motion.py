"""Editable frontal cutout choreography derived from a six-part rig proposal.

This authors technical candidates, never anatomical or artistic approval. All
joint support samples come from the supplied master; no hidden art is invented.
"""
import json
from pathlib import Path

from PIL import Image

from . import motion
from .action_set import ACTIONS, local_path
from .bundle import open_png, write_json

SUPPORTED_ACTIONS = (*ACTIONS, 'wave', 'cheer')


def _nearest(pixels, point):
    return min(pixels, key=lambda p: ((p[0]-point[0])**2+(p[1]-point[1])**2, p[1], p[0]))


def _support(parent, child, anchor):
    """Bridge the actual cut edge with source-colored, alpha-clipped underlap."""
    start = _nearest(parent, anchor)
    end = _nearest(child, start)
    row = [x for x, y in child if y == end[1]]
    radius = max(1, min(6, (max(row)-min(row)+2)//2))
    return {'parent_px': list(start), 'child_px': list(end),
            'source_px': list(end), 'radius_px': radius}


def _poses(name):
    # torso, left upper/lower arm, right upper/lower arm, left/right hip,
    # left/right knee, root rise. Screen-left/right are intentionally explicit.
    return {
        'idle': [(0,0,0,0,0,0,0,0,0,0), (0,2,-3,-2,3,0,0,0,0,-1),
                 (0,0,0,0,0,0,0,0,0,0), (0,-2,3,2,-3,0,0,0,0,0)],
        'walk': [(0,-6,-12,-6,-2,-4,-2,10,2,0), (0,0,-4,0,4,0,0,0,0,0),
                 (0,6,2,6,12,2,4,-2,-10,0), (0,0,-4,0,4,0,0,0,0,0)],
        'run': [(0,-10,-50,-8,-10,4,6,-4,-22,0), (0,-4,-30,4,25,0,0,8,-8,-2),
                (0,8,10,10,50,-6,-4,22,4,0), (0,-4,-25,4,30,0,0,8,-8,-2)],
        'attack': [(-3,15,20,-10,-25,0,0,0,0,0), (-5,25,35,-15,-40,0,0,0,0,0),
                   (4,-40,-45,10,15,0,0,0,0,0), (0,0,0,0,0,0,0,0,0,0)],
        'jump': [(0,8,-10,-8,10,-3,3,10,-10,0), (0,45,30,-45,-30,-8,8,20,-20,-3),
                 (0,55,35,-55,-35,-6,6,28,-28,-5), (0,20,10,-20,-10,-3,3,12,-12,-2),
                 (0,0,0,0,0,0,0,0,0,0)],
        'hurt': [(-4,-10,-15,10,15,0,0,0,0,0), (-7,-15,-25,15,25,0,0,0,0,-1),
                 (-2,-5,-10,5,10,0,0,0,0,0), (0,0,0,0,0,0,0,0,0,0)],
        'wave': [(0,55,90,0,0,0,0,0,0,0), (0,55,120,0,0,0,0,0,0,0),
                 (0,55,85,0,0,0,0,0,0,0), (0,55,120,0,0,0,0,0,0,0)],
        'cheer': [(0,40,35,-40,-35,0,0,0,0,0), (0,140,15,-140,-15,0,0,0,0,-1),
                  (0,125,25,-125,-25,0,0,0,0,-2), (0,140,15,-140,-15,0,0,0,0,0)],
    }[name]


def prepare(rig_dir: Path, actions: list[str]) -> Path:
    """Write a relative, editable motion request beside rig_draft.produce outputs.

    Only selected profiles are authored. The caller must use motion.produce's
    selected_actions and explicit provisional_rig workflow for unreviewed rigs.
    """
    if (not isinstance(actions, list) or not actions or
            any(not isinstance(name, str) or name not in SUPPORTED_ACTIONS for name in actions)
            or len(set(actions)) != len(actions)):
        raise ValueError('actions requires unique supported character action names')
    rig_dir = Path(rig_dir)
    draft = json.loads((rig_dir/'rig-draft.request.json').read_text())
    master = open_png(local_path(rig_dir, draft.get('master')), max_pixels=128**2).convert('RGBA')
    parts = motion.load_rig(draft, rig_dir, master)
    expected = {'torso','head','arm_left','arm_right','leg_left','leg_right'}
    if len(parts) != 6 or {p['id'] for p in parts} != expected:
        raise ValueError('character motion requires the six named rig-draft parts')
    authored, pixels_by_id = [], {}
    for original in parts:
        name = original['id']
        pixels = original['pixels']
        segments = [(name, pixels, original['anchor_px'], original['parent'])]
        if name.startswith(('arm_', 'leg_')):
            top, bottom = min(y for x,y in pixels), max(y for x,y in pixels)
            cut = (top+bottom+1)//2
            upper = {(x,y) for x,y in pixels if y < cut}
            lower = pixels-upper
            if not upper or not lower:
                raise motion.PoseQualityError('limb needs at least two occupied rows for an editable joint')
            row = [x for x,y in lower if y == cut]
            if not row:
                raise motion.PoseQualityError('limb must cross its proposed elbow/knee row')
            anchor = [(min(row)+max(row))//2,cut]
            segments = [(name, upper, original['anchor_px'], original['parent']),
                        (name+'_lower', lower, anchor, name)]
        for pid, owned, anchor, parent in segments:
            filename = 'character-'+pid+'-mask.png'
            mask = Image.new('L', master.size)
            for xy in owned:
                mask.putpixel(xy,255)
            mask.save(rig_dir/filename)
            part = {'id':pid, 'role':original['role'], 'parent':parent,
                    'anchor_px':anchor, 'mask':filename}
            if parent:
                part['joint_underlap'] = _support(pixels_by_id[parent], owned, anchor)
            if pid.endswith('_lower') and name.startswith('leg_'):
                part['contact_px'] = original['contact_px']
            authored.append(part)
            pixels_by_id[pid] = owned
    request = {'schema_version':1, 'master':draft['master'], 'approved':False, 'single_body':True,
               'pivot_px_from_top_left':draft['pivot_px_from_top_left'],
               'rig':{'parts':authored}, 'actions':{}, 'extra_actions':{}}
    ids = ['torso','arm_left','arm_left_lower','arm_right','arm_right_lower',
           'leg_left','leg_right','leg_left_lower','leg_right_lower']
    for name in actions:
        frames = []
        for index, pose in enumerate(_poses(name)):
            transforms = {pid:{'angle_deg':angle} for pid,angle in zip(ids,pose[:-1]) if angle}
            transforms['head'] = {'angle_deg':-pose[0]}
            if name == 'run' and index in (0,2):
                swing = 'leg_right' if index == 0 else 'leg_left'
                transforms[swing]['offset_px'] = [0,-max(1,master.height//32)]
            frame = {'duration_ms':160 if name == 'idle' else 90 if name == 'run' else 120,
                     'parts':transforms, 'root_offset_px':[0,pose[-1]]}
            frames.append(frame)
        if name in ACTIONS:
            request['actions'][name] = {'frames':frames}
        else:
            request['extra_actions'][name] = {'loop':name == 'wave', 'frames':frames}
    path = rig_dir/'motion.request.json'
    write_json(path,request)
    return path
