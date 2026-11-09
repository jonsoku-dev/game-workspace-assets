"""Schema-version-2 assembly validation, plus a real Blender/webstage build when available."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import assembly  # noqa: E402

SPEC = importlib.util.spec_from_file_location("model_build", ROOT / "tools/build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

GRINDER = {
    "schema_version": 2, "name": "Grinder", "texel_density_px_per_m": 128, "bake_samples": 2,
    "materials": {"steel": {"base": "#7d8a90", "metallic": 0.9, "roughness": 0.4, "grain": "brushed", "wear": 0.2},
                  "enamel": {"base": "#e2601c", "roughness": 0.45, "wear": 0.6, "dirt": 0.4}},
    "parts": [{"id": "body", "shape": "box", "size_m": [0.6, 0.3, 0.3], "position_m": [0, 0, 0.15],
               "bevel_m": 0.01, "material": "enamel"},
              {"id": "blade", "shape": "saw_blade", "radius_m": 0.14, "thickness_m": 0.004, "teeth": 24,
               "tooth_depth_m": 0.012, "bore_radius_m": 0.02, "parent": "hub", "material": "steel"}],
    "pivots": [{"id": "hub", "parent": "body", "position_m": [0.3, -0.152, 0.0]}],
    "animations": [{"name": "blade_spin", "target": "hub", "loop": True,
                    "spin": {"axis": "y", "rpm": 240, "duration_s": 0.5}}],
    "lod_ratios": [0.5], "budget": {"triangles": 20000, "texture_px": 256},
}


def tool(name):
    return shutil.which(name) is not None


class AssemblySchemaTests(unittest.TestCase):
    def spec(self, **changes):
        data = copy.deepcopy(GRINDER)
        data.update(changes)
        return data

    def test_valid_assembly_normalises_nodes_and_defaults(self):
        spec = assembly.validate(self.spec())
        self.assertEqual([n["id"] for n in spec["nodes"]], ["hub", "body", "blade"])
        self.assertEqual(spec["materials"]["enamel"]["metallic"], 0.0)
        self.assertEqual(spec["nodes"][2]["teeth"], 24)

    def test_build_dispatches_schema_two(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            request.write_text(json.dumps(self.spec()))
            self.assertEqual(build.read_request(request)["schema_version"], 2)

    def test_rejections_name_the_problem(self):
        cases = {
            "unknown part key": self.spec(parts=[dict(GRINDER["parts"][0], colour="red")] + GRINDER["parts"][1:]),
            "missing material": self.spec(parts=[dict(GRINDER["parts"][0], material="gold")] + GRINDER["parts"][1:]),
            "parent cycle": self.spec(pivots=[{"id": "hub", "parent": "blade", "position_m": [0, 0, 0]}]),
            "fast spin aliases": self.spec(animations=[{"name": "s", "target": "hub", "loop": True,
                                                        "spin": {"axis": "y", "rpm": 1800, "duration_s": 0.5}}]),
            "loop not whole turns": self.spec(animations=[{"name": "s", "target": "hub", "loop": True,
                                                           "spin": {"axis": "y", "rpm": 100, "duration_s": 0.5}}]),
            "keys out of order": self.spec(animations=[{"name": "k", "target": "body", "keys": [
                {"t": 0.5, "position_m": [0, 0, 0]}, {"t": 0.2, "position_m": [0, 0, 1]}]}]),
            "mixed key channels": self.spec(animations=[{"name": "k", "target": "body", "keys": [
                {"t": 0, "position_m": [0, 0, 0]}, {"t": 1, "rotation_deg": [0, 0, 90]}]}]),
            "bore larger than root": self.spec(parts=[GRINDER["parts"][0], dict(GRINDER["parts"][1], bore_radius_m=0.13)]),
            "arc span": self.spec(parts=GRINDER["parts"] + [{"id": "guard", "shape": "arc", "inner_radius_m": 0.1,
                                                              "outer_radius_m": 0.12, "depth_m": 0.02, "start_deg": 0,
                                                              "end_deg": 360, "material": "steel"}]),
            "lods increase": self.spec(lod_ratios=[0.3, 0.6]),
            "texture size": self.spec(budget={"triangles": 1000, "texture_px": 300}),
        }
        for label, data in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                assembly.validate(data)

    def test_v1_requests_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            request.write_text(json.dumps({"schema_version": 1, "name": "Lantern", "preset": "lantern"}))
            self.assertEqual(build.read_request(request)["preset"], "lantern")


def glb_json(path):
    data = Path(path).read_bytes()
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + length])


@unittest.skipUnless(tool("blender") and tool("webstage") and tool("node")
                     and (ROOT / "three/node_modules").is_dir(), "Blender, webstage, node and three deps required")
class AssemblyBuildTests(unittest.TestCase):
    def run_build(self, spec, folder):
        request = Path(folder) / "request.json"
        request.write_text(json.dumps(spec))
        out = Path(folder) / "bundle"
        result = subprocess.run([sys.executable, str(ROOT / "tools/build.py"), "--request", str(request),
                                 "--out", str(out)], capture_output=True, text=True, timeout=900)
        return result, out

    def test_real_build_bakes_animates_lods_and_validates(self):
        with tempfile.TemporaryDirectory() as folder:
            result, out = self.run_build(GRINDER, folder)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            files = json.loads(result.stdout)["files"]
            for name in files.values():
                self.assertTrue((out / name).is_file(), name)
            raw = glb_json(out / files["raw"])
            self.assertEqual({n["name"] for n in raw["nodes"]}, {"hub", "body", "blade"})
            self.assertEqual(len(raw["images"]), 3)  # one shared base / ORM / normal atlas
            self.assertEqual([a["name"] for a in raw["animations"]], ["blade_spin"])
            validation = json.loads((out / files["validation"]).read_text())
            self.assertTrue(all(validation["assembly_checks"].values()))
            self.assertEqual(validation["animations"][0]["duration_s"], 0.5)
            self.assertLess(validation["lods"][0]["triangles"], validation["triangle_count"])
            metadata = json.loads((out / files["metadata"]).read_text())
            self.assertTrue(metadata["quality"]["passed"])
            self.assertEqual(metadata["review"]["artistic_acceptance"], "pending")
            for part in metadata["quality"]["parts"].values():
                self.assertEqual(part["non_manifold_edges"], 0)
                self.assertLessEqual(part["uv_overlap"], 0.01)

    def test_quality_gates_refuse_floating_and_off_axis_parts(self):
        floating = copy.deepcopy(GRINDER)
        floating["pivots"][0]["position_m"] = [0.3, -0.16, 0.0]          # blade hangs 8 mm in front of the body
        off_axis = copy.deepcopy(GRINDER)
        off_axis["parts"][1]["position_m"] = [0.0, 0.0, 0.03]              # blade not centred on its spin pivot
        for label, spec, code in (("floating", floating, "floating-part"), ("off axis", off_axis, "off-axis-spin")):
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                result, out = self.run_build(spec, folder)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(code, result.stderr)
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
