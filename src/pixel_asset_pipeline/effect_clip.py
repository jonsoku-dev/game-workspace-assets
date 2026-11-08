"""Bounded offline repurposing of authored GIFs; no synthesis or semantic matting."""
from collections import deque
from pathlib import Path
import hashlib
import io
import json

from PIL import Image

from .action_set import digest, duration, local_path, point
from .bundle import write_json
from .sheet import export_sheet
from .spec import rgb

MAX_SOURCE_FRAMES = 256
MAX_DECODE_PIXELS = 16_777_216
PHASES = ('charge', 'travel', 'impact')


def _read_bounded(path, limit, label):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'{label} exceeds {limit // 1_048_576} MiB')
    return data


def _size(value, label, maximum=512):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(v) is not int or not 1 <= v <= maximum for v in value)):
        raise ValueError(f'{label} requires two integers in 1..{maximum}')
    return value


def _remove_edge_color(frame, color):
    """Exact 4-connected keying keeps enclosed matching interior pixels intact."""
    pixels = frame.load()
    width, height = frame.size
    queue = deque()

    def add(x, y):
        if pixels[x, y][3] and pixels[x, y][:3] == color:
            pixels[x, y] = (*color, 0)
            queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                add(nx, ny)


def produce(request_path: Path, stage: Path) -> dict[str, str]:
    """Use with bundle.publish(out, produce, request_path); paths are request-relative."""
    request_bytes = _read_bounded(request_path, 1_048_576, 'effect-clip request')
    request = json.loads(request_bytes.decode('utf-8'))
    allowed = {'schema_version', 'source', 'actor_cell_size', 'effect_size',
               'pivot_px_from_top_left', 'background', 'phases', 'license', 'notice'}
    if (not isinstance(request, dict) or type(request.get('schema_version')) is not int
            or request['schema_version'] != 1 or request.keys() - allowed):
        raise ValueError('effect-clip requires schema_version 1 and known fields')
    paths = {key: local_path(request_path.parent, request.get(key))
             for key in ('source', 'license', 'notice')}
    inputs = {key: _read_bounded(path, 16_777_216 if key == 'source' else 1_048_576, key)
              for key, path in paths.items()}
    for key in ('license', 'notice'):
        if not inputs[key].decode('utf-8').strip():
            raise ValueError('license and notice require nonempty text of at most 1 MiB')
    actor_size = _size(request.get('actor_cell_size'), 'actor_cell_size')
    size = _size(request.get('effect_size'), 'effect_size')
    if any(effect > actor * 4 for effect, actor in zip(size, actor_size)):
        raise ValueError('effect_size must not exceed four actor cells on either axis')
    pivot = point(request.get('pivot_px_from_top_left'), size, 'pivot')
    background = request.get('background')
    color = None
    if background == {'mode': 'preserve'}:
        pass
    elif isinstance(background, dict) and set(background) == {'mode', 'color'} and background['mode'] == 'edge-color':
        color = rgb(background['color'])
    else:
        raise ValueError('background requires preserve or explicit edge-color and #RRGGBB color')
    phases = request.get('phases')
    if not isinstance(phases, dict) or set(phases) != set(PHASES):
        raise ValueError('phases requires exactly charge, travel, impact')
    selection, tags = [], []
    for name in PHASES:
        entries = phases[name]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
            raise ValueError('each phase requires 1..64 explicit frame selections')
        start = len(selection)
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) != {'frame', 'duration_ms'}
                    or type(entry['frame']) is not int or not 0 <= entry['frame'] < MAX_SOURCE_FRAMES):
                raise ValueError('each selection requires frame in 0..255 and duration_ms')
            duration(entry['duration_ms'])
            selection.append({'phase': name, **entry})
        tags.append({'name': name, 'from': start, 'to': len(selection) - 1, 'direction': 'forward'})
    if len(selection) > 64 or size[0] * size[1] * len(selection) > MAX_DECODE_PIXELS:
        raise ValueError('output exceeds frame or pixel budget')
    if sum(entry['duration_ms'] for entry in selection) > 120000:
        raise ValueError('effect duration exceeds 120000 ms')

    selected, source_frames, transparent = {}, [], False
    wanted = {entry['frame'] for entry in selection}
    decoded_pixels = 0
    # Sequential seek/load applies Pillow's GIF disposal/composition before copying RGBA.
    with Image.open(io.BytesIO(inputs['source']), formats=['GIF']) as source:
        source_size = source.size
        if any(side > 1024 for side in source_size):
            raise ValueError('GIF dimensions exceed 1024')
        if size[0] * source.height != size[1] * source.width:
            raise ValueError('effect_size must preserve the source aspect ratio exactly')
        index = 0
        while True:
            if index >= MAX_SOURCE_FRAMES:
                raise ValueError('GIF exceeds 256 source frames')
            decoded_pixels += source.width * source.height
            if source.size != source_size or decoded_pixels > MAX_DECODE_PIXELS:
                raise ValueError('GIF exceeds decoded pixel budget or changes canvas size')
            source.load()
            source_frames.append({'frame': index, 'duration_ms': source.info.get('duration'),
                                  'disposal': source.disposal_method})
            if index in wanted:
                frame = source.convert('RGBA')
                transparent |= frame.getchannel('A').getextrema()[0] == 0
                if color is not None:
                    _remove_edge_color(frame, color)
                selected[index] = frame.resize(tuple(size), Image.Resampling.NEAREST)
            index += 1
            try:
                source.seek(index)
            except EOFError:
                break
    if wanted - selected.keys():
        raise ValueError('selected frame is outside the source GIF')
    if color is None and not transparent:
        raise ValueError('opaque GIF requires an explicit edge-color background')
    frames = [selected[entry['frame']] for entry in selection]
    if not any(frame.getchannel('A').getbbox() for frame in frames):
        raise ValueError('selected effect clip is fully invisible after background removal')
    durations = [entry['duration_ms'] for entry in selection]
    stage.mkdir(parents=True, exist_ok=True)
    files = export_sheet(frames, durations, pivot, False, stage)
    metadata = {
        'frames': [{'frame': {'x': i * size[0], 'y': 0, 'w': size[0], 'h': size[1]},
                    'rotated': False, 'trimmed': False, 'duration': ms}
                   for i, ms in enumerate(durations)],
        'meta': {'image': files['sheet'], 'frameTags': tags,
                 'pixelfx': {'frameSize': size, 'pivot': pivot, 'frames': len(frames), 'loop': False}},
    }
    write_json(stage / files['metadata'], metadata)
    files.update(provenance='effect-clip.json', license='LICENSE', notice='NOTICE')
    for key in ('license', 'notice'):
        (stage / files[key]).write_bytes(inputs[key])
    write_json(stage / files['provenance'], {
        'schema_version': 1, 'producer': 'local-gif-repurpose',
        'source': {key: {'path': request[key], 'sha256': hashlib.sha256(data).hexdigest()}
                   for key, data in inputs.items()},
        'request_sha256': hashlib.sha256(request_bytes).hexdigest(), 'source_size': list(source_size),
        'source_frames': source_frames, 'background': background,
        'actor_cell_size': actor_size, 'effect_size': size,
        'scale_relative_to_actor': [size[i] / actor_size[i] for i in range(2)],
        'resampling': 'nearest', 'selection': selection, 'pivot_px_from_top_left': pivot,
        'artifacts': {key: {'path': filename, 'sha256': digest(stage / filename)}
                      for key, filename in files.items() if key != 'provenance'},
        'review': {'status': 'pending', 'preview': files['preview'],
                   'limits': 'No redraw or semantic matting; exact edge-color removal may retain halos. '
                             'GIF preview rounds timing; sheet metadata is exact. Engine acceptance is separate.'},
    })
    return files
