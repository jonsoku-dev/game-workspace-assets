"""Bake local character poses to one self-contained Rive state machine."""
import hashlib
from io import BytesIO
import json

from PIL import Image

from .action_set import duration, local_path
from .bundle import open_png, write_json
from .rive_binary import bake


def produce(request_path, stage):
    with request_path.open('rb') as stream:
        raw = stream.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError('Rive request exceeds 1 MiB')
    request = json.loads(raw)
    fields = {'schema_version', 'actions', 'size', 'cell_size', 'pivot_px_from_top_left', 'events'}
    if (not isinstance(request, dict) or type(request.get('schema_version')) is not int
            or request['schema_version'] != 1 or set(request) - fields):
        raise ValueError('expected a version 1 pose manifest or motion action-set request')
    if request.get('events'):
        raise ValueError('Rive character export supports poses only; effect events need separate composition')
    if ('size' in request) == ('cell_size' in request):
        raise ValueError('specify exactly one size or cell_size')
    size = request.get('size', request.get('cell_size'))
    if not isinstance(size, list) or len(size) != 2 or any(type(x) is not int or not 1 <= x <= 512 for x in size):
        raise ValueError('Rive frames must be 1..512 pixels on each axis')
    actions = request.get('actions')
    if not isinstance(actions, dict) or not 1 <= len(actions) <= 32:
        raise ValueError('expected 1..32 named actions')

    animations, states, cache = [], [], {}
    frame_count = byte_count = 0
    for index, (name, action) in enumerate(actions.items()):
        if (not name.strip() or len(name) > 80 or not isinstance(action, dict)
                or set(action) != {'loop', 'frames'} or type(action['loop']) is not bool):
            raise ValueError('each named action requires loop and frames')
        frames = action['frames']
        if not isinstance(frames, list) or not frames:
            raise ValueError('actions require at least one frame')
        frame_count += len(frames)
        if frame_count > 256 or frame_count * size[0] * size[1] > 16_777_216:
            raise ValueError('Rive frame or pixel budget exceeded')
        sequence, pins = [], []
        for frame in frames:
            if not isinstance(frame, dict) or set(frame) != {'path', 'duration_ms'}:
                raise ValueError('frame requires a PNG path and duration_ms')
            ms = duration(frame['duration_ms'])
            source = local_path(request_path.parent, frame['path'])
            if source not in cache:
                with source.open('rb') as stream:
                    data = stream.read(16_777_217)
                byte_count += len(data)
                if len(data) > 16_777_216 or byte_count > 33_554_432:
                    raise ValueError('Rive PNG byte budget exceeded')
                image = open_png(BytesIO(data), max_pixels=size[0] * size[1]).convert('RGBA')
                if list(image.size) != size:
                    raise ValueError('all frames must match the declared canvas size')
                # Only visible artwork and alpha are needed by the player.
                image.info.clear()
                encoded = BytesIO()
                image.save(encoded, format='PNG')
                cache[source] = encoded.getvalue(), hashlib.sha256(data).hexdigest()
            png, source_digest = cache[source]
            sequence.append((png, ms))
            pins.append({'path': frame['path'], 'sha256': source_digest, 'duration_ms': ms})
        total = sum(ms for _, ms in sequence)
        if total > 120_000:
            raise ValueError('Rive action exceeds 120 seconds')
        animations.append((name, action['loop'], sequence))
        states.append({'name': name, 'value': index, 'loop': action['loop'], 'duration_ms': total, 'frames': pins})

    result = bake(*size, animations)
    (stage / 'character.riv').write_bytes(result)
    write_json(stage / 'rive.json', {'schema_version': 1, 'format': 'rive', 'artboard': 'Character',
              'state_machine': 'Character Actions', 'number_input': 'action', 'size': size,
              'request_sha256': hashlib.sha256(raw).hexdigest(), 'states': states,
              'file': 'character.riv', 'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()})
    return {'character': 'character.riv', 'metadata': 'rive.json'}
