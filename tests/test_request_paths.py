"""sheet, tile, variant and style profiles resolve inputs inside the request folder only."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_asset_pipeline import sheet, tile, variant
from pixel_asset_pipeline.spec import Request


class RequestPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.outside = Path(temp.name)
        self.root = self.outside / "requests"
        self.root.mkdir()
        Image.new("RGBA", (16, 16), (40, 90, 60, 255)).save(self.outside / "escape.png")
        (self.outside / "profile.json").write_text(json.dumps({"schema_version": 1, "palette": ["#335544"]}))
        (self.root / "link.png").symlink_to(self.outside / "escape.png")

    def request(self, data):
        path = self.root / "request.json"
        path.write_text(json.dumps({"schema_version": 1, **data}))
        return path

    def test_parent_absolute_and_symlinked_inputs_are_rejected(self):
        for value in ("../escape.png", str(self.outside / "escape.png"), "link.png"):
            with self.subTest(value=value):
                cases = [
                    (sheet.produce, {"frames": [{"path": value, "duration_ms": 100}], "pivot_px_from_top_left": [8, 15]}),
                    (tile.produce, {"source": value, "size": 16, "palette": ["#285a3c"]}),
                    (variant.produce, {"base": value, "base_metadata": "meta.json", "equipment": "e.png",
                                       "anchor": [1, 1], "offset": [0, 0], "allowed_region": [0, 0, 4, 4]}),
                ]
                for producer, data in cases:
                    stage = self.root / "stage"
                    stage.mkdir(exist_ok=True)
                    with self.subTest(producer=producer.__module__), \
                            self.assertRaisesRegex(ValueError, "source paths"):
                        producer(self.request(data), stage)
        with self.assertRaisesRegex(ValueError, "source paths"):
            Request.load(self.request({"kind": "icon", "prompt": "x", "profile": "../profile.json"}))


if __name__ == "__main__":
    unittest.main()
