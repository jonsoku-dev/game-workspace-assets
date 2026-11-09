"""Offline Blender worker for schema-version-2 parametric assemblies.

Builds bevelled parametric parts in a named hierarchy, bakes each part's library material
(grain, edge wear, cavity dirt) to base color / ORM / normal textures with Cycles, adds
rigid animations, measures mesh quality and assembly gates, exports LOD0 and decimated
LODs as GLB, and renders a lit review sheet. Any failed gate raises before publication.
Run: blender --background --factory-startup --python assembly_worker.py -- request.json stage/
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

FPS = 30  # keep in step with assembly.FPS
CONTACT_M = 0.002


def fail(message):
    raise ValueError(message)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def color(hex_value, scale=1.0):
    rgb = [int(hex_value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return (*[min(1.0, srgb_to_linear(c) * scale) for c in rgb], 1.0)


# ---------------------------------------------------------------- shapes (Z-up, round axes along Y)

def ring_faces(bm, outer, inner, closed=True):
    """Quads between two equal-length vertex loops."""
    count = len(outer)
    last = count if closed else count - 1
    return [bm.faces.new((outer[i], outer[(i + 1) % count], inner[(i + 1) % count], inner[i])) for i in range(last)]


def solidify_y(bm, faces, depth):
    """Extrude flat faces lying on y=0 into a closed slab from -depth/2 to +depth/2."""
    for v in bm.verts:
        v.co.y = -depth / 2
    result = bmesh.ops.extrude_face_region(bm, geom=faces)
    moved = [g for g in result["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def circle(bm, radius, segments, start=0.0, end=2 * math.pi, closed=True):
    count = segments if closed else segments + 1
    step = (end - start) / segments
    return [bm.verts.new((radius * math.cos(start + i * step), 0, radius * math.sin(start + i * step)))
            for i in range(count)]


def build_shape(node):
    bm = bmesh.new()
    shape = node["shape"]
    if shape == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        sx, sy, sz = node["size_m"]
        for v in bm.verts:
            v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    elif shape == "cylinder":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=node["segments"], radius1=node["radius_m"],
                              radius2=node["radius_m"], depth=node["depth_m"])
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "X"))
    elif shape == "tube":
        outer = circle(bm, node["outer_radius_m"], node["segments"])
        inner = circle(bm, node["inner_radius_m"], node["segments"])
        solidify_y(bm, ring_faces(bm, outer, inner), node["depth_m"])
    elif shape == "saw_blade":
        teeth, r, depth = node["teeth"], node["radius_m"], node["tooth_depth_m"]
        outline = []
        for i in range(teeth):
            base = 2 * math.pi * i / teeth
            # Raked tooth: root, then a tip leaning forward in the cutting direction.
            for angle, radius in ((base, r - depth), (base + 2 * math.pi / teeth * 0.72, r)):
                outline.append(bm.verts.new((radius * math.cos(angle), 0, radius * math.sin(angle))))
        bore = circle(bm, node["bore_radius_m"], 2 * teeth)
        solidify_y(bm, ring_faces(bm, outline, bore), node["thickness_m"])
    elif shape == "arc":
        start, end = math.radians(node["start_deg"]), math.radians(node["end_deg"])
        outer = circle(bm, node["outer_radius_m"], node["segments"], start, end, closed=False)
        inner = circle(bm, node["inner_radius_m"], node["segments"], start, end, closed=False)
        solidify_y(bm, ring_faces(bm, outer, inner, closed=False), node["depth_m"])
    elif shape == "extrude":
        verts = [bm.verts.new((x, 0, z)) for x, z in node["profile_m"]]
        face = bm.faces.new(verts)
        solidify_y(bm, [face], node["depth_m"])
    elif shape == "lathe":
        verts = [bm.verts.new((r, 0, z)) for r, z in node["profile_m"]]
        edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
        bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi,
                       steps=node["segments"], use_duplicate=False)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(node["id"])
    bm.to_mesh(mesh)
    bm.free()
    return mesh


# ---------------------------------------------------------------- materials

def signal_material(name, spec):
    """Procedural surface signals (base, roughness, metallic, bumped normal) for baking."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    n = nt.nodes.new
    out = n("ShaderNodeOutputMaterial")
    coords = n("ShaderNodeTexCoord")
    mapping = n("ShaderNodeMapping")
    nt.links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    if spec["grain"] == "brushed":
        mapping.inputs["Scale"].default_value = (0.04, 1.0, 1.0)
    noise = n("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = spec["grain_scale"]
    noise.inputs["Detail"].default_value = 8 if spec["grain"] == "cast" else 4
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    breakup = n("ShaderNodeTexNoise")
    breakup.inputs["Scale"].default_value = 9.0
    breakup.inputs["Detail"].default_value = 6
    nt.links.new(coords.outputs["Object"], breakup.inputs["Vector"])

    # Base colour varies +-9% with grain.
    variation = n("ShaderNodeValToRGB")
    variation.color_ramp.elements[0].color = color(spec["base"], 0.84 if spec["grain"] != "none" else 1.0)
    variation.color_ramp.elements[1].color = color(spec["base"], 1.08 if spec["grain"] != "none" else 1.0)
    nt.links.new(noise.outputs["Fac"], variation.inputs["Fac"])

    # Convex edge mask: bevelled normal versus true normal, broken up by low-frequency noise.
    bevel = n("ShaderNodeBevel")
    # Measured on bevelled parts: the bevelled/true normal dot stays above 0.997 on flats and
    # falls to ~0.97 within a few centimetres of convex edges at this radius.
    bevel.inputs["Radius"].default_value = 0.025
    bevel.samples = 16
    geometry = n("ShaderNodeNewGeometry")
    dot = n("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(bevel.outputs["Normal"], dot.inputs[0])
    nt.links.new(geometry.outputs["Normal"], dot.inputs[1])
    edge_ramp = n("ShaderNodeMapRange")
    edge_ramp.inputs["From Min"].default_value = 0.998
    edge_ramp.inputs["From Max"].default_value = 0.975
    nt.links.new(dot.outputs["Value"], edge_ramp.inputs["Value"])
    edge_mask = n("ShaderNodeMath")
    edge_mask.operation = "MULTIPLY"
    edge_mask.use_clamp = True
    nt.links.new(edge_ramp.outputs["Result"], edge_mask.inputs[0])
    wear_breakup = n("ShaderNodeMapRange")
    wear_breakup.inputs["From Min"].default_value = 0.35
    wear_breakup.inputs["From Max"].default_value = 0.65
    wear_breakup.inputs["To Max"].default_value = 2.0 * spec["wear"]
    nt.links.new(breakup.outputs["Fac"], wear_breakup.inputs["Value"])
    nt.links.new(wear_breakup.outputs["Result"], edge_mask.inputs[1])

    # Cavity dirt from local ambient occlusion.
    ao = n("ShaderNodeAmbientOcclusion")
    ao.only_local = True
    ao.inputs["Distance"].default_value = 0.04
    ao.samples = 8
    cavity = n("ShaderNodeMapRange")
    cavity.inputs["From Min"].default_value = 1.0
    cavity.inputs["From Max"].default_value = 0.55
    cavity.inputs["To Max"].default_value = spec["dirt"]
    nt.links.new(ao.outputs["AO"], cavity.inputs["Value"])

    base = n("ShaderNodeMix")
    base.data_type = "RGBA"
    base.inputs[7].default_value = color(spec["edge"])
    nt.links.new(edge_mask.outputs["Value"], base.inputs["Factor"])
    nt.links.new(variation.outputs["Color"], base.inputs[6])
    dirty = n("ShaderNodeMix")
    dirty.data_type = "RGBA"
    dirty.inputs[7].default_value = color(spec["base"], 0.28)
    nt.links.new(cavity.outputs["Result"], dirty.inputs["Factor"])
    nt.links.new(base.outputs[2], dirty.inputs[6])

    rough = n("ShaderNodeMapRange")  # grain -> roughness +-0.08 around the material value
    rough.inputs["To Min"].default_value = max(0.02, spec["roughness"] - 0.08)
    rough.inputs["To Max"].default_value = min(1.0, spec["roughness"] + 0.08)
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    rough_edges = n("ShaderNodeMix")  # worn edges are polished, cavities are matte
    rough_edges.data_type = "FLOAT"
    rough_edges.inputs[3].default_value = max(0.05, spec["roughness"] * 0.55)
    nt.links.new(edge_mask.outputs["Value"], rough_edges.inputs["Factor"])
    nt.links.new(rough.outputs["Result"], rough_edges.inputs[2])
    rough_dirt = n("ShaderNodeMix")
    rough_dirt.data_type = "FLOAT"
    rough_dirt.inputs[3].default_value = min(1.0, spec["roughness"] + 0.3)
    nt.links.new(cavity.outputs["Result"], rough_dirt.inputs["Factor"])
    nt.links.new(rough_edges.outputs[0], rough_dirt.inputs[2])

    metal = n("ShaderNodeMix")  # paint wears through to bare metal
    metal.data_type = "FLOAT"
    metal.inputs[2].default_value = spec["metallic"]
    metal.inputs[3].default_value = max(spec["metallic"], 0.9 if spec["wear"] > 0 else spec["metallic"])
    nt.links.new(edge_mask.outputs["Value"], metal.inputs["Factor"])

    bump = n("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.0 if spec["grain"] == "none" else 0.22
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    principled = n("ShaderNodeBsdfPrincipled")
    nt.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    emission = n("ShaderNodeEmission")
    return mat, {"out": out, "base": dirty.outputs[2], "roughness": rough_dirt.outputs[0],
                 "metallic": metal.outputs[0], "principled": principled, "emission": emission}


def bake_atlas(parts, signal_sets, kind, size, samples):
    """Bake one signal of every part into one shared atlas image in a single Cycles pass."""
    image = bpy.data.images.new(f"atlas_{kind}", size, size, alpha=False, float_buffer=False)
    image.colorspace_settings.name = "sRGB" if kind == "base" else "Non-Color"
    added = []
    for mat, signals in signal_sets.values():
        nt = mat.node_tree
        for link in list(signals["out"].inputs["Surface"].links):
            nt.links.remove(link)
        if kind == "normal":
            nt.links.new(signals["principled"].outputs["BSDF"], signals["out"].inputs["Surface"])
        else:
            nt.links.new(signals[kind], signals["emission"].inputs["Color"])
            nt.links.new(signals["emission"].outputs["Emission"], signals["out"].inputs["Surface"])
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        nt.nodes.active = node
        added.append((nt, node))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.context.scene.cycles.samples = samples if kind != "normal" else max(1, samples // 4)
    bpy.ops.object.bake(type="NORMAL" if kind == "normal" else "EMIT", margin=max(4, size // 128),
                        normal_space="TANGENT")
    for nt, node in added:
        nt.nodes.remove(node)
    return image


def pixels(image):
    data = np.empty(image.size[0] * image.size[1] * 4, dtype=np.float32)
    image.pixels.foreach_get(data)
    return data.reshape(image.size[1], image.size[0], 4)


def final_material(obj, spec, base, orm, normal):
    mat = bpy.data.materials.new(obj.name + "_pbr")
    mat.use_nodes = True
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    t_base = nt.nodes.new("ShaderNodeTexImage")
    t_base.image = base
    nt.links.new(t_base.outputs["Color"], p.inputs["Base Color"])
    t_orm = nt.nodes.new("ShaderNodeTexImage")
    t_orm.image = orm
    split = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(t_orm.outputs["Color"], split.inputs["Color"])
    nt.links.new(split.outputs["Green"], p.inputs["Roughness"])
    nt.links.new(split.outputs["Blue"], p.inputs["Metallic"])
    t_normal = nt.nodes.new("ShaderNodeTexImage")
    t_normal.image = normal
    normal_map = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(t_normal.outputs["Color"], normal_map.inputs["Color"])
    nt.links.new(normal_map.outputs["Normal"], p.inputs["Normal"])
    if "emission" in spec and spec["emission_strength"] > 0:
        p.inputs["Emission Color"].default_value = color(spec["emission"])
        p.inputs["Emission Strength"].default_value = spec["emission_strength"]
    return mat


# ---------------------------------------------------------------- quality

def mesh_report(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    volume = bm.calc_volume(signed=True) if not non_manifold else None
    triangles = len(bm.faces)
    uv = bm.loops.layers.uv.active
    uv_out = 0
    tris = []
    for f in bm.faces:
        if uv is None:
            break
        points = [l[uv].uv.copy() for l in f.loops]
        uv_out += sum(1 for p in points if not (-1e-4 <= p.x <= 1 + 1e-4 and -1e-4 <= p.y <= 1 + 1e-4))
        tris.append(points)
    uv_area = sum(abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2 for a, b, c in tris)
    surface = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return {"triangles": triangles, "non_manifold_edges": non_manifold, "degenerate_faces": degenerate,
            "signed_volume_m3": volume, "uv_present": uv is not None, "uv_outside_unit": uv_out,
            "uv_overlap": uv_overlap(tris), "uv_area": uv_area, "surface_m2": surface}, tris


def uv_overlap(tris, grid=256):
    """Share of covered UV cells covered by more than one triangle (cell-centre sampling)."""
    if not tris:
        return 0.0
    counts = np.zeros((grid, grid), dtype=np.int32)
    centres = (np.arange(grid) + 0.5) / grid
    for a, b, c in tris:
        xs = [a.x, b.x, c.x]
        ys = [a.y, b.y, c.y]
        x0, x1 = max(0, int(min(xs) * grid)), min(grid, int(max(xs) * grid) + 1)
        y0, y1 = max(0, int(min(ys) * grid)), min(grid, int(max(ys) * grid) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        px, py = np.meshgrid(centres[x0:x1], centres[y0:y1])
        d = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
        if abs(d) < 1e-14:
            continue
        l1 = ((b.y - c.y) * (px - c.x) + (c.x - b.x) * (py - c.y)) / d
        l2 = ((c.y - a.y) * (px - c.x) + (a.x - c.x) * (py - c.y)) / d
        inside = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        counts[y0:y1, x0:x1] += inside
    covered = np.count_nonzero(counts)
    return float(np.count_nonzero(counts > 1) / covered) if covered else 0.0


def world_vertices(obj):
    matrix = obj.matrix_world
    return [matrix @ v.co for v in obj.data.vertices]


def bvh(obj):
    return BVHTree.FromPolygons(world_vertices(obj), [tuple(p.vertices) for p in obj.data.polygons])


def ancestors(obj):
    parent = obj.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def subtree_parts(root, parts):
    return [o for o in parts if o == root or root in ancestors(o)]


# ---------------------------------------------------------------- scene

def build(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps = FPS
    objects = {}
    for node in spec["nodes"]:
        if node["kind"] == "pivot":
            obj = bpy.data.objects.new(node["id"], None)
            obj.empty_display_size = 0.05
        else:
            obj = bpy.data.objects.new(node["id"], build_shape(node))
        scene.collection.objects.link(obj)
        objects[node["id"]] = obj
    for node in spec["nodes"]:
        obj = objects[node["id"]]
        if node["parent"]:
            obj.parent = objects[node["parent"]]
        obj.location = node["position_m"]
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = Euler([math.radians(a) for a in node["rotation_deg"]], "XYZ")
    bpy.context.view_layer.update()
    parts = [objects[n["id"]] for n in spec["nodes"] if n["kind"] == "part"]
    nodes = {n["id"]: n for n in spec["nodes"]}
    for obj in parts:
        node = nodes[obj.name]
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        if node["bevel_m"] > 0:
            bevel = obj.modifiers.new("bevel", "BEVEL")
            bevel.width = node["bevel_m"]
            bevel.segments = 2
            bevel.limit_method = "ANGLE"
            bevel.angle_limit = math.radians(35)
            bevel.harden_normals = True
            bpy.ops.object.modifier_apply(modifier="bevel")
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    return objects, parts


def atlas_size(parts, density, cap):
    area = sum(f.area for obj in parts for f in obj.data.polygons)
    wanted = math.sqrt(area / 0.65) * density
    size = 256
    while size < wanted and size < cap:
        size *= 2
    return size


def unwrap_and_bake(spec, parts):
    """Unwrap every part, pack all islands into one shared atlas, bake base/ORM/normal once."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.render.bake.use_selected_to_active = False
    nodes = {n["id"]: n for n in spec["nodes"]}
    for obj in parts:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    # Smart project fits each part to the full square; equalise island scale by 3D area across
    # all parts first so texel density is uniform in the shared atlas.
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(margin=0.004, rotate=True, scale=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    size = atlas_size(parts, spec["texel_density_px_per_m"], spec["budget"]["texture_px"])
    signal_sets = {}
    for obj in parts:
        material_spec = spec["materials"][nodes[obj.name]["material"]]
        signal_sets[obj.name] = signal_material(obj.name + "_signals", material_spec)
        obj.data.materials.clear()
        obj.data.materials.append(signal_sets[obj.name][0])
    images = {kind: bake_atlas(parts, signal_sets, kind, size, spec["bake_samples"])
              for kind in ("base", "roughness", "metallic", "normal")}
    orm = bpy.data.images.new("atlas_orm", size, size, alpha=False)
    orm.colorspace_settings.name = "Non-Color"
    r, m = pixels(images["roughness"]), pixels(images["metallic"])
    packed = np.ones_like(r)
    packed[..., 1] = r[..., 0]
    packed[..., 2] = m[..., 0]
    orm.pixels.foreach_set(packed.ravel())
    for image in (images["base"], orm, images["normal"]):
        image.pack()
    baked = {}
    for obj in parts:
        material_spec = spec["materials"][nodes[obj.name]["material"]]
        obj.data.materials.clear()
        # Distinct material objects sharing three atlas images: the compiler cannot merge
        # sibling meshes (and their animation targets) by material identity.
        obj.data.materials.append(final_material(obj, material_spec, images["base"], orm, images["normal"]))
        bpy.data.materials.remove(signal_sets[obj.name][0])
        baked[obj.name] = {"texture_px": size, "material": nodes[obj.name]["material"]}
    bpy.data.images.remove(images["roughness"])
    bpy.data.images.remove(images["metallic"])
    return baked


def animate(spec, objects):
    scene = bpy.context.scene
    end = 0
    summary = []
    for item in spec["animations"]:
        obj = objects[item["target"]]
        obj.animation_data_create()
        action = bpy.data.actions.new(item["name"])
        obj.animation_data.action = action
        rest_location, rest_rotation = obj.location.copy(), obj.rotation_euler.copy()
        if "spin" in item:
            spin = item["spin"]
            axis = "xyz".index(spin["axis"])
            frames = max(2, round(spin["duration_s"] * FPS))
            turn = math.radians(360 * spin["rpm"] / 60 * spin["duration_s"])
            for frame, angle in ((0, 0.0), (frames, turn)):
                rotation = rest_rotation.copy()
                rotation[axis] += angle
                obj.rotation_euler = rotation
                obj.keyframe_insert("rotation_euler", index=axis, frame=frame)
            duration = spin["duration_s"]
        else:
            for key in item["keys"]:
                frame = round(key["t"] * FPS)
                if "position_m" in key:
                    obj.location = key["position_m"]
                    obj.keyframe_insert("location", frame=frame)
                if "rotation_deg" in key:
                    obj.rotation_euler = Euler([math.radians(a) for a in key["rotation_deg"]], "XYZ")
                    obj.keyframe_insert("rotation_euler", frame=frame)
            duration = item["keys"][-1]["t"]
        fcurves = getattr(action, "fcurves", None)
        if fcurves is None or not len(fcurves):
            fcurves = [fc for layer in action.layers for strip in layer.strips
                       for bag in strip.channelbags for fc in bag.fcurves]
        for fcurve in fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "LINEAR" if item["interpolation"] == "linear" or "spin" in item else "BEZIER"
        track = obj.animation_data.nla_tracks.new()
        track.name = item["name"]
        track.strips.new(item["name"], 0, action)
        obj.animation_data.action = None
        obj.location, obj.rotation_euler = rest_location, rest_rotation
        end = max(end, round(duration * FPS))
        summary.append({"name": item["name"], "target": item["target"], "duration_s": duration,
                        "loop": item["loop"], "kind": "spin" if "spin" in item else "keys"})
    scene.frame_start, scene.frame_end = 0, end
    return summary


def gates(spec, objects, parts, baked):
    nodes = {n["id"]: n for n in spec["nodes"]}
    errors, per_part = [], {}
    total = 0
    atlas_tris = []
    for obj in parts:
        report, tris = mesh_report(obj)
        atlas_tris.extend(tris)
        size = baked[obj.name]["texture_px"]
        density = size * math.sqrt(report["uv_area"] / report["surface_m2"]) if report["surface_m2"] else 0
        report["texel_density_px_per_m"] = round(density, 1)
        report["texture_px"] = size
        per_part[obj.name] = report
        total += report["triangles"]
        if report["non_manifold_edges"]:
            errors.append({"code": "non-manifold", "part": obj.name,
                           "message": f"{obj.name}: {report['non_manifold_edges']} open or shared edges; close the shape."})
        if report["degenerate_faces"]:
            errors.append({"code": "degenerate-faces", "part": obj.name,
                           "message": f"{obj.name}: {report['degenerate_faces']} zero-area faces."})
        if report["signed_volume_m3"] is not None and report["signed_volume_m3"] <= 0:
            errors.append({"code": "inverted-normals", "part": obj.name,
                           "message": f"{obj.name}: normals point inward (signed volume {report['signed_volume_m3']:.6f})."})
        if not report["uv_present"] or report["uv_outside_unit"]:
            errors.append({"code": "uv-range", "part": obj.name, "message": f"{obj.name}: UVs missing or outside 0..1."})
        if report["uv_overlap"] > 0.01:
            errors.append({"code": "uv-overlap", "part": obj.name,
                           "message": f"{obj.name}: {report['uv_overlap']:.1%} of baked texels are shared by overlapping UVs."})
        wanted = spec["texel_density_px_per_m"]
        capped = size >= spec["budget"]["texture_px"]
        if density < wanted * 0.4 and not capped or density > wanted * 4:
            errors.append({"code": "texel-density", "part": obj.name,
                           "message": f"{obj.name}: {density:.0f} px/m against the {wanted} px/m target."})
    shared = uv_overlap(atlas_tris, grid=512)
    if shared > 0.01:
        errors.append({"code": "uv-overlap", "part": None,
                       "message": f"{shared:.1%} of the shared atlas is painted by more than one part."})
    if total > spec["budget"]["triangles"]:
        errors.append({"code": "triangle-budget", "part": None,
                       "message": f"LOD0 has {total} triangles over the budget of {spec['budget']['triangles']}."})
    trees = {obj.name: bvh(obj) for obj in parts}
    for obj in parts:
        if nodes[obj.name]["free"] or len(parts) == 1:
            continue
        # Vertices miss flat faces resting on each other (an n-gon has no interior vertex), so
        # sample face centres too.
        samples = world_vertices(obj) + [obj.matrix_world @ p.center for p in obj.data.polygons]
        step = max(1, len(samples) // 1200)
        nearest = math.inf
        for other in parts:
            if other == obj:
                continue
            for point in samples[::step]:
                hit = trees[other.name].find_nearest(point)
                if hit[0] is not None and hit[3] < nearest:
                    nearest = hit[3]
        per_part[obj.name]["nearest_other_part_m"] = round(nearest, 5)
        if nearest > CONTACT_M:
            errors.append({"code": "floating-part", "part": obj.name,
                           "message": f"{obj.name}: nearest other part is {nearest * 1000:.1f} mm away; it is bolted to nothing."})
    for item in spec["animations"]:
        if "spin" not in item:
            continue
        pivot = objects[item["target"]]
        axis = pivot.matrix_world.to_3x3() @ Vector([1.0 if a == item["spin"]["axis"] else 0.0 for a in "xyz"])
        axis.normalize()
        origin = pivot.matrix_world.translation
        spinning = subtree_parts(pivot, parts)
        if not spinning:
            continue
        points = [v for obj in spinning for v in world_vertices(obj)]
        lo = Vector([min(p[i] for p in points) for i in range(3)])
        hi = Vector([max(p[i] for p in points) for i in range(3)])
        centre = (lo + hi) / 2
        offset = (centre - origin) - axis * (centre - origin).dot(axis)
        radius = max((p - origin).length for p in points)
        if offset.length > max(0.001, radius * 0.005):
            errors.append({"code": "off-axis-spin", "part": item["target"],
                           "message": f"{item['name']}: the spinning parts' centre is {offset.length * 1000:.1f} mm off the "
                                      f"{item['target']} axis, so it will wobble; move the pivot to the hub centre."})
    all_points = [v for obj in parts for v in world_vertices(obj)]
    low = Vector([min(p[i] for p in all_points) for i in range(3)])
    high = Vector([max(p[i] for p in all_points) for i in range(3)])
    if abs(low.z) > 0.001:
        errors.append({"code": "not-grounded", "part": None,
                       "message": f"The lowest point is at z={low.z:.4f} m; the asset must rest on z=0."})
    size = high - low
    if spec["expected_size_m"]:
        for axis, (actual, wanted) in enumerate(zip(size, spec["expected_size_m"])):
            if abs(actual - wanted) > wanted * 0.02:
                errors.append({"code": "unexpected-size", "part": None,
                               "message": f"{'XYZ'[axis]} size is {actual:.3f} m, expected {wanted:.3f} m (2%)."})
    return {"triangles": total, "parts": per_part, "errors": errors, "atlas_uv_overlap": round(shared, 4),
            "bounds_min": list(low), "bounds_max": list(high), "dimensions_m": list(size)}


def export(path, apply=True):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", export_apply=apply, export_yup=True,
                              export_animations=True, export_animation_mode="ACTIONS",
                              export_force_sampling=True, export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_extras=False)


def export_lods(spec, parts, stage):
    lods = []
    for index, ratio in enumerate(spec["lod_ratios"], 1):
        added = []
        for obj in parts:
            if len(obj.data.polygons) > 64:
                modifier = obj.modifiers.new("lod", "DECIMATE")
                modifier.ratio = ratio
                modifier.use_collapse_triangulate = True
                added.append((obj, modifier))
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        triangles = sum(sum(len(p.vertices) - 2 for p in obj.evaluated_get(depsgraph).data.polygons) for obj in parts)
        name = f"model.lod{index}.glb"
        export(stage / name)
        for obj, modifier in added:
            obj.modifiers.remove(modifier)
        lods.append({"ratio": ratio, "file": name, "triangles": triangles})
    return lods


# ---------------------------------------------------------------- review renders

def look_at(camera, target):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_review(bounds_min, bounds_max):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("review")
    world.use_nodes = True
    nt = world.node_tree
    seen = nt.nodes["Background"]
    seen.inputs["Color"].default_value = (0.045, 0.055, 0.06, 1)
    seen.inputs["Strength"].default_value = 0.35
    # Reflections see a soft studio gradient (bright above, dim below) so metals read as metal.
    sky = nt.nodes.new("ShaderNodeBackground")
    coords = nt.nodes.new("ShaderNodeTexCoord")
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.03, 0.035, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.85, 0.88, 0.9, 1)
    remap = nt.nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = -1.0
    nt.links.new(coords.outputs["Generated"], split.inputs["Vector"])
    nt.links.new(split.outputs["Z"], remap.inputs["Value"])
    nt.links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], sky.inputs["Color"])
    sky.inputs["Strength"].default_value = 0.7
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(sky.outputs["Background"], mix.inputs[1])
    nt.links.new(seen.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], nt.nodes["World Output"].inputs["Surface"])
    scene.world = world
    low, high = Vector(bounds_min), Vector(bounds_max)
    centre = (low + high) / 2
    radius = max((high - low).length / 2, 0.05)
    ground = bpy.data.meshes.new("review_ground")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=radius * 6)
    bm.to_mesh(ground)
    bm.free()
    floor = bpy.data.objects.new("review_ground", ground)
    floor.location = (centre.x, centre.y, low.z)
    mat = bpy.data.materials.new("review_ground")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.035, 0.04, 0.045, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.85
    ground.materials.append(mat)
    scene.collection.objects.link(floor)
    for name, energy, direction, size, tint in (("key", 260, (-0.8, -1.2, 1.4), 2.0, (1, 0.96, 0.9)),
                                                ("fill", 70, (1.3, -0.6, 0.6), 3.0, (0.85, 0.9, 1.0)),
                                                ("rim", 220, (0.2, 1.4, 1.1), 1.5, (1, 1, 1))):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy * radius * radius
        light.size = size * radius
        light.color = tint
        obj = bpy.data.objects.new(name, light)
        obj.location = centre + Vector(direction).normalized() * radius * 4
        look_at(obj, centre)
        scene.collection.objects.link(obj)
    camera = bpy.data.objects.new("review_camera", bpy.data.cameras.new("review_camera"))
    camera.data.lens = 50
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera, centre, radius, floor


def render_view(camera, centre, radius, azimuth, elevation, size, path):
    scene = bpy.context.scene
    distance = radius / math.tan(camera.data.angle / 2) * 1.12
    a, e = math.radians(azimuth), math.radians(elevation)
    camera.location = centre + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * distance
    look_at(camera, centre)
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path))
    data = pixels(image).copy()
    bpy.data.images.remove(image)
    return data


def compose(tiles, columns, path):
    height = max(t.shape[0] for t in tiles)
    width = max(t.shape[1] for t in tiles)
    rows = math.ceil(len(tiles) / columns)
    sheet = np.zeros((rows * height, columns * width, 4), dtype=np.float32)
    sheet[..., 3] = 1
    sheet[..., :3] = 0.03
    for index, tile in enumerate(tiles):
        r, c = divmod(index, columns)
        top = (rows - 1 - r) * height  # Blender images start at the bottom row
        sheet[top:top + tile.shape[0], c * width:c * width + tile.shape[1]] = tile
    image = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    image.pixels.foreach_set(sheet.ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()


def review(spec, objects, parts, quality, animations, stage):
    camera, centre, radius, floor = setup_review(quality["bounds_min"], quality["bounds_max"])
    scratch = stage.parent / "renders"
    scratch.mkdir(exist_ok=True)
    views = [(-35, 18), (35, 18), (90, 8), (145, 22), (-35, 55)]
    tiles = [render_view(camera, centre, radius, az, el, 384, scratch / f"view{i}.png") for i, (az, el) in enumerate(views)]
    small = render_view(camera, centre, radius, -35, 18, 128, scratch / "game.png")
    padded = np.zeros((384, 384, 4), dtype=np.float32)
    padded[..., 3] = 1
    padded[..., :3] = 0.03
    padded[128:256, 128:256] = small
    tiles.append(padded)
    nodes = {n["id"]: n for n in spec["nodes"]}
    offsets = {obj.name: Vector(nodes[obj.name]["exploded_offset_m"]) for obj in parts
               if any(nodes[obj.name]["exploded_offset_m"])}
    if offsets:
        tracks = [t for o in objects.values() if o.animation_data for t in o.animation_data.nla_tracks]
        for track in tracks:  # NLA evaluation would otherwise put animated parts back at rest
            track.mute = True
        for obj in parts:
            if obj.name in offsets:
                obj.location += offsets[obj.name]
        tiles.append(render_view(camera, centre, radius * 1.25, -35, 22, 384, scratch / "exploded.png"))
        for obj in parts:
            if obj.name in offsets:
                obj.location -= offsets[obj.name]
        for track in tracks:
            track.mute = False
    scene = bpy.context.scene
    for item in animations[:2]:
        target = objects[item["target"]]
        track = target.animation_data.nla_tracks[item["name"]]
        action = track.strips[0].action
        target.animation_data.action = action
        if hasattr(target.animation_data, "action_slot") and action.slots:
            target.animation_data.action_slot = action.slots[0]
        track.mute = True
        # Spins avoid symmetric quarter turns; keyed motion shows its travel through to the end pose.
        for fraction in ((0.11, 0.23, 0.37) if item["kind"] == "spin" else (0.3, 0.65, 1.0)):
            step = int(fraction * 100)
            scene.frame_set(round(item["duration_s"] * FPS * fraction))
            tiles.append(render_view(camera, centre, radius, -20, 12, 384, scratch / f"{item['name']}{step}.png"))
        target.animation_data.action = None
        track.mute = False
        scene.frame_set(0)
    compose(tiles, 4, stage / "review.png")
    render_view(camera, centre, radius, -35, 18, 768, stage / "preview.png")
    bpy.data.objects.remove(floor)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    spec = json.loads(Path(argv[0]).read_text())
    stage = Path(argv[1])
    stage.mkdir(parents=True)
    objects, parts = build(spec)
    baked = unwrap_and_bake(spec, parts)
    quality = gates(spec, objects, parts, baked)
    if quality["errors"]:
        fail("Assembly quality gates failed: " + json.dumps(quality["errors"]))
    animations = animate(spec, objects)
    bpy.ops.wm.save_as_mainfile(filepath=str(stage / "source.blend"), compress=True)
    export(stage / "model.glb")
    lods = export_lods(spec, parts, stage)
    review(spec, objects, parts, quality, animations, stage)
    metadata = {
        "schema_version": 2, "name": spec["name"], "kind": "assembly",
        "original": {"bounds_min": quality["bounds_min"], "bounds_max": quality["bounds_max"],
                     "dimensions_m": quality["dimensions_m"], "triangles": quality["triangles"],
                     "materials": len(parts), "meshes": len(parts)},
        "nodes": [{"id": n["id"], "kind": n["kind"], "parent": n["parent"], "shape": n.get("shape"),
                   "material": n.get("material")} for n in spec["nodes"]],
        "materials": spec["materials"], "baked": baked, "animations": animations, "lods": lods,
        "quality": {"passed": True, "triangles": quality["triangles"], "parts": quality["parts"],
                    "budget": spec["budget"], "texel_density_target_px_per_m": spec["texel_density_px_per_m"]},
        "review": {"sheet": "review.png", "views": "front-left, front-right, side, back, top-left at 384px; "
                   "game size 128px; exploded state; animation samples",
                   "visual_review": "pending", "artistic_acceptance": "pending"},
    }
    (stage / "model.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # Blender would otherwise print a traceback and exit 0 in some paths
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        sys.exit(1)
