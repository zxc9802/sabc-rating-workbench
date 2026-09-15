"""Rebuild the original SABC sculpture: Blender --background --python scripts/build_dossier.py.

Exports editable Blender source, a self-contained GLB, and a transparent fallback render.
The lettering is converted to geometry; no font file is redistributed.
"""
from pathlib import Path
import math
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public' / 'models'
SOURCE = ROOT / 'design'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)


def material(name, color, metal=0, rough=.25, transmission=0, glow=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = next((node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if shader is None:
        shader = mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        output = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
        mat.node_tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metal
    shader.inputs['Roughness'].default_value = rough
    shader.inputs['Transmission Weight'].default_value = transmission
    shader.inputs['Coat Weight'].default_value = .5
    shader.inputs['IOR'].default_value = 1.46
    if glow:
        shader.inputs['Emission Color'].default_value = (*color, 1)
        shader.inputs['Emission Strength'].default_value = glow
    return mat


glass = material('Smoked optical glass', (.07, .095, .12), .06, .17, .65)
silver = material('Brushed platinum', (.64, .68, .7), .85, .23)
white = material('Ivory engraving', (.88, .9, .88), .25, .3, glow=.12)
amber = material('Champagne accent', (.92, .57, .2), .65, .22, glow=.35)
muted = material('Etched lines', (.31, .37, .4), .45, .4)
font = bpy.data.fonts.load('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
latin = bpy.data.fonts.load('/System/Library/Fonts/Supplemental/Arial.ttf')


def box(name, pos, size, mat, bevel=.055, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mod = obj.modifiers.new('Polished radius', 'BEVEL')
    mod.width = bevel
    mod.segments = 4
    bpy.ops.object.modifier_apply(modifier=mod.name)
    for face in obj.data.polygons:
        face.use_smooth = True
    normal = obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    bpy.ops.object.modifier_apply(modifier=normal.name)
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def label(text, x, y, z, size, parent, mat=white):
    curve = bpy.data.curves.new(text, 'FONT')
    curve.body = text
    curve.font = latin if text.isascii() else font
    curve.size = size
    curve.extrude = .001
    curve.resolution_u = 3
    obj = bpy.data.objects.new(text, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(mat)
    obj.parent = parent
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    obj.select_set(False)


def panel(name, x, y, z, width, height, yaw=0):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = (x, y, z)
    root.rotation_euler.z = yaw
    curve = bpy.data.curves.new(name + ' rim', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = .018
    curve.bevel_resolution = 3
    points = []
    radius = .09
    for cx, cz, angle in [(width / 2 - radius, height / 2 - radius, 0), (-width / 2 + radius, height / 2 - radius, 90), (-width / 2 + radius, -height / 2 + radius, 180), (width / 2 - radius, -height / 2 + radius, 270)]:
        for step in range(7):
            a = math.radians(angle + step * 15)
            points.append((cx + math.cos(a) * radius, -.13, cz + math.sin(a) * radius, 1))
    spline = curve.splines.new('POLY')
    spline.points.add(len(points) - 1)
    for point, position in zip(spline.points, points):
        point.co = position
    spline.use_cyclic_u = True
    rim = bpy.data.objects.new(name + ' rim', curve)
    bpy.context.collection.objects.link(rim)
    rim.parent = root
    rim.data.materials.append(silver)
    bpy.ops.object.select_all(action='DESELECT')
    rim.select_set(True)
    bpy.context.view_layer.objects.active = rim
    bpy.ops.object.convert(target='MESH')
    box(name + ' glass', (0, -.055, 0), (width, .15, height), glass, .08, root)
    return root


box('Platinum plinth', (0, .05, .05), (4.65, 1.62, .18), silver, .06)
box('Floating glass plinth', (0, .05, .15), (4.54, 1.5, .12), glass, .045)
box('Warm light seam', (0, -.727, .11), (4.3, .015, .016), amber, .006)
rear = panel('Project dossier', -1.38, .5, 1.88, 1.8, 3.1, -.17)
label('项目资料', -.7, -.15, 1.15, .23, rear)
for i in range(9):
    box('Document rule', (-.08, -.145, .78 - i * .22), (1.17 if i % 3 else .8, .009, .017), muted, .004, rear)
middle = panel('Evidence dossier', -.98, .15, 1.55, 1.86, 2.57, -.1)
label('证据依据', -.72, -.15, .9, .19, middle)
for i in range(7):
    box('Evidence rule', (-.14, -.145, .56 - i * .22), (1.09 if i % 2 else .75, .009, .017), muted, .004, middle)
front = panel('Eight dimension assessment', .58, -.29, 1.96, 2.85, 3.45, .05)
label('八维评估', -.78, -.15, 1.13, .35, front)
label('SABC  /  PROJECT INTELLIGENCE', -.99, -.15, .94, .087, front, muted)
box('Assessment header seam', (0, -.15, .78), (2.38, .018, .019), amber, .004, front)
for i, title in enumerate(['战略', '市场', '回报', '资源', '复制', '现金', '风险', '机会']):
    x, z = -.99 + (i % 2) * 1.21, .44 - (i // 2) * .37
    box('Dimension index', (x + .015, -.16, z + .065), (.05, .023, .05), white, .018, front)
    label(title, x + .14, -.16, z, .21, front)
    box('Dimension guide', (x + .47, -.145, z - .08), (.59, .008, .011), muted, .003, front)
for i, grade in enumerate('SABC'):
    x = -.96 + i * .64
    box('Grade ' + grade, (x, -.23, -1.18), (.51, .22, .48), glass, .065, front)
    label(grade, x - .115, -.35, -1.29, .32, front)

# Only model meshes are exported. Lights and camera belong to the source/render.
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT / 'sabc-dossier.glb'), export_format='GLB', use_selection=True, export_apply=True, export_animations=False)

scene = bpy.context.scene
scene.world.color = (.23, .25, .28)
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.resolution_x = 1000
scene.render.resolution_y = 850
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.view_settings.view_transform = 'AgX'


def area(name, position, power, color, size):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.color, data.shape, data.size = power, color, 'DISK', size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector((0, 0, 1.6)) - obj.location).to_track_quat('-Z', 'Y').to_euler()


area('Softbox silver', (-3, -4, 6), 700, (.83, .9, 1), 5)
area('Champagne rim', (3, 2, 4), 950, (1, .71, .4), 4)
area('Front fill', (3, -6, 2), 350, (1, .96, .88), 4)
bpy.ops.object.camera_add(location=(4.4, -10.7, 5))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 1.82)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 5.75
scene.camera = camera
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.filepath = str(OUT / 'sabc-dossier.png')
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / 'sabc-dossier.blend'))
bpy.ops.render.render(write_still=True)
