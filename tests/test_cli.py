import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from pixel_asset_pipeline.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / "moss.json"
        self.profile.write_text(json.dumps({"schema_version": 1, "palette": ["#335544", "#ffbb66"]}))
        self.request = self.root / "request.json"
        self.fields = {"schema_version": 1, "kind": "icon", "prompt": "seed", "profile": "moss.json"}
        self.request.write_text(json.dumps(self.fields))
        self.draft = self.root / "draft.png"
        im = Image.new("RGBA", (12, 16))
        ImageDraw.Draw(im).rectangle((3, 3, 8, 12), fill=(24, 100, 67, 255))
        im.save(self.draft)
        self.output = self.root / "bundle"

    def invoke(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main([str(x) for x in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def build(self):
        return self.invoke("build", "--request", self.request, "--out", self.output, "--draft", self.draft)

    def test_profile_resolves_by_request_location_and_bundle_is_reusable(self):
        with patch("pixel_asset_pipeline.provider.generate", side_effect=AssertionError("external generation")):
            code, stdout, _ = self.build()
        self.assertEqual(code, 0)
        files = json.loads(stdout)["files"]
        meta = json.loads((self.output / files["metadata"]).read_text())
        self.assertEqual(meta["request"]["palette"], ["#335544", "#ffbb66"])
        self.assertEqual(meta["import"], {"filter": "nearest", "pivot_px_from_top_left": [12, 12]})
        self.assertEqual((self.output / files["source"]).read_bytes(), self.draft.read_bytes())
        args = ("validate", "--request", self.request, self.output / files["sprite"])
        self.assertTrue(json.loads(self.invoke(*args)[1])["passed"])
        self.assertEqual(self.build()[0], 2)
        self.profile.write_text(json.dumps({"schema_version": 1, "palette": ["#ff0000"]}))
        code, stdout, _ = self.invoke(*args)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stdout)["checks"]["palette"])

    def test_invalid_inputs_publish_nothing(self):
        for update in ({"schema_version": True}, {"size": 3}, {"kind": "tile"},
                       {"palette": ["red"]}, {"outline": "#000000"}, {"max_colors": 13},
                       {"provider_url": "https://invalid.example"}):
            with self.subTest(update=update):
                self.request.write_text(json.dumps({**self.fields, **update}))
                code, _, stderr = self.build()
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(stderr)["status"], "error")
                self.assertFalse(self.output.exists())
        self.request.write_text(json.dumps(self.fields))
        self.draft.write_bytes(b"not a PNG")
        self.assertEqual(self.build()[0], 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".pixel-build-*")))

    def test_codex_failure_never_falls_back_or_publishes(self):
        with patch("pixel_asset_pipeline.provider.generate", side_effect=RuntimeError("Codex unavailable")):
            code, _, stderr = self.invoke("build", "--request", self.request, "--codex", "--out", self.output)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stderr)["error"], "Codex unavailable")
        self.assertFalse(self.output.exists())

    def test_style_reference_sends_only_chosen_pixels_and_layout(self):
        from PIL import PngImagePlugin
        reference = self.root / "private-filename.png"
        note = PngImagePlugin.PngInfo()
        note.add_text("project", "private annotation")
        Image.new("RGBA", (600, 300), (49, 90, 51, 255)).save(reference, pnginfo=note)

        def generate(prompt, output, references):
            self.assertNotIn(reference.name, prompt)
            self.assertEqual([item.name for item in references], ["layout.png", "style.png"])
            with Image.open(references[1]) as image:
                self.assertEqual(image.size, (512, 256))
                self.assertNotIn("project", image.info)
            output.write_bytes(self.draft.read_bytes())

        with patch("pixel_asset_pipeline.provider.generate", side_effect=generate):
            code, _, error = self.invoke("build", "--request", self.request, "--out", self.output,
                                         "--codex", "--style-reference", reference)
        self.assertEqual(code, 0, error)
        meta = json.loads((self.output / "metadata.json").read_text())
        self.assertTrue(meta["style_reference_used"])
        self.assertNotIn(reference.name, (self.output / "metadata.json").read_text())

    def test_local_build_rejects_codex_reference_before_reading_it(self):
        with patch("pixel_asset_pipeline.provider.generate", side_effect=AssertionError("network")):
            code, _, error = self.invoke("build", "--request", self.request, "--out", self.output,
                                         "--draft", self.draft, "--style-reference", self.root/"missing.png")
        self.assertEqual(code, 2)
        self.assertIn("requires --codex", error)
        self.assertFalse(self.output.exists())
