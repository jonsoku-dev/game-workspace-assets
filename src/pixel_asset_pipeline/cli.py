"""Build a validated local bundle for the game-art layer."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw

from . import action_set, asset_set, character, effect_clip, effects, motion, provider, raster, rig_draft, rive, sheet, snap, tile, variant
from .bundle import open_png, publish, write_json
from .spec import Request, rgb


LOCAL_PRODUCERS = {
    "character": (character.produce, "make character actions, a Rive file and an offline player"),
    "rive": (rive.produce, "export pose animations to a self-contained Rive file with a selectable state machine"),
    "rig-draft": (rig_draft.produce, "propose an editable rig for a separated front-facing figure"),
    "snap": (snap.produce, "sample a guided pixel grid and prepare a palette-limited master"),
    "effect-clip": (effect_clip.produce, "reorder an existing GIF into charge, travel and impact phases"),
    "motion": (motion.produce, "author six local articulated actions from an approved master and explicit rig"),
    "action-set": (action_set.produce, "pack six authored actions with timed local pixelfx effects"),
    "variant": (variant.produce, "attach equipment without rescaling a character"),
    "compare": (asset_set.produce, "review a set of build bundles at 1x and 4x"),
    "sheet": (sheet.produce, "pack same-grid poses with a common pivot and frame timings"),
    "tile": (tile.produce, "inspect an opaque repeating terrain tile"),
    "effect": (effects.produce, "render local movement, interaction, impact and ambient effect sheets"),
}

FILES = dict(sprite="asset.png", preview="preview.png", metadata="metadata.json",
             validation="validation.json", source="draft.png")


def placement_guide(spec):
    image = Image.new("RGB", (spec.size, spec.size), "#fafafa")
    drawing = ImageDraw.Draw(image)
    bottom = spec.size - (3 if spec.kind == "character" else 2)
    drawing.rectangle((1, 1, spec.size - 2, bottom), fill="#dddddd")
    drawing.line((1, bottom, spec.size - 2, bottom), fill="#777777")
    return image.resize((spec.size * 8, spec.size * 8), Image.Resampling.NEAREST)


def build(spec, output, draft, style_reference=None):
    if draft is not None and style_reference is not None:
        raise ValueError("--style-reference requires --codex")
    return publish(output, _static_sprite, spec, draft, style_reference)


def _static_sprite(spec, draft, style_reference, stage):
    source = stage / FILES["source"]
    if draft is None:
        guide = stage.parent / "layout.png"
        placement_guide(spec).save(guide)
        references = [guide]
        if style_reference:
            swatch = open_png(style_reference).convert("RGBA")
            swatch.info.clear()
            swatch.thumbnail((512, 512), Image.Resampling.NEAREST)
            example = stage.parent / "style.png"
            swatch.save(example)
            references.append(example)
        provider.generate(spec.art_direction(style_reference is not None), source, tuple(references))
    else:
        shutil.copyfile(draft, source)
    image = raster.process(open_png(source), *spec.raster_args(),
                           outline=rgb(spec.outline) if spec.outline else None)
    asset = stage / FILES["sprite"]
    image.save(asset)
    report = raster.validate(open_png(asset), *spec.raster_args())
    if not report["passed"]:
        raise ValueError(f"asset failed validation: {report['checks']}")
    image.resize((spec.size * 6, spec.size * 6), Image.Resampling.NEAREST).save(stage / FILES["preview"])
    write_json(stage / FILES["validation"], report)
    pivot = [spec.size / 2, spec.size - 2 if spec.kind == "character" else spec.size / 2]
    write_json(stage / FILES["metadata"], {
        "schema_version": 1, "request": asdict(spec),
        "origin": "codex-imagegen" if draft is None else "local-draft",
        "generation_prompt": spec.art_direction(style_reference is not None) if draft is None else None,
        "style_reference_used": style_reference is not None,
        "import": {"filter": "nearest", "pivot_px_from_top_left": pivot},
        "visual_review": "pending",
    })
    return FILES


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pixel-asset", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("build", help="produce a verified sprite bundle")
    make.add_argument("--request", type=Path, required=True)
    make.add_argument("--out", type=Path, required=True)
    source = make.add_mutually_exclusive_group(required=True)
    source.add_argument("--draft", type=Path, help="use a local transparent PNG, fully offline")
    source.add_argument("--codex", action="store_true", help="generate using Codex's native image tool")
    make.add_argument("--style-reference", type=Path, help="send one chosen style PNG to native Codex with --codex")
    for name, (producer, help_text) in LOCAL_PRODUCERS.items():
        local = commands.add_parser(name, help=help_text)
        local.add_argument("--request", type=Path, required=True)
        local.add_argument("--out", type=Path, required=True)
        local.set_defaults(producer=producer)
    check = commands.add_parser("validate", help="inspect a final PNG without modifying it")
    check.add_argument("--request", type=Path, required=True)
    check.add_argument("png", type=Path)
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "producer"):
            result = publish(args.out, args.producer, args.request)
        elif args.command == "build":
            result = build(Request.load(args.request), args.out, args.draft, args.style_reference)
        else:
            request = Request.load(args.request)
            result = raster.validate(open_png(args.png, max_pixels=raster.MAX_SIZE ** 2), *request.raster_args())
        if args.command == "character":
            report = json.loads((args.out / result["files"]["report"]).read_text())
            result["status"] = report["status"]
            if "reason" in report:
                result["reason"] = report["reason"]
        print(json.dumps(result, ensure_ascii=False))
        if result.get("status") == "needs_review":
            return 1
        return 0 if result.get("passed", True) else 1
    except (OSError, ValueError, RuntimeError, Image.DecompressionBombError) as exc:
        print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
