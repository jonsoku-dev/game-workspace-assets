"""Self-authored hurricane lantern: formed metal, hollow glass and connected cage."""
import math

import bpy
from mathutils import Vector


def material(name, color, metallic=0, roughness=.4, emission=0, transmission=0):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Transmission Weight'].default_value = transmission
    shader.inputs['IOR'].default_value = 1.46
    shader.inputs['Emission Color'].default_value = (*color, 1)
    shader.inputs['Emission Strength'].default_value = emission
    return result


def mesh_object(name, vertices, faces, finish):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(finish)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def turned(name, profile, finish, segments=48, closed=False):
    """Revolve an explicit sheet/solid section, retaining true hollow interiors."""
    vertices, rings, faces = [], [], []
    for radius, z in profile:
        ring = []
        for index in range(segments if radius else 1):
            angle = math.tau * index / segments
            ring.append(len(vertices))
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
        rings.append(ring)
    pairs = list(zip(rings, rings[1:]))
    if closed:
        pairs.append((rings[-1], rings[0]))
    for lower, upper in pairs:
        for index in range(segments):
            following = (index + 1) % segments
            if len(lower) == 1:
                faces.append((lower[0], upper[following], upper[index]))
            elif len(upper) == 1:
                faces.append((lower[index], lower[following], upper[0]))
            else:
                faces.append((lower[index], lower[following], upper[following], upper[index]))
    return mesh_object(name, vertices, faces, finish)


def tube(name, points, radius, finish, smooth=False, closed=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 8
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    curve.use_fill_caps = True
    spline = curve.splines.new('BEZIER' if smooth else 'POLY')
    spline.use_cyclic_u = closed
    if smooth:
        spline.bezier_points.add(len(points) - 1)
        for point, coordinate in zip(spline.bezier_points, points):
            point.co = coordinate
            point.handle_left_type = 'AUTO'
            point.handle_right_type = 'AUTO'
    else:
        spline.points.add(len(points) - 1)
        for point, coordinate in zip(spline.points, points):
            point.co = (*coordinate, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    obj.data.materials.append(finish)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def hoop(name, radius, z, thickness, finish):
    return tube(name, [(radius * math.cos(math.tau * i / 64),
                        radius * math.sin(math.tau * i / 64), z) for i in range(64)],
                thickness, finish, closed=True)


def pin(name, a, b, radius, finish, vertices=24):
    direction = Vector(b) - Vector(a)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                       depth=direction.length, location=(Vector(a) + Vector(b)) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    obj.data.materials.append(finish)
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    return obj


def flame(name, profile, finish, offset_y=0):
    vertices, faces = [], []
    segments = 24
    for radius, z, lean in profile:
        for i in range(segments):
            angle = math.tau * i / segments
            vertices.append((lean + radius * math.cos(angle),
                             offset_y + radius * .65 * math.sin(angle), z))
    for row in range(len(profile) - 1):
        for i in range(segments):
            a = row * segments + i
            b = row * segments + (i + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    faces.extend([tuple(reversed(range(segments))),
                  tuple((len(profile) - 1) * segments + i for i in range(segments))])
    return mesh_object(name, vertices, faces, finish)


def lantern(height):
    enamel = material('Deep petrol vitreous enamel', (.018, .095, .085), .38, .28)
    iron = material('Graphite blackened steel', (.035, .043, .046), .76, .34)
    brass = material('Warm satin brass', (.43, .235, .075), .78, .31)
    wick = material('Charred woven wick', (.018, .011, .007), 0, .9)
    glass = material('Clear chimney glass', (.96, .985, .97), 0, .075, transmission=1)
    amber = material('Flame amber mantle', (1, .19, .009), emission=2)
    gold = material('Flame golden core', (1, .62, .075), emission=4)

    turned('Rolled foot and shouldered oil reservoir', [
        (0, .002), (.056, .002), (.064, .003), (.069, .007),
        (.070, .013), (.069, .018), (.066, .021), (.067, .030),
        (.066, .043), (.062, .053), (.055, .062), (.042, .069),
        (.030, .072), (0, .072),
    ], enamel)
    hoop('Reservoir rolled standing seam', .0685, .014, .0022, iron)
    turned('Pressed burner mounting cup', [
        (.018, .071), (.033, .071), (.036, .075), (.036, .079),
        (.031, .082), (.020, .083),
    ], brass, closed=True)

    # A real air gap surrounds the burner; eight webs carry the chimney seat.
    hoop('Lower perforated collar bead', .031, .083, .0016, iron)
    hoop('Upper perforated collar bead', .031, .095, .0016, iron)
    for i in range(8):
        angle = math.tau * i / 8
        x, y = .031 * math.cos(angle), .031 * math.sin(angle)
        pin('Collar ventilation web', (x, y, .083), (x, y, .095), .0018, brass, 12)
    turned('Burner wick gallery', [(0, .081), (.017, .081), (.021, .086),
                                  (.020, .092), (.013, .096), (.009, .101),
                                  (.008, .109), (0, .109)], brass, segments=32)
    pin('Exposed cotton wick', (0, 0, .106), (0, 0, .114), .003, wick, 16)
    pin('Wick adjustment spindle', (.012, -.005, .087), (.045, -.005, .087), .0017, brass, 12)
    pin('Wick adjustment wheel', (.044, -.005, .087), (.048, -.005, .087), .007, brass, 20)

    turned('Hollow blown hurricane chimney', [
        (.030, .094), (.034, .098), (.043, .112), (.048, .132),
        (.0485, .151), (.046, .175), (.039, .205), (.033, .231),
        (.032, .253), (.0308, .253), (.0318, .231), (.0378, .205),
        (.0448, .175), (.0473, .151), (.0468, .132), (.0418, .112),
        (.0328, .098), (.0288, .094),
    ], glass, segments=64, closed=True)
    hoop('Chimney lower retaining bead', .032, .097, .002, iron)
    hoop('Chimney top retaining bead', .032, .253, .002, iron)

    flame('Leaning amber flame', [(.001, .112, 0), (.006, .119, -.001),
                                (.007, .130, 0), (.005, .143, .002),
                                (.0025, .155, .006), (.00015, .166, .004)], amber)
    for side in (-1, 1):
        flame('Golden inner flame', [(.0006, .113, 0), (.003, .120, 0),
                                    (.0035, .127, .001), (.002, .136, .002),
                                    (.0001, .146, .003)], gold, offset_y=side * .0038)

    for side in (-1, 1):
        tube('Swept structural air tube', [
            (side * .047, 0, .048), (side * .062, 0, .063),
            (side * .066, 0, .111), (side * .066, 0, .206),
            (side * .060, 0, .253), (side * .044, 0, .276),
            (side * .027, 0, .282),
        ], .0055, enamel, smooth=True)
        for radius, z in ((.054, .125), (.050, .202)):
            pin('Hoop to air tube socket', (side * radius, 0, z),
                (side * .067, 0, z), .0028, brass, 16)
        pin('Bail pivot bearing', (side * .059, 0, .246),
            (side * .076, 0, .246), .007, brass)
        pin('Bail shoulder rivet', (side * .074, 0, .246),
            (side * .080, 0, .246), .004, iron)
    hoop('Lower protective cage hoop', .054, .125, .0025, brass)
    hoop('Upper protective cage hoop', .050, .202, .0025, brass)
    for side in (-1, 1):
        tube('Front and rear bowed guard', [(0, side * .033, .098),
                                           (0, side * .054, .125),
                                           (0, side * .056, .163),
                                           (0, side * .050, .202),
                                           (0, side * .032, .253)],
             .0022, iron, smooth=True)

    turned('Double wall pressed exhaust hood', [
        (.032, .253), (.043, .255), (.058, .264), (.061, .268),
        (.060, .272), (.052, .278), (.041, .286), (.028, .293),
        (.025, .298), (.0235, .298), (.0265, .292), (.040, .284),
        (.051, .276), (.0585, .270), (.059, .268), (.057, .266),
        (.042, .257), (.032, .255),
    ], enamel, closed=True)
    hoop('Hood rolled drip edge', .0595, .269, .0016, iron)
    hoop('Exhaust bottom bead', .025, .297, .0014, brass)
    hoop('Exhaust top bead', .025, .316, .0014, brass)
    for i in range(10):
        angle = math.tau * i / 10
        x, y = .025 * math.cos(angle), .025 * math.sin(angle)
        pin('Open exhaust grille support', (x, y, .297), (x, y, .316), .0022, iron, 12)
    turned('Raised rain cap with open exhaust below', [
        (.022, .315), (.038, .315), (.041, .318), (.038, .322),
        (.029, .326), (.015, .329), (0, .330),
    ], enamel)

    tube('Pivoting steel carrying bail', [
        (-.077, 0, .246), (-.086, 0, .275), (-.085, 0, .334),
        (-.062, 0, .386), (0, 0, .413), (.062, 0, .386),
        (.085, 0, .334), (.086, 0, .275), (.077, 0, .246),
    ], .003, iron, smooth=True)
    tube('Bail center grip sleeve', [(-.032, 0, .405), (0, 0, .413), (.032, 0, .405)],
         .005, brass, smooth=True)

    objects = list(bpy.context.scene.objects)
    bpy.context.view_layer.update()
    top = max((obj.matrix_world @ vertex.co).z for obj in objects for vertex in obj.data.vertices)
    bottom = min((obj.matrix_world @ vertex.co).z for obj in objects for vertex in obj.data.vertices)
    scale = height / (top - bottom)
    for obj in objects:
        obj.location.z -= bottom
        obj.location *= scale
        obj.scale *= scale
    bpy.context.view_layer.update()
    return objects
