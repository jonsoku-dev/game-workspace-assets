import copy
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from pixel_asset_pipeline import action_set, motion
from pixel_asset_pipeline.bundle import publish
from pixel_asset_pipeline.cli import main


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        image = Image.new('RGBA', (48, 48))
        draw = ImageDraw.Draw(image)
        rectangles = [('body', 'torso', None, [24, 24], [21, 18, 7, 13]),
                      ('head', 'head', 'body', [24, 18], [20, 11, 9, 7]),
                      ('left', 'arm_left', 'body', [20, 20], [17, 20, 4, 11]),
                      ('right', 'arm_right', 'body', [28, 20], [28, 20, 4, 11]),
                      ('legl', 'leg_left', None, [23, 31], [21, 31, 3, 10]),
                      ('legr', 'leg_right', None, [26, 31], [25, 31, 3, 10])]
        parts = []
        for i, (pid, role, parent, anchor, rect) in enumerate(rectangles):
            x, y, w, h = rect
            draw.rectangle((x, y, x+w-1, y+h-1), fill=(40+i*25, 100, 180, 255))
            parts.append(dict(id=pid, role=role, parent=parent, anchor_px=anchor, rect=rect))
        image.save(self.root / 'master.png')
        self.request = dict(schema_version=1, approved=True, master='master.png',
                            pivot_px_from_top_left=[24, 41], rig={'parts': parts})

    def build(self, name='out', request=None):
        path = self.root / f'{name}.json'
        path.write_text(json.dumps(self.request if request is None else request))
        return publish(self.root / name, motion.produce, path)

    def test_cli_and_followup_action_set_palette_identity_and_metrics(self):
        path = self.root / 'request.json'
        path.write_text(json.dumps(self.request))
        before = (self.root / 'master.png').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['motion', '--request', str(path), '--out', str(self.root / 'out')]), 0)
        out = self.root / 'out'
        report = json.loads((out / 'inspection.json').read_text())
        self.assertEqual(report['artistic_acceptance'], 'unverified')
        self.assertTrue(report['passed'])
        self.assertEqual(before, (self.root / 'master.png').read_bytes())
        with Image.open(out / 'neutral.png') as neutral, Image.open(self.root / 'master.png') as master:
            self.assertEqual(neutral.tobytes(), master.tobytes())
            palette = {color for _, color in master.getcolors(48 * 48)}
        for name, action in report['actions'].items():
            self.assertGreater(action['unique_poses'], 1)
            with Image.open(out / f'{name}-01.png') as frame:
                self.assertLessEqual({color for _, color in frame.getcolors(48 * 48)}, palette)
        result = publish(self.root / 'packed', action_set.produce, out / 'action-set.request.json')
        self.assertEqual(result['status'], 'ready')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            publish(out, motion.produce, path)

    def test_targeted_attack_override_and_contact_measurement(self):
        self.build('first')
        request = copy.deepcopy(self.request)
        request['actions'] = {'attack': {'frames': [
            {'duration_ms': 50, 'parts': {'left': {'angle_deg': -45}}, 'contacts': {'left': [20, 20]}},
            {'duration_ms': 200, 'parts': {'left': {'angle_deg': 90}}}]}}
        self.build('second', request)
        for name in ('idle', 'walk', 'run', 'jump', 'hurt'):
            self.assertEqual((self.root/'first'/f'{name}-01.png').read_bytes(),
                             (self.root/'second'/f'{name}-01.png').read_bytes())
        report = json.loads((self.root/'second'/'inspection.json').read_text())
        self.assertEqual(report['actions']['attack']['frames'][0]['contact_error_px']['left'], [0, 0])
        self.assertNotEqual((self.root/'first'/'attack-01.png').read_bytes(),
                            (self.root/'second'/'attack-01.png').read_bytes())

    def test_negative_contracts_are_atomic(self):
        cases = []
        request = copy.deepcopy(self.request); request['approved'] = False; cases.append(request)
        request = copy.deepcopy(self.request); request['master'] = '../escape.png'; cases.append(request)
        request = copy.deepcopy(self.request); request['rig']['parts'][1]['parent'] = 'head'; cases.append(request)
        request = copy.deepcopy(self.request); request['rig']['parts'][0]['rect'] = [0, 0, 48, 48]; cases.append(request)
        request = copy.deepcopy(self.request); request['rig']['parts'].pop(); cases.append(request)
        request = copy.deepcopy(self.request); request['actions'] = {'attack': {'frames': [{'duration_ms': 1}, {'duration_ms': 1}]}}; cases.append(request)
        request = copy.deepcopy(self.request); request['actions'] = {'attack': {'frames': [{'duration_ms': 1, 'parts': {'left': {'angle_deg': float('nan')}}}, {'duration_ms': 1}]}}; cases.append(request)
        for index, request in enumerate(cases):
            with self.subTest(index=index), self.assertRaises((ValueError, OSError)):
                self.build(f'bad{index}', request)
            self.assertFalse((self.root / f'bad{index}').exists())

    def test_clipping_holds_and_foot_landmark_are_measured(self):
        request = copy.deepcopy(self.request)
        request['rig']['parts'][4]['contact_px'] = [23, 40]
        request['actions'] = {'attack': {'frames': [
            {'duration_ms': 120, 'contacts': {'legl': [23, 40]}},
            {'duration_ms': 120, 'hold': True},
            {'duration_ms': 120, 'root_offset_px': [32, 0],
             'parts': {'left': {'angle_deg': 90}}}]}}
        self.build(request=request)
        report = json.loads((self.root/'out'/'inspection.json').read_text())
        action = report['actions']['attack']
        self.assertEqual(action['frames'][0]['contact_points_px']['legl'], [23, 40])
        self.assertEqual(action['frames'][0]['contact_error_px']['legl'], [0, 0])
        self.assertEqual(action['duplicate_frames'], [1])
        self.assertEqual(action['unmarked_adjacent_duplicates'], [])
        self.assertGreater(action['frames'][2]['clipped_part_pixels'], 0)
        self.assertFalse(report['passed'])
        self.assertEqual(report['technical_status'], 'needs-clipping-review')

    def test_review_artifacts_show_declared_measurements_without_inferred_feet(self):
        request = copy.deepcopy(self.request)
        request['rig']['parts'][4]['contact_px'] = [23, 40]
        request['actions'] = {'attack': {'frames': [
            {'duration_ms': 80, 'contacts': {'legl': [24, 40], 'left': [20, 20]}},
            {'duration_ms': 120, 'root_offset_px': [32, 0],
             'parts': {'left': {'angle_deg': 90}}, 'contacts': {'legl': [23, 40]}}]}}
        result = self.build('review', request)
        files = result['files']
        report = json.loads((self.root/'review'/'inspection.json').read_text())
        measured = report['actions']['attack']['frames'][0]['contact_measurements']
        self.assertEqual(measured['legl'], {'target_px': [24, 40], 'measured_px': [23, 40],
                         'delta_px': [-1, 0], 'distance_px': 1.0, 'landmark': 'contact_px'})
        self.assertEqual(measured['left']['landmark'], 'anchor_px')
        self.assertEqual(report['actions']['walk']['frames'][0]['contact_measurements'], {})
        self.assertGreater(report['actions']['attack']['frames'][1]['clipped_part_pixels'], 0)
        self.assertEqual(report['visual_review'], 'unverified')
        self.assertEqual(report['artistic_acceptance'], 'unverified')
        for key in ('master', 'rig_preview', 'motion_qa'):
            self.assertEqual(report['review_files'][key], files[key])
            with Image.open(self.root/'review'/files[key]) as preview:
                self.assertEqual(preview.format, 'PNG')
                if key == 'master':
                    with Image.open(self.root/'master.png') as original:
                        self.assertEqual(preview.size, original.size)
                        self.assertEqual(preview.tobytes(), original.tobytes())
                else:
                    self.assertGreater(preview.width, 48)
                    self.assertGreater(preview.height, 48)
                    if key == 'motion_qa':
                        self.assertIn((255, 142, 127), {color for _, color in preview.getcolors(65536)})

    def test_joint_nudge_changes_diagram_and_pose_without_changing_master(self):
        self.build('a')
        request = copy.deepcopy(self.request)
        request['rig']['parts'][3]['anchor_px'][0] += 1
        self.build('b', request)
        self.assertEqual((self.root/'a'/'master.png').read_bytes(), (self.root/'b'/'master.png').read_bytes())
        self.assertEqual((self.root/'a'/'neutral.png').read_bytes(), (self.root/'b'/'neutral.png').read_bytes())
        self.assertNotEqual((self.root/'a'/'rig.png').read_bytes(), (self.root/'b'/'rig.png').read_bytes())
        self.assertNotEqual((self.root/'a'/'attack-01.png').read_bytes(), (self.root/'b'/'attack-01.png').read_bytes())
        self.assertNotEqual((self.root/'a'/'motion-qa.png').read_bytes(), (self.root/'b'/'motion-qa.png').read_bytes())
        self.build('repeat', request)
        for filename in ('master.png', 'rig.png', 'motion-qa.png'):
            self.assertEqual((self.root/'b'/filename).read_bytes(), (self.root/'repeat'/filename).read_bytes())

    def test_decoded_master_mask_and_request_keep_their_original_hashes_on_swap(self):
        request = copy.deepcopy(self.request)
        part = request['rig']['parts'][2]
        x, y, w, h = part.pop('rect')
        mask = Image.new('L', (48, 48))
        ImageDraw.Draw(mask).rectangle((x, y, x+w-1, y+h-1), fill=255)
        mask_path = self.root/'left-mask.png'
        mask.save(mask_path)
        part['mask'] = mask_path.name
        master_bytes = (self.root/'master.png').read_bytes()
        mask_bytes = mask_path.read_bytes()
        request_bytes = json.dumps(request).encode()
        original_open = motion.open_png
        calls = 0

        def swap_after_decode(source, *args, **kwargs):
            nonlocal calls
            image = original_open(source, *args, **kwargs)
            calls += 1
            if calls == 1:
                Image.new('RGBA', (48, 48), 'red').save(self.root/'master.png')
                (self.root/'race.json').write_text(json.dumps({**request, 'approved': False}))
            elif calls == 2:
                Image.new('L', (48, 48)).save(mask_path)
            return image

        with patch.object(motion, 'open_png', side_effect=swap_after_decode):
            self.build('race', request)
        report = json.loads((self.root/'race/inspection.json').read_text())
        self.assertEqual(report['source']['sha256'], hashlib.sha256(master_bytes).hexdigest())
        self.assertEqual(report['source']['request_sha256'], hashlib.sha256(request_bytes).hexdigest())
        self.assertEqual(report['rig'][2]['mask_sha256'], hashlib.sha256(mask_bytes).hexdigest())
        self.assertNotEqual(master_bytes, (self.root/'master.png').read_bytes())
        self.assertNotEqual(mask_bytes, mask_path.read_bytes())
        with Image.open(io.BytesIO(master_bytes)) as original, Image.open(self.root/'race/master.png') as generated:
            self.assertEqual(original.tobytes(), generated.tobytes())

    def test_mask_and_hierarchy(self):
        request = copy.deepcopy(self.request)
        part = request['rig']['parts'][2]
        x, y, w, h = part.pop('rect')
        mask = Image.new('L', (48, 48))
        ImageDraw.Draw(mask).rectangle((x, y, x+w-1, y+h-1), fill=255)
        mask.save(self.root / 'left-mask.png')
        part['mask'] = 'left-mask.png'
        self.build(request=request)
        report = json.loads((self.root/'out'/'inspection.json').read_text())
        self.assertNotEqual(report['actions']['attack']['frames'][1]['anchors_px']['left'], [20, 20])


if __name__ == '__main__':
    unittest.main()
