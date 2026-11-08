"""Exercise texture trust-boundary checks in the real Blender runtime."""
from pathlib import Path
import shutil
import subprocess
import unittest


class TextureTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('blender'), 'Local Blender required')
    def test_packed_base_color_and_rejections(self):
        tools = Path(__file__).resolve().parents[1] / 'tools'
        script = f'''
import sys, tempfile
from pathlib import Path
sys.path.insert(0, {str(tools)!r})
import bpy
from blender_worker import validate_materials, static_source
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
obj.data.uv_layers.active.name = 'PaintUV'
mat = bpy.data.materials.new('paint')
mat.use_nodes = True
obj.data.materials.append(mat)
node = mat.node_tree.nodes.new('ShaderNodeTexImage')
uv = mat.node_tree.nodes.new('ShaderNodeUVMap')
uv.uv_map = 'PaintUV'
mat.node_tree.links.new(uv.outputs['UV'], node.inputs['Vector'])
bsdf = mat.node_tree.nodes.get('Principled BSDF')
mat.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
def rejects(reason):
    try:
        validate_materials([obj])
    except ValueError as error:
        assert reason in str(error), str(error)
    else:
        raise AssertionError('Invalid source accepted: '+reason)
rejects('packed local PNG/JPEG')
with tempfile.TemporaryDirectory() as directory:
    image = bpy.data.images.new('pattern', width=2, height=2)
    image.pixels[:] = [1,0,0,1, 0,1,0,1, 0,0,1,1, 1,1,0,1]
    image.filepath_raw = str(Path(directory)/'pattern.png')
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    image = bpy.data.images.load(str(Path(directory)/'pattern.png'))
    node.image = image
    rejects('packed local PNG/JPEG')
    image.pack()
    validate_materials([obj])
    uv.uv_map = 'missing'
    rejects('Named UV map')
    uv.uv_map = 'PaintUV'
    mat.node_tree.links.remove(node.inputs['Vector'].links[0])
    rejects('explicit UV Map')
    mat.node_tree.links.new(uv.outputs['UV'], node.inputs['Vector'])
    mat.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Roughness'])
    rejects('Only image Color')
    mat.node_tree.links.remove(bsdf.inputs['Roughness'].links[0])
    # JPEG uses the same actual Blender decoder and source admission path.
    image.filepath_raw = str(Path(directory)/'pattern.jpg')
    image.file_format = 'JPEG'
    image.save()
    jpeg = bpy.data.images.load(str(Path(directory)/'pattern.jpg'))
    jpeg.pack()
    node.image = jpeg
    validate_materials([obj])
    obj.keyframe_insert(data_path='location', frame=1)
    source = Path(directory)/'animated.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    try:
        static_source(source)
    except ValueError as error:
        assert 'animation' in str(error)
    else:
        raise AssertionError('Animation accepted')
    obj = bpy.context.selected_objects[0]
    obj.animation_data_clear()
    rig = bpy.data.objects.new('Rig', bpy.data.armatures.new('Rig'))
    bpy.context.scene.collection.objects.link(rig)
    obj.parent = rig
    source = Path(directory)/'rigged.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    try:
        static_source(source)
    except ValueError as error:
        assert 'Rigged meshes' in str(error)
    else:
        raise AssertionError('Rig accepted')
print('TEXTURE_BOUNDARIES_OK')
'''
        result = subprocess.run(['blender', '--background', '--factory-startup', '--offline-mode',
                                 '--disable-autoexec', '--python-exit-code', '1', '--python-expr', script],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('TEXTURE_BOUNDARIES_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
