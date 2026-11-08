import json
import os
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline.asset_set import produce
from pixel_asset_pipeline.bundle import publish
from pixel_asset_pipeline.cli import build
from pixel_asset_pipeline.spec import Request


class AssetSetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        draft = self.root / 'draft.png'
        image = Image.new('RGBA', (16, 16))
        ImageDraw.Draw(image).rectangle((3, 3, 12, 12), fill='#335544')
        image.save(draft)
        spec = Request('icon', 'seed', 24, 12, ['#335544'], 'woodland', 'front', None)
        for name in ('one', 'two'):
            build(spec, self.root / name, draft)
        self.data = {'schema_version': 1, 'name': 'Woodland set', 'assets': [
            {'id': 'seed', 'label': 'Seed', 'bundle': 'one',
             'reference': {'path': 'one/asset.png', 'provenance': 'same-atlas-exemplar'}},
            {'id': 'other', 'label': 'Other', 'bundle': 'two'}]}
        self.request = self.root / 'set.json'
        self.output = self.root / 'comparison'

    def run_set(self):
        self.request.write_text(json.dumps(self.data))
        return publish(self.output, produce, self.request)

    def test_real_bundles_keep_pixels_provenance_and_duplicate_source_truth(self):
        result = self.run_set()
        manifest = json.loads((self.output / result['files']['manifest']).read_text())
        self.assertEqual(manifest['scales'], [1, 4])
        self.assertFalse(manifest['generation_executed'])
        self.assertEqual(manifest['distinct_source_count'], 1)
        self.assertEqual(manifest['visual_review'], 'pending')
        self.assertEqual(manifest['assets'][0]['reference']['role'], 'local-comparison-only')
        self.assertEqual(manifest['assets'][0]['declared_origin'], 'local-draft')
        with Image.open(self.output / result['files']['contact_sheet']) as sheet:
            # Native and four-fold opaque pixels are rendered without interpolation.
            with Image.open(self.root / 'one/asset.png') as sprite:
                for scale, x in ((1, 14), (4, 100)):
                    enlarged = sprite.resize((24 * scale, 24 * scale), Image.Resampling.NEAREST)
                    expected = Image.new('RGB', enlarged.size, '#ddd9cf')
                    expected.paste(enlarged, mask=enlarged)
                    actual = sheet.crop((x, 52, x + 24 * scale, 52 + 24 * scale))
                    self.assertEqual(actual.tobytes(), expected.tobytes())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_set()

    def test_local_workspace_alias_is_supported(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.request.write_text(json.dumps(self.data))
        result = publish(self.output, produce, alias / 'set.json')
        self.assertEqual(result['status'], 'ready')

    def test_rejects_stale_failed_or_mismatched_bundle_before_publish(self):
        path = self.root / 'one/validation.json'
        original = path.read_text()
        for value in ({'passed': False}, {'passed': True}, []):
            path.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'validation'):
                self.run_set()
            self.assertFalse(self.output.exists())
        path.write_text(original)
        Image.new('RGBA', (32, 32)).save(self.root / 'one/asset.png')
        with self.assertRaisesRegex(ValueError, 'validation'):
            self.run_set()

    def test_bounded_requests_and_safe_files(self):
        for update in ({'assets': self.data['assets'] * 7}, {'schema_version': True}, {'upload': True}):
            original = self.data.copy()
            self.data.update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.run_set()
            self.data = original
        source = self.root / 'one/asset.png'
        source.unlink()
        os.mkfifo(source)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.run_set()
        source.unlink()
        source.write_bytes(b'x' * (4 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, 'bounded'):
            self.run_set()

    def test_rejects_reference_size_mismatch_absolute_paths_and_bad_pivot(self):
        reference = self.data['assets'][0]['reference']
        Image.new('RGBA', (8, 8), '#335544').save(self.root / 'ref.png')
        reference['path'] = 'ref.png'
        with self.assertRaisesRegex(ValueError, 'native size'):
            self.run_set()
        reference['path'] = '/etc/passwd'
        with self.assertRaisesRegex(ValueError, 'relative'):
            self.run_set()
        del self.data['assets'][0]['reference']
        path = self.root / 'one/metadata.json'
        meta = json.loads(path.read_text())
        meta['import']['pivot_px_from_top_left'] = [0, 0]
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'pivot'):
            self.run_set()


if __name__ == '__main__':
    unittest.main()
