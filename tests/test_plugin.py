import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / 'examples' / 'mock-game-plugin' / 'import.mjs'


def write_draft(path):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    rows = []
    for y in range(32):
        row = bytearray([0])
        for x in range(32):
            row.extend((255, 0, 0, 255) if 10 <= x < 22 and 8 <= y < 25 else (0, 0, 0, 0))
        rows.append(row)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 32, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


class PluginImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='plugin integration ')
        self.addCleanup(self.temporary.cleanup)
        self.foreign = Path(self.temporary.name)
        self.request = self.foreign / 'request with spaces.json'
        self.request.write_text(json.dumps({'schema_version': 1, 'kind': 'character',
                                           'prompt': 'A red pixel character', 'size': 32}))
        self.draft = self.foreign / 'draft with spaces.png'
        write_draft(self.draft)
        self.destination = self.foreign / 'game asset.png'

    def invoke(self, cli, *args, mode=None):
        environment = dict(os.environ, PIXEL_ASSET_CLI=str(cli))
        if mode:
            environment['MOCK_MODE'] = mode
        return subprocess.run(['node', str(IMPORTER), str(self.request), str(self.destination), *map(str, args)],
                              cwd=self.foreign, env=environment, text=True, capture_output=True, timeout=30)

    def real_cli(self):
        adjacent = Path(sys.executable).parent / 'pixel-asset'
        command = os.environ.get('PIXEL_ASSET_CLI') or (str(adjacent) if adjacent.is_file() else shutil.which('pixel-asset'))
        self.assertTrue(command, 'Install this project and run tests with its Python environment')
        return command

    def fake_cli(self):
        script = self.foreign / 'fake pixel-asset'
        script.write_text(f'#!{sys.executable}\n' + f'png = bytes.fromhex({self.draft.read_bytes().hex()!r})\n' + '''import json, os, pathlib, sys
args = sys.argv[1:]
bundle = pathlib.Path(args[args.index('--out') + 1])
bundle.mkdir()
mode = os.environ.get('MOCK_MODE', '')
if mode == 'no_draft': assert '--codex' in args and '--draft' not in args
files = dict(sprite='asset.png', preview='preview.png', metadata='metadata.json', validation='validation.json', source='draft.png')
for name, filename in files.items():
    (bundle / filename).write_bytes(png if filename.endswith('.png') else b'{}')
(bundle / 'metadata.json').write_text(json.dumps({'schema_version': 1, 'import': {'filter': 'nearest', 'pivot_px_from_top_left': [16,30]}}))
(bundle / 'validation.json').write_text(json.dumps({'passed': 'true' if mode == 'truthy' else mode != 'rejected'}))
if mode == 'traversal': files['sprite'] = '../asset.png'
if mode == 'symlink':
    (bundle / 'asset.png').unlink()
    (bundle / 'asset.png').symlink_to(bundle / 'preview.png')
if mode == 'failed': sys.exit(3)
print(json.dumps({'schema_version': 2 if mode == 'version' else 1, 'status': 'ready', 'files': files}))
''')
        script.chmod(0o755)
        return script

    def test_real_cli_import_from_foreign_directory_and_refuse_overwrite(self):
        cli = self.real_cli()
        result = self.invoke(cli, self.draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'imported')
        self.assertEqual(json.loads(result.stdout)['import']['pivot_px_from_top_left'], [16, 30])
        accepted = self.destination.read_bytes()
        self.assertTrue(accepted.startswith(b'\x89PNG\r\n\x1a\n'))
        result = self.invoke(cli, self.draft)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.destination.read_bytes(), accepted)

    def test_real_cli_rejected_request_never_imports(self):
        self.request.write_text(json.dumps({'schema_version': 1, 'kind': 'invalid', 'prompt': 'invalid'}))
        result = self.invoke(self.real_cli(), self.draft)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.destination.exists())

    def test_rejected_or_malformed_bundles_never_import(self):
        cli = self.fake_cli()
        for mode in ('rejected', 'truthy', 'version', 'traversal', 'symlink', 'failed'):
            with self.subTest(mode=mode):
                result = self.invoke(cli, mode=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.destination.exists())

    def test_validation_failure_preserves_existing_art(self):
        self.destination.write_bytes(b'accepted art')
        result = self.invoke(self.fake_cli(), mode='rejected')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.destination.read_bytes(), b'accepted art')

    def test_missing_source_never_starts_generation(self):
        result = self.invoke(self.fake_cli())
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.destination.exists())

    def test_explicit_codex_mode_is_forwarded(self):
        result = self.invoke(self.fake_cli(), "--codex", mode='no_draft')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
