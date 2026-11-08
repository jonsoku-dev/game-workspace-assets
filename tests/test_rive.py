import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, PngImagePlugin

from pixel_asset_pipeline.bundle import publish
from pixel_asset_pipeline.rive import produce


class RiveExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.request = self.root / 'poses.json'
        self.data = {'schema_version': 1, 'cell_size': [8, 8], 'pivot_px_from_top_left': [4, 8],
                     'events': [], 'actions': {'walk': {'loop': True, 'frames': [
                         {'path': 'one.png', 'duration_ms': 141}]}}}
        info = PngImagePlugin.PngInfo()
        info.add_text('comment', 'private source annotation')
        Image.new('RGBA', (8, 8), 'green').save(self.root / 'one.png', pnginfo=info)

    def export(self):
        self.request.write_text(json.dumps(self.data))
        return publish(self.root / 'out', produce, self.request)

    def test_motion_request_preserves_state_and_input_hash_without_private_png_text(self):
        self.export()
        out = self.root / 'out'
        data = (out / 'character.riv').read_bytes()
        receipt = json.loads((out / 'rive.json').read_text())
        self.assertNotIn(b'private source annotation', data)
        self.assertEqual(receipt['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt['states'][0]['value'], 0)
        self.assertEqual(receipt['states'][0]['duration_ms'], 141)
        self.assertEqual(receipt['states'][0]['frames'][0]['sha256'],
                         hashlib.sha256((self.root / 'one.png').read_bytes()).hexdigest())

    def test_effect_events_and_mismatched_frames_do_not_publish_a_partial_character(self):
        self.data['events'] = [{'frame': 0}]
        with self.assertRaisesRegex(ValueError, 'effect events'):
            self.export()
        self.data['events'] = []
        self.data['cell_size'] = [8, 9]
        with self.assertRaisesRegex(ValueError, 'canvas size'):
            self.export()
        self.assertFalse((self.root / 'out').exists())
