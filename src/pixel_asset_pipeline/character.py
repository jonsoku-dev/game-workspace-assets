"""Make a reviewable character, ordered Rive states and a portable player from one PNG."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from . import character_motion, character_player, motion, rig_draft, rive
from .action_set import ACTIONS, local_path
from .bundle import open_png, write_json

AUTOMATIC_ACTIONS = {*ACTIONS, 'wave', 'cheer'}


def _request(raw):
    value = json.loads(raw)
    allowed = {'schema_version', 'source', 'motion_request', 'frames', 'reference', 'actions', 'title', 'language'}
    if (not isinstance(value, dict) or type(value.get('schema_version')) is not int
            or value['schema_version'] != 1 or value.keys() - allowed
            or len(value.keys() & {'source', 'motion_request', 'frames'}) != 1
            or ('reference' in value and 'frames' not in value)):
        raise ValueError('character requires schema_version 1 and one frames, source or motion_request input')
    actions = value.get('actions')
    if (not isinstance(actions, list) or not 1 <= len(actions) <= 32
            or any(not isinstance(name, str) or not name.strip() or len(name) > 80 for name in actions)
            or len(set(actions)) != len(actions)):
        raise ValueError('actions must be an ordered list of 1..32 distinct names')
    if 'source' in value and set(actions) - AUTOMATIC_ACTIONS:
        raise ValueError('unknown automatic action; supported names: ' + ', '.join(sorted(AUTOMATIC_ACTIONS)))
    if value.get('language', 'ko') not in ('ko', 'ja'):
        raise ValueError('language must be ko or ja')
    title = value.get('title')
    if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > 120):
        raise ValueError('title must be a nonempty string of at most 120 characters')
    return value


class Inputs:
    """Capture each source once, even when multiple selected frames or the reference share it."""

    def __init__(self, base):
        self.base = base.resolve()
        self.data = {}
        self.media = set()
        self.media_bytes = 0
        self.pins = []

    def read(self, root, relative, limit, *, media=True):
        path = local_path(root, relative)
        data = motion.snapshot(path, limit, 'character input', self.data)
        if media and path not in self.media:
            self.media_bytes += len(data)
            if self.media_bytes > 33_554_432:
                raise ValueError('character inputs exceed 32 MiB')
            self.media.add(path)
        key = path.relative_to(self.base).as_posix()
        if not any(pin['path'] == key for pin in self.pins):
            self.pins.append({'path': key, 'sha256': hashlib.sha256(data).hexdigest(),
                              'byteCount': len(data)})
        return data


def _copy_motion_recipe(request_path, relative, stage, inputs):
    base = request_path.parent.resolve()
    path = local_path(base, relative)
    recipe = json.loads(inputs.read(base, relative, 1_048_576, media=False))
    if not isinstance(recipe, dict) or recipe.get('approved') is not True:
        raise ValueError('authored motion_request requires an approved source and rig')
    parts = recipe.get('rig', {}).get('parts') if isinstance(recipe.get('rig'), dict) else None
    if not isinstance(parts, list) or not 2 <= len(parts) <= 24 or any(not isinstance(part, dict) for part in parts):
        raise ValueError('authored rig requires 2..24 parts')
    master = inputs.read(path.parent, recipe.get('master'), 16_777_216)
    (stage / 'master.png').write_bytes(master)
    recipe['master'] = 'master.png'
    # Bounded, flat filenames let the exported recipe run again from this folder.
    for index, part in enumerate(parts):
        if 'mask' in part:
            mask = inputs.read(path.parent, part['mask'], 16_777_216)
            part['mask'] = f'part-{index}-mask.png'
            (stage / part['mask']).write_bytes(mask)
    recipe_path = stage / 'motion.request.json'
    write_json(recipe_path, recipe)
    return recipe_path


def _copy_cels(request_path, request, stage, inputs):
    base = request_path.parent.resolve()
    path = local_path(base, request['frames'])
    manifest = json.loads(inputs.read(base, request['frames'], 1_048_576, media=False))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('actions'), dict):
        raise ValueError('frames input requires a pose manifest with named actions')
    if set(request['actions']) - manifest['actions'].keys():
        raise ValueError('requested action missing from the pose manifest')

    copied = {}
    selected = {}
    count = 0
    for name in request['actions']:
        action = manifest['actions'][name]
        if not isinstance(action, dict) or not isinstance(action.get('frames'), list) or not action['frames']:
            raise ValueError('each selected action needs a nonempty frame list')
        count += len(action['frames'])
        if count > 256:
            raise ValueError('Rive frame budget exceeded')
        for frame in action['frames']:
            if not isinstance(frame, dict) or set(frame) != {'path', 'duration_ms'}:
                raise ValueError('frame requires a PNG path and duration_ms')
            source = local_path(path.parent, frame['path'])
            if source not in copied:
                data = inputs.read(path.parent, frame['path'], 16_777_216)
                filename = f'cel-{len(copied):03}.png'
                (stage / filename).write_bytes(data)
                copied[source] = filename
            frame['path'] = copied[source]
        selected[name] = action
    manifest['actions'] = selected
    target = stage / 'rive-poses.json'
    write_json(target, manifest)
    if 'reference' in request:
        source = inputs.read(base, request['reference'], 16_777_216)
        reference = open_png(BytesIO(source)).convert('RGBA')
        reference.info.clear()
        reference.save(stage / 'reference.png')
    return target


def _export(stage, pose_file, report):
    rive.produce(pose_file, stage)
    metadata = json.loads((stage / 'rive.json').read_text())
    character_player.write_player(stage / 'player.html', (stage / 'character.riv').read_bytes(),
                                  metadata, report['title'], report['language'])
    report.update(status='ready', rive_sha256=metadata['sha256'])


def produce(request_path: Path, stage: Path):
    raw = motion.snapshot(request_path, 1_048_576, 'character request', {})
    request = _request(raw)
    language = request.get('language', 'ko')
    title = request.get('title', '캐릭터' if language == 'ko' else 'キャラクター')
    inputs = Inputs(request_path.parent)
    automatic = 'source' in request
    report = {'schema_version': 1, 'status': 'needs_review', 'title': title, 'language': language,
              'actions': request['actions'], 'request_sha256': hashlib.sha256(raw).hexdigest(),
              'mode': 'drawn-frames' if 'frames' in request else 'source-rig' if automatic else 'authored-rig',
              'artistic_acceptance': 'unreviewed',
              'inputs': inputs.pins}

    if 'frames' in request:
        pose_file = _copy_cels(request_path, request, stage, inputs)
        _export(stage, pose_file, report)
    else:
        _from_rig(request_path, request, stage, report, automatic, inputs)
    write_json(stage / 'character.json', report)
    files = {path.name: path.name for path in stage.iterdir()}
    for role, name in (('report', 'character.json'), ('character', 'character.riv'),
                       ('player', 'player.html'), ('metadata', 'rive.json')):
        if name in files:
            files[role] = files.pop(name)
    return files


def _from_rig(request_path, request, stage, report, automatic, inputs):
    report['rig_status'] = 'provisional' if automatic else 'authored'
    with TemporaryDirectory(dir=stage.parent) as scratch:
        temp = Path(scratch)
        rig = temp / 'rig'
        rig.mkdir()
        motion_dir = temp / 'motion'
        motion_dir.mkdir()
        try:
            if automatic:
                data = inputs.read(inputs.base, request['source'], 16_777_216)
                (stage / 'master.png').write_bytes(data)
                (temp / 'source.png').write_bytes(data)
                draft = temp / 'draft.json'
                write_json(draft, {'schema_version': 1, 'source': 'source.png'})
                rig_draft.produce(draft, rig)
                shutil.copyfile(rig / 'joint-preview.png', stage / 'joint-preview.png')
                recipe_path = character_motion.prepare(rig, request['actions'])
            else:
                recipe_path = _copy_motion_recipe(request_path, request['motion_request'], rig, inputs)
            recipe = json.loads(recipe_path.read_text())
            for name in dict.fromkeys([recipe['master'], *(p['mask'] for p in recipe['rig']['parts'] if 'mask' in p)]):
                if Path(name).name != name:
                    raise ValueError('prepared rig paths must be flat')
                shutil.copyfile(rig / name, stage / name)
            shutil.copyfile(recipe_path, stage / 'motion.request.json')
            outputs = motion.produce(recipe_path, motion_dir, selected_actions=request['actions'],
                                     provisional_rig=automatic)
            for role in ('inspection', 'rig_preview', 'motion_qa'):
                shutil.copyfile(motion_dir / outputs[role], stage / outputs[role])
            inspection = json.loads((motion_dir / outputs['inspection']).read_text())
            if inspection['passed']:
                pose_file = motion_dir / outputs['rive_poses']
                pose_manifest = json.loads(pose_file.read_text())
                for action in pose_manifest['actions'].values():
                    for frame in action['frames']:
                        name = frame['path']
                        shutil.copyfile(motion_dir / name, stage / name)
                shutil.copyfile(pose_file, stage / pose_file.name)
                _export(stage, stage / pose_file.name, report)
            else:
                report['reason'] = inspection['technical_status']
        except (rig_draft.UnsupportedSilhouette, motion.PoseQualityError) as error:
            report['reason'] = str(error)
