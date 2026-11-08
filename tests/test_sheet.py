import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_asset_pipeline.sheet import export_sheet, produce


class SheetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.frames = [Image.new("RGBA", (12, 16)) for _ in range(2)]
        self.frames[0].putpixel((2, 3), (27, 48, 19, 255))
        self.frames[0].putpixel((0, 0), (99, 77, 55, 0))
        self.frames[1].putpixel((6, 15), (172, 91, 40, 128))

    def test_sheet_crops_preserve_all_rgba_bytes_and_exact_timing(self):
        files = export_sheet(self.frames, [83, 125], (6, 16), True, self.stage)
        metadata = json.loads((self.stage / files["metadata"]).read_text())
        self.assertEqual(metadata, {
            "schema_version": 1,
            "frames": [{"rect": {"x": 0, "y": 0, "w": 12, "h": 16}, "duration_ms": 83},
                       {"rect": {"x": 12, "y": 0, "w": 12, "h": 16}, "duration_ms": 125}],
            "pivot_px_from_top_left": [6, 16], "loop": True,
        })
        with Image.open(self.stage / files["sheet"]) as sheet:
            self.assertEqual(sheet.mode, "RGBA")
            for index, source in enumerate(self.frames):
                self.assertEqual(sheet.crop((index * 12, 0, (index + 1) * 12, 16)).tobytes(),
                                 source.tobytes())
        with Image.open(self.stage / files["preview"]) as gif:
            self.assertEqual(gif.size, (72, 96))
            self.assertEqual(gif.n_frames, 2)
            self.assertEqual(gif.info["loop"], 0)
            self.assertEqual(gif.info["duration"], 80)
            gif.seek(1)
            self.assertEqual(gif.info["duration"], 130)
            self.assertEqual(gif.convert("RGBA").getextrema()[3], (255, 255))

    def test_output_is_deterministic_and_nonlooping_preview_has_no_loop_extension(self):
        export_sheet(self.frames, [100, 200], (6, 16), False, self.stage)
        other = self.root / "other"
        other.mkdir()
        export_sheet(self.frames, [100, 200], (6, 16), False, other)
        for file in self.stage.iterdir():
            self.assertEqual(file.read_bytes(), (other / file.name).read_bytes())
        with Image.open(self.stage / "preview.gif") as gif:
            self.assertNotIn("loop", gif.info)

    def test_request_paths_are_relative_to_request_not_working_directory(self):
        for index, frame in enumerate(self.frames):
            frame.save(self.root / f"pose-{index}.png")
        request = self.root / "request.json"
        request.write_text(json.dumps({
            "schema_version": 1, "frames": [
                {"path": "pose-0.png", "duration_ms": 80},
                {"path": "pose-1.png", "duration_ms": 120}],
            "pivot_px_from_top_left": [6, 16], "loop": True,
        }))
        self.assertEqual(produce(request, self.stage)["sheet"], "sheet.png")

    def test_identical_preview_holds_are_bounded_without_losing_sheet_timing(self):
        for durations in ([60_000] * 10 + [55_340], [60_000] * 10 + [55_350],
                          [60_000] * 10 + [55_360], [60_000] * 12, [60_000] * 64):
            with self.subTest(total=sum(durations)):
                frames = [self.frames[0]] * len(durations)
                export_sheet(frames, durations, (6, 16), True, self.stage)
                metadata = json.loads((self.stage / "sheet.json").read_text())
                self.assertEqual([entry["duration_ms"] for entry in metadata["frames"]], durations)
                with Image.open(self.stage / "preview.gif") as gif:
                    self.assertEqual(gif.n_frames, 1)
                    self.assertEqual(gif.info["duration"], min(655_350, sum(durations)))

    def test_long_identical_hold_does_not_discard_the_following_pose(self):
        export_sheet([self.frames[0]] * 12 + [self.frames[1]], [60_000] * 13,
                     (6, 16), False, self.stage)
        with Image.open(self.stage / "preview.gif") as gif:
            self.assertEqual(gif.n_frames, 2)
            self.assertEqual(gif.info["duration"], 655_350)
            first = gif.convert("RGB").tobytes()
            gif.seek(1)
            self.assertEqual(gif.info["duration"], 60_000)
            self.assertNotEqual(gif.convert("RGB").tobytes(), first)

    def test_invalid_export_inputs_write_nothing(self):
        defaults = {"frames": self.frames, "durations": [100, 100], "pivot": (6, 16),
                    "loop": True, "stage": self.stage}
        for update in (
            {"frames": []}, {"frames": self.frames * 33}, {"durations": [100]},
            {"durations": [True, 100]}, {"durations": [0, 100]},
            {"durations": [60001, 100]}, {"durations": [10.0, 100]},
            {"loop": 1}, {"pivot": [6.0, 16]}, {"pivot": [6, 17]},
            {"pivot": [-1, 0]}, {"pivot": None},
            {"frames": [self.frames[0], Image.new("RGBA", (12, 15))]},
            {"frames": [self.frames[0], Image.new("RGB", (12, 16))]},
            {"frames": [Image.new("RGBA", (513, 16))] * 2},
        ):
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    export_sheet(**{**defaults, **update})
                self.assertFalse(list(self.stage.iterdir()))

    def test_invalid_requests_are_rejected(self):
        request = self.root / "request.json"
        for value in (
            {"schema_version": 1, "frames": []},
            {"schema_version": True, "frames": []},
            {"schema_version": 1, "frames": [], "provider_url": "invalid"},
            {"schema_version": 1, "frames": ["pose.png"]},
            {"schema_version": 1, "frames": [{"path": "", "duration_ms": 100}]},
            {"schema_version": 1, "frames": [{"path": "pose.png", "duration_ms": 100, "trim": True}]},
        ):
            with self.subTest(value=value):
                request.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    produce(request, self.stage)
                self.assertFalse(list(self.stage.iterdir()))

    def test_production_walk_has_four_native_grounded_poses_with_fixed_identity(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        with Image.open(examples / "codex-scout-styled" / "asset.png") as image:
            reference = image.convert("RGBA")
        palette = {color for _, color in reference.getcolors()}
        pixels = []
        for path in sorted((examples / "production" / "walk" / "frames").glob("*.png")):
            with Image.open(path) as frame:
                self.assertEqual((frame.mode, frame.size), ("RGBA", (48, 48)))
                self.assertEqual(frame.getbbox()[3], 46)
                self.assertEqual(frame.crop((0, 0, 48, 37)).tobytes(),
                                 reference.crop((0, 0, 48, 37)).tobytes())
                self.assertLessEqual({color for _, color in frame.getcolors()}, palette)
                pixels.append(frame.tobytes())
        self.assertEqual(len(pixels), 4)
        self.assertEqual(len(set(pixels)), 4)
