"""Offline Blender worker: static selected meshes, direct Principled PBR with packed base color images.

No animation, constraints, modifiers, shape keys, linked libraries or procedural
shader graphs are admitted. The source is saved before preview-only dressing.
"""
import json
import hashlib
import math
import sys
import tempfile
from array import array
from pathlib import Path

import bpy
from mathutils import Vector


# Blender does not consistently add the script directory to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lantern import lantern
from ember import ember, motion


def require(condition, message):
    if not condition:
        raise ValueError(message)


def static_source(path):
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    selected = list(bpy.context.selected_objects)
    require(selected and all(o.type == 'MESH' for o in selected),
            'Source must have one or more whole mesh objects selected, with no other selected types')
    require(bpy.context.scene.unit_settings.scale_length == 1.0,
            'Source must use one Blender unit per meter (scale_length=1)')
    for obj in selected:
        require(not obj.library and not obj.data.library, 'Linked mesh libraries are unsupported')
        require(not obj.modifiers and not obj.constraints and not obj.animation_data,
                'Apply modifiers and remove constraints/animation before export')
        require(not obj.data.shape_keys and not obj.data.animation_data,
                'Shape keys and animated meshes are unsupported')
        require(not obj.hide_render and not obj.hide_get(), 'Selected meshes must be visible')
        require(len(obj.data.polygons) > 0, 'Selected mesh has no faces')
        parent = obj.parent
        while parent:
            require(parent.type != 'ARMATURE', 'Rigged meshes are unsupported; detach and remove the rig')
            require(not parent.animation_data and not parent.constraints,
                    'Animated/constrained parents are unsupported')
            parent = parent.parent
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    for obj in list(bpy.data.objects):
        if obj not in selected:
            bpy.data.objects.remove(obj, do_unlink=True)
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    # Discard source scene machinery; only the selected local asset survives.
    scene = bpy.data.scenes.new('Asset')
    for obj in selected:
        scene.collection.objects.link(obj)
    bpy.context.window.scene = scene
    for old in list(bpy.data.scenes):
        if old != scene:
            bpy.data.scenes.remove(old)
    bpy.data.orphans_purge(do_recursive=True)
    return selected


def validate_materials(objects):
    allowed = {'ShaderNodeOutputMaterial', 'ShaderNodeBsdfPrincipled', 'ShaderNodeTexImage',
               'ShaderNodeUVMap', 'ShaderNodeNormalMap'}
    for mat in {m for obj in objects for m in obj.data.materials if m}:
        require(not mat.library and not mat.animation_data, 'Linked or animated materials unsupported')
        if not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        require(not mat.node_tree.animation_data, 'Animated shader nodes unsupported')
        require(all(n.bl_idname in allowed for n in nodes), 'Only direct Principled PBR/image nodes supported')
        outputs = [n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
        require(len(outputs) == 1, 'Material needs one active output')
        output = outputs[0]
        require(not output.inputs['Volume'].is_linked and not output.inputs['Displacement'].is_linked,
                'Volume and displacement unsupported')
        require(output.inputs['Surface'].is_linked and
                output.inputs['Surface'].links[0].from_node.type == 'BSDF_PRINCIPLED',
                'Surface must connect directly to Principled BSDF')
        for node in nodes:
            if node.type == 'NORMAL_MAP':
                require(node.space == 'TANGENT', 'Only tangent-space normal maps supported')
            if node.type == 'TEX_IMAGE':
                img = node.image
                require(img and img.source == 'FILE' and not img.library and img.packed_file,
                        'Textures must be packed local PNG/JPEG still images; pack before saving the .blend')
                require(img.file_format in {'PNG', 'JPEG'} and img.has_data,
                        'Packed texture must decode as PNG/JPEG')
                require(all(0 < edge <= 2048 for edge in img.size), 'Texture dimensions must be from 1 to 2048 pixels')
                require(img.colorspace_settings.name == 'sRGB', 'Base Color image must use sRGB')
                require(node.interpolation == 'Linear' and node.extension == 'REPEAT',
                        'Base Color image must use Linear interpolation and Repeat extension')
                require(node.inputs['Vector'].is_linked and
                        node.inputs['Vector'].links[0].from_node.type == 'UVMAP',
                        'Texture requires an explicit UV Map node')
                uv_name = node.inputs['Vector'].links[0].from_node.uv_map
                users = [o for o in objects if mat in list(o.data.materials)]
                require(uv_name and all(uv_name in o.data.uv_layers for o in users),
                        'Named UV map is missing from a textured mesh')
                require(all(all(math.isfinite(c) for c in loop.uv)
                            for o in users for loop in o.data.uv_layers[uv_name].data),
                        'UV coordinates must be finite')
                require(node.outputs['Color'].is_linked and all(
                        link.to_node.type == 'BSDF_PRINCIPLED' and link.to_socket.name == 'Base Color'
                        for link in node.outputs['Color'].links) and not node.outputs['Alpha'].is_linked,
                        'Only image Color directly connected to Principled Base Color is supported')
        for link in mat.node_tree.links:
            source, target = link.from_node.type, link.to_node.type
            require((source == 'BSDF_PRINCIPLED' and target == 'OUTPUT_MATERIAL') or
                    (source == 'UVMAP' and target == 'TEX_IMAGE') or
                    (source == 'NORMAL_MAP' and target == 'BSDF_PRINCIPLED' and link.to_socket.name == 'Normal') or
                    (source == 'TEX_IMAGE' and target == 'BSDF_PRINCIPLED' and
                     link.from_socket.name == 'Color' and link.to_socket.name == 'Base Color'),
                    'Only direct Principled PBR and explicit UV base color texture connections supported')


def stats():
    bpy.context.view_layer.update()
    objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    coords = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    require(coords, 'No mesh vertices')
    require(all(math.isfinite(c) for v in coords for c in v), 'Nonfinite geometry')
    low = [min(v[i] for v in coords) for i in range(3)]
    high = [max(v[i] for v in coords) for i in range(3)]
    triangles = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    textures = []
    for mat in {m for o in objects for m in o.data.materials if m and m.use_nodes}:
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                image = node.image
                pixels = bytes(max(0, min(255, round(v * 255))) for v in image.pixels[:])
                textures.append({'width': image.size[0], 'height': image.size[1],
                                 'rgba_sha256': hashlib.sha256(pixels).hexdigest()})
    return {'textures': sorted(textures, key=lambda t: t['rgba_sha256']), 'meshes': len(objects), 'triangles': triangles, 'bounds_min': low,
            'bounds_max': high, 'dimensions_m': [b-a for a, b in zip(low, high)],
            'materials': sorted({m.name for o in objects for m in o.data.materials if m}),
            'units': 'meters', 'up_axis': '+Z'}


def render_preview(stage, measured):
    scene = bpy.context.scene
    center = Vector([(a+b)/2 for a, b in zip(measured['bounds_min'], measured['bounds_max'])])
    extent = max(measured['dimensions_m'])
    require(extent > 0, 'Asset has no physical extent')
    def aim(obj):
        obj.rotation_euler = (center-obj.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add(location=center + Vector((1.5, -2.4, 1.3))*extent)
    camera = bpy.context.object
    aim(camera)
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = extent*1.65
    camera.data.clip_start = max(extent/10000, 0.00001)
    camera.data.clip_end = extent*100 + 10
    scene.camera = camera
    for name, location, energy, color in [
        ('Key', (-1.3, -1.7, 2.3), 170, (1, .88, .72)),
        ('Fill', (1.7, -.8, 1.1), 90, (.72, .85, 1)),
        ('Rim', (.5, 1.6, 2), 200, (1, .9, .75)),
    ]:
        bpy.ops.object.light_add(type='AREA', location=center+Vector(location)*extent)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy*extent*extent
        light.data.shape = 'DISK'
        light.data.size = extent*2
        light.data.color = color
        aim(light)
    world = bpy.data.worlds.new('Preview studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.14, .18, .17, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .5
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 24
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(stage/'preview.png')
    bpy.ops.render.render(write_still=True)


def render_review(stage, measured):
    """Three readable views, each with an independently rendered 128px companion."""
    scene = bpy.context.scene
    center = Vector([(a+b)/2 for a, b in zip(measured['bounds_min'], measured['bounds_max'])])
    extent = max(measured['dimensions_m'])
    views = [('front', (0, -3, 1.05)), ('side', (3, 0, 1.05)),
             ('rear', (-1.8, 2.6, 1.25))]
    width, height = 1152, 512
    pixels = array('f', (.06, .08, .075, 1)) * (width * height)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    with tempfile.TemporaryDirectory(prefix='.review-', dir=stage) as temporary:
        for column, (name, direction) in enumerate(views):
            camera = scene.camera
            camera.location = center + Vector(direction) * extent
            camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
            for size in (384, 128):
                scene.render.resolution_x = scene.render.resolution_y = size
                path = Path(temporary) / f'{name}-{size}.png'
                scene.render.filepath = str(path)
                bpy.ops.render.render(write_still=True)
                image = bpy.data.images.load(str(path), check_existing=False)
                source = array('f', [0]) * (size * size * 4)
                image.pixels.foreach_get(source)
                x = column * 384 + (384-size)//2
                y = 128 if size == 384 else 0
                for row in range(size):
                    target = ((y+row) * width + x) * 4
                    pixels[target:target+size*4] = source[row*size*4:(row+1)*size*4]
                bpy.data.images.remove(image)
    sheet = bpy.data.images.new('Three-angle model review', width=width, height=height, alpha=True)
    sheet.pixels.foreach_set(pixels)
    sheet.filepath_raw = str(stage / 'review.png')
    sheet.file_format = 'PNG'
    sheet.save()
    bpy.data.images.remove(sheet)
    return {'file': 'review.png', 'columns_left_to_right': [name for name, _ in views],
            'upper_row_px': 384, 'lower_row_px': 128,
            'lower_row_independently_rendered': True, 'art_approval': 'not established'}


def main():
    args = sys.argv[sys.argv.index('--')+1:]
    require(len(args) == 2, 'Expected absolute spec and fresh stage paths')
    spec_path, stage = map(Path, args)
    require(spec_path.is_absolute() and stage.is_absolute(), 'Paths must be absolute')
    spec = json.loads(spec_path.read_text())
    require(spec.get('schema_version') == 1, 'Unsupported schema_version')
    require(set(spec) <= {'schema_version', 'name', 'preset', 'source_blend', 'height_m', 'seed'}, 'Unknown input keys')
    require(isinstance(spec.get('name'), str) and spec['name'].strip(), 'Name required')
    require(('preset' in spec) != ('source_blend' in spec), 'Choose preset or source_blend')
    require('seed' not in spec or spec.get('preset') == 'embers', 'seed applies to embers only')
    require(not stage.exists() or (stage.is_dir() and not any(stage.iterdir())), 'Stage must be empty')
    stage.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if 'source_blend' in spec:
        path = Path(spec['source_blend'])
        require(path.is_absolute() and path.is_file() and path.suffix.lower() == '.blend', 'Invalid source_blend')
        require('height_m' not in spec, 'height_m applies to lantern only')
        objects = static_source(path)
    elif spec.get('preset') == 'embers':
        require('height_m' not in spec, 'height_m applies to lantern only')
        effect = motion(spec.get('seed', 23))
        objects = ember()
        (stage/'effect.json').write_text(json.dumps(effect, indent=2, allow_nan=False)+'\n')
    else:
        require(spec['preset'] == 'lantern', 'Unknown preset')
        height = spec.get('height_m', .30)
        require(type(height) in (int, float) and math.isfinite(height) and .01 <= height <= 10,
                'height_m must be a finite number from .01 to 10')
        objects = lantern(height)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    validate_materials(objects)
    original = stats()
    require(original['triangles'] > 0, 'Asset has no triangles')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(stage/'source.blend'), check_existing=False)
    bpy.ops.export_scene.gltf(filepath=str(stage/'model.glb'), export_format='GLB',
                              use_selection=True, export_animations=False, export_cameras=False,
                              export_lights=False, export_yup=True, export_apply=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(stage/'model.glb'))
    reimported = stats()
    tolerance = max(1e-6, max(original['dimensions_m'])*1e-5)
    checks = {
        'triangles_match': original['triangles'] == reimported['triangles'],
        'texture_pixels_match': original['textures'] == reimported['textures'],
        'materials_match': original['materials'] == reimported['materials'],
        'bounds_match': all(abs(a-b) <= tolerance for key in ('bounds_min', 'bounds_max')
                            for a, b in zip(original[key], reimported[key])),
        'mesh_count_match': original['meshes'] == reimported['meshes'],
    }
    require(all(checks.values()), 'GLB roundtrip mismatch: '+json.dumps(checks))
    report = {'schema_version': 1, 'name': spec['name'], 'blender_version': bpy.app.version_string,
              'scope': 'selected static meshes; direct Principled PBR with optional packed PNG/JPEG base color',
              'original': original, 'reimported': reimported, 'checks': checks,
              'bounds_tolerance_m': tolerance, 'glb_up_axis': '+Y',
              'flags': {'roundtrip_verified': True, 'source_self_contained': True,
                        'preview_dressing_exported': False, 'engine_integration_verified': False}}
    if spec.get('preset') == 'embers':
        report['effect'] = {'file': 'effect.json', 'seed': spec.get('seed', 23),
                            'up_axis': '+Y', 'base_mesh_dimensions_m': [
                                original['dimensions_m'][i] for i in (0, 2, 1)],
                            'motion_contract': 'tools/ember.py module docstring; opaque native mesh with scale envelope'}
    render_preview(stage, reimported)
    report['review'] = render_review(stage, reimported)
    (stage/'model.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
