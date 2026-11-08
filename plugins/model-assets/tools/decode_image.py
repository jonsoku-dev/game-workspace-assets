"""Decode a local embedded PNG/JPEG with Blender, never source-provided code."""
import json
from pathlib import Path
import sys
import bpy

source, target = map(Path, sys.argv[sys.argv.index('--') + 1:])
image = bpy.data.images.load(str(source), check_existing=False)
width, height = image.size
if image.file_format not in {'PNG', 'JPEG'} or not 0 < width <= 2048 or not 0 < height <= 2048:
    raise ValueError('Expected decoded PNG/JPEG no larger than 2048px')
# Image datablock pixels are stored in their image color space, before shader conversion.
pixels = bytes(max(0, min(255, round(value * 255))) for value in image.pixels[:])
if len(pixels) != width * height * 4:
    raise ValueError('Image decoder did not produce RGBA pixels')
target.write_bytes(pixels)
target.with_suffix('.json').write_text(json.dumps({'width': width, 'height': height}))
