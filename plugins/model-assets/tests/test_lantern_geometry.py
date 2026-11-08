"""Small real-Blender check for the authored static model's structural contract."""
from pathlib import Path
import shutil
import subprocess
import unittest


class LanternGeometryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('blender'), 'Local Blender required')
    def test_hollow_connected_static_lantern(self):
        tools = Path(__file__).resolve().parents[1] / 'tools'
        script = f'''
import sys
sys.path.insert(0, {str(tools)!r})
import bpy
from lantern import lantern
from blender_worker import stats, validate_materials
bpy.ops.wm.read_factory_settings(use_empty=True)
objects = lantern(.3)
assert objects and all(obj.type == 'MESH' and not obj.modifiers for obj in objects)
validate_materials(objects)
measured = stats()
assert abs(measured['dimensions_m'][2] - .3) < 1e-6
assert abs(measured['bounds_min'][2]) < 1e-6
assert 0 < measured['triangles'] < 100000
chimney = bpy.data.objects['Hollow blown hurricane chimney']
assert all(vertex.co.x**2 + vertex.co.y**2 > .028**2 for vertex in chimney.data.vertices)
assert len(bpy.data.objects['Swept structural air tube'].data.polygons) > 0
assert len(bpy.data.objects['Bail pivot bearing'].data.polygons) > 0
glass = chimney.data.materials[0].node_tree.nodes.get('Principled BSDF')
assert glass.inputs['Transmission Weight'].default_value == 1
assert bpy.data.objects['Leaning amber flame'].data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value > 0
print('LANTERN_GEOMETRY_OK')
'''
        result = subprocess.run(['blender', '--background', '--factory-startup', '--offline-mode',
                                 '--disable-autoexec', '--python-exit-code', '1', '--python-expr', script],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('LANTERN_GEOMETRY_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
