# Scout equipment variants

The base is the existing approved 48×48 scout in `../../codex-scout-styled/`.
The lantern and staff are hand-placed native-resolution pixel art. They use only
colors already visible in that base. No image service, resampling, recoloring,
or base recropping is involved.

`base.request.json`, `lantern.request.json`, and `staff.request.json` are reusable
schema version 1 inputs. Paths resolve relative to the request file. The producer
places each equipment PNG's top-left at `anchor + offset`; the common anchor
`[36, 31]` is the scout's right hand in top-left canvas coordinates.
`allowed_region` is `[left, top, right, bottom]` with exclusive right/bottom.
`allowed_occlusion` explicitly permits covering the hand only. The bottom three
canvas rows and the outer edge remain protected regardless of those rectangles.

Each named output directory contains `asset.png`, an 8× nearest-neighbor
`preview.png`, `metadata.json`, and `validation.json`. Metadata records source
hashes, the original body bounds, pivot, request and composition origin.
`comparison.png` shows source art above composed variants at 8× scale.

Edit `sources/*.pixels.txt` for native pixels. Each character is one pixel and
`.` is transparent. `sources/palette.json` maps the remaining symbols to hex
colors. The matching `sources/*.png` files are the rendered, reusable overlays;
keep the text and PNG pixels synchronized when editing. These sources are
project-authored, without third-party art inputs.

The producer is `pixel_asset_pipeline.variant.produce(request_path, stage)`.
The CLI owns publication and output-directory protection. Producer validation
fails before emitting artifacts on malformed input, palette drift, partial alpha,
edge contact, clipping, unauthorized overlap or changed foot pixels.

Current results pass automated raster and preservation checks. The comparison
was visually inspected at native-pixel enlargement by the implementing agent.
Human creative approval and actual game-engine import remain unverified;
`visual_review` remains `pending` in generated metadata.
