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
            environment = dict(os.environ, PYTHONPATH=str(package / "src"), PYTHONDONTWRITEBYTECODE="1")
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
            }
            for target, source in fixtures.items():
                destination = work / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, destination)
            shutil.copytree(ROOT / "examples/production/set/acorn-v2", work / "acorn")
            Image.new("RGB", (32, 32), "#425e3a").save(work / "grass.png")

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
