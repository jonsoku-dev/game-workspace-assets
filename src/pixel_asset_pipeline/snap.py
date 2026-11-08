"""Guided, offline reconstruction of a soft PNG on an explicit native grid."""
from collections import Counter
import hashlib
import io
from pathlib import Path
import struct

from PIL import Image

from .action_set import local_path
from .bundle import open_png, write_json
from .spec import read_object, rgb

MAX_SOURCE_BYTES = 16_777_216
MAX_SOURCE_PIXELS = 4_194_304
PREVIEW_SCALE = 8


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} requires an integer in {low}..{high}')
    return value


def image_colors(image):
    return {color for _, color in image.getcolors(image.width * image.height)}


def reduce_palette(samples, limit, supplied):
    visible = [color[:3] for color in samples if color[3]]
    colors = set(visible)
    if supplied is not None:
        if not isinstance(supplied, list) or not 1 <= len(supplied) <= limit:
            raise ValueError('palette requires 1..max_colors #RRGGBB colors')
        palette = [rgb(color) for color in supplied]
        if len(set(palette)) != len(palette):
            raise ValueError('palette colors must be distinct')
    elif len(colors) <= limit:
        palette = sorted(colors)
    else:
        # Keep the darkest sampled outline candidate even when it occupies few cells.
        darkest = min(colors, key=lambda c: (299*c[0] + 587*c[1] + 114*c[2], c))
        strip = Image.new('RGB', (len(visible), 1))
        strip.putdata(visible)
        quantized = strip.quantize(colors=limit-1, method=Image.Quantize.MEDIANCUT,
                                   dither=Image.Dither.NONE).convert('RGB')
        palette = sorted(image_colors(quantized) | {darkest})
    nearest = {color: min(palette, key=lambda candidate:
                         (sum((a-b)**2 for a, b in zip(color, candidate)), candidate))
               for color in colors}
    return [(*nearest[color[:3]], 255) if color[3] else (0, 0, 0, 0) for color in samples], palette


def produce(request_path: Path, stage: Path):
    """Write a reviewed-later native master and comparisons; publish via bundle.publish."""
    if request_path.stat().st_size > 1_048_576:
        raise ValueError('snap request exceeds 1 MiB')
    request = read_object(request_path, {'source', 'crop', 'grid_size', 'max_colors', 'palette', 'alpha_cutoff'})
    source_path = local_path(request_path.parent, request.get('source'))
    with source_path.open('rb') as source_file:
        source_bytes = source_file.read(MAX_SOURCE_BYTES + 1)
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ValueError('source exceeds 16 MiB')
    source = open_png(io.BytesIO(source_bytes), max_pixels=MAX_SOURCE_PIXELS).convert('RGBA')
    crop = request.get('crop')
    if not isinstance(crop, list) or len(crop) != 4 or any(type(v) is not int for v in crop):
        raise ValueError('crop requires [x,y,width,height] integers')
    x, y, width, height = crop
    if x < 0 or y < 0 or width < 1 or height < 1 or x+width > source.width or y+height > source.height:
        raise ValueError('crop must lie inside the source')
    grid = request.get('grid_size')
    if not isinstance(grid, list) or len(grid) != 2:
        raise ValueError('grid_size requires [native_width,native_height]')
    gw, gh = (integer(value, 4, 128, 'grid_size') for value in grid)
    if gw > width or gh > height:
        raise ValueError('grid_size must not upscale the crop')
    limit = integer(request.get('max_colors', 16), 2, 64, 'max_colors')
    cutoff = integer(request.get('alpha_cutoff', 128), 1, 255, 'alpha_cutoff')
    cropped = source.crop((x, y, x+width, y+height))
    samples = []
    # Integer cell centres support non-integral block sizes without interpolation.
    for row in range(gh):
        for col in range(gw):
            sx, sy = (2*col+1)*width//(2*gw), (2*row+1)*height//(2*gh)
            color = cropped.getpixel((sx, sy))
            samples.append((*color[:3], 255) if color[3] >= cutoff else (0, 0, 0, 0))
    occupied = sum(bool(color[3]) for color in samples)
    if occupied < 2 or occupied == gw*gh:
        raise ValueError('snap needs at least two visible cells and transparent margin; adjust crop/grid/alpha_cutoff')
    reduced, palette = reduce_palette(samples, limit, request.get('palette'))
    native = Image.new('RGBA', (gw, gh))
    native.putdata(samples)
    result = Image.new('RGBA', (gw, gh))
    result.putdata(reduced)
    result.save(stage / 'asset.png')
    cropped.save(stage / 'source-crop.png')
    comparison = Image.new('RGBA', (gw*2, gh))
    comparison.paste(native, (0, 0))
    comparison.paste(result, (gw, 0))
    comparison.save(stage / 'comparison-native.png')
    before = cropped.resize((gw*PREVIEW_SCALE, gh*PREVIEW_SCALE), Image.Resampling.NEAREST)
    after = result.resize(before.size, Image.Resampling.NEAREST)
    enlarged = Image.new('RGBA', (before.width*2, before.height))
    enlarged.paste(before, (0, 0))
    enlarged.paste(after, (before.width, 0))
    enlarged.save(stage / 'comparison.png')
    source_counts = Counter(value for (value,) in struct.iter_unpack('>I', source.tobytes()))
    report = {
        'schema_version': 1, 'technical_status': 'passed', 'passed': True,
        'visual_review': 'required', 'artistic_acceptance': 'unverified',
        'source': {'path': request['source'], 'sha256': hashlib.sha256(source_bytes).hexdigest(),
                   'size_px': list(source.size), 'rgba_color_count': len(source_counts),
                   'visible_rgb_color_count': len({c >> 8 for c in source_counts if c & 255}),
                   'partial_alpha_pixel_count': sum(n for c, n in source_counts.items() if 0 < (c & 255) < 255)},
        'geometry': {'crop_xywh': crop, 'grid_size': grid,
                     'cell_size_source_px': [width/gw, height/gh],
                     'sample_position': 'floor((2*cell+1)*crop_extent/(2*grid_extent))',
                     'sampling': 'cell-centre-nearest-no-interpolation'},
        'alpha_cutoff': cutoff, 'max_colors': limit,
        'palette_mode': 'explicit' if request.get('palette') is not None else 'median-cut-with-darkest-sample',
        'palette': ['#%02x%02x%02x' % color for color in palette],
        'sampled_visible_color_count': len({c[:3] for c in samples if c[3]}),
        'output_visible_color_count': len({c[:3] for c in reduced if c[3]}),
        'output_opaque_pixels': occupied, 'output_transparent_pixels': gw*gh-occupied,
        'recolored_cells': sum(a != b for a, b in zip(samples, reduced)),
        'output_sha256': hashlib.sha256((stage / 'asset.png').read_bytes()).hexdigest(),
        'comparison': {'left': 'source crop (native: centre samples before palette reduction)',
                       'right': 'snapped output', 'scale': PREVIEW_SCALE, 'resampling': 'nearest'},
        'limitations': ['Caller supplies the grid and crop; no automatic grid or anatomy detection.',
                        'No background removal, outline synthesis, or speck deletion.',
                        'Details smaller than a grid cell can be lost; inspect outlines and transparency before rigging.',
                        'Review and approve the new master before setting motion approved:true.']}
    write_json(stage / 'inspection.json', report)
    return {'asset': 'asset.png', 'source_crop': 'source-crop.png',
            'comparison_native': 'comparison-native.png', 'comparison': 'comparison.png',
            'inspection': 'inspection.json'}
