# Local GIF effect repurposing

This importer rearranges existing pixels; it does not generate, redraw, infer motion phases, or perform semantic matting. Supply a local GIF whose reuse rights you have checked, plus its actual license and provenance notice. The input GIF is never modified. Request, GIF, license, and notice are each read once with byte caps; decode, hashes, and credit copies use those same snapshots. Individual blank frames remain valid, but an entirely invisible selected clip is rejected after keying and scaling.

Callable integration: `bundle.publish(output_path, effect_clip.produce, request_path)`.
The CLI integration owns the command name and argument parsing.

```json
{
  "schema_version": 1,
  "source": "effect.gif",
  "license": "LICENSE",
  "notice": "NOTICE",
  "actor_cell_size": [48, 48],
  "effect_size": [32, 32],
  "pivot_px_from_top_left": [16, 16],
  "background": {"mode": "edge-color", "color": "#ffffff"},
  "phases": {
    "charge": [{"frame": 0, "duration_ms": 80}],
    "travel": [{"frame": 2, "duration_ms": 60}, {"frame": 1, "duration_ms": 60}],
    "impact": [{"frame": 3, "duration_ms": 100}]
  }
}
```

Use `{"mode":"preserve"}` for existing transparency. For an opaque source, select an exact background color explicitly. Only matching opaque pixels connected to the canvas edges by four-neighbor paths are removed. Enclosed matching colors stay intact. This cannot reliably remove gradients, antialiasing halos, or complex backgrounds; review the result and supply a clean transparent source when necessary.

Frame indexes are zero-based source GIF display frames after disposal/composition. Each phase must contain explicit ordered frame selections and durations; phases concatenate as charge, travel, impact. Repeat or reverse indexes deliberately. Durations are exact integer milliseconds in metadata; GIF previews round to centiseconds. The result is a single nonlooping clip with phase tags, not three automatically triggered engine events. Actor contact events remain the action-set author's responsibility.

`effect_size` preserves the complete GIF canvas aspect ratio exactly, uses nearest-neighbor sampling, and is limited to 512 pixels per axis and four actor cells per axis. It does not crop or recenter frames, preserving registration. Pivot coordinates refer to the resized effect cell, not the actor cell. Source limits are 16 MiB, 1024 pixels per side, 256 decoded frames, and 16,777,216 total decoded logical pixels. Output limits are 64 selected frames, 16,777,216 pixels, and 120 seconds.

Outputs: `sheet.png`, Aseprite-compatible `sheet.json` with `meta.pixelfx` and phase tags, checkerboard `preview.gif`, unchanged `LICENSE`/`NOTICE`, and `effect-clip.json`. The latter records input/request/output SHA-256 hashes, source timing/disposal, selection order, scale, background operation, and pending visual review. The action-set event uses the returned sheet, metadata, license and notice filenames. Review the preview and actor composite before acceptance; format checks do not certify artwork quality or engine behavior.

## Evidence and reference limits

Public searches on 2026-11-08 for `zero_f_i_l_m`, the exact Korean phrase `AI가 그린 이펙트 GIF야`, and combinations with background/effect terms did not locate the exact post. The user-provided screenshot's idea is a workflow reference, not a verified public-source quotation, asset license, or imported artwork. No social-media asset is bundled.

Pillow's official [GIF documentation](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#gif) specifies seek, transparency indexes, frame duration, and disposal modes 0–3. Its [GIF decoder source](https://pillow.readthedocs.io/en/stable/_modules/PIL/GifImagePlugin.html) applies prior disposal during sequential seek/load; the importer copies the resulting RGBA display frame instead of independently compositing delta tiles. Regression fixtures exercise disposal 1, 2, and 3, transparent inputs, exact edge keying, explicit order/timing, and action-set compositing.
