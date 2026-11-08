"""Source-derived rigs preserve pixels and pose connected selected actions."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline import character_motion, motion, rig_draft

ROOT = Path(__file__).resolve().parents[1]


class CharacterMotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self, size=(64,64), actions=None):
        root = self.root/f'{size[0]}x{size[1]}'
        root.mkdir()
        with Image.open(ROOT/'examples/production/rig-draft/relaxed-sprite.png') as source:
            source.resize(size,Image.Resampling.NEAREST).save(root/'source.png')
        request = root/'source.json'
        request.write_text(json.dumps({'schema_version':1,'source':'source.png'}))
        rig = root/'rig'
        rig.mkdir()
        rig_draft.produce(request,rig)
        path = character_motion.prepare(rig,list(character_motion.SUPPORTED_ACTIONS) if actions is None else actions)
        data = json.loads(path.read_text())
        master = Image.open(rig/data['master']).convert('RGBA')
        return rig, path, data, master, motion.load_rig(data,rig,master)

    def test_editable_relative_masks_exact_neutral_and_no_inferred_approval(self):
        rig,path,data,master,parts = self.prepare(actions=['wave','run'])
        self.assertEqual(path,rig/'motion.request.json')
        self.assertIs(data['approved'],False)
        self.assertEqual(set(data['actions']),{'run'})
        self.assertEqual(set(data['extra_actions']),{'wave'})
        self.assertEqual(len(parts),10)
        self.assertTrue(all(not Path(p['mask']).is_absolute() for p in parts))
        neutral,_ = motion.render(master,parts,{'parts':{},'root_offset_px':[0,0]})
        self.assertEqual(neutral.tobytes(),master.tobytes())
        self.assertEqual((rig/'master.png').read_bytes(),(rig.parent/'source.png').read_bytes())
        self.assertIs(json.loads((rig/'rig-draft.request.json').read_text())['approved'],False)
        self.assertEqual(sum(len(p['pixels']) for p in parts),sum(bool(p[3]) for p in motion.pixel_data(master)))
        for part in parts:
            if part['parent']:
                self.assertIn(tuple(part['joint_underlap']['source_px']),part['pixels'])
        before = path.read_bytes()
        character_motion.prepare(rig,['wave','run'])
        self.assertEqual(before,path.read_bytes())

    def test_all_profiles_connected_unclipped_and_distinct_across_varied_proportions(self):
        for size in ((64,64),(64,80),(96,96)):
            with self.subTest(size=size):
                rig,path,data,master,parts = self.prepare(size)
                signatures = []
                palette = set(motion.pixel_data(master))
                for name,action in {**data['actions'],**data['extra_actions']}.items():
                    poses = []
                    for frame in motion.frames_for({'frames':action['frames']},parts,master.size):
                        rendered,report = motion.render(master,parts,frame)
                        self.assertEqual(report['clipped_part_pixels'],0,(size,name))
                        components = motion.foreground_components(rendered)
                        self.assertEqual(sum(c['area_px']>=4 for c in components),1,(size,name))
                        self.assertLessEqual(set(motion.pixel_data(rendered)),palette)
                        poses.append(rendered.tobytes())
                    self.assertGreater(len(set(poses)),1,(size,name))
                    signatures.append(tuple(poses))
                self.assertEqual(len(set(signatures)),8)

    def test_front_jog_alternates_bent_arm_and_opposite_leg(self):
        rig,path,data,master,parts = self.prepare(actions=['run'])
        frames = data['actions']['run']['frames']
        first,opposite = frames[0]['parts'],frames[2]['parts']
        self.assertGreater(abs(first['arm_left_lower']['angle_deg']),abs(first['arm_right_lower']['angle_deg']))
        self.assertGreater(abs(opposite['arm_right_lower']['angle_deg']),abs(opposite['arm_left_lower']['angle_deg']))
        self.assertGreater(abs(first['leg_right_lower']['angle_deg']),abs(first['leg_left_lower']['angle_deg']))
        self.assertGreater(abs(opposite['leg_left_lower']['angle_deg']),abs(opposite['leg_right_lower']['angle_deg']))
        for frame, swing, stance in ((frames[0],'leg_right_lower','leg_left_lower'),
                                     (frames[2],'leg_left_lower','leg_right_lower')):
            _,report = motion.render(master,parts,frame)
            self.assertLess(report['contact_points_px'][swing][1],report['contact_points_px'][stance][1])

    def test_short_arms_long_torso_and_broad_head_anatomy(self):
        root = self.root/'different'
        root.mkdir()
        image = Image.new('RGBA',(64,64))
        draw = ImageDraw.Draw(image)
        for box,color in [((22,7,41,17),'#705046'),((29,18,34,20),'#d7a474'),
                          ((19,21,44,24),'#668750'),((27,25,36,44),'#668750'),
                          ((19,25,23,29),'#668750'),((40,25,44,29),'#668750'),
                          ((19,30,23,33),'#d7a474'),((40,30,44,33),'#d7a474'),
                          ((27,45,30,56),'#454b75'),((33,45,36,56),'#454b75'),
                          ((25,57,30,58),'#705046'),((33,57,38,58),'#705046')]:
            draw.rectangle(box,fill=color)
        image.save(root/'source.png')
        request = root/'source.json'
        request.write_text(json.dumps({'schema_version':1,'source':'source.png'}))
        rig = root/'rig'
        rig.mkdir()
        rig_draft.produce(request,rig)
        path = character_motion.prepare(rig,list(character_motion.SUPPORTED_ACTIONS))
        data = json.loads(path.read_text())
        parts = motion.load_rig(data,rig,image)
        for name,action in {**data['actions'],**data['extra_actions']}.items():
            for frame in motion.frames_for({'frames':action['frames']},parts,image.size):
                rendered,report = motion.render(image,parts,frame)
                self.assertEqual(report['clipped_part_pixels'],0,name)
                self.assertEqual(sum(c['area_px']>=4 for c in motion.foreground_components(rendered)),1,name)

    def test_producer_exports_only_requested_actions_and_keeps_provisional_status(self):
        rig,path,data,master,parts = self.prepare(actions=['wave','run'])
        data['actions']['attack'] = {'frames':[]}
        path.write_text(json.dumps(data))
        output = rig.parent/'motion'
        output.mkdir()
        files = motion.produce(path,output,selected_actions=['wave','run'],provisional_rig=True)
        report = json.loads((output/'inspection.json').read_text())
        self.assertEqual(set(report['actions']),{'wave','run'})
        self.assertEqual(report['rig_status'],'provisional')
        self.assertTrue(report['passed'])
        self.assertIn('rive_poses',files)
        self.assertFalse((output/'attack-01.png').exists())
        with self.assertRaisesRegex(ValueError,'approved'):
            motion.produce(path,output)

    def test_tight_margins_reject_only_the_selected_unsafe_profile(self):
        with Image.open(ROOT/'examples/production/rig-draft/relaxed-sprite.png') as source:
            source.crop((17,7,47,60)).save(self.root/'source.png')
        request = self.root/'source.json'
        request.write_text(json.dumps({'schema_version':1,'source':'source.png'}))
        rig = self.root/'rig'
        rig.mkdir()
        rig_draft.produce(request,rig)
        path = character_motion.prepare(rig,['idle'])
        self.assertEqual(set(json.loads(path.read_text())['actions']),{'idle'})
        path = character_motion.prepare(rig, ['wave'])
        rendered = self.root / 'wave-output'
        rendered.mkdir()
        outputs = motion.produce(path, rendered, selected_actions=['wave'], provisional_rig=True)
        self.assertFalse(json.loads((rendered / outputs['inspection']).read_text())['passed'])
        self.assertNotIn('rive_poses', outputs)

    def test_unknown_duplicate_and_empty_selection_rejected_before_writing(self):
        for actions in ([],['unknown'],['run','run'],[None],'run'):
            with self.subTest(actions=actions),self.assertRaisesRegex(ValueError,'unique supported'):
                character_motion.prepare(self.root,actions)
        self.assertEqual(list(self.root.iterdir()),[])
