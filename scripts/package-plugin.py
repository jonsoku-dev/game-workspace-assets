#!/usr/bin/env python3
"""Stage only the files needed for local Codex plugin installation."""

import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory for the installable plugin")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = (
        ".codex-plugin/plugin.json",
        ".agents/plugins/marketplace.json",
        ".agents/skills/pixel-asset-pipeline/SKILL.md",
        ".agents/skills/pixel-asset-pipeline/references/production.md",
        ".agents/skills/pixel-asset-pipeline/references/snap.md",
        ".agents/skills/pixel-asset-pipeline/references/rig-draft.md",
        ".agents/skills/pixel-asset-pipeline/references/effect-clip.md",
        "pyproject.toml",
        "src/pixel_asset_pipeline/__init__.py",
        "src/pixel_asset_pipeline/asset_set.py",
        "src/pixel_asset_pipeline/action_set.py",
        "src/pixel_asset_pipeline/bundle.py",
        "src/pixel_asset_pipeline/cli.py",
        "src/pixel_asset_pipeline/motion.py",
        "src/pixel_asset_pipeline/snap.py",
        "src/pixel_asset_pipeline/rig_draft.py",
        "src/pixel_asset_pipeline/character.py",
        "src/pixel_asset_pipeline/character_motion.py",
        "src/pixel_asset_pipeline/character_player.py",
        "src/pixel_asset_pipeline/player/index.html",
        "src/pixel_asset_pipeline/player/style.css",
        "src/pixel_asset_pipeline/player/player.js",
        "src/pixel_asset_pipeline/player/vendor/LICENSE",
        "src/pixel_asset_pipeline/player/vendor/package.json",
        "src/pixel_asset_pipeline/player/vendor/integrity.json",
        "src/pixel_asset_pipeline/player/vendor/rive.js",
        "src/pixel_asset_pipeline/player/vendor/rive.wasm",
        "src/pixel_asset_pipeline/player/vendor/rive_fallback.wasm",
        "src/pixel_asset_pipeline/rive.py",
        "src/pixel_asset_pipeline/rive_binary.py",
        "src/pixel_asset_pipeline/effect_clip.py",
        "src/pixel_asset_pipeline/effects.py",
        "src/pixel_asset_pipeline/fx_qa.py",
        "src/pixel_asset_pipeline/pose_qa.py",
        "src/pixel_asset_pipeline/sheet.py",
        "src/pixel_asset_pipeline/tile.py",
        "src/pixel_asset_pipeline/variant.py",
        "src/pixel_asset_pipeline/provider.py",
        "src/pixel_asset_pipeline/raster.py",
        "src/pixel_asset_pipeline/spec.py",
    )
    for relative in paths:
        if not (root / relative).is_file() or (root / relative).resolve() != root / relative:
            parser.error(f"Missing required plugin content: {relative}")
    destination = args.destination.resolve()
    if destination == root or root in destination.parents:
        parser.error("Destination must be outside the source repository")
    destination.mkdir(parents=True, exist_ok=False)
    for relative in paths:
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(destination)


if __name__ == "__main__":
    main()
