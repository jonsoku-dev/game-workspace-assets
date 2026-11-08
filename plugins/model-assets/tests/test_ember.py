import importlib.util
import math
from pathlib import Path
import random
import shutil
import subprocess
import unittest


TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('ember_producer', TOOLS / 'ember.py')
ember = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ember)


class EmberTests(unittest.TestCase):
    def test_seeded_portable_motion_contract(self):
        state = random.getstate()
        result = ember.motion(23)
        self.assertEqual(result, ember.motion(23))
        self.assertNotEqual(result, ember.motion(24))
        self.assertEqual(random.getstate(), state)
        self.assertEqual(set(result), {'schema_version', 'kind', 'units', 'duration_s', 'particles'})
        self.assertEqual((result['schema_version'], result['kind'], result['units']),
                         (1, 'mesh-particles', 'meters'))
        self.assertEqual(len(result['particles']), 24)
        self.assertGreater(result['duration_s'], 0)
        for particle in result['particles']:
            self.assertEqual(set(particle), {'offset', 'drift', 'start_s', 'life_s', 'scale', 'spin'})
            for key in ('offset', 'drift', 'spin'):
                self.assertEqual(len(particle[key]), 3)
                self.assertTrue(all(math.isfinite(value) for value in particle[key]))
            self.assertTrue(0 <= particle['start_s'] < result['duration_s'])
            self.assertTrue(0 < particle['life_s'] < result['duration_s'])
            self.assertTrue(1 <= particle['scale'] <= 2)
            self.assertGreater(particle['drift'][1], 0)
        for axis in (0, 2):
            self.assertTrue(any(p['drift'][axis] < 0 for p in result['particles']))
            self.assertTrue(any(p['drift'][axis] > 0 for p in result['particles']))

    def test_invalid_seeds(self):
        for seed in (True, -1, 4294967296, 23.0, '23', None):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                ember.motion(seed)

    @unittest.skipUnless(shutil.which('blender'), 'Local Blender required')
    def test_actual_ember_is_a_nonzero_volume_emissive_mesh(self):
        script = f'''
import sys
sys.path.insert(0, {str(TOOLS)!r})
import bpy, bmesh
from ember import ember
from blender_worker import stats, validate_materials
bpy.ops.wm.read_factory_settings(use_empty=True)
objects = ember()
assert len(objects) == 1 and objects[0].type == 'MESH'
validate_materials(objects)
measured = stats()
assert measured['triangles'] == 8
assert all(abs(a-b)<1e-8 for a,b in zip(measured['dimensions_m'], [.002,.0016,.0036]))
mesh = bmesh.new()
mesh.from_mesh(objects[0].data)
assert abs(mesh.calc_volume()) > 1e-10
mesh.free()
shader = objects[0].data.materials[0].node_tree.nodes.get('Principled BSDF')
assert shader.inputs['Emission Strength'].default_value > 1
assert shader.inputs['Alpha'].default_value == 1
print('EMBER_VOLUME_OK')
'''
        result = subprocess.run(['blender', '--background', '--factory-startup', '--offline-mode',
                                 '--disable-autoexec', '--python-exit-code', '1', '--python-expr', script],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('EMBER_VOLUME_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
