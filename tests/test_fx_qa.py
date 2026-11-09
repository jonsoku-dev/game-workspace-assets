import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline import fx_qa


def sparks(head, tail, count=24):
    """Streaks radiating from a contact point; heads use `head`, the rest `tail`."""
    image = Image.new("RGBA", (128, 96))
    draw = ImageDraw.Draw(image)
    for i in range(count):
        x1, y1 = 20 + (i * 37) % 90, 10 + (i * 23) % 60
        draw.line((16, 80, x1, y1), fill=(*tail, 255), width=2)
        draw.line((16, 80, 16 + (x1 - 16) // 5, 80 + (y1 - 80) // 5), fill=(*head, 255), width=3)
    return image


class FxQATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        enamel = Image.new("RGBA", (96, 96), (232, 96, 28, 255))
        ImageDraw.Draw(enamel).rectangle((10, 10, 40, 40), fill=(255, 150, 90, 255))   # highlight
        enamel.save(self.root / "enamel.png")

    def request(self, layer, surfaces):
        layer.save(self.root / "emissive.png")
        path = self.root / "fx.json"
        path.write_text(json.dumps({"schema_version": 1, "name": "sparks", "emissive": ["emissive.png"],
                                    "surfaces": surfaces}))
        return path

    def run_qa(self, path):
        out = self.root / ("qa-" + str(len(list(self.root.glob("qa-*")))))
        run = subprocess.run([sys.executable, "-m", "pixel_asset_pipeline.cli", "fx-qa", "--request", str(path),
                              "--out", str(out)], capture_output=True, text=True)
        self.assertIn(run.returncode, (0, 1), run.stderr)
        return run.returncode, json.loads((out / "fx-qa.json").read_text()), out

    def test_dim_orange_sparks_on_orange_paint_fail_and_regrade_repairs(self):
        path = self.request(sparks((214, 120, 62), (176, 92, 50)),
                            [{"name": "enamel", "image": "enamel.png"}, {"name": "steel", "color": "#3a4458"}])
        code, report, out = self.run_qa(path)
        self.assertEqual(code, 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertTrue({"no-hot-core", "dimmer-than-surface", "hue-camouflage"} <= codes, codes)
        preview = report["regraded_preview"]
        self.assertEqual(preview["ramp_name"], "amber")
        self.assertEqual([f for f in preview["remaining_findings"] if f["severity"] == "error"], [])
        self.assertGreater(preview["measured"]["core_share"], report["measured"]["core_share"])
        for name in ("fx-comparison.png", "emissive-regraded.png"):
            self.assertTrue((out / name).is_file())

    def test_white_hot_sparks_on_steel_pass_with_hot_ramp(self):
        path = self.request(sparks((255, 250, 235), (255, 196, 90)), [{"name": "steel", "color": "#3a4458"}])
        code, report, _ = self.run_qa(path)
        self.assertEqual(code, 0, report["findings"])
        self.assertTrue(report["passed"])
        self.assertEqual(report["regraded_preview"]["ramp_name"], "hot")

    def test_regrade_keeps_alpha_and_maps_brightest_to_core(self):
        layer = sparks((214, 120, 62), (120, 60, 30))
        hot = fx_qa.regrade(layer, fx_qa.HOT_RAMP)
        self.assertEqual(hot.getchannel("A").tobytes(), layer.getchannel("A").tobytes())
        data = hot.tobytes()
        pixels = [data[i:i + 4] for i in range(0, len(data), 4)]
        brightest = max(pixels, key=lambda p: sum(p[:3]) if p[3] else -1)
        self.assertGreater(min(brightest[:3]), 220)

    def test_invalid_requests(self):
        layer = sparks((255, 255, 255), (255, 200, 90))
        layer.save(self.root / "emissive.png")
        for data in ({"emissive": [], "surfaces": [{"name": "a", "color": "#000000"}]},
                     {"emissive": ["emissive.png"], "surfaces": [{"name": "a"}]},
                     {"emissive": ["emissive.png"], "surfaces": [{"name": "a", "color": "#000000", "image": "x.png"}]},
                     {"emissive": ["/etc/passwd"], "surfaces": [{"name": "a", "color": "#000000"}]}):
            (self.root / "bad.json").write_text(json.dumps({"schema_version": 1, **data}))
            with self.subTest(data=data), self.assertRaises((ValueError, OSError)):
                fx_qa.load(self.root / "bad.json")


if __name__ == "__main__":
    unittest.main()
