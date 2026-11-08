# Workshop rescue crate

Original self-authored game prop. Geometry, teal enamel wear, ivory/graphite rescue emblem and hazard stripe are generated locally by `create_crate.py`; no downloaded textures, models or third-party artwork. The recipe is the editable design reference. Brass corner caps, inset panels, lid gasket, latches, skids and open side handles give it a readable structure from above. The top/front emblems remain identifiable in the independent 128px review frames.

```sh
blender --background --factory-startup --offline-mode --disable-autoexec --python-exit-code 1 --python create_crate.py -- .
python3 ../../plugins/model-assets/tools/build.py --request crate.json --out crate-v4
```

Run from this directory. Use a fresh output directory on each rebuild. `rescue-crate.blend` contains a packed copy of `rescue-paint.png`; that external PNG is an authoring reference and is unnecessary to consume the source. The source selects all 27 static meshes, uses meters, and has all bevel modifiers applied. The atlas is explicit UV mapped to the inset panels; material colors use sRGB for the image and linear PBR constants for hardware.

`crate-v3/preview.png` is the reference render; `review.png` includes three views independently rendered at 384px and 128px. `model.json`, `three-validation.json`, and the Webstage receipt distinguish Blender roundtrip, actual Three GLTFLoader/image decoding, and hero budget checks. Author visual review found a clear crate silhouette, inset panels, open grips, corner protection and legible high contrast emblems at gameplay size. It does not establish user acceptance or host game integration. Parent session owns final browser verification and SSOT recording.
