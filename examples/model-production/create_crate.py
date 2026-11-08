"""Original workshop rescue crate; run in Blender offline to recreate packed source.

All geometry, emblem and paint texture are authored here, without downloaded assets.
"""
import math
from pathlib import Path
import random
import sys
import bpy

out = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
rng = random.Random(684)
size = 512
image = bpy.data.images.new('Rescue paint - original atlas', width=size, height=size, alpha=True)
# Left half teal painted panel with ivory rescue cross; right half dark framing.
pixels = []
for y in range(size):
    for x in range(size):
        u, v = (x % 256) / 255, y / 511
        color = (.10, .40, .38) if x < 256 else (.13, .18, .20)
        if x < 256:
            border = min(u, 1-u, v, 1-v)
            if border < .025 or (rng.random() < .035 and border < .13):
                color = (.59, .62, .54)
            # Broad ivory diamond and teal cross are readable at gameplay size.
            if abs(u-.5) + abs(v-.5) < .28:
                color = (.94, .83, .53)
                if (abs(u-.5) < .035 and abs(v-.5) < .16) or (abs(v-.5) < .035 and abs(u-.5) < .16):
                    color = (.08, .24, .24)
            if .13 < u < .87 and .13 < v < .18:
                color = (.91, .53, .20) if int((u+v)*24) % 2 else (.13, .18, .20)
            if rng.random() < .012:
                color = tuple(c * .65 for c in color)
        grain = rng.uniform(-.018, .018)
        pixels.extend([max(0, min(1, c+grain)) for c in color] + [1])
image.pixels.foreach_set(pixels)
image.filepath_raw = str(out / 'rescue-paint.png')
image.file_format = 'PNG'
image.save()
bpy.data.images.remove(image)
image = bpy.data.images.load(str(out / 'rescue-paint.png'))
image.pack()

def material(name, color, metal, rough):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Roughness'].default_value = rough
    return mat
paint = material('Rescue enamel', (1, 1, 1), .12, .52)
tex = paint.node_tree.nodes.new('ShaderNodeTexImage')
tex.image = image
uv = paint.node_tree.nodes.new('ShaderNodeUVMap')
uv.uv_map = 'PaintUV'
paint.node_tree.links.new(uv.outputs['UV'], tex.inputs['Vector'])
paint.node_tree.links.new(tex.outputs['Color'], paint.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
frame = material('Graphite protective frame', (.035, .065, .075), .65, .34)
metal = material('Brushed brass hardware', (.48, .31, .10), .8, .38)
rubber = material('Inset rubber gasket', (.012, .022, .025), .0, .85)
objects = []

def box(name, position, dimensions, mat, bevel=.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    obj.data.uv_layers.active.name = 'PaintUV'
    # Each box face uses the panel half of the atlas, including its oriented emblem.
    for face in obj.data.polygons:
        for index, coordinate in zip(face.loop_indices, [(0,0),(1,0),(1,1),(0,1)]):
            obj.data.uv_layers.active.data[index].uv = (.025 + coordinate[0] * .45, .025 + coordinate[1] * .95)
    if bevel:
        modifier = obj.modifiers.new('Machined edge', 'BEVEL')
        modifier.width = bevel
        modifier.segments = 2
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    objects.append(obj)
    return obj
box('Sealed graphite case', (0,0,.34), (.94,.68,.62), frame, .045)
# Panels are visibly inset within rails, rather than a flat painted cube.
box('Front rescue panel', (0,-.351,.35), (.74,.025,.42), paint)
box('Rear rescue panel', (0,.351,.35), (.74,.025,.42), paint)
box('Left rescue panel', (-.481,0,.35), (.025,.49,.42), paint)
box('Right rescue panel', (.481,0,.35), (.025,.49,.42), paint)
box('Lid dark seal', (0,0,.666), (.96,.70,.025), rubber, .02)
box('Top rescue lid', (0,0,.700), (.81,.55,.055), paint, .025)
for x in [-.45,.45]:
    for y in [-.315,.315]:
        box('Corner impact boot', (x,y,.12), (.14,.14,.23), frame, .025)
        box('Corner cap', (x,y,.64), (.14,.14,.16), metal, .02)
for x in [-.28,.28]:
    box('Front latch', (x,-.382,.59), (.09,.035,.16), metal, .008)
    box('Latch key slot', (x,-.403,.58), (.035,.008,.012), rubber, .002)
# Side carry handles have actual negative space and two anchored ends.
for x in [-.508,.508]:
    for y in [-.13,.13]:
        box('Handle stand off', (x,y,.44), (.07,.055,.06), metal, .008)
    box('Carry handle grip', (x*1.075,0,.44), (.045,.29,.05), frame, .012)
for x in [-.34,.34]:
    box('Skid runner', (x,0,.025), (.13,.62,.05), rubber, .012)
bpy.ops.object.select_all(action='DESELECT')
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 1
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'rescue-crate.blend'))
