"""Stage the independent 3D plugin without copying installed dependencies or assets."""
import argparse
from pathlib import Path
from shutil import copy2


ROOT = Path(__file__).resolve().parent
FILES = (
    ".codex-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
    ".agents/skills/model-assets/SKILL.md",
    "tools/build.py",
    "tools/assembly.py",
    "tools/assembly_worker.py",
    "tools/decode_image.py",
    "tools/blender_worker.py",
    "tools/lantern.py",
    "tools/ember.py",
    "tools/serve.py",
    "three/package.json",
    "three/package-lock.json",
    "three/inspect.mjs",
    "three/loader.mjs",
    "three/decode.mjs",
    "three/viewer.html",
    "three/viewer.mjs",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    destination = parser.parse_args().destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        parser.error("Choose a fresh folder outside the plugin")
    for name in FILES:
        source = ROOT / name
        if not source.is_file() or source.resolve() != source:
            parser.error(f"Missing regular plugin file: {name}")
    destination.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / name, target)
    print(destination)


if __name__ == "__main__":
    main()
