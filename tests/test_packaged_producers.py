"""Exercise the installed-source entry points without relying on repo-relative imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "examples" / "production"


class PackagedProducerTests(unittest.TestCase):
    def test_local_commands_from_foreign_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            package = work / "plugin"
            subprocess.run([sys.executable, str(ROOT / "scripts/package-plugin.py"), str(package)],
                           cwd=work, check=True, capture_output=True)
            self.assertFalse((package / "examples").exists())
            self.assertTrue((package / ".agents/skills/pixel-asset-pipeline/references/production.md").is_file())
            env = {**os.environ, "PYTHONPATH": str(package / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
            cmd = [sys.executable, "-m", "pixel_asset_pipeline.cli"]
            for command, request, expected_file in [
                ("variant", "gear/staff.request.json", "gear/staff/asset.png"),
                ("compare", "set/compare-best-v2.json", "set/comparison-best-v2/contact-sheet.png"),
                ("sheet", "walk/request.json", "walk/result/sheet.png"),
                ("tile", "tiles/grass-request.json", "tiles/grass/tile.png"),
                ("effect", "effects/pickup/request.json", "effects/pickup/result/sheet.png"),
                ("effect", "effects/flame/request.json", "effects/flame/result/sheet.png"),
            ]:
                with self.subTest(command=command, request=request):
                    output = work / Path(request).parent / command
                    args = cmd + [command, "--request", str(SAMPLES / request), "--out", str(output)]
                    run = subprocess.run(args, cwd=work, env=env, capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    manifest = json.loads(run.stdout)
                    self.assertEqual((manifest["schema_version"], manifest["status"]), (1, "ready"))
                    self.assertEqual(sorted(p.name for p in output.iterdir()), sorted(manifest["files"].values()))
                    name = Path(expected_file).name
                    with Image.open(output / name) as built, Image.open(SAMPLES / expected_file) as sample:
                        self.assertEqual(built.size, sample.size)
                        if command != "compare":  # Contact-sheet text depends on the installed Pillow font.
                            self.assertEqual(built.convert("RGBA").tobytes(), sample.convert("RGBA").tobytes())
                    if command == "compare":
                        data = json.loads((output / manifest["files"]["manifest"]).read_text())
                        self.assertEqual([entry["id"] for entry in data["assets"]], ["scout", "acorn", "lantern"])
                    retry = subprocess.run(args, cwd=work, env=env, capture_output=True, text=True)
                    self.assertEqual(retry.returncode, 2)
                    self.assertEqual(json.loads(retry.stderr)["status"], "error")
