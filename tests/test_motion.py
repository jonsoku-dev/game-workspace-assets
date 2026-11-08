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

    def extra_actions(self):
        return {
            'wave': {'loop': True, 'frames': [
                {'duration_ms': 80, 'parts': {'left': {'angle_deg': -80}, 'right': {'angle_deg': 20}}},
                {'duration_ms': 120, 'parts': {'left': {'angle_deg': -130}, 'right': {'angle_deg': 20}}},
                {'duration_ms': 80, 'parts': {'left': {'angle_deg': -80}, 'right': {'angle_deg': 20}}}]},
            'cheer': {'loop': False, 'frames': [
                {'duration_ms': 130, 'parts': {'left': {'angle_deg': -165}, 'right': {'angle_deg': 165}}},
                {'duration_ms': 160, 'root_offset_px': [0, -1],
                 'parts': {'left': {'angle_deg': -145}, 'right': {'angle_deg': 145}}}]}}

    def test_extra_actions_keep_core_contract_and_feed_rive_with_exact_poses(self):
        from pixel_asset_pipeline import rive

        self.build('base')
        request = copy.deepcopy(self.request)
        request['extra_actions'] = self.extra_actions()
        result = self.build('extra', request)
        out = self.root/'extra'
        expected_order = [*action_set.ACTIONS, 'wave', 'cheer']
        manifest_path = out/result['files']['rive_poses']
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(list(manifest['actions']), expected_order)
        self.assertEqual(manifest['cell_size'], [48, 48])
        self.assertEqual(manifest['pivot_px_from_top_left'], [24, 41])
        self.assertEqual(list(json.loads((out/'action-set.request.json').read_text())['actions']), list(action_set.ACTIONS))
        for filename in ('action-set.request.json', 'neutral.png', 'master.png', 'rig.png'):
            self.assertEqual((out/filename).read_bytes(), (self.root/'base'/filename).read_bytes())
        for name in action_set.ACTIONS:
            for path in (self.root/'base').glob(name+'-*.png'):
                self.assertEqual((out/path.name).read_bytes(), path.read_bytes())
        packed = publish(self.root/'packed-extra', action_set.produce, out/'action-set.request.json')
        self.assertEqual(packed['status'], 'ready')
        report = json.loads((out/'inspection.json').read_text())
        self.assertEqual(list(report['actions']), expected_order)
        self.assertIsInstance(report['actions']['wave']['loop_seam_changed_pixels'], int)
        self.assertIsNone(report['actions']['cheer']['loop_seam_changed_pixels'])
        self.assertEqual(report['actions']['wave']['duplicate_frames'], [2])
        self.assertEqual(report['visual_review'], 'unverified')
        self.assertEqual(report['artistic_acceptance'], 'unverified')
        with Image.open(self.root/'master.png') as master:
            parts = motion.load_rig(request, self.root, master)
            for name, action in request['extra_actions'].items():
                frames = motion.frames_for({'frames': action['frames']}, parts, master.size)
                self.assertEqual(manifest['actions'][name]['loop'], action['loop'])
                for index, frame in enumerate(frames):
                    expected, _ = motion.render(master, parts, frame)
                    entry = manifest['actions'][name]['frames'][index]
                    self.assertEqual(entry, {'path': f'{name}-{index:02}.png', 'duration_ms': frame['duration_ms']})
                    self.assertEqual(result['files'][f'{name}_{index}'], entry['path'])
                    with Image.open(out/entry['path']) as produced:
                        self.assertEqual(produced.tobytes(), expected.tobytes())
        publish(self.root/'rive-extra', rive.produce, manifest_path)
        rive_report = json.loads((self.root/'rive-extra/rive.json').read_text())
        self.assertEqual([state['name'] for state in rive_report['states']], expected_order)
        for state in rive_report['states']:
            for entry in state['frames']:
                self.assertEqual(entry['sha256'], hashlib.sha256((out/entry['path']).read_bytes()).hexdigest())

    def test_extra_actions_reject_unsafe_names_reserved_roles_and_malformed_entries(self):
        action = self.extra_actions()['wave']
        names = ('../escape', '/absolute', 'a/b', r'a\b', '.', '..', 'Wave', 'wáve',
                 '', 'two words', '0wave', 'wave\n', 'x'*33, *action_set.ACTIONS,
                 'master', 'neutral', 'request', 'inspection', 'rig', 'rig_preview', 'motion_qa', 'rive_poses', 'idle_0')
        cases = [{name: action} for name in names]
        cases.extend([None, [], {'wave': action, 'wave_0': action}, {'wave': {'frames': action['frames']}},
                      {'wave': {**action, 'loop': 1}}, {'wave': {**action, 'loop': None}},
                      {'wave': {**action, 'unknown': True}}, {'wave': {**action, 'frames': []}},
                      {'wave': {**action, 'frames': [{'duration_ms': 100}, {'duration_ms': 100}]}},
                      {f'extra{i}': action for i in range(27)}])
        for index, extras in enumerate(cases):
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                self.build(f'invalid-extra{index}', {**self.request, 'extra_actions': extras})
            self.assertFalse((self.root/f'invalid-extra{index}').exists())

    def test_extra_action_duplicate_sequences_and_aggregate_budgets_are_rejected(self):
        duplicate_core = motion.defaults(self.request['rig']['parts'])['idle']
        cases = [
            {'wave': {'loop': True, **duplicate_core}},
            {'wave': self.extra_actions()['wave'], 'cheer': self.extra_actions()['wave']},
            {f'extra{i}': {'loop': False, 'frames': self.extra_actions()['wave']['frames'] * 10}
             for i in range(8)},
        ]
        for index, extras in enumerate(cases):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'distinct|256-frame'):
                self.build(f'duplicate-extra{index}', {**self.request, 'extra_actions': extras})
            self.assertFalse((self.root/f'duplicate-extra{index}').exists())
        with patch.object(motion, 'MAX_PIXELS', 48*48*28), self.assertRaisesRegex(ValueError, 'budget'):
            self.build('extra-budget', {**self.request, 'extra_actions': self.extra_actions()})
        self.assertFalse((self.root/'extra-budget').exists())

    def test_empty_extra_actions_preserves_default_output(self):
        first = self.build('without')
        second = self.build('empty', {**self.request, 'extra_actions': {}})
        self.assertEqual(first, second)
        self.assertNotIn('rive_poses', first['files'])
        self.assertFalse((self.root/'without/rive-poses.json').exists())
        for filename in first['files'].values():
            if filename != 'inspection.json':
                self.assertEqual((self.root/'without'/filename).read_bytes(), (self.root/'empty'/filename).read_bytes())

    def test_sizeable_8_connected_components_report_bounds_and_ignore_single_specks(self):
        image = Image.new('RGBA', (12, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((1, 1, 2, 2), fill='red')
        draw.rectangle((3, 3, 4, 4), fill='red')
        draw.rectangle((8, 2, 9, 3), fill='red')
        image.putpixel((11, 11), (255, 0, 0, 255))
        self.assertEqual(motion.foreground_components(image), [
            {'area_px': 8, 'bounds_xywh': [1, 1, 4, 4]},
            {'area_px': 4, 'bounds_xywh': [8, 2, 2, 2]},
            {'area_px': 1, 'bounds_xywh': [11, 11, 1, 1]}])

    def test_single_body_split_blocks_rive_manifest_but_preserves_diagnostics(self):
        request = copy.deepcopy(self.request)
        request['extra_actions'] = self.extra_actions()
        request['actions'] = {'attack': {'frames': [
            {'duration_ms': 100},
            {'duration_ms': 100, 'parts': {'left': {'offset_px': [-8, 0]}}}]}}
        result = self.build('permissive', request)
        self.assertIn('rive_poses', result['files'])
        report = json.loads((self.root/'permissive/inspection.json').read_text())
        self.assertTrue(report['passed'])
        request['single_body'] = True
        result = self.build('one-body', request)
        report = json.loads((self.root/'one-body/inspection.json').read_text())
        self.assertFalse(report['passed'])
        self.assertFalse(report['single_body_passed'])
        self.assertEqual(report['technical_status'], 'needs-connectivity-review')
        self.assertEqual(report['rive_export_status'], 'blocked-single-body')
        self.assertNotIn('rive_poses', result['files'])
        self.assertFalse((self.root/'one-body/rive-poses.json').exists())
        self.assertEqual(report['component_neighbors'], 8)
        self.assertEqual(report['component_min_area_px'], 4)
        self.assertEqual(len(report['rest_foreground_components']), 1)
        first, torn = report['actions']['attack']['frames']
        self.assertEqual(first['sizeable_component_count'], 1)
        self.assertEqual(first['new_sizeable_components'], 0)
        self.assertEqual(torn['sizeable_component_count'], 2)
        self.assertEqual(torn['new_sizeable_components'], 1)
        self.assertEqual(torn['foreground_components'][1], {'area_px': 44, 'bounds_xywh': [9, 20, 4, 11]})
        self.assertTrue((self.root/'one-body/motion-qa.png').is_file())
        core = json.loads((self.root/'one-body/action-set.request.json').read_text())
        self.assertEqual(list(core['actions']), list(action_set.ACTIONS))
        with self.assertRaisesRegex(ValueError, 'single_body'):
            self.build('bad-one-body', {**request, 'single_body': 1})

    def test_authored_underlap_repairs_a_split_and_preserves_rest_palette_and_export(self):
        request = copy.deepcopy(self.request)
        request['single_body'] = True
        request['actions'] = {name: {'frames': [
            {'duration_ms': 100}, {'duration_ms': 100, 'root_offset_px': [i+1, 0]}]}
            for i, name in enumerate(action_set.ACTIONS)}
        request['extra_actions'] = {'wave': {'loop': True, 'frames': [
            {'duration_ms': 100}, {'duration_ms': 100, 'parts': {'left': {'offset_px': [-4, 0]}}}]}}
        before = (self.root/'master.png').read_bytes()
        self.build('split', request)
        broken = json.loads((self.root/'split/inspection.json').read_text())
        self.assertFalse(broken['passed'])
        self.assertFalse((self.root/'split/rive-poses.json').exists())
        request['rig']['parts'][2]['joint_underlap'] = {
            'parent_px': [23, 22], 'child_px': [19, 23], 'radius_px': 3,
            'source_px': [19, 23], 'edge_px': [20, 23]}
        result = self.build('continuous', request)
        report = json.loads((self.root/'continuous/inspection.json').read_text())
        self.assertTrue(report['passed'])
        self.assertTrue(report['single_body_passed'])
        self.assertEqual(report['rive_export_status'], 'ready')
        self.assertIn('rive_poses', result['files'])
        first, posed = report['actions']['wave']['frames']
        self.assertFalse(first['joint_underlaps'][0]['active'])
        self.assertEqual(first['joint_underlaps'][0]['drawn_pixels'], 0)
        self.assertTrue(posed['joint_underlaps'][0]['active'])
        self.assertGreater(posed['joint_underlaps'][0]['visible_support_pixels'], 0)
        self.assertEqual(posed['sizeable_component_count'], 1)
        self.assertEqual(posed['joint_underlaps'][0]['sizeable_component_count'], 1)
        self.assertEqual(posed['joint_underlaps'][0]['part'], 'left')
        self.assertEqual((self.root/'master.png').read_bytes(), before)
        self.assertEqual((self.root/'continuous/neutral.png').read_bytes(), (self.root/'split/neutral.png').read_bytes())
        with Image.open(self.root/'master.png') as master:
            palette = {c for _, c in master.getcolors(48*48)}
        for path in (self.root/'continuous').glob('wave-*.png'):
            with Image.open(path) as image:
                self.assertLessEqual({c for _, c in image.getcolors(48*48)}, palette)
        self.assertEqual(report['artistic_acceptance'], 'unverified')
        self.build('continuous-repeat', request)
        for filename in result['files'].values():
            self.assertEqual((self.root/'continuous'/filename).read_bytes(), (self.root/'continuous-repeat'/filename).read_bytes())

    def test_underlap_handles_moving_occluder_when_parent_and_child_share_transform(self):
        master = Image.new('RGBA', (24, 24))
        draw = ImageDraw.Draw(master)
        draw.rectangle((10, 5, 15, 11), fill='#345678')
        draw.rectangle((10, 12, 15, 14), fill='#e0a040')
        draw.rectangle((10, 15, 15, 20), fill='#345678')
        support = {'parent_px': [12, 10], 'child_px': [12, 16], 'radius_px': 2, 'source_px': [12, 16]}
        rig = {'parts': [
            {'id': 'body', 'role': 'torso', 'parent': None, 'anchor_px': [12, 10], 'rect': [10, 5, 6, 7]},
            {'id': 'arm', 'role': 'arm_left', 'parent': 'body', 'anchor_px': [12, 12],
             'rect': [10, 15, 6, 6], 'joint_underlap': support},
            {'id': 'scarf', 'role': 'accessory', 'parent': 'body', 'anchor_px': [12, 12], 'rect': [10, 12, 6, 3]}]}
        loaded = motion.load_rig({'rig': rig}, self.root, master)
        neutral, report = motion.render(master, loaded, {'parts': {}, 'root_offset_px': [0, 0]})
        self.assertEqual(neutral.tobytes(), master.tobytes())
        self.assertFalse(report['joint_underlaps'][0]['active'])
        moved, report = motion.render(master, loaded, {'parts': {'scarf': {'offset_px': [6, 0]}}, 'root_offset_px': [0, 0]})
        self.assertTrue(report['joint_underlaps'][0]['active'])
        self.assertGreater(report['joint_underlaps'][0]['visible_support_pixels'], 0)
        self.assertEqual(moved.getpixel((12, 13)), (52, 86, 120, 255))
        self.assertEqual(moved.getpixel((0, 0)), (0, 0, 0, 0))
        translated, report = motion.render(master, loaded, {'parts': {}, 'root_offset_px': [2, 0]})
        self.assertFalse(report['joint_underlaps'][0]['active'])
        self.assertEqual(translated.getpixel((14, 13)), master.getpixel((12, 13)))

    def test_underlap_rejects_invalid_samples_geometry_and_excessive_posed_span(self):
        support = {'parent_px': [23, 22], 'child_px': [19, 23], 'radius_px': 3, 'source_px': [19, 23]}
        changes = [{'radius_px': 0}, {'radius_px': 7}, {'radius_px': True},
                   {'source_px': [0, 0]}, {'source_px': [22, 35]}, {'edge_px': [0, 0]},
                   {'source_px': [48, 48]}, {'parent_px': [True, 22]}, {'unknown': 1},
                   {'child_px': [23, 22]}, {'parent_px': [0, 0], 'child_px': [47, 47]}]
        for index, change in enumerate(changes):
            request = copy.deepcopy(self.request)
            request['rig']['parts'][2]['joint_underlap'] = {**support, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build(f'invalid-underlap{index}', request)
            self.assertFalse((self.root/f'invalid-underlap{index}').exists())
        request = copy.deepcopy(self.request)
        request['rig']['parts'][0]['joint_underlap'] = support
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.build('root-underlap', request)
        request = copy.deepcopy(self.request)
        request['rig']['parts'][2]['anchor_px'] = [48, 48]
        request['rig']['parts'][2]['joint_underlap'] = support
        request['actions'] = {'attack': {'frames': [
            {'duration_ms': 100}, {'duration_ms': 100, 'parts': {'left': {'angle_deg': 180}}}]}}
        with self.assertRaisesRegex(ValueError, 'span exceeds 64'):
            self.build('long-underlap', request)
        self.assertFalse((self.root/'long-underlap').exists())

    def test_clipped_pose_blocks_new_rive_manifest_without_single_body_requirement(self):
        request = copy.deepcopy(self.request)
        request['extra_actions'] = self.extra_actions()
        request['extra_actions']['wave']['frames'][1]['root_offset_px'] = [32, 0]
        result = self.build('clipped-extra', request)
        report = json.loads((self.root/'clipped-extra/inspection.json').read_text())
        self.assertFalse(report['passed'])
        self.assertEqual(report['technical_status'], 'needs-clipping-review')
        self.assertEqual(report['rive_export_status'], 'blocked-clipping')
        self.assertNotIn('rive_poses', result['files'])
        self.assertFalse((self.root/'clipped-extra/rive-poses.json').exists())
        self.assertTrue((self.root/'clipped-extra/motion-qa.png').is_file())


if __name__ == '__main__':
    unittest.main()
