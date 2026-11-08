"""Run the packaged skill's local examples as a host outside the repository."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_packaged_documentation_matches_and_exercises_public_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            staging = Path(folder)
            package, work = staging / "plugin", staging / "host"
            work.mkdir()
            subprocess.run([sys.executable, str(ROOT / "scripts/package-plugin.py"), str(package)],
                           cwd=work, check=True, capture_output=True, timeout=30)
            environment = dict(os.environ, PYTHONPATH=str(package / "src"),
                               PYTHONDONTWRITEBYTECODE="1", PYTHONWARNINGS="error")
            cli = [sys.executable, "-m", "pixel_asset_pipeline.cli"]

            def invoke(arguments):
                result = subprocess.run(cli + arguments, cwd=work, env=environment,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            help_text = invoke(["--help"])
            choices = re.search(r"\{([^}]+)\}", help_text)
            self.assertIsNotNone(choices, help_text)
            commands = choices.group(1).split(",")
            skill_root = package / ".agents/skills/pixel-asset-pipeline"
            manifest = json.loads((package / ".codex-plugin/plugin.json").read_text())
            package_version = re.search(r'^version = "([^"]+)"',
                                        (package / "pyproject.toml").read_text(), re.MULTILINE)
            self.assertIsNotNone(package_version)
            self.assertEqual(manifest["version"], package_version.group(1))
            skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
            routes = re.findall(r"^\|\s*`([^`]+)`\s*\|", skill, re.MULTILINE)
            self.assertCountEqual(routes, commands, "Skill routing must cover the public CLI exactly once")
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill):
                if "://" not in link:
                    self.assertTrue((skill_root / link).is_file(), f"Missing packaged skill resource: {link}")
            reference = (skill_root / "references/production.md").read_text(encoding="utf-8")
            sections = re.findall(r"^## (\S+) · [^\n]+\n(.*?)(?=^## |\Z)",
                                  reference, re.MULTILINE | re.DOTALL)
            self.assertCountEqual([name for name, _ in sections], commands)

            fixtures = {
                "source.png": "examples/codex-scout-styled/draft.png",
                "style.json": "examples/woodland/style.json",
                "art/scout.png": "examples/codex-scout-styled/asset.png",
                "gear/staff.png": "examples/production/gear/sources/staff.png",
                "step-a.png": "examples/production/walk/frames/01.png",
                "step-b.png": "examples/production/walk/frames/02.png",
                "relaxed-sprite.png": "examples/production/rig-draft/relaxed-sprite.png",
                "motion-master.png": "examples/production/motion/master.png",
            }
            for action in ("idle", "walk", "run", "attack", "jump", "hurt"):
                for index in (1, 2):
                    fixtures[f"{action}-{index}.png"] = f"examples/production/walk/frames/{index:02}.png"
            for target, source in fixtures.items():
                destination = work / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, destination)
            shutil.copytree(ROOT / "examples/production/set/acorn-v2", work / "acorn")
            Image.new("RGB", (32, 32), "#425e3a").save(work / "grass.png")

            with Image.open(work / "motion-master.png") as master:
                master.convert("RGBA").resize((160, 160), Image.Resampling.BILINEAR).save(work / "soft.png")
            spell = []
            for x in (2, 7, 12):
                frame = Image.new("RGBA", (16, 16))
                frame.paste((255, 184, 50, 255), (x, 6, x + 2, 9))
                spell.append(frame)
            spell[0].save(work / "spell.gif", save_all=True, append_images=spell[1:], duration=80, disposal=2)
            (work / "spell-license.txt").write_text("CC0-1.0\n")
            (work / "spell-notice.txt").write_text("Original synthetic CLI fixture.\n")

            character_section = dict(sections)["character"]
            cel_manifest = re.findall(r"```json\n(.*?)\n```", character_section, re.DOTALL)[1]
            (work / "courier-cels.json").write_text(json.dumps(json.loads(cel_manifest)))
            for command, section in sections:
                with self.subTest(command=command):
                    snippets = re.findall(r"```sh\n(.*?)\n```", section, re.DOTALL)
                    self.assertTrue(snippets, f"Missing local example for {command}")
                    arguments = shlex.split(snippets[0])
                    self.assertEqual(arguments[:2], ["pixel-asset", command])
                    self.assertNotIn("--codex", arguments)
                    self.assertNotIn("--style-reference", arguments)
                    if command == "build":
                        self.assertIn("--draft", arguments)
                    # Execute only the CLI, never shell prose, operators, or an external generator.
                    for token in arguments[2:]:
                        self.assertFalse(Path(token).is_absolute() or ".." in Path(token).parts)
                    request_path = work / arguments[arguments.index("--request") + 1]
                    examples = re.findall(r"```json\n(.*?)\n```", section, re.DOTALL)
                    if command == "validate":
                        self.assertTrue(request_path.is_file())
                    else:
                        self.assertTrue(examples, f"Missing JSON request example for {command}")
                        request_path.write_text(json.dumps(json.loads(examples[0])), encoding="utf-8")
                    result = json.loads(invoke(arguments[1:]))
                    if command == "validate":
                        self.assertIs(result["passed"], True)
                        continue
                    output = work / arguments[arguments.index("--out") + 1]
                    self.assertEqual((result["schema_version"], result["status"]), (1, "ready"))
                    self.assertCountEqual([path.name for path in output.iterdir()], result["files"].values())
                    for filename in result["files"].values():
                        self.assertEqual(Path(filename).name, filename)
                        self.assertTrue((output / filename).is_file())
                    if command == "motion":
                        report = json.loads((output / "inspection.json").read_text())
                        self.assertTrue(report["neutral_exact_visible_reconstruction"])
                        self.assertTrue(report["passed"])
                        packed = json.loads(invoke(["action-set", "--request",
                                                   "motion-out/action-set.request.json", "--out", "motion-actions"]))
                        self.assertEqual(packed["status"], "ready")
