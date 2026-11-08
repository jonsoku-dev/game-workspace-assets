import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_asset_pipeline import action_set
from pixel_asset_pipeline.bundle import publish
from pixel_asset_pipeline.cli import main


class ActionSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGBA', (8, 8), (0, 0, 255, 255)).save(self.root / 'pose.png')
        self.request = {'schema_version': 1, 'cell_size': [8, 8], 'pivot_px_from_top_left': [4, 7],
                        'actions': {name: {'loop': loop, 'frames': [
                            {'path': 'pose.png', 'duration_ms': 30},
                            {'path': 'pose.png', 'duration_ms': 70}]} for name, loop in action_set.ACTIONS.items()}}
        fx = Image.new('RGBA', (4, 2), (255, 0, 0, 255))
        fx.paste((0, 255, 0, 255), (2, 0, 4, 2))
        fx.save(self.root / 'fx.png')
        meta = {'frames': [{'frame': {'x': i * 2, 'y': 0, 'w': 2, 'h': 2}, 'duration': ms,
                            'rotated': False, 'trimmed': False} for i, ms in enumerate([20, 40])],
                'meta': {'image': 'fx.png', 'pixelfx': {'frameSize': [2, 2], 'pivot': [1, 2], 'frames': 2, 'loop': False}}}
        (self.root / 'fx.json').write_text(json.dumps(meta))
        (self.root / 'LICENSE').write_text('MIT example source license')
        (self.root / 'NOTICE').write_text('Source provenance')
        self.event = {'action': 'attack', 'frame': 1, 'sheet': 'fx.png', 'metadata': 'fx.json',
                      'license': 'LICENSE', 'notice': 'NOTICE', 'at_px': [5, 3], 'effect_anchor_px': [1, 1]}

    def build(self, request=None):
        path = self.root / 'request.json'
        path.write_text(json.dumps(request or self.request))
        return publish(self.root / 'out', action_set.produce, path)

    def test_atlas_events_credits_and_composite_preview(self):
        self.request['events'] = [self.event]
        result = self.build()
        self.assertEqual(result['status'], 'ready')
        out = self.root / 'out'
        meta = json.loads((out / result['files']['metadata']).read_text())
        event = meta['events'][0]
        self.assertEqual(event['start_ms'], 30)
        self.assertEqual(event['duration_ms'], 60)
        self.assertEqual(event['pivot_px_from_top_left'], [1, 2])
        self.assertEqual(event['effect_anchor_px'], [1, 1])
        self.assertEqual([f['duration_ms'] for f in event['frames']], [20, 40])
        self.assertEqual(meta['actions']['attack']['frames'][1]['rect'], {'x': 8, 'y': 24, 'w': 8, 'h': 8})
        self.assertEqual(meta['actions']['idle']['frames'][0]['source']['sha256'],
                         meta['actions']['hurt']['frames'][1]['source']['sha256'])
        with Image.open(out / 'atlas.png') as atlas:
            self.assertEqual(atlas.size, (16, 48))
            self.assertEqual(atlas.getpixel((8, 24)), (0, 0, 255, 255))
        self.assertEqual((out / 'effect-0-LICENSE').read_text(), 'MIT example source license')
        self.assertEqual(json.loads((out / 'effect-0.json').read_text())['meta']['image'], 'effect-0.png')
        self.assertEqual(len(json.loads((out / 'credits.json').read_text())['effects']), 1)
        with Image.open(out / 'preview.gif') as gif:
            colors, durations = [], []
            for i in range(gif.n_frames):
                gif.seek(i)
                # Sprite contact is (5,3), effect anchor (1,1), 12px label area, 4x preview.
                colors.append(gif.convert('RGB').getpixel((4 * 4, (12 + 2) * 4)))
                durations.append(gif.info['duration'])
            self.assertIn((255, 0, 0), colors)
            self.assertIn((0, 255, 0), colors)
            self.assertIn(20, durations)
            self.assertEqual(sum(durations), 600)

    def test_more_than_64_effect_frames_and_pre_crop_budget(self):
        path = self.root / 'fx.json'
        meta = json.loads(path.read_text())
        meta['frames'] = [copy.deepcopy(meta['frames'][0]) for _ in range(91)]
        meta['meta']['pixelfx']['frames'] = 91
        for frame in meta['frames']:
            frame['duration'] = 10
        path.write_text(json.dumps(meta))
        stage = self.root / 'stage'
        stage.mkdir()
        with self.assertRaisesRegex(ValueError, 'pixel budget'):
            action_set.load_effect(self.event, self.root, 0, stage, pixel_budget=363)
        self.assertEqual(list(stage.iterdir()), [])
        self.request['events'] = [self.event]
        self.build()
        result = json.loads((self.root / 'out' / 'action-set.json').read_text())
        self.assertEqual(len(result['events'][0]['frames']), 91)
        self.assertEqual(result['events'][0]['duration_ms'], 910)

    def test_preview_loop_survival_and_newest_contact_retrigger(self):
        path = self.root / 'fx.json'
        meta = json.loads(path.read_text())
        meta['frames'][1]['duration'] = 180
        path.write_text(json.dumps(meta))
        self.request['events'] = [{**self.event, 'action': 'idle'}]
        self.build()
        with Image.open(self.root / 'out' / 'preview.gif') as gif:
            intervals = []
            elapsed = 0
            for i in range(gif.n_frames):
                gif.seek(i)
                stop = elapsed + gif.info['duration']
                intervals.append((elapsed, stop, gif.convert('RGB').getpixel((16, 56))))
                elapsed = stop
        for timestamp in (99, 100, 129):
            self.assertEqual(next(color for start, stop, color in intervals if start <= timestamp < stop),
                             (0, 255, 0))
        self.assertEqual(next(color for start, stop, color in intervals if start <= 130 < stop),
                         (255, 0, 0))

    def test_tiny_loop_long_tail_is_rejected_before_boundary_expansion(self):
        self.request['actions']['idle']['frames'] = [{'path': 'pose.png', 'duration_ms': 1}]
        path = self.root / 'fx.json'
        meta = json.loads(path.read_text())
        meta['frames'][1]['duration'] = 60000
        path.write_text(json.dumps(meta))
        self.request['events'] = [{**self.event, 'action': 'idle', 'frame': 0}]
        with self.assertRaisesRegex(ValueError, 'frame budget'):
            self.build()
        self.assertFalse((self.root / 'out').exists())

    def test_cli_and_new_output_safety(self):
        request = self.root / 'request.json'
        request.write_text(json.dumps(self.request))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(['action-set', '--request', str(request), '--out', str(self.root / 'out')]), 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(set(result['files']), {'atlas', 'metadata', 'preview', 'credits'})
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.build()
        self.assertTrue((self.root / 'out' / 'atlas.png').exists())

    def test_invalid_requests_leave_no_bundle(self):
        cases = []
        for field, value in [('cell_size', [10000, 10000]), ('pivot_px_from_top_left', [True, 0]), ('events', [self.event] * 9)]:
            request = copy.deepcopy(self.request)
            request[field] = value
            cases.append(request)
        for key, value in [('loop', True), ('frames', [{'path': '../outside.png', 'duration_ms': 10}]),
                           ('frames', [{'path': 'pose.png', 'duration_ms': True}]), ('frames', []),
                           ('frames', [{'path': 'pose.png', 'duration_ms': 60000}] * 64)]:
            request = copy.deepcopy(self.request)
            request['actions']['attack'][key] = value
            cases.append(request)
        request = copy.deepcopy(self.request)
        del request['actions']['hurt']
        cases.append(request)
        for request in cases:
            with self.subTest(request=request):
                with self.assertRaises((ValueError, OSError)):
                    self.build(request)
                self.assertFalse((self.root / 'out').exists())

    def test_effect_bounds_contact_and_trim_validation(self):
        self.request['events'] = [self.event]
        for field, value in [('frame', 2), ('at_px', [-1, 2]), ('effect_anchor_px', [3, 0]), ('action', [])]:
            request = copy.deepcopy(self.request)
            request['events'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(request)
        metadata = self.root / 'fx.json'
        source = json.loads(metadata.read_text())
        source['frames'][0]['trimmed'] = True
        metadata.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, 'trimmed'):
            self.build()
        self.assertFalse((self.root / 'out').exists())

    def test_symlink_escape_and_oversized_request(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / 'pose.png'
            Image.new('RGBA', (8, 8)).save(outside)
            (self.root / 'escape.png').symlink_to(outside)
            self.request['actions']['idle']['frames'][0]['path'] = 'escape.png'
            with self.assertRaisesRegex(ValueError, 'within'):
                self.build()
        request = self.root / 'big.json'
        request.write_text(' ' * 1_048_577)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            publish(self.root / 'out', action_set.produce, request)


if __name__ == '__main__':
    unittest.main()
