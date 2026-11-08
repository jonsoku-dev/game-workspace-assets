import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pixel_asset_pipeline.provider import generate


THREAD = "12345678-1234-4234-8234-123456789abc"


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / "draft.png"
        self.folder = self.root / "generated_images" / THREAD
        self.folder.mkdir(parents=True)
        self.env = patch.dict(os.environ, {"CODEX_HOME": str(self.root),
                                          "OPENAI_API_KEY": "do-not-leak",
                                          "OPENAI_BASE_URL": "https://invalid.example",
                                          "HTTPS_PROXY": "http://invalid.example"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.which = patch("pixel_asset_pipeline.provider.shutil.which", return_value="/bin/codex")
        self.which.start()
        self.addCleanup(self.which.stop)

    def transport(self, command, **kwargs):
        self.command, self.options = command, kwargs
        Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(self.folder / "native.png")
        for event in [{"type": "thread.started", "thread_id": THREAD},
                      {"type": "turn.completed"}]:
            kwargs["stdout"].write((json.dumps(event) + "\n").encode())
        return subprocess.CompletedProcess(command, 0)

    def test_success_uses_private_native_image_without_api_key_or_shell(self):
        with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=self.transport):
            generate("scout $(secret)", self.destination)
        self.assertEqual(self.destination.read_bytes(), (self.folder / "native.png").read_bytes())
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("OPENAI_API_KEY", self.options["env"])
        self.assertNotIn("shell", self.options)
        self.assertIn("--ephemeral", self.command)
        self.assertIn("read-only", self.command)
        disabled = {self.command[i + 1] for i, flag in enumerate(self.command) if flag == "--disable"}
        self.assertTrue({"shell_tool", "unified_exec", "apps", "plugins", "hooks"}.issubset(disabled))
        self.assertNotIn("OPENAI_BASE_URL", self.options["env"])
        self.assertNotIn("HTTPS_PROXY", self.options["env"])
        self.assertNotIn("scout $(secret)", self.command)
        self.assertIn(b"scout $(secret)", self.options["input"])

    def test_reference_is_attached_as_one_argument(self):
        reference = self.root / "reference with spaces.png"
        Image.new("RGBA", (2, 2)).save(reference)
        with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=self.transport):
            generate("reference scout", self.destination, (reference,))
        index = self.command.index("--image")
        self.assertEqual(self.command[index + 1], str(reference.resolve()))

    def test_transport_failure_does_not_reveal_logs(self):
        result = subprocess.CompletedProcess([], 9, "secret giant log", "secret")
        with patch("pixel_asset_pipeline.provider.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "exit 9") as error:
                generate("scout", self.destination)
        self.assertNotIn("secret", str(error.exception))
        self.assertFalse(self.destination.exists())

    def test_missing_stale_multiple_and_symlink_images_are_rejected(self):
        def broken(mode):
            def run(command, **kwargs):
                result = self.transport(command, **kwargs)
                source = self.folder / "native.png"
                if mode == "missing":
                    source.unlink()
                elif mode == "stale":
                    os.utime(source, ns=(1, 1))
                elif mode == "multiple":
                    Image.new("RGBA", (2, 2)).save(self.folder / "second.png")
                elif mode == "symlink":
                    source.rename(self.root / "outside.png")
                    source.symlink_to(self.root / "outside.png")
                return result
            return run
        for mode in ("missing", "stale", "multiple", "symlink"):
            with self.subTest(mode=mode):
                for path in self.folder.iterdir():
                    path.unlink()
                with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=broken(mode)):
                    with self.assertRaises(RuntimeError):
                        generate("scout", self.destination)
                self.assertFalse(self.destination.exists())

    def test_unrelated_thread_image_is_not_used(self):
        other = self.root / "generated_images" / "other"
        other.mkdir()
        Image.new("RGBA", (2, 2)).save(other / "native.png")
        def run(command, **kwargs):
            kwargs["stdout"].write((json.dumps({"type": "thread.started", "thread_id": THREAD}) +
                                     '\n{"type":"turn.completed"}\n').encode())
            return subprocess.CompletedProcess(command, 0)
        with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "exactly one image"):
                generate("scout", self.destination)

    def test_invalid_stream_timeout_and_invalid_png(self):
        def invalid(command, **kwargs):
            kwargs["stdout"].write(b"not JSON\n")
            return subprocess.CompletedProcess(command, 0)
        with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=invalid):
            with self.assertRaisesRegex(RuntimeError, "invalid generation event"):
                generate("scout", self.destination)
        with patch("pixel_asset_pipeline.provider.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("codex", 600)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                generate("scout", self.destination)
        def bad_png(command, **kwargs):
            result = self.transport(command, **kwargs)
            (self.folder / "native.png").write_bytes(b"not PNG")
            return result
        with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=bad_png):
            with self.assertRaisesRegex(RuntimeError, "invalid PNG"):
                generate("scout", self.destination)

    def test_existing_destination_is_preserved(self):
        self.destination.write_bytes(b"existing")
        with patch("pixel_asset_pipeline.provider.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                generate("scout", self.destination)
        run.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), b"existing")

    def test_incomplete_failed_or_non_object_events_are_rejected(self):
        for events in ([{"type": "thread.started", "thread_id": THREAD}],
                       [{"type": "turn.failed"}], [[]]):
            with self.subTest(events=events):
                def run(command, **kwargs):
                    for event in events:
                        kwargs["stdout"].write((json.dumps(event) + "\n").encode())
                    return subprocess.CompletedProcess(command, 0)
                with patch("pixel_asset_pipeline.provider.subprocess.run", side_effect=run):
                    with self.assertRaises(RuntimeError):
                        generate("scout", self.destination)
                self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
