"""Reproduce original 32px terrain art and a mixed placement study, offline.

Run from the workspace: .venv/bin/python examples/production/tiles/make_sources.py
All clusters are native pixels; wrapped drawing preserves motifs at tile borders.
"""
import json
import math
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
PALETTE = ['#344d37', '#425e3a', '#52723e', '#668344', '#7e984e',
           '#70533c', '#896548', '#a77e55', '#bd9465', '#5d4937']
COLORS = [tuple(bytes.fromhex(color[1:])) + (255,) for color in PALETTE]


def paint(image, x, y, color):
    image.putpixel((x % 32, y % 32), COLORS[color])


def sources():
    grass = Image.new('RGBA', (32, 32), COLORS[2])
    # Unequal broad moss patches, with small paired blade highlights.
    for x, y, width, height in [(1, 1, 7, 4), (16, 4, 9, 3), (6, 14, 6, 5),
                                 (22, 20, 8, 4), (2, 28, 9, 3), (13, 27, 5, 3)]:
        for dy in range(height):
            for dx in range(width):
                if dx + dy > 0 and dx - dy < width - 1:
                    paint(grass, x + dx, y + dy, 1 if dy > 0 else 3)
    for x, y in [(3, 8), (12, 3), (25, 11), (17, 16), (7, 24), (29, 28), (20, 30), (30, 3)]:
        for dx, dy, color in [(0, 0, 0), (1, 0, 0), (1, -1, 3), (2, -2, 4),
                              (2, -1, 3), (3, -1, 3), (0, -1, 3)]:
            paint(grass, x + dx, y + dy, color)
    path = grass.copy()
    lefts = [8 + round(1.5 * math.sin(2 * math.pi * y / 32)) for y in range(32)]
    rights = [24 + round(math.sin(2 * math.pi * y / 32 + 0.8)) for y in range(32)]
    for y in range(32):
        for x in range(lefts[y], rights[y]):
            edge = min(x - lefts[y], rights[y] - 1 - x)
            paint(path, x, y, 5 if edge == 0 else 6 if edge < 3 else 7)
        paint(path, lefts[y] - 1, y, 0 if y % 5 < 3 else 1)
        paint(path, rights[y], y, 3 if y % 7 < 4 else 1)
    # Low-contrast compressed earth clods and horizontal stone chips.
    for x, y, width in [(12, 3, 4), (17, 10, 4), (13, 20, 3), (19, 27, 3), (19, 0, 2)]:
        for dx in range(width):
            paint(path, x + dx, y, 8)
            paint(path, x + dx, y + 1, 6)
        paint(path, x + width, y + 1, 5)
    for name, image in [('grass', grass), ('dirt-path', path)]:
        assert image.size == (32, 32) and image.getchannel('A').getextrema() == (255, 255)
        assert {color for _, color in image.getcolors(1024)} <= set(COLORS)
        for bounds in ((0, 0, 1, 32), (31, 0, 32, 32)):
            assert image.crop(bounds).tobytes() == grass.crop(bounds).tobytes()
        image.save(ROOT / f'{name}-source.png')
        (ROOT / f'{name}-request.json').write_text(json.dumps({
            'schema_version': 1, 'source': f'{name}-source.png',
            'size': 32, 'max_colors': 10, 'palette': PALETTE,
        }, indent=2) + '\n')
    assembly = Image.new('RGBA', (32 * 7, 32 * 6))
    for row in range(6):
        for column in range(7):
            assembly.paste(path if column == 3 else grass, (column * 32, row * 32))
    assembly.save(ROOT / 'mixed-assembly-native.png')
    assembly.resize((896, 768), Image.Resampling.NEAREST).save(ROOT / 'mixed-assembly.png')


if __name__ == '__main__':
    sources()
