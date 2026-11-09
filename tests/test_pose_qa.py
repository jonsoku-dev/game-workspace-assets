import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline import pose_qa

FLOOR = 180
TIPS = {  # a 200x200 canvas, body ~100px tall standing on y=180, facing right
    "guard": (150, 165), "load": (40, 60), "contact": (175, 120),
    "follow": (160, 176), "recover-bad": (150, 70), "recover-good": (155, 170),
}


def figure(tip, feet=((80, 20), (120, 20)), grip=(100, 125), sink=0, lift_back=0):
    image = Image.new("RGBA", (200, 200))
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 80, 110, 160), fill=(60, 70, 90, 255))           # torso and legs
    draw.ellipse((92, 64, 108, 80), fill=(200, 160, 130, 255))           # head
    (back, back_w), (front, front_w) = feet
    draw.rectangle((back - back_w // 2, 160, back + back_w // 2, FLOOR - 1 - lift_back), fill=(40, 30, 30, 255))
    draw.rectangle((front - front_w // 2, 160, front + front_w // 2, FLOOR - 1), fill=(40, 30, 30, 255))
    draw.line((grip, tip), fill=(180, 190, 200, 255), width=4)          # the tool
    if sink:
        draw.rectangle((tip[0] - 2, FLOOR, tip[0] + 2, FLOOR + sink), fill=(180, 190, 200, 255))
    return image


class PoseQATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def request(self, frames, steps, contact=2, loop=True, planted=None, grips=False, **extra):
        entries = []
        for ident, image in frames.items():
            image.save(self.root / f"{ident}.png")
            sockets = {"tip": list(TIPS.get(ident.split("@")[0], (150, 165)))}
            if grips:
                sockets["grip"] = [100, 125]
            entries.append({"id": ident, "image": f"{ident}.png", "sockets": sockets})
        sequence = {"steps": [{"frame": f, "ms": ms} for f, ms in steps], "contact_step": contact, "loop": loop}
        if planted:
            sequence["planted"] = planted
        data = {"schema_version": 1, "name": "fixture", "canvas": [200, 200], "floor_y": FLOOR,
                "frames": entries, "sequences": {"attack": sequence}, **extra}
        path = self.root / "request.json"
        path.write_text(json.dumps(data))
        return path

    def assess(self, *args, **kwargs):
        return pose_qa.assess(pose_qa.load(self.request(*args, **kwargs)))

    def attack(self, recovery):
        frames = {name: figure(TIPS[name]) for name in ("guard", "load", "contact", "follow", recovery)}
        steps = [("guard", 180), ("load", 160), ("contact", 100), ("follow", 140), (recovery, 180), ("guard", 180)]
        return frames, steps

    def codes(self, report):
        return {f["code"] for f in report["findings"] if f["severity"] == "error"}

    def test_recovery_that_swings_back_above_rest_is_a_reversal(self):
        report, _ = self.assess(*self.attack("recover-bad"))
        self.assertIn("post-contact-reversal", self.codes(report))
        self.assertFalse(report["passed"])
        bad = next(f for f in report["findings"] if f["code"] == "post-contact-reversal")
        self.assertEqual(bad["where"], "step 4")
        report, _ = self.assess(*self.attack("recover-good"))
        self.assertNotIn("post-contact-reversal", self.codes(report))

    def test_tip_jump_plans_inbetweens_without_moving_later_steps(self):
        report, plans = self.assess(*self.attack("recover-good"))
        self.assertIn("tip-jump", self.codes(report))
        load = next(p for p in plans if p["from"] == "guard" and p["to"] == "load")
        self.assertEqual(load["count"], len(load["inbetweens"]))
        self.assertEqual(sum(load["timing_ms"]), 180)          # the outgoing hold is split, total unchanged
        self.assertEqual(load["method"], "linear")
        # Each planned step is within the per-step limit.
        points = [TIPS["guard"]] + [tuple(i["tip"]) for i in load["inbetweens"]] + [TIPS["load"]]
        body = report["body_height_px"]
        limit = pose_qa.DEFAULTS["max_step_body"] * body + 1
        self.assertTrue(all(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 <= limit for a, b in zip(points, points[1:])))

    def test_grip_sockets_plan_an_arc_and_detect_tool_length_drift(self):
        frames, steps = self.attack("recover-good")
        report, plans = self.assess(frames, steps, grips=True)
        self.assertTrue(all(p["method"] == "arc-around-grip" for p in plans))
        self.assertIn("tool-length-drift", self.codes(report))      # load tip is much farther from the grip
        path = self.request(frames, steps, grips=True)
        data = json.loads(path.read_text())
        for entry in data["frames"]:
            if entry["id"] in ("load", "follow", "guard"):
                entry["foreshortened"] = True
        path.write_text(json.dumps(data))
        report, _ = pose_qa.assess(pose_qa.load(path))
        self.assertIn("tool_length", report)

    def test_floor_penetration_is_measured_in_pixels(self):
        frames, steps = self.attack("recover-good")
        frames["follow"] = figure(TIPS["follow"], sink=12)
        report, _ = self.assess(frames, steps)
        sunk = next(f for f in report["findings"] if f["code"] == "floor-penetration")
        self.assertEqual(sunk["where"], "follow")
        self.assertGreaterEqual(sunk["depth_px"], 12)

    def test_planted_feet_skate_or_lift_but_unplanted_steps_only_warn(self):
        frames, steps = self.attack("recover-good")
        frames["follow"] = figure(TIPS["follow"], feet=((60, 20), (135, 20)))
        planted = [{"from": 2, "to": 3, "feet": ["front", "back"]}]
        report, _ = self.assess(frames, steps, planted=planted)
        self.assertIn("foot-skate", self.codes(report))
        report, _ = self.assess(frames, steps)
        self.assertNotIn("foot-skate", self.codes(report))
        self.assertIn("ground-contact-shift", {f["code"] for f in report["findings"]})
        frames["follow"] = figure(TIPS["follow"], lift_back=15)
        report, _ = self.assess(frames, steps, planted=planted)
        lifted = [f for f in report["findings"] if f["code"] == "foot-lift"]
        self.assertEqual(len(lifted), 1)
        self.assertIn("back", lifted[0]["message"])

    def test_threshold_override_and_invalid_requests(self):
        frames, steps = self.attack("recover-good")
        report, _ = self.assess(frames, steps, thresholds={"max_step_body": 5})
        self.assertNotIn("tip-jump", self.codes(report))
        path = self.request(frames, steps)
        for change in ({"canvas": [100, 100]}, {"floor_y": 999}, {"thresholds": {"bogus": 1}},
                       {"sequences": {"attack": {"steps": [{"frame": "missing", "ms": 10}] * 2}}}):
            data = dict(json.loads(path.read_text()), **change)
            (self.root / "bad.json").write_text(json.dumps(data))
            with self.subTest(change=change), self.assertRaises(ValueError):
                pose_qa.load(self.root / "bad.json")
        data = json.loads(path.read_text())
        data["frames"][0]["image"] = "../escape.png"
        (self.root / "bad.json").write_text(json.dumps(data))
        with self.assertRaises((ValueError, OSError)):
            pose_qa.load(self.root / "bad.json")

    def test_cli_publishes_report_trail_and_fails_on_errors(self):
        path = self.request(*self.attack("recover-bad"))
        out = self.root / "qa"
        run = subprocess.run([sys.executable, "-m", "pixel_asset_pipeline.cli", "pose-qa", "--request", str(path),
                              "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["status"], "failed")
        self.assertIn("post-contact-reversal", result["findings"])
        for name in ("pose-qa.json", "tip-trail.png", "breakdowns.json"):
            self.assertTrue((out / name).is_file())
        report = json.loads((out / "pose-qa.json").read_text())
        self.assertEqual(report["artistic_acceptance"], "pending")


if __name__ == "__main__":
    unittest.main()
