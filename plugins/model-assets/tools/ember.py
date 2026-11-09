"""Original angular 3D coal spark and deterministic Y-up local motion.

For phase = positive_mod(elapsed-start_s, duration_s), draw only phase < life_s.
Let u = phase/life_s. Position is offset + drift*u, plus
sin(pi*u)*.35*[drift.z, 0, -drift.x]; rotation is spin*phase in XYZ radians.
Scale is particle.scale*sqrt(sin(pi*u)): an opaque, depth-writing ember shrinks
to zero at both life boundaries. No billboard, texture or custom alpha shader.
"""
import math
import random


def motion(seed=23):
    if type(seed) is not int or not 0 <= seed <= 4294967295:
        raise ValueError('seed must be an integer from 0 to 4294967295')
    rng = random.Random(seed)
    duration = 3.2
    particles = []
    for index in range(24):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(.001, .004)
        drift_angle = angle + rng.uniform(-.8, .8)
        drift_radius = rng.uniform(.006, .016)
        particles.append({
            'offset': [radius * math.cos(angle), rng.uniform(0, .002), radius * math.sin(angle)],
            'drift': [drift_radius * math.cos(drift_angle), rng.uniform(.027, .060),
                      drift_radius * math.sin(drift_angle)],
            'start_s': (index + rng.uniform(.05, .95)) * duration / 24,
            'life_s': rng.uniform(1.1, 2.1),
            'scale': rng.uniform(1, 2),
            'spin': [rng.uniform(-4, 4), rng.uniform(-6, 6), rng.uniform(-4, 4)],
        })
    return {'schema_version': 1, 'kind': 'mesh-particles', 'units': 'meters',
            'duration_s': duration, 'particles': particles}


def sample(particle, duration, elapsed):
    """Reference sampler for the docstring contract; every runtime must reproduce it."""
    age = (elapsed - particle['start_s']) % duration
    visible = age < particle['life_s']
    u = age / particle['life_s'] if visible else 0.0
    envelope = math.sin(math.pi * u)
    drift = particle['drift']
    lateral = [drift[2], 0.0, -drift[0]]
    return {'visible': visible,
            'position': [o + d * u + envelope * 0.35 * l for o, d, l in zip(particle['offset'], drift, lateral)],
            'rotation': [s * age for s in particle['spin']],
            'scale': particle['scale'] * math.sqrt(max(0.0, envelope)) if visible else 0.0}


def ember():
    import bpy

    # Blender Z maps to exported glTF +Y: the longest axis is 3.6 mm.
    vertices = [(0, 0, .0018), (-.0002, .0001, -.0018),
                (-.001, 0, 0), (0, -.0008, -.00015),
                (.001, .0001, .0002), (0, .0008, 0)]
    faces = [(0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 2),
             (1, 3, 2), (1, 4, 3), (1, 5, 4), (1, 2, 5)]
    mesh = bpy.data.meshes.new('Angular ember solid')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Three dimensional coal spark', mesh)
    bpy.context.collection.objects.link(obj)
    material = bpy.data.materials.new('Hot amber coal')
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (.22, .032, .004, 1)
    shader.inputs['Roughness'].default_value = .65
    shader.inputs['Emission Color'].default_value = (1, .18, .012, 1)
    shader.inputs['Emission Strength'].default_value = 1.8
    obj.data.materials.append(material)
    return [obj]
