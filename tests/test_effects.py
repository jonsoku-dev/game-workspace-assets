import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_asset_pipeline.effects import produce


PALETTE = ["#c36643", "#e5ad57", "#fff1d0"]


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = self.root / "request.json"

    def build(self, preset="pickup", folder="out", **changes):
        request = {"schema_version": 1, "preset": preset, "size": 32,
                   "palette": PALETTE, "seed": 17, **changes}
        self.request.write_text(json.dumps(request))
        stage = self.root / folder
        files = produce(self.request, stage)
        sheet = Image.open(stage / files["sheet"])
        sheet.load()
        metadata = json.loads((stage / files["metadata"]).read_text())
        report = json.loads((stage / files["effect"]).read_text())
        return sheet, metadata, report, stage

    def frames(self, image, metadata):
        return [image.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]))
                for r in [frame["rect"] for frame in metadata["frames"]]]

    def test_both_presets_are_deterministic_native_palette_locked_motion(self):
        for preset, count, duration in (("pickup", 10, 60), ("flame", 12, 80)):
            with self.subTest(preset=preset):
                image, meta, report, stage = self.build(preset, preset)
                repeat, _, _, _ = self.build(preset, preset + "-repeat")
                self.assertEqual(image.tobytes(), repeat.tobytes())
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (32 * count, 32))
                self.assertEqual(meta["pivot_px_from_top_left"], [16, 16])
                self.assertEqual(meta["loop"], preset == "flame")
                self.assertEqual([entry["duration_ms"] for entry in meta["frames"]], [duration] * count)
                self.assertTrue(report["passed"])
                frames = self.frames(image, meta)
                self.assertGreater(len({f.tobytes() for f in frames}), count // 2)
                for checks in report["frame_checks"]:
                    self.assertTrue(checks["rgba"] and checks["binary_alpha"] and checks["palette"])
                with Image.open(stage / "preview.gif") as preview:
                    self.assertEqual(preview.n_frames, count)
                    self.assertEqual(preview.info.get("loop"), 0 if preset == "flame" else None)

    def test_pickup_anticipates_travels_and_vanishes_preserving_sparks(self):
        image, meta, report, _ = self.build()
        frames = self.frames(image, meta)
        self.assertLess(frames[0].getbbox()[2] - frames[0].getbbox()[0], 5)
        self.assertGreater(frames[5].getbbox()[2] - frames[5].getbbox()[0], 15)
        self.assertIsNone(frames[-1].getbbox())
        self.assertTrue(report["terminal_blank"])
        self.assertIsNotNone(frames[-2].getbbox())

    def test_flame_has_stationary_base_and_cyclic_transition(self):
        image, meta, report, _ = self.build("flame")
        frames = self.frames(image, meta)
        self.assertFalse(report["terminal_blank"])
        self.assertTrue(all(frame.getpixel((16, 25))[3] == 255 for frame in frames))
        def distance(a, b):
            return sum(a.getpixel((x, y)) != b.getpixel((x, y))
                       for y in range(a.height) for x in range(a.width))
        adjacent = [distance(frames[i], frames[(i + 1) % len(frames)]) for i in range(len(frames))]
        self.assertLessEqual(adjacent[-1], max(adjacent[:-1]) * 1.5)
        self.assertGreater(distance(frames[0], frames[6]), 20)

    def test_seed_palette_and_size_change_real_output(self):
        image, _, _, _ = self.build("flame")
        changed, _, _, _ = self.build("flame", "seed", seed=18)
        self.assertNotEqual(image.tobytes(), changed.tobytes())
        recolored, _, report, _ = self.build("flame", "palette", palette=["#33463d", "#99aa69", "#cad58d"])
        self.assertNotEqual(image.tobytes(), recolored.tobytes())
        self.assertTrue(all(check["palette"] for check in report["frame_checks"]))
        for preset, count in (("pickup", 10), ("flame", 12)):
            first, _, _, _ = self.build(preset, preset + "-first")
            changed, _, _, _ = self.build(preset, preset + "-changed", seed=18)
            self.assertNotEqual(first.tobytes(), changed.tobytes())
            for size in (16, 64):
                small, _, _, _ = self.build(preset, preset + str(size), size=size)
                self.assertEqual(small.size, (size * count, size))

    def test_legacy_pixels_remain_compatible(self):
        for preset, expected in {
            "pickup": "5de713e81a8d058f253dec160e0bae2f6fc1154d20d95766e80e460d9f626552",
            "flame": "1a73b907db80df8ace2d7db845229a2f72e21fc69c1122f696d1c84ff0eab566",
        }.items():
            image, meta, _, _ = self.build(preset)
            pixels = b"".join(frame.tobytes() for frame in self.frames(image, meta))
            self.assertEqual(hashlib.sha256(pixels).hexdigest(), expected)

    def test_feedback_presets_resolve_and_publish_timing_anchor_and_event(self):
        signatures = set()
        for preset in ("step", "land", "slash", "impact", "confirm", "deny"):
            for size in (16, 32, 64):
                with self.subTest(preset=preset, size=size):
                    image, meta, report, _ = self.build(preset, preset + str(size), size=size)
                    repeated, _, _, _ = self.build(preset, "repeat", size=size)
                    self.assertEqual(image.tobytes(), repeated.tobytes())
                    self.assertEqual(image.size, (size * report["frame_count"], size))
                    self.assertTrue(report["passed"])
                    self.assertTrue(report["terminal_blank"])
                    self.assertFalse(meta["loop"])
                    self.assertEqual(report["timing_ms"], [f["duration_ms"] for f in meta["frames"]])
                    self.assertEqual(sum(report["timing_ms"]), report["duration_ms"])
                    ground = preset in {"step", "land"}
                    self.assertEqual(report["anchor"], "ground" if ground else "event")
                    self.assertEqual(meta["pivot_px_from_top_left"],
                                     [size // 2, round(size * 0.8125) if ground else size // 2])
                    self.assertEqual(report["pivot_px_from_top_left"], meta["pivot_px_from_top_left"])
                    self.assertTrue(report["trigger_intent"])
                    frames = self.frames(image, meta)
                    self.assertIsNotNone(frames[report["reduced_motion_frame"]].getbbox())
                    self.assertIsNotNone(frames[-2].getbbox())
                    self.assertIsNone(frames[-1].getbbox())
                    if size == 32:
                        signatures.add(image.tobytes())
        self.assertEqual(len(signatures), 6)

    def test_ground_strength_direction_and_ui_shape_differ_without_color(self):
        def masks(preset):
            image, meta, report, _ = self.build(preset)
            return [f.getchannel("A") for f in self.frames(image, meta)], report
        step, step_report = masks("step")
        land, land_report = masks("land")
        self.assertLess(max(sum(f.histogram()[1:]) for f in step),
                        max(sum(f.histogram()[1:]) for f in land))
        self.assertLess(step_report["duration_ms"], land_report["duration_ms"])
        slash, _ = masks("slash")
        self.assertTrue(all(f.getbbox()[0] >= 16 for f in slash[:-1]))
        confirm, confirm_report = masks("confirm")
        deny, deny_report = masks("deny")
        self.assertNotEqual([f.tobytes() for f in confirm], [f.tobytes() for f in deny])
        self.assertNotEqual(confirm_report["timing_ms"], deny_report["timing_ms"])
        self.assertEqual(deny[4].tobytes(), deny[5].tobytes())
        self.assertNotEqual(confirm[0].tobytes(), confirm[2].tobytes())

    def test_malformed_requests_fail_before_writing(self):
        for changes in ({"preset": "storm"}, {"preset": []}, {"size": True}, {"size": 65},
                        {"seed": True}, {"seed": 2**31}, {"palette": []},
                        {"palette": ["#000000"] * 3}, {"palette": ["red", "#000000", "#ffffff"]},
                        {"schema_version": True}, {"unknown": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.build(**changes)
        self.assertFalse((self.root / "out").exists())
