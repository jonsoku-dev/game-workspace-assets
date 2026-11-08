# Native woodland terrain pair

Original, deterministic local pixel art: 32×32 opaque grass (5 colors) and a north–south dirt path (9 colors), sharing a ten-color palette. Broad moss patches and paired grass blades use low-contrast clusters; compacted earth has irregular banks and small stone highlights. No downloaded art, models, remote generation, or external source material is included.

The path is a **straight segment**; this pair does not include corners, junctions, end caps, or an autotile set. Use grass in adjacent columns and repeat the path vertically. The accompanying mixed placement is an explicit example, not an engine scene.

From the workspace, reproduce the source PNGs and mixed assembly:

```sh
.venv/bin/python examples/production/tiles/make_sources.py
```

Produce fresh bundles (choose destinations that do not already exist):

```sh
.venv/bin/pixel-asset tile --request examples/production/tiles/grass-request.json --out /tmp/woodland-grass
.venv/bin/pixel-asset tile --request examples/production/tiles/dirt-path-request.json --out /tmp/woodland-path
```

Request source paths are relative to their request file. The checked-in `grass/` and `dirt-path/` folders hold native PNGs, 3×3 repeats enlarged four times with nearest-neighbor sampling, metadata, and validation. `mixed-assembly-native.png` places 7×6 tiles; `mixed-assembly.png` enlarges that placement four times.

Validation checks exact square size, full opacity, declared palette membership, at most 12 colors, and a contrast-based seam heuristic. Per axis, the seam's mean absolute RGB channel jump must be at most `max(8, 2 × mean interior neighboring jump)`, with channels measured on 0…255. This permits legitimate alternating or textured edges; opposite pixels need not be identical. It can miss perceptual seams and repeated motifs, and can reject deliberate strong boundaries. A passing result is not a seamlessness or visual-quality guarantee.

The producer never resizes, crops, recolors, or fits the native tile. Human visual acceptance and actual engine integration remain pending. The repeated grass motif is visibly regular; variants would be a separate art task.
