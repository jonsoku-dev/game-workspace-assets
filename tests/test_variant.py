import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pixel_asset_pipeline.variant import produce


class VariantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = Image.new("RGBA", (16, 16))
        ImageDraw.Draw(self.base).rectangle((5, 3, 9, 13), fill=(39, 22, 37, 255))
        self.base.putpixel((8, 8), (250, 221, 174, 255))
        self.base.save(self.root / "base.png")
        self.metadata = {
            "schema_version": 1,
            "request": {"kind": "character", "size": 16, "limit": 2,
                        "palette": ["#271625", "#faddae"]},
            "import": {"filter": "nearest", "pivot_px_from_top_left": [8, 14]},
        }
        self.overlay = Image.new("RGBA", (4, 3))
        ImageDraw.Draw(self.overlay).rectangle((0, 0, 2, 1), fill=(250, 221, 174, 255))
        self.request = {
            "schema_version": 1, "base": "base.png", "base_metadata": "metadata.json",
            "equipment": "overlay.png", "anchor": [9, 8], "offset": [0, 0],
            "allowed_region": [9, 8, 12, 10], "allowed_occlusion": [[9, 8, 10, 10]],
        }

    def run_request(self):
        for name, data in (("request", self.request), ("metadata", self.metadata)):
            (self.root / f"{name}.json").write_text(json.dumps(data))
        self.overlay.save(self.root / "overlay.png")
        return produce(self.root / "request.json", self.root / "output")

    def test_places_at_anchor_plus_offset_and_preserves_base(self):
        self.request["anchor"] = [8, 7]
        self.request["offset"] = [1, 1]
        files = self.run_request()
        result = Image.open(self.root / "output" / files["asset"])
        self.assertEqual(result.getpixel((11, 8)), (250, 221, 174, 255))
        for y in range(16):
            for x in range(16):
                if not (9 <= x < 12 and 8 <= y < 10):
                    self.assertEqual(result.getpixel((x, y)), self.base.getpixel((x, y)))
        self.assertEqual(result.crop((0, 13, 16, 16)).tobytes(), self.base.crop((0, 13, 16, 16)).tobytes())
        report = json.loads((self.root / "output/validation.json").read_text())
        self.assertTrue(report["passed"])
        metadata = json.loads((self.root / "output/metadata.json").read_text())
        self.assertEqual(metadata["import"], self.metadata["import"])
        self.assertEqual(metadata["base_visible_bounds"], [5, 3, 10, 14])

    def test_base_copy_is_byte_identical_in_pixel_data(self):
        self.request = {k: self.request[k] for k in ("schema_version", "base", "base_metadata")}
        self.run_request()
        self.assertEqual(Image.open(self.root / "output/asset.png").tobytes(), self.base.tobytes())

    def test_rejects_clip_region_occlusion_and_foot_changes(self):
        original = self.request.copy()
        cases = [
            {"offset": [6, 0]},
            {"allowed_region": [10, 8, 12, 10]},
            {"allowed_occlusion": []},
            {"offset": [0, 5], "allowed_region": [9, 13, 12, 15], "allowed_occlusion": [[9, 13, 10, 15]]},
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                self.request = {**original, **patch}
                with self.assertRaises(ValueError):
                    self.run_request()
                self.assertFalse((self.root / "output").exists())

    def test_rejects_malformed_and_unapproved_pixels(self):
        for pixel in ((250, 221, 174, 128), (255, 0, 0, 255)):
            self.overlay.putpixel((0, 0), pixel)
            with self.subTest(pixel=pixel), self.assertRaises(ValueError):
                self.run_request()
        self.overlay.putpixel((0, 0), (250, 221, 174, 255))
        original = self.request.copy()
        for patch in ({"anchor": [True, 8]}, {"offset": [1]}, {"allowed_region": [9, 8, 30, 10]},
                      {"allowed_occlusion": ["bad"]}, {"unknown": True}, {"schema_version": True}):
            self.request = {**original, **patch}
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.run_request()

    def test_rejects_changed_base_pivot_and_non_rgba_overlay(self):
        self.metadata["import"]["pivot_px_from_top_left"] = [7, 14]
        with self.assertRaises(ValueError):
            self.run_request()
        self.metadata["import"]["pivot_px_from_top_left"] = [8, 14]
        self.overlay = self.overlay.convert("RGB")
        with self.assertRaises(ValueError):
            self.run_request()

    def test_production_sources_match_pixels_and_bundles_preserve_the_scout(self):
        root = Path(__file__).resolve().parents[1] / "examples/production/gear"
        palette = json.loads((root / "sources/palette.json").read_text())
        for name in ("base", "lantern", "staff"):
            request = json.loads((root / f"{name}.request.json").read_text())
            if name != "base":
                rows = (root / f"sources/{name}.pixels.txt").read_text().splitlines()
                source = Image.open(root / f"sources/{name}.png")
                self.assertEqual(source.size, (len(rows[0]), len(rows)))
                for y, row in enumerate(rows):
                    for x, symbol in enumerate(row):
                        expected = (0, 0, 0, 0) if symbol == "." else (*bytes.fromhex(palette[symbol][1:]), 255)
                        self.assertEqual(source.getpixel((x, y)), expected)
            stage = self.root / name
            produce(root / f"{name}.request.json", stage)
            result = Image.open(stage / "asset.png")
            base = Image.open(root / request["base"])
            built = Image.open(root / name / "asset.png")
            self.assertEqual(result.tobytes(), built.tobytes())
            region = request.get("allowed_region", [0, 0, 0, 0])
            for y in range(48):
                for x in range(48):
                    if not (region[0] <= x < region[2] and region[1] <= y < region[3]):
                        self.assertEqual(result.getpixel((x, y)), base.getpixel((x, y)))
