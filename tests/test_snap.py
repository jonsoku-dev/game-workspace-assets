"""Guided snapping preserves native cells and feeds the real motion producer."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFilter

from pixel_asset_pipeline import motion, snap
from pixel_asset_pipeline.bundle import publish

ROOT = Path(__file__).resolve().parents[1]


class SnapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with Image.open(ROOT / 'examples/production/motion/master.png') as source:
            self.master = source.convert('RGBA')
        # Original synthetic control, enlarged and softened to create subpixel edges.
        soft = self.master.resize((288, 288), Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(.7))
        for y in range(soft.height):
            for x in range(soft.width):
                r, g, b, a = soft.getpixel((x, y))
                if a:
                    soft.putpixel((x, y), (min(255, r+x%7), min(255, g+y%5), b, a))
        soft.save(self.root / 'soft.png')
        self.request = {'schema_version': 1, 'source': 'soft.png', 'crop': [0, 0, 288, 288],
                        'grid_size': [48, 48], 'max_colors': 8, 'alpha_cutoff': 128}

    def build(self, name='out', request=None):
        path = self.root / f'{name}.json'
        path.write_text(json.dumps(self.request if request is None else request))
        return publish(self.root / name, snap.produce, path)

    def test_soft_high_color_source_to_native_to_actual_motion(self):
        before = (self.root / 'soft.png').read_bytes()
        self.assertEqual(self.build()['status'], 'ready')
        self.assertEqual(before, (self.root / 'soft.png').read_bytes())
        report = json.loads((self.root / 'out/inspection.json').read_text())
        self.assertEqual(report['source']['sha256'], hashlib.sha256(before).hexdigest())
        self.assertGreater(report['source']['visible_rgb_color_count'], 64)
        self.assertGreater(report['source']['partial_alpha_pixel_count'], 0)
        self.assertLessEqual(report['output_visible_color_count'], 8)
        self.assertEqual(report['visual_review'], 'required')
        self.assertEqual(report['geometry']['cell_size_source_px'], [6, 6])
        with Image.open(self.root / 'out/asset.png') as image:
            self.assertEqual(image.size, (48, 48))
            self.assertEqual(set(image.getchannel('A').getextrema()), {0, 255})
            self.assertEqual(image.getchannel('A').tobytes(), self.master.getchannel('A').tobytes())
        for filename, size in [('comparison-native.png', (96, 48)), ('comparison.png', (768, 384))]:
            with Image.open(self.root / 'out' / filename) as image:
                self.assertEqual(image.size, size)
        rig = json.loads((ROOT / 'examples/production/motion/request.json').read_text())
        rig['master'] = 'out/asset.png'
        path = self.root / 'motion.json'
        path.write_text(json.dumps(rig))
        self.assertEqual(publish(self.root / 'animated', motion.produce, path)['status'], 'ready')
        check = json.loads((self.root / 'animated/inspection.json').read_text())
        self.assertTrue(check['neutral_exact_visible_reconstruction'])
        self.assertTrue(check['passed'])
        self.assertTrue(all(action['unique_poses'] > 1 for action in check['actions'].values()))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.build()

    def test_repeated_runs_are_deterministic(self):
        first, second = self.build('first'), self.build('second')
        self.assertEqual(first, second)
        for filename in first['files'].values():
            self.assertEqual((self.root / 'first' / filename).read_bytes(),
                             (self.root / 'second' / filename).read_bytes())

    def test_explicit_palette_keeps_outline_and_transparent_rgb_is_zero(self):
        image = Image.new('RGBA', (24, 24), (255, 0, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((4, 4, 19, 19), fill='#16191fff')
        draw.rectangle((8, 8, 15, 15), fill='#f0a63aff')
        image.save(self.root / 'outline.png')
        request = {**self.request, 'source': 'outline.png', 'crop': [0, 0, 24, 24],
                   'grid_size': [6, 6], 'palette': ['#16191f', '#f0a63a'], 'max_colors': 2}
        self.build(request=request)
        with Image.open(self.root / 'out/asset.png') as result:
            self.assertEqual(result.getpixel((1, 1)), (22, 25, 31, 255))
            self.assertEqual(result.getpixel((2, 2)), (240, 166, 58, 255))
            self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))

    def test_crop_offset_and_nonintegral_cell_geometry(self):
        image = Image.new('RGBA', (20, 20))
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 6, 10, 10), fill=(40, 80, 120, 255))
        image.save(self.root / 'offset.png')
        self.build(request={**self.request, 'source': 'offset.png', 'crop': [3, 3, 13, 13],
                            'grid_size': [5, 5]})
        report = json.loads((self.root / 'out/inspection.json').read_text())
        self.assertEqual(report['geometry']['cell_size_source_px'], [2.6, 2.6])
        with Image.open(self.root / 'out/asset.png') as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
            self.assertEqual(image.getpixel((1, 1)), (40, 80, 120, 255))

    def test_invalid_inputs_publish_nothing(self):
        bad_fields = [
            {'source': '../escape.png'}, {'crop': [-1, 0, 10, 10]},
            {'crop': [0, 0, 500, 500]}, {'crop': [0, 0, True, 10]},
            {'grid_size': [3, 48]}, {'grid_size': [129, 48]}, {'grid_size': [True, 48]},
            {'grid_size': [48]}, {'grid_size': [48, 48], 'crop': [0, 0, 12, 12]},
            {'alpha_cutoff': 0}, {'alpha_cutoff': True}, {'max_colors': 65},
            {'palette': ['bad']}, {'palette': ['#000000', '#000000']},
            {'unknown': 1}, {'schema_version': 2}]
        for index, changed in enumerate(bad_fields):
            with self.subTest(changed=changed), self.assertRaises((ValueError, OSError)):
                self.build(f'bad{index}', {**self.request, **changed})
            self.assertFalse((self.root / f'bad{index}').exists())

    def test_unusable_empty_opaque_single_cell_and_decode_caps(self):
        for name, image in [('empty', Image.new('RGBA', (48, 48))),
                            ('opaque', Image.new('RGBA', (48, 48), (20, 30, 40, 255))),
                            ('single', Image.new('RGBA', (48, 48)))]:
            if name == 'single':
                image.putpixel((24, 24), (20, 30, 40, 255))
            image.save(self.root / f'{name}.png')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'visible cells'):
                self.build(name, {**self.request, 'source': f'{name}.png', 'crop': [0, 0, 48, 48]})
            self.assertFalse((self.root / name).exists())
        Image.new('RGBA', (2049, 2049)).save(self.root / 'large.png')
        with self.assertRaisesRegex(ValueError, 'pixels'):
            self.build('large', {**self.request, 'source': 'large.png'})
        (self.root / 'broken.png').write_bytes(b'not a PNG')
        with self.assertRaises(OSError):
            self.build('broken', {**self.request, 'source': 'broken.png'})
        self.assertFalse((self.root / 'large').exists())
        self.assertFalse((self.root / 'broken').exists())
