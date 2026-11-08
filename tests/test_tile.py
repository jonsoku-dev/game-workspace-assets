import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_asset_pipeline.tile import produce, validate


class TileTests(unittest.TestCase):
    def test_repeating_alternating_pixels_can_pass_without_identical_edges(self):
        image = Image.new("RGBA", (8, 8), "black")
        for y in range(8):
            for x in range(8):
                image.putpixel((x, y), ((255, 255, 255, 255) if (x + y) % 2 else (0, 0, 0, 255)))
        self.assertNotEqual(image.getpixel((0, 0)), image.getpixel((7, 0)))
        self.assertTrue(validate(image, 8, [(0, 0, 0), (255, 255, 255)], 2)["passed"])

    def test_smooth_ramp_exposes_bad_wrap_seam(self):
        image = Image.new("RGBA", (8, 8))
        colors = [(x * 30,) * 3 for x in range(8)]
        for y in range(8):
            for x in range(8):
                image.putpixel((x, y), (*colors[x], 255))
        report = validate(image, 8, colors, 8)
        self.assertFalse(report["passed"])
        self.assertFalse(report["metrics"]["seams"]["x"]["passed"])
        self.assertTrue(report["metrics"]["seams"]["y"]["passed"])

    def test_terrain_rejects_sprite_transparency_wrong_size_and_palette(self):
        for image in (Image.new("RGBA", (8, 8)), Image.new("RGB", (9, 8)),
                      Image.new("RGB", (8, 8), "white")):
            self.assertFalse(validate(image, 8, [(0, 0, 0)], 1)["passed"])

    def test_producer_preserves_native_pixels_and_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = Image.new("RGBA", (8, 8), (32, 64, 32, 255))
            image.putpixel((2, 1), (48, 80, 48, 255))
            source = root / "source.png"
            image.save(source)
            request = root / "request.json"
            original = {"schema_version": 1, "source": "source.png", "size": 8,
                        "palette": ["#204020", "#305030"]}
            request.write_text(json.dumps(original))
            stage = root / "stage"
            stage.mkdir()
            files = produce(request, stage)
            with Image.open(stage / files["tile"]) as actual:
                self.assertEqual(actual.tobytes(), image.tobytes())
            with Image.open(stage / files["repeat_preview"]) as repeat:
                self.assertEqual(repeat.size, (96, 96))
                self.assertEqual(repeat.getpixel((33, 70)), (32, 64, 32, 255))
                self.assertEqual(repeat.getpixel((40, 68)), (48, 80, 48, 255))
            report = json.loads((stage / files["validation"]).read_text())
            self.assertTrue(report["passed"])
            self.assertEqual(report["visual_review"], "pending")
            for key, value in (("size", 9), ("max_colors", 13), ("palette", ["#ffffff"])):
                data = json.loads(request.read_text())
                data[key] = value
                request.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    produce(request, stage)
                request.write_text(json.dumps(original))


if __name__ == "__main__":
    unittest.main()
