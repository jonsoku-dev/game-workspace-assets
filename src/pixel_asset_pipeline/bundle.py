"""Local artifact I/O shared by the asset producers."""
import json
from pathlib import Path
import tempfile

from PIL import Image


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def open_png(path, max_pixels=16_777_216):
    with Image.open(path, formats=["PNG"]) as source:
        if source.width * source.height > max_pixels or source.is_animated:
            raise ValueError(f"expected a static PNG of at most {max_pixels} pixels")
        source.load()
        return source.copy()


def publish(output: Path, producer, *inputs):
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists; choose a new bundle path")
    output.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".pixel-build-") as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        files = producer(*inputs, stage)
        for filename in files.values():
            if Path(filename).name != filename or not (stage / filename).is_file():
                raise ValueError(f"missing or invalid bundle artifact: {filename}")
        stage.rename(output)
    return {"schema_version": 1, "status": "ready", "files": files}
