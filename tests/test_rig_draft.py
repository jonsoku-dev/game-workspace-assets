"""Restricted humanoid proposals remain editable, exact, and explicitly unapproved."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_asset_pipeline import motion, rig_draft
from pixel_asset_pipeline.bundle import publish

ROOT = Path(__file__).resolve().parents[1]


def draw_person(path):
    """Self-authored nonrectangular front-facing traveller with separated limbs."""
    image = Image.new('RGBA',(64,64))
    draw = ImageDraw.Draw(image)
    draw.polygon([(25,8),(38,8),(40,10),(40,18),(37,21),(26,21),(23,18),(23,10)],fill='#493c36')
    draw.rectangle((26,11,37,18),fill='#e0b17f')
    draw.rectangle((28,13,29,14),fill='#242b35')
    draw.rectangle((34,13,35,14),fill='#242b35')
    draw.rectangle((29,22,34,23),fill='#bd8a65')
    draw.polygon([(21,24),(42,24),(44,25),(44,28),(40,28),(37,26),(26,26),(23,28),(19,28),(19,25)],fill='#4c785f')
    draw.polygon([(26,26),(37,26),(37,35),(36,38),(36,43),(27,43),(27,38),(26,35)],fill='#4c785f')
    draw.rectangle((30,27,33,36),fill='#a6b391')
    draw.rectangle((19,29,23,35),fill='#4c785f')
    draw.rectangle((40,29,44,35),fill='#4c785f')
    draw.polygon([(19,36),(23,36),(24,37),(24,39),(18,39),(18,37)],fill='#e0b17f')
    draw.polygon([(40,36),(44,36),(45,37),(45,39),(39,39),(39,37)],fill='#e0b17f')
    draw.rectangle((27,44,30,55),fill='#42465d')
    draw.rectangle((33,44,36,55),fill='#42465d')
    draw.polygon([(27,56),(30,56),(30,58),(25,58),(25,57)],fill='#493c36')
    draw.polygon([(33,56),(36,56),(38,57),(38,58),(33,58)],fill='#493c36')
    image.save(path)
    return image


class RigDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = draw_person(self.root/'person.png')
        self.request = {'schema_version':1,'source':'person.png'}

    def build(self,name='out',request=None):
        path=self.root/(name+'.json')
        path.write_text(json.dumps(self.request if request is None else request))
        return publish(self.root/name,rig_draft.produce,path)

    def test_nonrectangular_person_partition_neutral_and_explicit_review_boundary(self):
        before=(self.root/'person.png').read_bytes()
        self.assertEqual(before,(ROOT/'examples/production/rig-draft/relaxed-sprite.png').read_bytes())
        self.assertEqual(self.build()['status'],'ready')
        self.assertEqual(before,(self.root/'person.png').read_bytes())
        report=json.loads((self.root/'out/inspection.json').read_text())
        self.assertEqual(report['source']['sha256'],hashlib.sha256(before).hexdigest())
        self.assertTrue(report['exact_partition'])
        self.assertTrue(report['neutral_exact_visible_reconstruction'])
        self.assertEqual(report['visual_review'],'required')
        self.assertIs(report['approved'],False)
        draft_path=self.root/'out/rig-draft.request.json'
        draft=json.loads(draft_path.read_text())
        self.assertIs(draft['approved'],False)
        self.assertEqual(len(draft['rig']['parts']),6)
        assigned=set()
        for part in draft['rig']['parts']:
            with Image.open(self.root/'out'/part['mask']) as mask:
                self.assertEqual(mask.size,self.master.size)
                self.assertEqual(mask.mode,'L')
                self.assertEqual(mask.getextrema(),(0,255))
                pixels={(x,y) for y in range(64) for x in range(64) if mask.getpixel((x,y))}
            self.assertFalse(pixels & assigned)
            assigned |= pixels
        self.assertEqual(assigned,{(x,y) for y in range(64) for x in range(64) if self.master.getpixel((x,y))[3]})
        with Image.open(self.root/'out/neutral.png') as neutral:
            self.assertEqual(neutral.tobytes(),self.master.tobytes())
        with self.assertRaisesRegex(ValueError,'approved'):
            publish(self.root/'not-approved',motion.produce,draft_path)
        self.assertFalse((self.root/'not-approved').exists())
        # A synthetic test actor explicitly accepts this fixture, never the producer.
        draft['approved']=True
        draft_path.write_text(json.dumps(draft))
        self.assertEqual(publish(self.root/'motion',motion.produce,draft_path)['status'],'ready')
        check=json.loads((self.root/'motion/inspection.json').read_text())
        self.assertTrue(check['neutral_exact_visible_reconstruction'])
        self.assertTrue(all(a['unique_poses']>1 for a in check['actions'].values()))
        self.assertFalse(report['approved'])

    def test_outputs_repeat_byte_for_byte_and_neck_guides_stay_explicit(self):
        first,second=self.build('first'),self.build('second')
        self.assertEqual(first,second)
        for filename in first['files'].values():
            self.assertEqual((self.root/'first'/filename).read_bytes(),(self.root/'second'/filename).read_bytes())
        request={**self.request,'guides':{'neck_y':22,'shoulder_y':25,'hip_y':42}}
        self.build('guided',request)
        report=json.loads((self.root/'guided/inspection.json').read_text())
        self.assertEqual(report['supplied_guides'],request['guides'])
        self.assertEqual(report['proposed_guides'],request['guides'])

    def test_ambiguous_merged_legs_arms_detached_and_asymmetry_are_rejected(self):
        for name in ('legs','arms','detached','asymmetric','opaque','soft'):
            image=self.master.copy()
            draw=ImageDraw.Draw(image)
            if name=='legs': draw.rectangle((31,44,32,58),fill='#42465d')
            elif name=='arms': draw.rectangle((18,24,45,39),fill='#4c785f')
            elif name=='detached': draw.rectangle((2,2,3,3),fill='#4c785f')
            elif name=='asymmetric': draw.rectangle((1,24,18,39),fill='#4c785f')
            elif name=='opaque': image=Image.new('RGBA',(64,64),'white')
            else: image.putpixel((0,0),(10,20,30,100))
            image.save(self.root/(name+'.png'))
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.build(name,{**self.request,'source':name+'.png'})
            self.assertFalse((self.root/name).exists())

    def test_invalid_guides_paths_schema_and_input_caps_leave_no_output(self):
        cases=[{'source':'../escape.png'},{'schema_version':True},{'schema_version':2},
               {'unknown':1},{'guides':None},{'guides':{'neck_y':True}},
               {'guides':{'neck_y':0}},{'guides':{'shoulder_y':38}},
               {'guides':{'hip_y':58}},{'guides':{'extra':22}}]
        for i,change in enumerate(cases):
            with self.subTest(change=change),self.assertRaises((ValueError,OSError)):
                self.build('invalid'+str(i),{**self.request,**change})
            self.assertFalse((self.root/('invalid'+str(i))).exists())
        Image.new('RGBA',(129,129)).save(self.root/'huge.png')
        with self.assertRaises(ValueError): self.build('huge',{**self.request,'source':'huge.png'})
        (self.root/'bad.png').write_bytes(b'not png')
        with self.assertRaises(OSError): self.build('bad',{**self.request,'source':'bad.png'})
        request=self.root/'oversized.json'
        request.write_bytes(b' '*(1_048_576+1))
        with self.assertRaisesRegex(ValueError,'byte limit'):
            publish(self.root/'oversized',rig_draft.produce,request)
        self.assertFalse((self.root/'oversized').exists())
