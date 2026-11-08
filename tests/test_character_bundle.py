import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from pixel_asset_pipeline import character
from pixel_asset_pipeline.bundle import publish


class CharacterBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cels = self.root / 'painted'
        self.cels.mkdir()
        for color in ('red', 'blue'):
            Image.new('RGBA', (12, 12), color).save(self.cels / (color + '.png'))
        self.manifest = {'schema_version': 1, 'size': [12, 12], 'actions': {
            'unselected': {'loop': False, 'frames': [{'path': '../outside.png', 'duration_ms': 10}]},
            'step': {'loop': True, 'frames': [{'path': 'blue.png', 'duration_ms': 71},
                                               {'path': 'red.png', 'duration_ms': 99}]},
            'hello': {'loop': False, 'frames': [{'path': 'red.png', 'duration_ms': 213}]}}}
        self.request = {'schema_version': 1, 'frames': 'painted/order.json', 'actions': ['hello', 'step'],
                        'title': '私の絵', 'language': 'ja'}

    def build(self):
        (self.cels / 'order.json').write_text(json.dumps(self.manifest))
        path = self.root / 'request.json'
        path.write_text(json.dumps(self.request))
        publish(self.root / 'output', character.produce, path)
        return self.root / 'output'

    def test_render_exact_authored_cels_without_rigging_or_unselected_files(self):
        out = self.build()
        meta = json.loads((out / 'rive.json').read_text())
        report = json.loads((out / 'character.json').read_text())
        self.assertEqual(report['mode'], 'drawn-frames')
        self.assertEqual([s['name'] for s in meta['states']], ['hello', 'step'])
        digest = hashlib.sha256((self.cels / 'red.png').read_bytes()).hexdigest()
        self.assertEqual(meta['states'][0]['frames'][0]['sha256'], digest)
        self.assertEqual(meta['states'][0]['duration_ms'], 213)
        self.assertEqual([s['value'] for s in meta['states']], [0, 1])
        self.assertTrue((out / 'player.html').is_file())
        self.assertFalse((out / 'motion.request.json').exists())
        self.assertEqual([p['path'] for p in report['inputs']],
                         ['painted/order.json', 'painted/red.png', 'painted/blue.png'])

    def test_reference_and_selected_cel_share_one_media_snapshot(self):
        self.request['reference'] = 'painted/red.png'
        # One legal 16 MiB PNG is still below the 32 MiB total when reused.
        path = self.cels / 'red.png'
        with path.open('ab') as stream:
            stream.truncate(16_777_216)
        out = self.build()
        report = json.loads((out / 'character.json').read_text())
        self.assertEqual(sum(pin['path'] == 'painted/red.png' for pin in report['inputs']), 1)
        self.assertTrue((out / 'reference.png').is_file())

    def test_invalid_or_escaping_selected_input_publishes_nothing(self):
        self.request['actions'] = ['unselected']
        with self.assertRaises((OSError, ValueError)):
            self.build()
        self.assertFalse((self.root / 'output').exists())

    def test_valid_source_with_unsupported_silhouette_leaves_only_review_material(self):
        im = Image.new('RGBA', (24, 24))
        im.paste('red', (8, 4, 15, 20))
        im.save(self.root / 'bar.png')
        self.request = {'schema_version': 1, 'source': 'bar.png', 'actions': ['wave']}
        out = self.build()
        report = json.loads((out / 'character.json').read_text())
        self.assertEqual(report['status'], 'needs_review')
        self.assertTrue(report['reason'])
        self.assertTrue((out / 'master.png').is_file())
        self.assertFalse((out / 'character.riv').exists())
