import tempfile
import unittest
from pathlib import Path

from pixel_asset_pipeline.bundle import read_once, sha256


class ReadOnceTests(unittest.TestCase):
    def test_bytes_are_read_once_per_run_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame.png"
            path.write_bytes(b"first")
            cache = {}
            first = read_once(path, cache)
            path.write_bytes(b"changed after decoding")
            # Hashing and copying later in the same run see the decoded bytes, not a re-read.
            self.assertEqual(read_once(path, cache), first)
            self.assertEqual(sha256(read_once(path, cache)), sha256(b"first"))
            with self.assertRaises(ValueError):
                read_once(path, {}, limit=4)


if __name__ == "__main__":
    unittest.main()
