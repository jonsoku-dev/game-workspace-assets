"""No-replace publication preserves destinations created while a producer runs."""
from pathlib import Path
import tempfile
import unittest

from pixel_asset_pipeline.bundle import publish


class BundlePublicationTests(unittest.TestCase):
    def test_destination_created_during_build_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for kind in ('empty-directory', 'directory', 'file', 'dangling-symlink'):
                with self.subTest(kind=kind):
                    output = root / kind

                    def producer(stage):
                        (stage / 'asset.txt').write_bytes(b'new art')
                        if kind.endswith('directory'):
                            output.mkdir()
                            if kind == 'directory':
                                (output / 'accepted.txt').write_bytes(b'accepted art')
                        elif kind == 'file':
                            output.write_bytes(b'accepted art')
                        else:
                            output.symlink_to(root / 'absent')
                        return {'asset': 'asset.txt'}

                    with self.assertRaises(OSError):
                        publish(output, producer)
                    if kind.endswith('directory'):
                        self.assertTrue(output.is_dir())
                        self.assertFalse((output / 'asset.txt').exists())
                        if kind == 'directory':
                            self.assertEqual((output / 'accepted.txt').read_bytes(), b'accepted art')
                    elif kind == 'file':
                        self.assertEqual(output.read_bytes(), b'accepted art')
                    else:
                        self.assertTrue(output.is_symlink())
                        self.assertEqual(output.readlink(), root / 'absent')
                    self.assertFalse(list(root.glob('.pixel-build-*')))

    def test_relative_destination_publishes_complete_bundle(self):
        with tempfile.TemporaryDirectory(dir='.') as folder:
            output = Path(folder) / 'result'

            def producer(stage):
                (stage / 'asset.txt').write_bytes(b'new art')
                return {'asset': 'asset.txt'}

            self.assertEqual(publish(output, producer)['status'], 'ready')
            self.assertEqual((output / 'asset.txt').read_bytes(), b'new art')
