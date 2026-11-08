# Woodland scout walk

Four hand-authored 48×48 RGBA poses derived from the project's
`examples/codex-scout-styled/asset.png`. The head, face, upper body and original
palette stay fixed. The lower limbs have separately drawn knees, cuffs and toes:
near-foot forward contact, near-foot support with far foot lifted, far-foot
forward contact, and far-foot support with near foot lifted. The four poses
repeat in that order at 130/110/130/110 ms.

At least one boot touches row 45 in every frame (exclusive bottom 46), with a
shared pivot `[24, 46]`. Nothing is trimmed or resampled in the production PNGs.
`author_frames.py` records the native-pixel drawing commands and checks the
unchanged identity pixels, palette, four distinct poses and shared ground line.
No runtime animation is needed to construct the poses.

Rebuild frames with `.venv/bin/python examples/production/walk/author_frames.py`.
Export to a new output directory with
`pixel-asset sheet --request examples/production/walk/request.json --out OUTPUT`.
`result/sheet.png` contains the exact input pixels, `result/sheet.json` describes
the rectangles and timing, and `result/preview.gif` is an enlarged checkerboard
viewing aid. GIF timing rounds to the nearest 10 ms, with a 10 ms minimum; the
JSON retains exact integer milliseconds. These sample timings need no rounding.
Consecutive visually identical GIF poses are merged. A single merged preview
hold longer than 655,350 ms (the GIF delay limit) is shortened to that limit;
every following distinct pose remains present. Production sheet frames and
their JSON timings are never shortened or merged.

This is a looping in-place four-pose walk preview, not engine integration or
proof of root motion, directional coverage or gameplay animation blending.
