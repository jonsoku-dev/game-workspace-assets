import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import threading
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from pixel_asset_pipeline import action_set, effect_clip
from pixel_asset_pipeline.action_set import digest
from pixel_asset_pipeline.bundle import publish


class EffectClipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        frames = []
        for color in ('red', 'green', 'blue'):
            image = Image.new('RGB', (8, 8), 'white')
            draw = ImageDraw.Draw(image)
            draw.rectangle((1, 1, 6, 6), fill=color)
            draw.rectangle((3, 3, 4, 4), fill='white')
            frames.append(image)
        frames[0].save(self.root / 'source.gif', save_all=True, append_images=frames[1:],
                       duration=[20, 30, 40], disposal=[1, 2, 3], optimize=True)
        (self.root / 'LICENSE').write_text('Synthetic test fixture; created locally for this test.')
        (self.root / 'NOTICE').write_text('No external artwork or claimed third-party license.')
        self.request = {
            'schema_version': 1, 'source': 'source.gif', 'actor_cell_size': [8, 8],
            'effect_size': [8, 8], 'pivot_px_from_top_left': [4, 4],
            'background': {'mode': 'edge-color', 'color': '#ffffff'},
            'phases': {name: [{'frame': i, 'duration_ms': 25 + i * 10}]
                       for i, name in enumerate(effect_clip.PHASES)},
            'license': 'LICENSE', 'notice': 'NOTICE'}

    def build(self, request=None, name='out'):
        path = self.root / 'request.json'
        path.write_text(json.dumps(self.request if request is None else request))
        return publish(self.root / name, effect_clip.produce, path)

    def test_real_gif_keying_order_duration_provenance_and_determinism(self):
        before = digest(self.root / 'source.gif')
        self.request['phases']['charge'][0]['frame'] = 2
        result = self.build()
        out = self.root / 'out'
        self.assertEqual(digest(self.root / 'source.gif'), before)
        meta = json.loads((out / 'sheet.json').read_text())
        self.assertEqual([f['duration'] for f in meta['frames']], [25, 35, 45])
        self.assertEqual(meta['meta']['pixelfx']['pivot'], [4, 4])
        self.assertEqual([t['name'] for t in meta['meta']['frameTags']], list(effect_clip.PHASES))
        with Image.open(out / 'sheet.png') as sheet:
            self.assertEqual(sheet.getpixel((0, 0))[3], 0)
            self.assertEqual(sheet.getpixel((3, 3)), (255, 255, 255, 255))
            self.assertEqual(sheet.getpixel((1, 1)), (0, 0, 255, 255))
        source = json.loads((out / 'effect-clip.json').read_text())
        self.assertEqual(source['source']['source']['sha256'], before)
        self.assertEqual([f['disposal'] for f in source['source_frames']], [1, 2, 3])
        for entry in source['artifacts'].values():
            self.assertEqual(digest(out / entry['path']), entry['sha256'])
        self.assertEqual(source['review']['status'], 'pending')
        self.build(name='second')
        for filename in result['files'].values():
            self.assertEqual((out / filename).read_bytes(), (self.root / 'second' / filename).read_bytes())

    def test_nearest_scale_and_existing_transparency_with_composited_disposal(self):
        palette = [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 12)
        frames = []
        for i in range(3):
            frame = Image.new('P', (8, 8), 0)
            frame.putpalette(palette)
            frame.putpixel((i + 1, 1), i + 1)
            frames.append(frame)
        frames[0].save(self.root / 'source.gif', save_all=True, append_images=frames[1:],
                       transparency=0, disposal=[1, 2, 3], optimize=False, duration=20)
        self.request['background'] = {'mode': 'preserve'}
        self.request['effect_size'] = [16, 16]
        self.request['pivot_px_from_top_left'] = [8, 8]
        self.build()
        with Image.open(self.root / 'out' / 'sheet.png') as sheet:
            self.assertEqual(sheet.getpixel((2, 2)), (255, 0, 0, 255))
            self.assertEqual(sheet.getpixel((3, 3)), (255, 0, 0, 255))
            self.assertEqual(sheet.getpixel((16 + 2, 2)), (255, 0, 0, 255))
            self.assertEqual(sheet.getpixel((16 + 4, 2)), (0, 255, 0, 255))
            self.assertEqual(sheet.getpixel((32 + 4, 2))[3], 0)
            self.assertEqual(sheet.getpixel((32 + 6, 2)), (0, 0, 255, 255))

    def test_action_set_import_and_composite_preview(self):
        self.build()
        Image.new('RGBA', (8, 8), '#808080').save(self.root / 'pose.png')
        request = {'schema_version': 1, 'cell_size': [8, 8], 'pivot_px_from_top_left': [4, 4],
                   'actions': {name: {'loop': loop, 'frames': [{'path': 'pose.png', 'duration_ms': 120}]}
                               for name, loop in action_set.ACTIONS.items()},
                   'events': [{'action': 'attack', 'frame': 0, 'sheet': 'out/sheet.png',
                               'metadata': 'out/sheet.json', 'license': 'out/LICENSE',
                               'notice': 'out/NOTICE', 'at_px': [4, 4]}]}
        path = self.root / 'actions.json'
        path.write_text(json.dumps(request))
        publish(self.root / 'actions', action_set.produce, path)
        data = json.loads((self.root / 'actions' / 'action-set.json').read_text())
        self.assertEqual(data['events'][0]['duration_ms'], 105)
        self.assertEqual(data['events'][0]['source']['sheet']['sha256'], digest(self.root / 'out' / 'sheet.png'))
        colors = set()
        with Image.open(self.root / 'actions' / 'preview.gif') as preview:
            for i in range(preview.n_frames):
                preview.seek(i)
                colors.update(color for _, color in preview.convert('RGB').getcolors(preview.width * preview.height))
        self.assertTrue({(255, 0, 0), (0, 128, 0), (0, 0, 255)} <= colors)

    def test_concurrent_source_swap_uses_snapshot_for_decode_hash_and_credits(self):
        originals = {name: (self.root / name).read_bytes()
                     for name in ('source.gif', 'LICENSE', 'NOTICE')}
        expected_request = json.dumps(self.request).encode('utf-8')
        decoding, swapped = threading.Event(), threading.Event()
        image_open = Image.open

        def replace_inputs():
            if not decoding.wait(5):
                raise AssertionError('decoder did not reach snapshot barrier')
            for name in originals:
                (self.root / name).write_bytes(b'replaced while decoding')
            (self.root / 'request.json').write_bytes(b'replaced request')
            swapped.set()

        def open_after_swap(fp, *args, **kwargs):
            if isinstance(fp, io.BytesIO):
                decoding.set()
                if not swapped.wait(5):
                    raise AssertionError('concurrent replacement did not finish')
            return image_open(fp, *args, **kwargs)

        with ThreadPoolExecutor(max_workers=1) as pool:
            replacement = pool.submit(replace_inputs)
            with patch.object(effect_clip.Image, 'open', side_effect=open_after_swap):
                self.build()
            replacement.result(timeout=5)
        out = self.root / 'out'
        data = json.loads((out / 'effect-clip.json').read_text())
        self.assertEqual(data['request_sha256'], hashlib.sha256(expected_request).hexdigest())
        for key, name in [('source', 'source.gif'), ('license', 'LICENSE'), ('notice', 'NOTICE')]:
            self.assertEqual(data['source'][key]['sha256'], hashlib.sha256(originals[name]).hexdigest())
        self.assertEqual((out / 'LICENSE').read_bytes(), originals['LICENSE'])
        self.assertEqual((out / 'NOTICE').read_bytes(), originals['NOTICE'])
        with Image.open(out / 'sheet.png') as sheet:
            self.assertEqual(sheet.getpixel((1, 1)), (255, 0, 0, 255))
        self.assertNotEqual(digest(self.root / 'source.gif'), data['source']['source']['sha256'])

    def test_empty_clip_rejected_but_intentional_empty_frame_preserved(self):
        blank = Image.new('RGB', (8, 8), 'white')
        blank.save(self.root / 'source.gif')
        for entries in self.request['phases'].values():
            entries[0]['frame'] = 0
        with self.assertRaisesRegex(ValueError, 'fully invisible'):
            self.build()
        self.assertFalse((self.root / 'out').exists())
        visible = blank.copy()
        visible.putpixel((2, 2), (255, 0, 0))
        blank.save(self.root / 'source.gif', save_all=True, append_images=[visible],
                   duration=[20, 20], disposal=2)
        self.request['phases']['impact'][0]['frame'] = 1
        self.build()
        with Image.open(self.root / 'out' / 'sheet.png') as sheet:
            self.assertIsNone(sheet.crop((0, 0, 8, 8)).getchannel('A').getbbox())
            self.assertEqual(sheet.getpixel((18, 2)), (255, 0, 0, 255))

    def test_snapshot_caps_actual_reads_despite_stale_size_check(self):
        local_path = effect_clip.local_path

        def grow_after_stat(root, value):
            path = local_path(root, value)
            if value == 'NOTICE':
                (self.root / 'LICENSE').write_bytes(b'x' * 1_048_577)
            return path

        with patch.object(effect_clip, 'local_path', side_effect=grow_after_stat):
            with self.assertRaisesRegex(ValueError, 'license exceeds 1 MiB'):
                self.build()
        self.assertFalse((self.root / 'out').exists())

    def test_invalid_inputs_do_not_publish(self):
        cases = []
        for key, value in [('source', '../source.gif'), ('effect_size', [8, 7]),
                           ('effect_size', [513, 513]), ('background', {'mode': 'auto'}),
                           ('background', {'mode': 'preserve'}), ('actor_cell_size', [True, 8]),
                           ('pivot_px_from_top_left', [9, 0])]:
            data = copy.deepcopy(self.request)
            data[key] = value
            cases.append(data)
        for key, value in [('frame', 3), ('frame', True), ('duration_ms', 0), ('duration_ms', True)]:
            data = copy.deepcopy(self.request)
            data['phases']['charge'][0][key] = value
            cases.append(data)
        data = copy.deepcopy(self.request)
        data['phases']['travel'] *= 64
        cases.append(data)
        for request in cases:
            with self.subTest(request=request), self.assertRaises((ValueError, OSError)):
                self.build(request)
            self.assertFalse((self.root / 'out').exists())

    def test_decoding_and_input_budgets(self):
        self.request['effect_size'] = [4, 4]
        self.request['pivot_px_from_top_left'] = [2, 2]
        with patch.object(effect_clip, 'MAX_DECODE_PIXELS', 128):
            with self.assertRaisesRegex(ValueError, 'decoded pixel budget'):
                self.build()
        with patch.object(effect_clip, 'MAX_SOURCE_FRAMES', 2):
            # Use only in-range selections so failure occurs during decode.
            self.request['phases']['impact'][0]['frame'] = 0
            with self.assertRaisesRegex(ValueError, 'source frames'):
                self.build()
        self.assertFalse((self.root / 'out').exists())
        (self.root / 'request.json').write_text(' ' * 1_048_577)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            publish(self.root / 'out', effect_clip.produce, self.root / 'request.json')


if __name__ == '__main__':
    unittest.main()
