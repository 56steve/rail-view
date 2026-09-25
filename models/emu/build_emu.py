"""Builds RailView's Mumbai suburban EMU coaches in Blender and exports them as glTF.

Run headless (no Blender window opens):

    blender -b --factory-startup -P models/emu/build_emu.py -- \
        --out frontend/public/models/emu.glb --renders /tmp/emu-renders

It builds the three coaches a Mumbai local is made of, from shared parts:
the driving cab car, the motor coach with its pantograph, and the plain
trailer, each in two liveries: the non-AC rakes (modelled on Central
Railway's ICF-built ones) and the ICF AC rakes (stainless, blue and red).
`REFERENCE.md` next to this script lists what they have to match.
Dimensions are from Indian Railways' EMU references (IRIMEE "Basics of
EMU", Central Railway's AC EMU book).

Frame (Blender, before glTF export): metres, Z up, each coach's front
(the cab end, on the cab car) towards +Y, origin at the coach's centre at
rail-top height. glTF export with +Y up turns that into three.js's frame:
+Y up and the front towards -Z, which is what `frontend/components/three`
expects. Each coach is a top-level node (`coach_cab_nonac`, ...,
`coach_trailer_ac`) with its four `wheelset_*` children, all at the origin.

Every line runs the same two liveries, so the colours are baked in. The
app relies on the material names "Glass" (windows light up at night) and
"Headlight"/"TailLight".
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import addon_utils
import bmesh
import bpy
from mathutils import Matrix, Vector

# -- dimensions (metres) -------------------------------------------------------

LENGTH = 20.73
HALF_LENGTH = LENGTH / 2
HALF_WIDTH = 3.66 / 2
GAUGE = 1.676
COACH_GAP = 0.9  # between coach ends in a rake, as in the app

BODY_BOTTOM_Z = 0.98  # bottom edge of the body side
FLOOR_Z = 1.2
SIDE_TOP_Z = 3.2  # sides are vertical to here, then curve into the roof
ROOF_Z = 4.0
ROOF_SQUARENESS = 2.6  # superellipse exponent of the roof profile
ROOF_PAINT_Z = 3.5  # above this the roof is light grey
FRONT_ROUNDING = 0.18  # radius of the cab front's corners and top edge: pressed sheet metal, not a soft curve
END_ROUNDING = 0.08  # the plain coach ends
# The cab front curves: in plan its corners sweep back from the centre,
# and above the lamp band it leans back. The body blends into that shape
# over the last FRONT_BLEND metres.
FRONT_BULGE = 0.1
# Side profile of the cab front, measured from a side photo of a Central
# Railway rake. The upper three quarters is one steady backward slope of
# about 26 degrees, rounding only slightly into the roof. The curvature is
# concentrated low down: a knee turns the slope into the upright lower
# nose, which stands furthest forward, and a rounded chin tucks its bottom
# edge back into the white lower body. The top of the cab ends up about a
# metre behind the lower nose.
FRONT_CHIN_TOP_Z = 1.4  # below this the nose's lower edge curves back...
FRONT_CHIN = 0.18  # ...this far by the bottom of the body
FRONT_RAKE_FROM_Z = 1.85  # the lower nose is upright up to here
FRONT_KNEE = 0.3  # how tightly it turns into the slope (a hyperbola's radius, metres)
FRONT_LEAN = 0.48  # tan of the slope (~26 degrees)
FRONT_ROLL_FROM_Z = 3.5  # above this the slope rounds slightly into the roof
FRONT_ROLL = 0.1  # extra setback that rounding adds by roof height
# The body is trimmed to the nose, not slanted: only the last
# FRONT_TRIM_DEPTH metres behind the nose line are drawn in to meet it, so
# the sides, roof and cab door further back stay exactly where they are.
FRONT_TRIM_DEPTH = 0.5
FRONT_BLEND = 1.8  # the stretch sliced finely enough to follow the nose
FRONT_TAPER = 0.03  # the cab narrows by this fraction of its width towards the nose

# Livery: white sides with a purple band low down and a thin purple stripe
# high up under the roof. The cab front is white with a yellow panel, and a
# thin purple stripe under it that runs into the side band.
SIDE_BAND_BOTTOM_Z = 1.25
SIDE_BAND_TOP_Z = 1.74
STRIPE_BOTTOM_Z = 3.1
STRIPE_TOP_Z = 3.17
FRONT_STRIPE_BOTTOM_Z = SIDE_BAND_BOTTOM_Z
FRONT_STRIPE_TOP_Z = 1.4
# The cab front is framed by a thick white structural surround (the body's
# rounded corners and top edge); the yellow is a panel set into the face
# inside it.
YELLOW_PANEL_WIDTH = 2.96
YELLOW_PANEL_TOP_Z = 3.66
YELLOW_PANEL_RECESS = 0.035
YELLOW_PANEL_BOTTOM_Z = 1.43  # just above the purple stripe

# Doorways: double-leaf sliding doors, recessed into the side.
DOOR_WIDTH = 1.3
DOOR_TOP_Z = 3.0
DOOR_RECESS = 0.045
DOOR_WINDOW_WIDTH = 0.24
DOOR_WINDOW_BOTTOM_Z = 2.0
DOOR_WINDOW_TOP_Z = 2.85
CAB_DOOR_Y = HALF_LENGTH - 1.45  # the driver's door, just behind the sloping cab front
CAB_DOOR_WIDTH = 0.62

# Passenger windows: narrow and upright, in pairs between the doorways.
WINDOW_SILL_Z = 1.95
WINDOW_HEIGHT = 1.0
WINDOW_WIDTH = 0.5
WINDOW_PAIR_GAP = 0.16  # pillar between the two windows of a pair
WINDOW_RECESS = 0.05
SHUTTER_DROP = 0.4  # how far the louvred shutter is pulled down

# Cab front.
LAMP_BAND_Z = 1.8  # centre of the black lamp band
LAMP_BAND_HEIGHT = 0.4
LAMP_BAND_WIDTH = 2.84
WINDSCREEN_BOTTOM_Z = 2.33
WINDSCREEN_TOP_Z = 3.1
WINDSCREEN_WIDTH = 1.14
WINDSCREEN_PILLAR = 0.46  # carries the train number and the electrification logo
WINDSCREEN_FLARE = 0.03  # each windscreen is this much wider at the top (a slight trapezoid)
DESTINATION_BOTTOM_Z = 3.28
DESTINATION_HEIGHT = 0.21
HEADLIGHT_Z = 3.72  # the upper headlight, above and between the destination boards

# The AC rakes (ICF-built) are unpainted stainless steel: a blue band low
# down the side with a thin red line under it and a red stripe just above
# it, and a blue stripe along the top of the side. Round the cab corner the
# band and stripe slope down to the front, where a blue band runs across
# under the yellow panel; the panel has a thick red border inside a
# stainless surround.
AC_RED_LINE_BOTTOM_Z = 1.06
AC_BAND_BOTTOM_Z = 1.12
AC_BAND_TOP_Z = 1.72
AC_STRIPE_GAP = 0.06  # stainless between the blue band and the red stripe
AC_STRIPE_HEIGHT = 0.12
AC_TOP_STRIPE_BOTTOM_Z = 3.04  # blue from here to the top of the side
AC_FRONT_BAND_TOP_Z = 1.42
AC_BORDER_WIDTH = 2.98  # outside of the red border
AC_BORDER_TOP_Z = 3.68
AC_BORDER_RECESS = 0.012
AC_YELLOW_WIDTH = 2.76
AC_YELLOW_TOP_Z = 3.57
AC_YELLOW_BOTTOM_Z = 1.53
# Wide sealed windows; on the cab car, a column of louvres and a blue panel
# behind the driver's door.
AC_WINDOW_WIDTH = 1.15
AC_WINDOW_SILL_Z = 2.0
AC_WINDOW_HEIGHT = 0.82
AC_WINDOW_SPACING = 0.45  # least side between neighbouring windows
AC_LOUVRE_Y = CAB_DOOR_Y - 0.72
AC_LOUVRE_WIDTH = 0.34
AC_LOUVRES_Z = ((1.45, 1.95), (2.5, 2.9))  # (bottom, top) of each louvre panel
AC_PANEL_Y = CAB_DOOR_Y - 1.55
AC_PANEL_WIDTH = 0.72
AC_PANEL_TOP_Z = 2.9

BOGIE_CENTRES = (-7.2, 7.2)
BOGIE_WHEELBASE = 2.896
WHEEL_RADIUS = 0.476
WHEEL_WIDTH = 0.135


@dataclass(frozen=True)
class Variant:
    """One kind of coach in a rake."""

    name: str
    cab: bool  # a driving cab at the +Y end
    pantograph: bool
    door_centres: tuple[float, ...]
    ac: bool = False


VARIANTS: dict[str, Variant] = {
    "cab": Variant("coach_cab_nonac", cab=True, pantograph=False, door_centres=(-6.8, 0.0, 6.5)),
    "motor": Variant("coach_motor_nonac", cab=False, pantograph=True, door_centres=(-6.3, 0.0, 6.3)),
    "trailer": Variant("coach_trailer_nonac", cab=False, pantograph=False, door_centres=(-6.3, 0.0, 6.3)),
    # The AC cab car's last doorway is further forward, leaving room for
    # the louvres and blue panel behind the driver's door.
    "cab_ac": Variant("coach_cab_ac", cab=True, pantograph=False, door_centres=(-6.8, 0.0, 5.9), ac=True),
    "motor_ac": Variant("coach_motor_ac", cab=False, pantograph=True, door_centres=(-6.3, 0.0, 6.3), ac=True),
    "trailer_ac": Variant("coach_trailer_ac", cab=False, pantograph=False, door_centres=(-6.3, 0.0, 6.3), ac=True),
}

# -- materials -------------------------------------------------------------------


@dataclass(frozen=True)
class Finish:
    colour: tuple[float, float, float]
    metallic: float = 0.0
    roughness: float = 0.5
    emission: tuple[float, float, float] | None = None
    emission_strength: float = 0.0


FINISHES: dict[str, Finish] = {
    "Body": Finish((0.82, 0.83, 0.83), metallic=0.05, roughness=0.4),
    "DoorLeaf": Finish((0.76, 0.77, 0.77), metallic=0.1, roughness=0.45),
    "Roof": Finish((0.62, 0.64, 0.65), roughness=0.7),
    "Purple": Finish((0.37, 0.05, 0.34), roughness=0.36),
    "Glass": Finish((0.035, 0.05, 0.065), metallic=0.1, roughness=0.04),
    "Grille": Finish((0.08, 0.085, 0.09), metallic=0.6, roughness=0.5),
    "Tread": Finish((0.45, 0.46, 0.47), metallic=0.6, roughness=0.5),
    "Steel": Finish((0.62, 0.64, 0.67), metallic=0.9, roughness=0.25),
    "CabYellow": Finish((0.86, 0.63, 0.008), roughness=0.33),
    "CabBlack": Finish((0.012, 0.012, 0.014), roughness=0.55),
    "BufferBeam": Finish((0.5, 0.51, 0.52), metallic=0.6, roughness=0.4),
    "Chrome": Finish((0.8, 0.81, 0.82), metallic=1.0, roughness=0.15),
    "SignRed": Finish((0.62, 0.02, 0.02), roughness=0.45),
    "Frame": Finish((0.6, 0.62, 0.64), metallic=0.7, roughness=0.35),
    "Seam": Finish((0.3, 0.31, 0.32), roughness=0.6),
    "LampHousing": Finish((0.05, 0.05, 0.055), metallic=0.3, roughness=0.35),
    "AmberLight": Finish((0.85, 0.18, 0.01), emission=(1.0, 0.22, 0.0), emission_strength=1.2),
    "DestinationText": Finish((1.0, 0.5, 0.05), emission=(1.0, 0.5, 0.05), emission_strength=2.5),
    "Underframe": Finish((0.06, 0.063, 0.068), metallic=0.3, roughness=0.75),
    "Bogie": Finish((0.035, 0.035, 0.04), metallic=0.4, roughness=0.6),
    "Wheel": Finish((0.35, 0.34, 0.33), metallic=0.9, roughness=0.4),
    "Rubber": Finish((0.015, 0.015, 0.015), roughness=0.9),
    "SignWhite": Finish((0.9, 0.9, 0.88), roughness=0.5),
    "Insulator": Finish((0.3, 0.07, 0.04), roughness=0.25),
    "PantographRed": Finish((0.5, 0.04, 0.03), metallic=0.3, roughness=0.45),
    "Headlight": Finish((1.0, 0.97, 0.88), emission=(1.0, 0.95, 0.82), emission_strength=5.0),
    "TailLight": Finish((0.75, 0.04, 0.03), emission=(1.0, 0.06, 0.03), emission_strength=2.5),
    "DestinationBoard": Finish((0.03, 0.035, 0.04), metallic=0.1, roughness=0.08, emission=(1.0, 0.45, 0.05), emission_strength=0.0),
    "Stainless": Finish((0.55, 0.57, 0.6), metallic=0.55, roughness=0.3),
    "AcBlue": Finish((0.013, 0.07, 0.485), roughness=0.35),
    "AcRed": Finish((0.75, 0.017, 0.01), roughness=0.38),
}

Materials = dict[str, bpy.types.Material]


def principled(material: bpy.types.Material) -> bpy.types.ShaderNode:
    if material.node_tree is None:  # node trees are on by default from Blender 5
        material.use_nodes = True
    return material.node_tree.nodes["Principled BSDF"]


def make_materials() -> Materials:
    materials = {}
    for name, finish in FINISHES.items():
        material = bpy.data.materials.new(name)
        bsdf = principled(material)
        bsdf.inputs["Base Color"].default_value = (*finish.colour, 1.0)
        bsdf.inputs["Metallic"].default_value = finish.metallic
        bsdf.inputs["Roughness"].default_value = finish.roughness
        if finish.emission is not None:
            bsdf.inputs["Emission Color"].default_value = (*finish.emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = finish.emission_strength
        materials[name] = material
    return materials


# -- mesh helpers --------------------------------------------------------------


def new_object(name: str, mesh: bpy.types.Mesh, collection: bpy.types.Collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def box(
    name: str,
    centre: tuple[float, float, float],
    size: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    bevel: float = 0.0,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((*size, 1.0)))
    if bevel > 0:
        bmesh.ops.bevel(
            bm, geom=bm.edges[:], offset=min(bevel, min(size) * 0.49), segments=3, profile=0.5, affect="EDGES", clamp_overlap=True
        )
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = new_object(name, mesh, collection)
    obj.location = centre
    return obj


def rounded_panel(
    name: str,
    centre: tuple[float, float, float],
    size: tuple[float, float, float],
    corner: float,
    axis: str,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    """A box whose corners are rounded only in the plane facing `axis`
    (for window and door openings: round corners, square reveals)."""
    obj = box(name, centre, size, material, collection)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    along = {"x": 0, "y": 1}[axis]
    edges = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co)[along]) > 1e-6]
    bmesh.ops.bevel(bm, geom=edges, offset=corner, segments=4, profile=0.5, affect="EDGES", clamp_overlap=True)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def cylinder(
    name: str,
    centre: tuple[float, float, float],
    radius: float,
    depth: float,
    axis: str,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    segments: int = 24,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    rotation = {"x": Matrix.Rotation(math.pi / 2, 4, "Y"), "y": Matrix.Rotation(math.pi / 2, 4, "X"), "z": Matrix()}[axis]
    bmesh.ops.transform(bm, matrix=rotation, verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = new_object(name, mesh, collection)
    obj.location = centre
    return obj


def rod(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    segments: int = 8,
) -> bpy.types.Object:
    """A round bar from `start` to `end`."""
    a, b = Vector(start), Vector(end)
    obj = cylinder(name, tuple((a + b) / 2), radius, (b - a).length, "z", material, collection, segments)
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return obj


def cone(
    name: str,
    centre: tuple[float, float, float],
    radius_back: float,
    radius_front: float,
    depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    """A cone along +Y (its wide end forward), for the horn's bell."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=radius_back, radius2=radius_front, depth=depth)
    bmesh.ops.transform(bm, matrix=Matrix.Rotation(-math.pi / 2, 4, "X"), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = new_object(name, mesh, collection)
    obj.location = centre
    return obj


def lamp(
    name: str,
    centre: tuple[float, float, float],
    radius: float,
    lens: bpy.types.Material,
    rim: bpy.types.Material,
    collection: bpy.types.Collection,
    depth: float = 0.05,
) -> list[bpy.types.Object]:
    """A lamp facing +Y: a rim with a real bore, the lens recessed at its
    back, domed slightly like glass."""
    x, y, z = centre
    mesh = bpy.data.meshes.new(f"{name}_rim")
    bm = bmesh.new()
    segments = 24
    outer_r, inner_r = radius * 1.28, radius

    def circle(r: float, dy: float) -> list[bmesh.types.BMVert]:
        return [bm.verts.new((r * math.cos(2 * math.pi * i / segments), dy, r * math.sin(2 * math.pi * i / segments))) for i in range(segments)]

    outer_front, inner_front, inner_back, outer_back = circle(outer_r, 0), circle(inner_r, 0), circle(inner_r, -depth), circle(outer_r, -depth)
    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((outer_front[i], outer_front[j], inner_front[j], inner_front[i]))
        bm.faces.new((inner_front[i], inner_front[j], inner_back[j], inner_back[i]))
        bm.faces.new((outer_back[i], outer_back[j], outer_front[j], outer_front[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(rim)
    rim_obj = new_object(f"{name}_rim", mesh, collection)
    rim_obj.location = centre
    glass = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=8, radius=inner_r)
    bmesh.ops.scale(bm, vec=(1.0, 0.25, 1.0), verts=bm.verts)
    bm.to_mesh(glass)
    bm.free()
    glass.materials.append(lens)
    lens_obj = new_object(name, glass, collection)
    lens_obj.location = (x, y - depth * 0.7, z)
    return [rim_obj, lens_obj]


def text_object(
    name: str,
    text: str,
    size: float,
    centre: tuple[float, float, float],
    rotation: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    weight: float = 0.0,
) -> bpy.types.Object:
    """Lettering as a thin mesh. The text lies in its local XY plane,
    reading along +X and facing +Z, before `rotation`. `weight` thickens
    the strokes (Blender's built-in font has no bold)."""
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.extrude = 0.003
    curve.offset = weight
    curve.resolution_u = 2
    holder = bpy.data.objects.new(f"{name}_curve", curve)
    collection.objects.link(holder)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(holder.evaluated_get(depsgraph), depsgraph=depsgraph)
    bpy.data.objects.remove(holder)
    bpy.data.curves.remove(curve)
    mesh.materials.clear()
    mesh.materials.append(material)
    obj = new_object(name, mesh, collection)
    obj.location = centre
    obj.rotation_euler = rotation
    return obj


# Rotations that stand lettering up on each face of the coach.
FACING_FRONT = (math.pi / 2, 0.0, math.pi)  # faces +Y, reads towards -X (the viewer's right)
FACING_LEFT_SIDE = (math.pi / 2, 0.0, math.pi / 2)  # faces +X, reads towards +Y
FACING_RIGHT_SIDE = (math.pi / 2, 0.0, -math.pi / 2)  # faces -X, reads towards -Y


def apply_modifiers(obj: bpy.types.Object) -> None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    bpy.data.meshes.remove(old)


def join(target: bpy.types.Object, parts: Iterable[bpy.types.Object]) -> None:
    """Merge `parts` into `target`, keeping each part's material."""
    parts = list(parts)
    if not parts:
        return
    with bpy.context.temp_override(
        active_object=target,
        selected_editable_objects=[target, *parts],
        selected_objects=[target, *parts],
    ):
        bpy.ops.object.join()


# -- the curved cab front ------------------------------------------------------------


CHIN_SPAN = FRONT_CHIN_TOP_Z - BODY_BOTTOM_Z
ROLL_SPAN = ROOF_Z - FRONT_ROLL_FROM_Z


def chin_depth(z: float) -> float:
    """0 above the chin, 1 at the bottom of the body; 0 below the body
    (the pilot and buffers stick out again there)."""
    if z < BODY_BOTTOM_Z - 1e-3:
        return 0.0
    return min(max((FRONT_CHIN_TOP_Z - z) / CHIN_SPAN, 0.0), 1.0)


def front_profile(z: float) -> float:
    """How far back the cab front's side profile is at height `z`,
    relative to the upright lower nose."""
    chin = chin_depth(z)
    rise = max(z - FRONT_RAKE_FROM_Z, 0.0)
    lean = FRONT_LEAN * (math.hypot(rise, FRONT_KNEE) - FRONT_KNEE)
    roll = max((z - FRONT_ROLL_FROM_Z) / ROLL_SPAN, 0.0)
    return FRONT_CHIN * chin**2 + lean + FRONT_ROLL * roll**2


def front_profile_slope(z: float) -> float:
    """d(front_profile)/dz: how far the front leans back per metre of rise
    (negative on the chin, which leans forward as it rises)."""
    chin = chin_depth(z)
    rise = max(z - FRONT_RAKE_FROM_Z, 0.0)
    lean = FRONT_LEAN * rise / math.hypot(rise, FRONT_KNEE)
    roll = max((z - FRONT_ROLL_FROM_Z) / ROLL_SPAN, 0.0)
    return -2 * FRONT_CHIN * chin / CHIN_SPAN + lean + 2 * FRONT_ROLL * roll / ROLL_SPAN


def front_setback(x: float, z: float) -> float:
    """How far the nose surface at (x, z) sits behind the foot of the nose:
    its side profile plus its curve in plan."""
    return FRONT_BULGE * min((x / HALF_WIDTH) ** 2, 1.0) + front_profile(z)


def move_with_front(x: float, y: float, z: float) -> tuple[float, float]:
    """Where a point on or just in front of the nose goes: back with the
    nose surface as a whole, so recesses carved into it keep their depth."""
    return x * (1 - FRONT_TAPER), y - front_setback(x, z)


def trim_to_front(x: float, y: float, z: float) -> tuple[float, float]:
    """Where a point of the flat-ended body goes once the body is trimmed
    to the curved nose. Points more than FRONT_TRIM_DEPTH behind the nose
    line stay put; points between there and the old flat end are drawn in
    evenly (so the sides and roof keep their shape, just shorter); points
    ahead of the old end, like the fronts of cutters, move back with the
    nose. The cab also narrows slightly towards the nose."""
    setback = front_setback(x, z)
    start = HALF_LENGTH - setback - FRONT_TRIM_DEPTH
    if y <= start:
        return x, y
    if y >= HALF_LENGTH:
        new_y = y - setback
    else:
        new_y = start + (y - start) * FRONT_TRIM_DEPTH / (FRONT_TRIM_DEPTH + setback)
    toward_nose = min((y - start) / (HALF_LENGTH - start), 1.0)
    return x * (1 - FRONT_TAPER * toward_nose), new_y


def front_facing(x: float, z: float) -> tuple[float, float]:
    """Yaw and pitch (radians) that turn something mounted on the cab
    front to face along the curved surface at (x, z)."""
    yaw = math.atan(-2 * FRONT_BULGE * x / HALF_WIDTH**2)
    pitch = math.atan(front_profile_slope(z))
    return yaw, pitch


def slice_region(bm: bmesh.types.BMesh, axis: int, start: float, stop: float, step: float, in_region: Callable[[bmesh.types.BMFace], bool]) -> None:
    """Cut the faces `in_region` accepts with planes across `axis`, so they
    can bend smoothly."""
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    value = start
    while value <= stop + 1e-9:
        faces = [f for f in bm.faces if in_region(f)]
        geom = list({e for f in faces for e in f.edges}) + faces + list({v for f in faces for v in f.verts})
        point = [0.0, 0.0, 0.0]
        point[axis] = value
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=point, plane_no=normal)
        value += step


def bend_to_front(bm: bmesh.types.BMesh, step: float, rigid: bool = False) -> None:
    """Slice the front of `bm` finely and fit it to the curved nose:
    trimming it (the body) or, if `rigid`, moving it back with the nose
    surface (cutters and panels on the nose)."""

    def near_front(face: bmesh.types.BMFace) -> bool:
        return all(v.co.y > HALF_LENGTH - FRONT_BLEND - 1e-4 for v in face.verts)

    slice_region(bm, 0, -HALF_WIDTH, HALF_WIDTH, step, near_front)
    slice_region(bm, 2, 0.0, ROOF_Z + 0.4, step, near_front)
    for v in bm.verts:
        x, y, z = v.co
        v.co.x, v.co.y = move_with_front(x, y, z) if rigid else trim_to_front(x, y, z)


def bend_object_to_front(obj: bpy.types.Object, step: float = 0.1) -> None:
    """`bend_to_front` for a separate object: one on the nose (a windscreen
    cutter, the bumper) moves with it; one on the cab side (the driver's
    door) is trimmed like the body, which leaves it where it is."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.transform(bm, matrix=obj.matrix_basis, verts=bm.verts)
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, 0)
    on_nose = max(v.co.y for v in bm.verts) > HALF_LENGTH - 0.05
    bend_to_front(bm, step, rigid=on_nose)
    bm.to_mesh(obj.data)
    bm.free()


def mount_on_front(obj: bpy.types.Object, lettering: bool = False) -> None:
    """Move a fitting back onto the curved front and turn it to face out.
    A fitting's own spin within the front's plane (about Y, like a wiper
    or the bars of the X plate) is applied first, then the tilt and turn
    onto the surface. Lettering is stood up by a quarter turn about X,
    which flips the sense of the tilt."""
    if not lettering:
        obj.rotation_mode = "YXZ"
    x, _, z = obj.location
    obj.location.y -= front_setback(x, z)
    obj.location.x = x * (1 - FRONT_TAPER)
    yaw, pitch = front_facing(x, z)
    obj.rotation_euler.x += -pitch if lettering else pitch
    obj.rotation_euler.z += yaw


# -- body shell ------------------------------------------------------------------


def body_profile(segments: int = 20) -> list[tuple[float, float]]:
    """The coach's cross-section, (x, z), anticlockwise from bottom right:
    vertical sides, then a superellipse roof with rounded cant rails."""
    points = [(HALF_WIDTH, BODY_BOTTOM_Z)]
    exponent = 2 / ROOF_SQUARENESS
    for i in range(segments + 1):
        t = math.pi * i / segments
        c, s = math.cos(t), math.sin(t)
        x = HALF_WIDTH * math.copysign(abs(c) ** exponent, c)
        z = SIDE_TOP_Z + (ROOF_Z - SIDE_TOP_Z) * abs(s) ** exponent
        points.append((x, z))
    points.append((-HALF_WIDTH, BODY_BOTTOM_Z))
    return points


SHELL_MATERIALS = ("Body", "Roof", "Purple", "CabYellow", "Stainless", "AcBlue", "AcRed")

# Round the cab corner the thick side band's top slopes down into the thin
# front stripe, from BAND_SLOPE_START behind the corner to BAND_SLOPE_END.
BAND_SLOPE_START = HALF_LENGTH - FRONT_ROUNDING - 0.7
BAND_SLOPE_END = HALF_LENGTH - FRONT_ROUNDING * 0.35


def band_top(y: float, ac: bool = False) -> float:
    """Height of the side band's top edge at `y` along the cab car."""
    side_top, front_top = (AC_BAND_TOP_Z, AC_FRONT_BAND_TOP_Z) if ac else (SIDE_BAND_TOP_Z, FRONT_STRIPE_TOP_Z)
    t = min(max((y - BAND_SLOPE_START) / (BAND_SLOPE_END - BAND_SLOPE_START), 0.0), 1.0)
    return side_top + (front_top - side_top) * t


def cut_band_slope(bm: bmesh.types.BMesh, ac: bool) -> None:
    """Slice the cab corner along the band's sloping top edge (and, on an
    AC car, the red stripe's edges parallel to it), so each is one clean
    line rather than steps."""
    side_top, front_top = (AC_BAND_TOP_Z, AC_FRONT_BAND_TOP_Z) if ac else (SIDE_BAND_TOP_Z, FRONT_STRIPE_TOP_Z)
    slope = (side_top - front_top) / (BAND_SLOPE_END - BAND_SLOPE_START)
    offsets = (0.0, AC_STRIPE_GAP, AC_STRIPE_GAP + AC_STRIPE_HEIGHT) if ac else (0.0,)
    for offset in offsets:
        faces = [f for f in bm.faces if all(BAND_SLOPE_START - 1e-4 <= v.co.y <= BAND_SLOPE_END + 1e-4 for v in f.verts)]
        geom = faces + list({e for f in faces for e in f.edges}) + list({v for f in faces for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, BAND_SLOPE_START, side_top + offset), plane_no=Vector((0, slope, 1)).normalized())


def is_cab_end(variant: Variant, centre: Vector, normal: Vector) -> bool:
    """Whether a face is on the cab car's front or the corners round it."""
    return variant.cab and centre.y > BAND_SLOPE_START - 1e-4 and centre.z < ROOF_Z + 0.1 and (abs(normal.x) > 0.3 or normal.y > 0.05)


def standard_livery(variant: Variant, c: Vector, n: Vector) -> str:
    side = abs(n.x) > 0.7
    if is_cab_end(variant, c, n):
        # The thick side band slopes down into the thin front stripe
        # round the corner; above it the cab front is yellow.
        if c.z < FRONT_STRIPE_BOTTOM_Z:
            return "Body"
        if c.z < band_top(c.y):
            return "Purple"
        if c.z > ROOF_PAINT_Z and n.z > 0.8:
            return "Roof"
        return "Body"
    if c.z > ROOF_PAINT_Z:
        return "Roof"
    if side and (SIDE_BAND_BOTTOM_Z < c.z < SIDE_BAND_TOP_Z or STRIPE_BOTTOM_Z < c.z < STRIPE_TOP_Z):
        return "Purple"
    return "Body"


def ac_livery(variant: Variant, c: Vector, n: Vector) -> str:
    cab_end = is_cab_end(variant, c, n)
    if cab_end or abs(n.x) > 0.7:
        # Red line, blue band, a gap, the red stripe; round the cab corner
        # the band and stripe slope down to the front, where the stripe
        # meets the red border of the yellow panel.
        top = band_top(c.y, ac=True) if cab_end else AC_BAND_TOP_Z
        if c.z < AC_RED_LINE_BOTTOM_Z:
            return "Stainless"
        if c.z < AC_BAND_BOTTOM_Z:
            return "AcRed"
        if c.z < top:
            return "AcBlue"
        if top + AC_STRIPE_GAP < c.z < top + AC_STRIPE_GAP + AC_STRIPE_HEIGHT:
            return "AcRed"
        if not cab_end and AC_TOP_STRIPE_BOTTOM_Z < c.z < SIDE_TOP_Z:
            return "AcBlue"
    if c.z > ROOF_PAINT_Z and (not cab_end or n.z > 0.8):
        return "Roof"
    return "Stainless"


def paint_shell(bm: bmesh.types.BMesh, variant: Variant) -> None:
    """Livery by where each face is and which way it faces. On the cab car
    it runs on the flat-fronted shell, before the front is bent, so the
    colour edges follow clean lines round the cab corners; the yellow panel
    is carved in afterwards."""
    slot = {name: i for i, name in enumerate(SHELL_MATERIALS)}
    livery = ac_livery if variant.ac else standard_livery
    bm.normal_update()
    for face in bm.faces:
        face.material_index = slot[livery(variant, face.calc_center_median(), face.normal)]


def make_shell(variant: Variant, materials: Materials, collection: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(variant.name)
    bm = bmesh.new()
    ring = [bm.verts.new((x, -HALF_LENGTH, z)) for x, z in body_profile()]
    rear_cap = bm.faces.new(ring)
    extruded = bmesh.ops.extrude_face_region(bm, geom=[rear_cap])
    front_cap = next(f for f in extruded["geom"] if isinstance(f, bmesh.types.BMFace))
    bmesh.ops.translate(bm, vec=(0, LENGTH, 0), verts=front_cap.verts[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()

    # Round the cab front's corners and top edge; soften the plain ends.
    def not_bottom(edge: bmesh.types.BMEdge) -> bool:
        return not all(v.co.z < BODY_BOTTOM_Z + 1e-4 for v in edge.verts)

    front_edges = [e for e in front_cap.edges if not_bottom(e)]
    rear_edges = [e for e in rear_cap.edges if not_bottom(e)]
    front_rounding = FRONT_ROUNDING if variant.cab else END_ROUNDING
    bmesh.ops.bevel(bm, geom=front_edges, offset=front_rounding, segments=4 if variant.cab else 3, profile=0.5, affect="EDGES", clamp_overlap=True)
    bmesh.ops.bevel(bm, geom=rear_edges, offset=END_ROUNDING, segments=3, profile=0.5, affect="EDGES", clamp_overlap=True)

    # Slices where the livery changes colour, and across the cab end so it
    # can bend into the curved front.
    if variant.ac:
        stripe_edges = (AC_STRIPE_GAP, AC_STRIPE_GAP + AC_STRIPE_HEIGHT)
        cuts = (
            AC_RED_LINE_BOTTOM_Z,
            AC_BAND_BOTTOM_Z,
            AC_FRONT_BAND_TOP_Z,
            *(AC_FRONT_BAND_TOP_Z + d for d in stripe_edges),
            AC_BAND_TOP_Z,
            *(AC_BAND_TOP_Z + d for d in stripe_edges),
            AC_TOP_STRIPE_BOTTOM_Z,
            ROOF_PAINT_Z,
        )
    else:
        cuts = (SIDE_BAND_BOTTOM_Z, FRONT_STRIPE_TOP_Z, SIDE_BAND_TOP_Z, STRIPE_BOTTOM_Z, STRIPE_TOP_Z, ROOF_PAINT_Z)
    for z in cuts:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0, 1))
    if variant.cab:
        for k in range(1, 8):
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, HALF_LENGTH - FRONT_BLEND * k / 7, 0), plane_no=(0, 1, 0))
        for y in (BAND_SLOPE_START, BAND_SLOPE_END):
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, y, 0), plane_no=(0, 1, 0))
        cut_band_slope(bm, variant.ac)
    paint_shell(bm, variant)
    if variant.cab:
        bend_to_front(bm, step=0.1)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    for name in SHELL_MATERIALS:
        mesh.materials.append(materials[name])
    return new_object(variant.name, mesh, collection)


# -- openings --------------------------------------------------------------------


@dataclass(frozen=True)
class FrontPanel:
    """A coloured panel set into the cab front."""

    material: str
    width: float
    bottom: float
    top: float
    recess: float
    top_corner: float
    bottom_corner: float


def front_panels(variant: Variant) -> list[FrontPanel]:
    """The cab front's panels, outermost first; the last is the yellow one."""
    if variant.ac:
        return [
            FrontPanel("AcRed", AC_BORDER_WIDTH, AC_FRONT_BAND_TOP_Z, AC_BORDER_TOP_Z, AC_BORDER_RECESS, 0.5, 0.2),
            FrontPanel("CabYellow", AC_YELLOW_WIDTH, AC_YELLOW_BOTTOM_Z, AC_YELLOW_TOP_Z, YELLOW_PANEL_RECESS, 0.42, 0.12),
        ]
    return [FrontPanel("CabYellow", YELLOW_PANEL_WIDTH, YELLOW_PANEL_BOTTOM_Z, YELLOW_PANEL_TOP_Z, YELLOW_PANEL_RECESS, 0.45, 0.06)]


def window_bays(variant: Variant) -> list[tuple[float, float]]:
    """Stretches of side between the ends and the doorways."""
    edges = [-HALF_LENGTH + 0.45]
    for centre in variant.door_centres:
        edges += [centre - DOOR_WIDTH / 2 - 0.32, centre + DOOR_WIDTH / 2 + 0.32]
    if not variant.cab:
        edges.append(HALF_LENGTH - 0.45)
    elif variant.ac:
        edges.append(AC_PANEL_Y - AC_PANEL_WIDTH / 2 - 0.25)
    else:
        edges.append(CAB_DOOR_Y - CAB_DOOR_WIDTH / 2 - 0.25)
    return list(zip(edges[::2], edges[1::2], strict=True))


def window_centres(variant: Variant) -> list[float]:
    """Windows come in pairs between the doorways; a stretch too short for
    a pair gets a single window. AC cars have wide single windows instead,
    spread evenly along each stretch."""
    if variant.ac:
        centres = []
        for start, end in window_bays(variant):
            room = end - start
            count = int((room + AC_WINDOW_SPACING) // (AC_WINDOW_WIDTH + AC_WINDOW_SPACING))
            spacing = (room - count * AC_WINDOW_WIDTH) / (count + 1)
            centres += [start + spacing * (i + 1) + AC_WINDOW_WIDTH * (i + 0.5) for i in range(count)]
        return centres
    pair = 2 * WINDOW_WIDTH + WINDOW_PAIR_GAP
    centres = []
    for start, end in window_bays(variant):
        room = end - start
        if room < WINDOW_WIDTH + 0.2:
            continue
        if room < pair + 0.3:
            centres.append((start + end) / 2)
            continue
        pairs = max(1, int((room + 0.45) // (pair + 0.45)))
        spacing = (room - pairs * pair) / (pairs + 1)
        for i in range(pairs):
            left = start + spacing * (i + 1) + pair * i
            centres += [left + WINDOW_WIDTH / 2, left + WINDOW_WIDTH * 1.5 + WINDOW_PAIR_GAP]
    return centres


def panel_seams(variant: Variant) -> list[float]:
    """Where the side's body panels join: mid-way across the wider pillars
    between windows (not the narrow pillar inside a pair). The AC cars'
    stainless sides show no painted seams."""
    if variant.ac:
        return []
    centres = sorted(window_centres(variant))
    seams = []
    for a, b in zip(centres, centres[1:], strict=False):
        middle = (a + b) / 2
        if b - a - WINDOW_WIDTH > 0.4 and not any(abs(middle - d) < DOOR_WIDTH for d in variant.door_centres):
            seams.append(middle)
    return seams


def door_cutters(
    y: float,
    width: float,
    leaves: int,
    into: Callable[[float], float],
    materials: Materials,
    cutters: bpy.types.Collection,
    leaf: str = "DoorLeaf",
    band: tuple[str, float, float] | None = ("Purple", SIDE_BAND_BOTTOM_Z, SIDE_BAND_TOP_Z),
) -> None:
    """A recessed sliding door: a steel trim, the leaves (the livery's
    `band` across them, as (material, bottom, top), if it has one), the gap
    between leaves and a narrow window in each."""
    mid_z = (FLOOR_Z + DOOR_TOP_Z) / 2
    height = DOOR_TOP_Z - FLOOR_Z
    rounded_panel("cut_door_trim", (into(0.008), y, mid_z + 0.02), (0.208, width + 0.1, height + 0.08), 0.1, "x", materials["Frame"], cutters)
    rounded_panel("cut_door_leaf", (into(DOOR_RECESS), y, mid_z), (DOOR_RECESS + 0.2, width, height), 0.06, "x", materials[leaf], cutters)
    if band is not None:
        band_material, band_bottom, band_top_z = band
        box("cut_door_band", (into(DOOR_RECESS + 0.002), y, (band_bottom + band_top_z) / 2), (DOOR_RECESS + 0.202, width - 0.02, band_top_z - band_bottom), materials[band_material], cutters)
    leaf_width = width / leaves
    for k in range(leaves):
        leaf_y = y - width / 2 + leaf_width * (k + 0.5)
        window_width = min(DOOR_WINDOW_WIDTH, leaf_width - 0.2)
        window_mid = (DOOR_WINDOW_BOTTOM_Z + DOOR_WINDOW_TOP_Z) / 2
        rounded_panel("cut_door_window", (into(DOOR_RECESS + 0.03), leaf_y, window_mid), (DOOR_RECESS + 0.23, window_width, DOOR_WINDOW_TOP_Z - DOOR_WINDOW_BOTTOM_Z), 0.05, "x", materials["Glass"], cutters)
    for k in range(1, leaves):
        box("cut_door_gap", (into(DOOR_RECESS + 0.015), y - width / 2 + leaf_width * k, mid_z), (DOOR_RECESS + 0.215, 0.014, height - 0.02), materials["Seam"], cutters)


def make_cutters(variant: Variant, materials: Materials, cutters: bpy.types.Collection) -> None:
    """Shapes carved out of the body. The faces they leave take the
    cutter's material: windows show the glass, doors their leaves, the
    shallow frames round them steel or black."""
    window_mid_z = WINDOW_SILL_Z + WINDOW_HEIGHT / 2
    for side in (1, -1):
        face = side * HALF_WIDTH

        def into(depth: float, face: float = face, side: int = side) -> float:
            return face - side * (depth / 2 - 0.1)

        if variant.ac:
            # Stainless doors with no band across them, and wide sealed
            # windows in black rubber, nearly flush.
            for y in variant.door_centres:
                door_cutters(y, DOOR_WIDTH, 2, into, materials, cutters, leaf="Stainless", band=None)
            ac_window_mid_z = AC_WINDOW_SILL_Z + AC_WINDOW_HEIGHT / 2
            for y in window_centres(variant):
                rounded_panel("cut_window_frame", (into(0.008), y, ac_window_mid_z), (0.208, AC_WINDOW_WIDTH + 0.07, AC_WINDOW_HEIGHT + 0.07), 0.1, "x", materials["CabBlack"], cutters)
                rounded_panel("cut_window", (into(0.025), y, ac_window_mid_z), (0.225, AC_WINDOW_WIDTH, AC_WINDOW_HEIGHT), 0.08, "x", materials["Glass"], cutters)
            if variant.cab:
                door_cutters(CAB_DOOR_Y, CAB_DOOR_WIDTH, 1, into, materials, cutters, leaf="Stainless", band=("AcBlue", AC_BAND_BOTTOM_Z, AC_BAND_TOP_Z))
                # Behind the driver's door: the louvre panels (slats added
                # with the side details) and the blue panel, which runs
                # down into the band.
                for bottom, top in AC_LOUVRES_Z:
                    rounded_panel("cut_louvre", (into(0.03), AC_LOUVRE_Y, (bottom + top) / 2), (0.23, AC_LOUVRE_WIDTH, top - bottom), 0.02, "x", materials["Seam"], cutters)
                panel_bottom = AC_BAND_TOP_Z - 0.1
                rounded_panel("cut_blue_panel", (into(0.012), AC_PANEL_Y, (panel_bottom + AC_PANEL_TOP_Z) / 2), (0.212, AC_PANEL_WIDTH, AC_PANEL_TOP_Z - panel_bottom), 0.04, "x", materials["AcBlue"], cutters)
            continue
        for y in variant.door_centres:
            door_cutters(y, DOOR_WIDTH, 2, into, materials, cutters)
        for y in window_centres(variant):
            rounded_panel("cut_window_frame", (into(0.008), y, window_mid_z), (0.208, WINDOW_WIDTH + 0.08, WINDOW_HEIGHT + 0.08), 0.08, "x", materials["Frame"], cutters)
            rounded_panel("cut_window", (into(WINDOW_RECESS), y, window_mid_z), (WINDOW_RECESS + 0.2, WINDOW_WIDTH, WINDOW_HEIGHT), 0.06, "x", materials["Glass"], cutters)
        for y in panel_seams(variant):
            box("cut_seam", (into(0.004), y, (SIDE_BAND_TOP_Z + STRIPE_BOTTOM_Z) / 2), (0.204, 0.012, STRIPE_BOTTOM_Z - SIDE_BAND_TOP_Z), materials["Seam"], cutters)
        if variant.cab:
            door_cutters(CAB_DOOR_Y, CAB_DOOR_WIDTH, 1, into, materials, cutters)

    if not variant.cab:
        return

    # Cab front: the yellow panel set into the face inside the surround
    # (large rounded corners at the top, following the roof; tighter ones at
    # the bottom), and in it the windscreens and destination boards in their
    # frames and the rounded black lamp band. On an AC car a shallower red
    # panel round the yellow one makes its thick red border.
    for panel in front_panels(variant):
        top_height = panel.top - 2.2
        rounded_panel("cut_panel_top", (0, HALF_LENGTH + 0.1 - panel.recess, 2.2 + top_height / 2), (panel.width, 0.2, top_height), panel.top_corner, "y", materials[panel.material], cutters)
        bottom_height = 2.6 - panel.bottom
        rounded_panel("cut_panel_bottom", (0, HALF_LENGTH + 0.1 - panel.recess - 0.001, panel.bottom + bottom_height / 2), (panel.width, 0.2, bottom_height), panel.bottom_corner, "y", materials[panel.material], cutters)
    front = HALF_LENGTH - YELLOW_PANEL_RECESS
    screen_mid_z = (WINDSCREEN_BOTTOM_Z + WINDSCREEN_TOP_Z) / 2
    screen_height = WINDSCREEN_TOP_Z - WINDSCREEN_BOTTOM_Z
    board_mid_z = DESTINATION_BOTTOM_Z + DESTINATION_HEIGHT / 2
    for sign in (-1, 1):
        x = sign * (WINDSCREEN_PILLAR + WINDSCREEN_WIDTH) / 2
        # Windscreen: a thick black frame, a stepped steel lip, then the
        # glass set well back.
        frame = rounded_panel("cut_screen_frame", (x, front + 0.088, screen_mid_z), (WINDSCREEN_WIDTH + 0.2, 0.2, screen_height + 0.2), 0.05, "y", materials["CabBlack"], cutters)
        lip = rounded_panel("cut_screen_lip", (x, front + 0.075, screen_mid_z), (WINDSCREEN_WIDTH + 0.04, 0.2, screen_height + 0.04), 0.03, "y", materials["Frame"], cutters)
        glass = rounded_panel("cut_windscreen", (x, front + 0.045, screen_mid_z), (WINDSCREEN_WIDTH, 0.29, screen_height), 0.025, "y", materials["Glass"], cutters)
        for panel, width in ((frame, WINDSCREEN_WIDTH + 0.2), (lip, WINDSCREEN_WIDTH + 0.04), (glass, WINDSCREEN_WIDTH)):
            flare_top(panel, WINDSCREEN_FLARE / width, screen_height / 2)
        # Destination board: a deep dark housing with the display inside.
        rounded_panel("cut_destination_frame", (x, front + 0.088, board_mid_z), (WINDSCREEN_WIDTH - 0.02, 0.2, DESTINATION_HEIGHT + 0.14), 0.03, "y", materials["CabBlack"], cutters)
        rounded_panel("cut_destination", (x, front + 0.06, board_mid_z), (WINDSCREEN_WIDTH - 0.16, 0.24, DESTINATION_HEIGHT), 0.015, "y", materials["DestinationBoard"], cutters)
    rounded_panel("cut_lamp_band", (0, front + 0.09, LAMP_BAND_Z), (LAMP_BAND_WIDTH, 0.2, LAMP_BAND_HEIGHT), LAMP_BAND_HEIGHT / 2 - 0.01, "y", materials["CabBlack"], cutters)
    for cutter in cutters.objects:
        if cutter.location.y > HALF_LENGTH - FRONT_BLEND - 0.6:
            bend_object_to_front(cutter)


def flare_top(obj: bpy.types.Object, ratio: float, half_height: float) -> None:
    """Widen a panel towards its top by `ratio` of its width, symmetrically
    about its centre: rectangle to slight trapezoid."""
    for v in obj.data.vertices:
        v.co.x *= 1 + ratio * (v.co.z / half_height + 1) / 2


def carve(shell: bpy.types.Object, cutters: bpy.types.Collection) -> None:
    modifier = shell.modifiers.new("carve", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.operand_type = "COLLECTION"
    modifier.collection = cutters
    modifier.solver = "MANIFOLD"
    modifier.material_mode = "TRANSFER"
    apply_modifiers(shell)


# -- sides ------------------------------------------------------------------------


def make_side_details(variant: Variant, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    details: list[bpy.types.Object] = []
    steel, grille = materials["Steel"], materials["Grille"]
    window_mid_z = WINDOW_SILL_Z + WINDOW_HEIGHT / 2
    band_mid_z = (SIDE_BAND_BOTTOM_Z + SIDE_BAND_TOP_Z) / 2
    for side in (1, -1):
        face = side * HALF_WIDTH
        facing = FACING_LEFT_SIDE if side > 0 else FACING_RIGHT_SIDE
        if variant.ac:
            if variant.cab:
                # Angled slats across the louvre panels behind the cab.
                for bottom, top in AC_LOUVRES_Z:
                    for k in range(int((top - bottom) / 0.05)):
                        slat = box("louvre", (face - side * 0.012, AC_LOUVRE_Y, bottom + 0.035 + k * 0.05), (0.008, AC_LOUVRE_WIDTH - 0.04, 0.03), materials["Stainless"], parts)
                        slat.rotation_euler = (0, side * math.radians(35), 0)  # tilted out at the bottom
                        details.append(slat)
        else:
            for y in window_centres(variant):
                # The dark safety grille over each window.
                grille_x = face - side * 0.025
                for k in range(1, 4):
                    details.append(box("grille_v", (grille_x, y - WINDOW_WIDTH / 2 + WINDOW_WIDTH * k / 4, window_mid_z), (0.012, 0.014, WINDOW_HEIGHT - 0.02), grille, parts))
                for k in range(1, 7):
                    details.append(box("grille_h", (grille_x, y, WINDOW_SILL_Z + WINDOW_HEIGHT * k / 7), (0.012, WINDOW_WIDTH - 0.02, 0.014), grille, parts))
                # Louvred shutter, part lowered behind the grille.
                shutter_x = face - side * 0.04
                shutter_top = WINDOW_SILL_Z + WINDOW_HEIGHT - 0.01
                details.append(box("shutter", (shutter_x, y, shutter_top - SHUTTER_DROP / 2), (0.012, WINDOW_WIDTH - 0.02, SHUTTER_DROP), materials["Frame"], parts))
                for k in range(1, 8):
                    details.append(box("louvre", (shutter_x + side * 0.007, y, shutter_top - SHUTTER_DROP * k / 8), (0.004, WINDOW_WIDTH - 0.04, 0.012), materials["Seam"], parts))
            for y in variant.door_centres:
                # Grab rails either side of the doorway, handles on the leaves.
                for dy in (-DOOR_WIDTH / 2 - 0.09, DOOR_WIDTH / 2 + 0.09):
                    details.append(cylinder("grab_rail", (face + side * 0.03, y + dy, 2.15), 0.016, 1.3, "z", steel, parts, 8))
                for dy in (-0.07, 0.07):
                    details.append(box("door_handle", (face - side * (DOOR_RECESS - 0.015), y + dy, 1.95), (0.03, 0.025, 0.3), steel, parts))
                # "CR" on the purple band, just behind the doorway.
                letters_y = y - DOOR_WIDTH / 2 - 0.62
                details.append(text_object("line_letters", "CR", 0.46, (side * (HALF_WIDTH + 0.002), letters_y, band_mid_z), facing, materials["SignWhite"], parts, weight=0.004))
            # "CENTRAL RAILWAY" under the roof stripe, over the first bay.
            first_bay = window_bays(variant)[1]
            details.append(text_object("railway_name", "CENTRAL RAILWAY", 0.085, (side * (HALF_WIDTH + 0.002), sum(first_bay) / 2, STRIPE_BOTTOM_Z - 0.09), facing, materials["CabBlack"], parts))
        details.append(box("gutter", (side * (HALF_WIDTH - 0.03), 0, SIDE_TOP_Z + 0.06), (0.05, LENGTH - 1.6, 0.035), materials["Roof"], parts))
        details.append(box("solebar", (side * (HALF_WIDTH - 0.08), 0, BODY_BOTTOM_Z - 0.05), (0.1, LENGTH - 0.4, 0.1), materials["Underframe"], parts))
        if variant.cab:
            # Steps up to the driver's door.
            for dy in (-CAB_DOOR_WIDTH / 2 + 0.03, CAB_DOOR_WIDTH / 2 - 0.03):
                details.append(box("step_rail", (side * (HALF_WIDTH - 0.06), CAB_DOOR_Y + dy, 0.66), (0.04, 0.04, 0.62), materials["Underframe"], parts))
            for z in (0.42, 0.7):
                details.append(box("step", (side * (HALF_WIDTH - 0.1), CAB_DOOR_Y, z), (0.2, CAB_DOOR_WIDTH - 0.04, 0.03), materials["Tread"], parts))
    return details


# -- roof -------------------------------------------------------------------------


def roof_rib(y: float, material: bpy.types.Material, collection: bpy.types.Collection) -> bpy.types.Object:
    """A thin rib across the roof, following its curve from gutter to gutter."""
    profile = [(x, z) for x, z in body_profile() if z > SIDE_TOP_Z + 0.12]
    mesh = bpy.data.meshes.new("roof_rib")
    bm = bmesh.new()
    rings = []
    for x, z in profile:
        length = math.hypot(x, z - SIDE_TOP_Z + 1.2)
        nx, nz = x / length, (z - SIDE_TOP_Z + 1.2) / length  # roughly outward
        rings.append([bm.verts.new((x + nx * h, y + dy, z + nz * h)) for dy, h in ((-0.025, 0.0), (-0.02, 0.014), (0.02, 0.014), (0.025, 0.0))])
    for a, b in zip(rings, rings[1:], strict=False):
        for i in range(3):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    return new_object("roof_rib", mesh, collection)


def insulator(centre: tuple[float, float, float], height: float, materials: Materials, parts: bpy.types.Collection, sheds: int = 6) -> list[bpy.types.Object]:
    """A ceramic post insulator on the roof: steel base and cap, ribbed
    (alternately wide and narrow) sheds between them."""
    x, y, z = centre
    cap = 0.035
    body = height - 2 * cap
    pieces = [
        cylinder("insulator_base", (x, y, z + cap / 2), 0.06, cap, "z", materials["Steel"], parts, 12),
        cylinder("insulator_cap", (x, y, z + height - cap / 2), 0.05, cap, "z", materials["Steel"], parts, 12),
        cylinder("insulator_core", (x, y, z + cap + body / 2), 0.035, body, "z", materials["Insulator"], parts, 10),
    ]
    for k in range(sheds):
        shed_z = z + cap + body * (k + 0.5) / sheds
        pieces.append(cylinder("insulator_shed", (x, y, shed_z), 0.085 if k % 2 == 0 else 0.065, 0.018, "z", materials["Insulator"], parts, 14))
    return pieces


def louvred_box(
    name: str,
    centre: tuple[float, float, float],
    size: tuple[float, float, float],
    materials: Materials,
    parts: bpy.types.Collection,
) -> list[bpy.types.Object]:
    """A roof equipment housing: a steel box on feet, with rows of angled
    louvres along both long sides, a lid seam and lifting handles."""
    x, y, z = centre
    w, length, h = size
    grey = materials["BufferBeam"]
    pieces = [box(name, centre, size, grey, parts, bevel=0.04)]
    pieces.append(box(f"{name}_lid_seam", (x, y, z + h / 2 - 0.04), (w + 0.012, length + 0.012, 0.012), materials["Seam"], parts))
    for side in (-1, 1):
        slats = max(4, int((length - 0.3) / 0.07))
        for k in range(slats):
            slat_y = y - (length - 0.3) / 2 + k * (length - 0.3) / (slats - 1)
            slat = box(f"{name}_louvre", (x + side * (w / 2 + 0.006), slat_y, z), (0.012, 0.035, h * 0.55), materials["Seam"], parts)
            slat.rotation_euler = (0, 0, side * math.radians(35))
            pieces.append(slat)
        for dy in (-length / 2 + 0.12, length / 2 - 0.12):
            pieces.append(box(f"{name}_foot", (x + side * (w / 2 - 0.08), y + dy, z - h / 2 - 0.03), (0.16, 0.12, 0.06), grey, parts))
    for dy in (-length / 2 - 0.02, length / 2 + 0.02):
        pieces.append(rod(f"{name}_handle", (x - 0.18, y + dy, z + h / 2 - 0.05), (x + 0.18, y + dy, z + h / 2 - 0.05), 0.012, materials["Steel"], parts))
    return pieces


def ac_unit(y: float, materials: Materials, parts: bpy.types.Collection, x: float = 0.0, width: float = 1.8, length: float = 2.8) -> list[bpy.types.Object]:
    """A roof-mounted air-conditioning package: a low rounded housing set
    into the roof, louvred along both sides, with two condenser fans under
    round grilles on top."""
    height = 0.42
    z = ROOF_Z - 0.06 + height / 2  # its foot sits inside the roof's curve
    top = z + height / 2
    casing = materials["Roof"]
    pieces = [
        box("ac_unit", (x, y, z), (width, length, height), casing, parts, bevel=0.08),
        box("ac_unit_seam", (x, y, top - 0.08), (width + 0.012, length + 0.012, 0.012), materials["Seam"], parts),
    ]
    for side in (-1, 1):
        slats = int((length - 0.5) / 0.07)
        for k in range(slats):
            slat_y = y - (length - 0.5) / 2 + k * (length - 0.5) / (slats - 1)
            slat = box("ac_unit_louvre", (x + side * (width / 2 + 0.006), slat_y, z - 0.03), (0.012, 0.035, height * 0.45), materials["Seam"], parts)
            slat.rotation_euler = (0, 0, side * math.radians(35))
            pieces.append(slat)
    for dy in (-length / 4, length / 4):
        pieces.append(cylinder("ac_fan_collar", (x, y + dy, top + 0.01), 0.4, 0.03, "z", casing, parts, 32))
        pieces.append(cylinder("ac_fan_grille", (x, y + dy, top + 0.03), 0.35, 0.014, "z", materials["Grille"], parts, 32))
        for angle in (math.radians(45), math.radians(-45)):
            bar = box("ac_fan_bar", (x, y + dy, top + 0.04), (0.7, 0.022, 0.012), materials["Steel"], parts)
            bar.rotation_euler = (0, 0, angle)
            pieces.append(bar)
        pieces.append(cylinder("ac_fan_hub", (x, y + dy, top + 0.045), 0.07, 0.02, "z", materials["Steel"], parts, 16))
    return pieces


def make_pantograph(y: float, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    """A single-arm pantograph, raised: base frame on four post insulators,
    red lower arm on a hinge shaft with its operating cylinder and springs,
    a guide rod, thin steel upper arms to a collector head with two carbon
    contact strips on sprung pans and curved horns."""
    grey, red, steel, dark = materials["BufferBeam"], materials["PantographRed"], materials["Steel"], materials["Underframe"]
    base_z = ROOF_Z + 0.33
    pieces: list[bpy.types.Object] = []
    # Post insulators on brackets, and the base frame (two rails, two cross members).
    for dx in (-0.55, 0.55):
        for dy in (-0.62, 0.62):
            pieces.append(box("insulator_bracket", (dx, y + dy, ROOF_Z - 0.01), (0.24, 0.24, 0.03), grey, parts))
            pieces += insulator((dx, y + dy, ROOF_Z), 0.3, materials, parts)
    for dx in (-0.55, 0.55):
        pieces.append(box("pantograph_rail", (dx, y, base_z + 0.03), (0.07, 1.5, 0.08), grey, parts, bevel=0.01))
    for dy in (-0.62, 0.62):
        pieces.append(box("pantograph_cross", (0, y + dy, base_z + 0.03), (1.2, 0.07, 0.07), grey, parts, bevel=0.01))
    hinge_y, hinge_z = y - 0.55, base_z + 0.12
    knee = (0.0, y + 0.75, base_z + 0.66)
    head_y, head_z = y - 0.05, base_z + 1.28
    # Hinge shaft with its bearings.
    pieces.append(rod("pantograph_shaft", (-0.5, hinge_y, hinge_z), (0.5, hinge_y, hinge_z), 0.035, red, parts, 12))
    for dx in (-0.5, 0.5):
        pieces.append(box("pantograph_bearing", (dx, hinge_y, hinge_z - 0.04), (0.1, 0.12, 0.1), grey, parts, bevel=0.015))
    # Lower arm: two tubes converging from the shaft to the knee, braced.
    for dx in (-0.28, 0.28):
        pieces.append(rod("pantograph_lower_arm", (dx, hinge_y, hinge_z), (dx * 0.2, knee[1], knee[2]), 0.032, red, parts, 10))
    pieces.append(rod("pantograph_brace", (-0.22, hinge_y + 0.35, hinge_z + 0.14), (0.22, hinge_y + 0.35, hinge_z + 0.14), 0.02, red, parts))
    pieces.append(rod("pantograph_knee", (-0.1, knee[1], knee[2]), (0.1, knee[1], knee[2]), 0.05, grey, parts, 12))
    # Guide rod from the base to just above the knee.
    pieces.append(rod("pantograph_guide", (0.12, hinge_y + 0.2, base_z + 0.08), (0.06, knee[1] - 0.12, knee[2] + 0.1), 0.014, steel, parts))
    # Operating cylinder and lifting springs on the base.
    pieces.append(cylinder("pantograph_cylinder", (-0.25, y + 0.25, base_z + 0.11), 0.07, 0.45, "y", grey, parts, 14))
    for dx in (0.18, 0.3):
        pieces.append(rod("pantograph_spring", (dx, y + 0.45, base_z + 0.08), (dx, hinge_y + 0.08, hinge_z + 0.02), 0.025, steel, parts, 8))
    # Upper arm: two thin tubes spreading from the knee to the head, braced.
    for dx in (-0.08, 0.08):
        pieces.append(rod("pantograph_upper_arm", (dx, knee[1], knee[2]), (dx * 3.6, head_y, head_z - 0.08), 0.017, steel, parts))
    mid = 0.55
    pieces.append(rod("pantograph_upper_brace", (-0.08 - 0.21 * mid, knee[1] + (head_y - knee[1]) * mid, knee[2] + (head_z - 0.08 - knee[2]) * mid), (0.08 + 0.21 * mid, knee[1] + (head_y - knee[1]) * mid, knee[2] + (head_z - 0.08 - knee[2]) * mid), 0.012, steel, parts))
    # Collector head: support beam, sprung pans with carbon strips, horns.
    pieces.append(box("pan_support", (0, head_y, head_z - 0.08), (0.7, 0.08, 0.05), grey, parts, bevel=0.01))
    for dy in (-0.09, 0.09):
        for dx in (-0.3, 0.3):
            pieces.append(cylinder("pan_spring", (dx, head_y + dy, head_z - 0.04), 0.02, 0.07, "z", steel, parts, 8))
        pieces.append(box("pan_bar", (0, head_y + dy, head_z), (1.5, 0.045, 0.03), steel, parts))
        pieces.append(box("contact_strip", (0, head_y + dy, head_z + 0.03), (1.1, 0.04, 0.03), dark, parts))
        for sign in (-1, 1):
            bend = [(sign * 0.75, head_z), (sign * 0.9, head_z - 0.02), (sign * 1.0, head_z - 0.1), (sign * 1.03, head_z - 0.2)]
            for (ax, az), (bx, bz) in zip(bend, bend[1:], strict=False):
                pieces.append(rod("pan_horn", (ax, head_y + dy, az), (bx, head_y + dy, bz), 0.016, steel, parts))
    # Insulated cable from the base frame down to the roof bushing.
    cable = [(0.55, y - 0.75, base_z), (0.7, y - 1.0, ROOF_Z + 0.2), (0.75, y - 1.3, ROOF_Z + 0.08)]
    for a, b in zip(cable, cable[1:], strict=False):
        pieces.append(rod("pantograph_cable", a, b, 0.025, materials["Rubber"], parts))
    pieces += insulator((0.75, y - 1.38, ROOF_Z - 0.02), 0.14, materials, parts, sheds=3)
    return pieces


def make_roof_details(variant: Variant, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    ribs = [roof_rib(-HALF_LENGTH + 0.6 + k * 1.2, materials["Roof"], parts) for k in range(15)]
    if variant.pantograph:
        pantograph_y = 5.6
        details = make_pantograph(pantograph_y, materials, parts)
        # Surge arrester and the roof isolating switch by the pantograph.
        details += insulator((-0.75, pantograph_y - 1.3, ROOF_Z - 0.02), 0.42, materials, parts, sheds=8)
        for dy in (-2.0, -2.8):
            details += insulator((-0.35, pantograph_y + dy, ROOF_Z - 0.02), 0.26, materials, parts)
        details.append(rod("isolator_blade", (-0.35, pantograph_y - 2.0, ROOF_Z + 0.26), (-0.35, pantograph_y - 2.8, ROOF_Z + 0.26), 0.02, materials["Steel"], parts))
        # High-voltage busbar on insulators, back along the roof to the coach end.
        support_ys = [pantograph_y - 1.8 - k * 2.2 for k in range(6)]
        for support_y in support_ys:
            details += insulator((0.35, support_y, ROOF_Z - 0.02), 0.22, materials, parts)
        details.append(rod("busbar", (0.35, pantograph_y - 1.0, ROOF_Z + 0.22), (0.35, support_ys[-1] - 1.2, ROOF_Z + 0.22), 0.018, materials["Steel"], parts))
        details.append(rod("busbar_drop", (0.35, pantograph_y - 1.0, ROOF_Z + 0.22), (0.55, pantograph_y - 0.75, ROOF_Z + 0.33), 0.018, materials["Steel"], parts))
        # Converter and resistor housings.
        details += louvred_box("roof_equipment", (-0.55, pantograph_y - 4.2, ROOF_Z + 0.16), (0.8, 2.4, 0.3), materials, parts)
        details += louvred_box("roof_equipment", (0.0, -6.8, ROOF_Z + 0.14), (1.4, 1.6, 0.26), materials, parts)
        if variant.ac:
            # One narrower AC package, clear of the busbar along x = 0.35.
            return ribs + details + ac_unit(-3.3, materials, parts, x=-0.45, width=1.5, length=2.6)
        vents = [box("ventilator", (0, y, ROOF_Z + 0.04), (1.0, 1.25, 0.14), materials["Roof"], parts, bevel=0.06) for y in (-4.2, -1.0)]
        return ribs + details + vents
    if variant.ac:
        # Two AC packages; on the cab car the forward one clears the roof box behind the cab.
        units = (-5.4, 4.4) if variant.cab else (-5.4, 5.4)
        return ribs + [piece for y in units for piece in ac_unit(y, materials, parts)]
    vents = [box("ventilator", (0, y, ROOF_Z + 0.04), (1.0, 1.25, 0.14), materials["Roof"], parts, bevel=0.06) for y in (-7.4, -4.2, -1.0, 2.2, 5.4)]
    return ribs + vents


# -- ends -----------------------------------------------------------------------


# Where the cab's lamps end up once mounted on the nose, in the coach's
# frame: filled in by make_cab_front, exported as markers for the app.
LAMP_ANCHORS: dict[str, tuple[float, float, float]] = {}

# Lettering on the cab front (stood up differently from the other fittings).
ON_FRONT_LETTERING = frozenset({"front_number", "front_icf", "front_destination"})


def make_cab_front(variant: Variant, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    """Seen from in front of the train, +X is on the viewer's left. The AC
    cab has a blue headlight housing and blue horns at both roof corners,
    rectangular lamps in the black band, blue "ICF" and no marker plates."""
    front = HALF_LENGTH
    ac = variant.ac
    chrome, grey, black = materials["Chrome"], materials["BufferBeam"], materials["CabBlack"]
    housing = materials["AcBlue"] if ac else grey
    details = [
        # Upper headlight: a rounded housing on the front face, two lamps.
        rounded_panel("headlight_flange", (0, front + 0.005, HEADLIGHT_Z), (0.66, 0.03, 0.32), 0.15, "y", housing if ac else chrome, parts),
        rounded_panel("headlight_housing", (0, front + 0.045, HEADLIGHT_Z), (0.58, 0.08, 0.26), 0.12, "y", housing, parts),
        # Horns (and, on the non-AC cab, a camera) on stalks at the roof's front corners.
        cone("horn", (-1.05, front - 0.2, ROOF_Z - 0.04), 0.03, 0.1, 0.3, housing, parts),
        cone("horn", (1.05, front - 0.2, ROOF_Z - 0.04), 0.03, 0.1, 0.3, housing, parts)
        if ac
        else box("camera", (1.05, front - 0.2, ROOF_Z - 0.04), (0.14, 0.24, 0.14), black, parts, bevel=0.03),
    ]
    marker_plates = () if ac else ((0.95, "dots"), (-0.32, "x"))
    for plate_x, kind in marker_plates:
        # Tail-end markers just under the lamp band: red dots, red X.
        details.append(box(f"{kind}_plate", (plate_x, front + 0.012, FRONT_STRIPE_TOP_Z + 0.1), (0.22, 0.02, 0.22), materials["SignWhite"], parts))
    for sign in (-1, 1):
        details += lamp("headlight", (sign * 0.14, front + 0.1, HEADLIGHT_Z), 0.07, materials["Headlight"], chrome, parts, depth=0.07)
        lamp_x = sign * (LAMP_BAND_WIDTH / 2 - 0.36)
        if ac:
            # A rectangular lamp at each end of the black band, behind a
            # chrome rim and three thin bars.
            details.append(box("lamp_unit", (lamp_x, front + 0.02, LAMP_BAND_Z), (0.4, 0.06, 0.26), materials["LampHousing"], parts, bevel=0.1))
            details.append(rounded_panel("lamp_rim", (lamp_x, front + 0.05, LAMP_BAND_Z), (0.32, 0.03, 0.19), 0.07, "y", chrome, parts))
            details.append(rounded_panel("lamp", (lamp_x, front + 0.066, LAMP_BAND_Z), (0.27, 0.01, 0.15), 0.06, "y", materials["Headlight"], parts))
            for dx in (-0.07, 0.0, 0.07):
                details.append(box("lamp_bar", (lamp_x + dx, front + 0.074, LAMP_BAND_Z), (0.012, 0.008, 0.15), chrome, parts))
        else:
            # Lamp units at the ends of the black band: amber outside, white inside.
            details.append(box("lamp_unit", (lamp_x, front + 0.02, LAMP_BAND_Z), (0.46, 0.06, 0.26), materials["LampHousing"], parts, bevel=0.12))
            for dx, lens in ((0.1, "AmberLight"), (-0.1, "Headlight")):
                details += lamp("lamp", (lamp_x + sign * dx, front + 0.07, LAMP_BAND_Z), 0.068, materials[lens], chrome, parts)
            for dx in (-0.2, 0.2):
                for dz in (-0.1, 0.1):
                    details.append(cylinder("bolt", (lamp_x + dx, front + 0.055, LAMP_BAND_Z + dz), 0.012, 0.02, "y", chrome, parts, 6))
        # Wiper parked on each windscreen; grab handle at each corner.
        screen_x = sign * (WINDSCREEN_PILLAR + WINDSCREEN_WIDTH) / 2
        wiper = box("wiper", (screen_x + sign * 0.12, front + 0.01, WINDSCREEN_BOTTOM_Z + 0.42), (0.025, 0.02, 0.7), materials["Rubber"], parts)
        wiper.rotation_euler = (0, -sign * math.radians(28), 0)
        details.append(wiper)
        details.append(cylinder("wiper_hub", (screen_x + sign * 0.28, front + 0.015, WINDSCREEN_BOTTOM_Z + 0.08), 0.03, 0.03, "y", black, parts, 12))
        details.append(cylinder("grab_handle", (sign * (HALF_WIDTH - 0.2), front - 0.08, 2.3), 0.016, 0.8, "z", materials["Steel"], parts, 8))
    # Red indicator lights in the black band: off-centre on the non-AC cab,
    # a pair either side of the middle on the AC cab.
    leds = ((-0.26, 0.26) if ac else (0.32, 0.46))
    for dx in leds:
        for dz in (0.07, -0.07):
            details += lamp("led", (dx, front + 0.07, LAMP_BAND_Z + dz), 0.03, materials["TailLight"], black, parts, depth=0.03)
    for plate_x, kind in marker_plates:
        for dx in (-0.09, 0.09):
            for dz in (-0.09, 0.09):
                details.append(cylinder("bolt", (plate_x + dx, front + 0.025, FRONT_STRIPE_TOP_Z + 0.1 + dz), 0.008, 0.012, "y", materials["Steel"], parts, 6))
        if kind == "dots":
            for dx, dz in ((-0.065, 0.065), (0.065, 0.065), (-0.065, -0.065), (0.065, -0.065)):
                details.append(cylinder("plate_dot", (plate_x + dx, front + 0.025, FRONT_STRIPE_TOP_Z + 0.1 + dz), 0.028, 0.01, "y", materials["SignRed"], parts, 12))
        else:
            for angle in (math.radians(45), math.radians(-45)):
                cross = box("x_bar", (plate_x, front + 0.025, FRONT_STRIPE_TOP_Z + 0.1), (0.26, 0.006, 0.038), materials["SignRed"], parts)
                cross.rotation_euler = (0, angle, 0)
                details.append(cross)
    # Markings: the electrification logo (and on the non-AC cab the train
    # number) on the pillar between the windscreens, "ICF" under them, the
    # destination on the boards.
    for k in range(3):
        bolt = box("logo_bar", (0.03 - k * 0.03, front + 0.012, 2.98 - k * 0.07), (0.3, 0.006, 0.022), materials["SignRed"], parts)
        bolt.rotation_euler = (0, math.radians(-24), 0)
        details.append(bolt)
    if ac:
        details.append(text_object("front_icf", "ICF", 0.3, (-0.42, front + 0.012, 2.12), FACING_FRONT, materials["AcBlue"], parts, weight=0.004))
    else:
        details.append(text_object("front_number", "5070", 0.16, (0, front + 0.012, 2.62), FACING_FRONT, black, parts, weight=0.002))
        details.append(text_object("front_icf", "ICF", 0.26, (0.3, front + 0.012, 2.115), FACING_FRONT, materials["Purple"], parts, weight=0.003))
    board_z = DESTINATION_BOTTOM_Z + DESTINATION_HEIGHT / 2
    board_x = (WINDSCREEN_PILLAR + WINDSCREEN_WIDTH) / 2
    for x, words in ((board_x, "MUMBAI CST"), (-board_x, "CSMT FAST")):
        details.append(text_object("front_destination", words, 0.12, (x, front - 0.035, board_z), FACING_FRONT, materials["DestinationText"], parts))
    panels = front_panels(variant)
    for fitting in details:
        base = fitting.name.split(".")[0]
        x, _, z = fitting.location
        # Onto the innermost recessed panel the fitting is on.
        for panel in reversed(panels):
            if abs(x) < panel.width / 2 and panel.bottom < z < panel.top - 0.05:
                fitting.location.y -= panel.recess
                break
        if base in ON_FRONT_LETTERING:
            mount_on_front(fitting, lettering=True)
        else:
            mount_on_front(fitting)
    record_lamp_anchors(details)
    # On the roof, behind the front: the equipment housing, and the stalks
    # carrying the horns and camera.
    roof_edge = front - front_setback(0.0, ROOF_Z)
    details += louvred_box("roof_box", (0, roof_edge - 1.0, ROOF_Z + 0.12), (2.0, 1.7, 0.3), materials, parts)
    for sign in (-1, 1):
        details.append(cylinder("stalk", (sign * 1.05, front - front_setback(1.05, ROOF_Z) - 0.2, ROOF_Z - 0.06), 0.025, 0.2, "z", grey, parts, 8))
    return details + make_cab_lower_front(materials, parts, ac)


# The two cabs' lamps may differ by this much and still share one set of
# markers in the app.
LAMP_ANCHOR_TOLERANCE = 0.05


def record_lamp_anchors(details: list[bpy.types.Object]) -> None:
    """Note where this cab's lamps ended up: the upper headlight pair and
    the lamps at each end of the black band. Every cab must agree (the app
    has one set of markers for all of them)."""
    headlights = [f.location for f in details if f.name.split(".")[0] == "headlight"]
    anchors = {"lamp_top": tuple(sum(v[i] for v in headlights) / len(headlights) for i in range(3))}
    for side_name, sign in (("lamp_left", 1), ("lamp_right", -1)):
        lenses = [f.location for f in details if f.name.split(".")[0] == "lamp" and f.location.x * sign > 0.5]
        anchors[side_name] = tuple(sum(v[i] for v in lenses) / len(lenses) for i in range(3))
    for name, location in anchors.items():
        known = LAMP_ANCHORS.setdefault(name, location)
        if (Vector(known) - Vector(location)).length > LAMP_ANCHOR_TOLERANCE:
            raise ValueError(f"{name} differs between cabs: {known} vs {location}")


# The buffer and coupler gear under the cab, kept compact as on the real
# car: buffer faces stand about 0.3 m proud of the bumper, the coupler head
# about level with them, and the lifeguard tucks in under the bumper.
BUMPER_Z = BODY_BOTTOM_Z - 0.2  # centre line of the bumper, buffers and coupler
BUMPER_BOTTOM_Z = BUMPER_Z - 0.22
BUFFER_X = 1.05  # buffer centres either side of the middle
BUFFER_FACE_RADIUS = 0.19
LIFEGUARD_BOTTOM_Z = 0.22


def bumper_face_y(x: float) -> float:
    """Where the bumper's face is at `x`: it follows the nose's bulge."""
    return HALF_LENGTH + 0.03 - FRONT_BULGE * min((x / HALF_WIDTH) ** 2, 1.0)


def make_cab_lower_front(materials: Materials, parts: bpy.types.Collection, ac: bool) -> list[bpy.types.Object]:
    """Below the cab: the bumper (white, numbered; stainless on an AC cab)
    with the coupler opening, a compact buffer in its housing at each side,
    the centre coupler, the air hoses, and the lifeguard grille."""
    front = HALF_LENGTH * 1.0
    grey, chrome, black = materials["BufferBeam"], materials["Chrome"], materials["CabBlack"]
    steel, dark = materials["Steel"], materials["Underframe"]
    bumper = box("front_bumper", (0, front - 0.14, BUMPER_Z), (3.3, 0.34, 0.44), materials["Stainless" if ac else "Body"], parts, bevel=0.05)
    bend_object_to_front(bumper)
    parts_list = [bumper]
    # Parts on the bumper sit on its curved face.
    on_bumper = [box("coupler_opening", (0, front + 0.02, BUMPER_Z), (0.62, 0.02, 0.32), black, parts, bevel=0.03)]
    if not ac:
        on_bumper += [text_object("bumper_number", "12", 0.1, (sign * 1.46, front + 0.035, BUMPER_Z + 0.08), FACING_FRONT, materials["SignRed"], parts) for sign in (1, -1)]
    for obj in on_bumper:
        x, _, _ = obj.location
        obj.location.y -= FRONT_BULGE * min((x / HALF_WIDTH) ** 2, 1.0)
        obj.location.x = x * (1 - FRONT_TAPER)
    parts_list += on_bumper

    # Each buffer: a plate bolted to the bumper, a box housing holding the
    # spring gear, a short plunger, and the round face; a bracket under the
    # housing ties it back into the chassis.
    for sign in (-1, 1):
        x = sign * BUFFER_X * (1 - FRONT_TAPER)
        face = bumper_face_y(BUFFER_X)
        parts_list += [
            box("buffer_plate", (x, face + 0.02, BUMPER_Z), (0.48, 0.04, 0.44), grey, parts, bevel=0.012),
            box("buffer_housing", (x, face + 0.11, BUMPER_Z), (0.36, 0.14, 0.34), grey, parts, bevel=0.02),
            cylinder("buffer_plunger", (x, face + 0.22, BUMPER_Z), 0.075, 0.08, "y", steel, parts, 16),
            cylinder("buffer_face", (x, face + 0.28, BUMPER_Z), BUFFER_FACE_RADIUS, 0.045, "y", chrome, parts, 32),
            cylinder("buffer_face_rim", (x, face + 0.255, BUMPER_Z), BUFFER_FACE_RADIUS - 0.012, 0.012, "y", grey, parts, 32),
            box("buffer_bracket", (x, face + 0.02, BUMPER_BOTTOM_Z + 0.02), (0.26, 0.3, 0.05), grey, parts, bevel=0.01),
        ]
        for dx in (-0.2, 0.2):
            for dz in (-0.18, 0.18):
                parts_list.append(cylinder("buffer_bolt", (x + dx, face + 0.045, BUMPER_Z + dz), 0.016, 0.012, "y", steel, parts, 6))

    # The headstock: the chassis' front cross beam behind the bumper, tied
    # back to the solebars, carrying the draft gear and the lifeguard.
    parts_list += [
        box("headstock", (0, front - 0.32, BUMPER_Z - 0.1), (3.0, 0.3, 0.26), dark, parts, bevel=0.02),
        box("draft_gear", (0, front - 0.2, BUMPER_Z - 0.02), (0.44, 0.3, 0.26), dark, parts, bevel=0.02),
    ]
    for side in (-1, 1):
        parts_list.append(box("chassis_member", (side * 1.25, front - 1.0, BODY_BOTTOM_Z - 0.12), (0.14, 1.4, 0.2), dark, parts))

    # Centre coupler: a short shank out of the coupler opening to a compact
    # head about level with the buffer faces.
    face = bumper_face_y(0.0)
    head_y = face + 0.22
    parts_list += [
        box("coupler_shank", (0, face + 0.1, BUMPER_Z - 0.02), (0.15, 0.22, 0.13), grey, parts, bevel=0.02),
        box("coupler_yoke", (0, face + 0.015, BUMPER_Z - 0.02), (0.26, 0.04, 0.2), dark, parts, bevel=0.01),
        box("coupler_head", (0, head_y, BUMPER_Z - 0.02), (0.28, 0.1, 0.24), grey, parts, bevel=0.025),
        box("coupler_knuckle", (0.07, head_y + 0.06, BUMPER_Z - 0.02), (0.1, 0.04, 0.18), dark, parts, bevel=0.01),
        rod("coupler_chain", (0.1, head_y - 0.02, BUMPER_Z - 0.13), (0.1, head_y - 0.05, BUMPER_Z - 0.3), 0.01, steel, parts),
    ]

    # Brake-pipe and main-reservoir hoses either side of the coupler: an
    # angle cock (red / yellow handle) on the bumper, a hose hanging down.
    for side, handle in ((-1, "SignRed"), (1, "CabYellow")):
        cock_x = side * 0.46
        cock_y = bumper_face_y(cock_x) + 0.05
        cock_z = BUMPER_BOTTOM_Z + 0.06
        parts_list += [
            cylinder("angle_cock", (cock_x, cock_y, cock_z), 0.03, 0.1, "y", steel, parts, 10),
            box("cock_handle", (cock_x + side * 0.05, cock_y + 0.02, cock_z + 0.04), (0.09, 0.02, 0.018), materials[handle], parts),
            rod("air_hose", (cock_x, cock_y + 0.04, cock_z), (cock_x + side * 0.03, cock_y + 0.1, cock_z - 0.14), 0.026, materials["Rubber"], parts, 10),
            rod("air_hose", (cock_x + side * 0.03, cock_y + 0.1, cock_z - 0.14), (cock_x + side * 0.01, cock_y + 0.11, cock_z - 0.3), 0.026, materials["Rubber"], parts, 10),
            box("hose_coupling", (cock_x + side * 0.01, cock_y + 0.11, cock_z - 0.33), (0.06, 0.07, 0.05), steel, parts),
        ]

    # The lifeguard: a shallow grille of upright slats under the bumper,
    # between two posts, with a thin red bar along its foot, braced back to
    # the headstock.
    grille_y = face + 0.02
    grille_mid_z = (BUMPER_BOTTOM_Z + LIFEGUARD_BOTTOM_Z) / 2
    grille_height = BUMPER_BOTTOM_Z - LIFEGUARD_BOTTOM_Z
    for sign in (-1, 1):
        parts_list.append(box("lifeguard_post", (sign * 1.36, grille_y - 0.03, grille_mid_z - 0.01), (0.08, 0.12, grille_height + 0.04), grey, parts, bevel=0.012))
    parts_list += [
        box("lifeguard_top", (0, grille_y - 0.04, BUMPER_BOTTOM_Z - 0.03), (2.8, 0.1, 0.06), grey, parts, bevel=0.012),
        box("lifeguard_rail", (0, grille_y, grille_mid_z - 0.02), (2.66, 0.04, 0.035), grey, parts),
        box("lifeguard_back", (0, grille_y - 0.1, grille_mid_z), (2.64, 0.03, grille_height - 0.04), dark, parts),
        box("lifeguard_foot", (0, grille_y - 0.02, LIFEGUARD_BOTTOM_Z - 0.02), (2.76, 0.07, 0.045), materials["SignRed"], parts, bevel=0.01),
    ]
    for k in range(21):
        parts_list.append(box("lifeguard_slat", (-1.3 + k * 2.6 / 20, grille_y - 0.04, grille_mid_z - 0.01), (0.04, 0.07, grille_height - 0.02), grey, parts))
    for x in (-1.05, -0.45, 0.45, 1.05):
        parts_list.append(box("lifeguard_bracket", (x, front - 0.12, BUMPER_BOTTOM_Z - 0.05), (0.03, 0.3, 0.12), grey, parts))
    return parts_list


def make_coach_end(sign: int, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    """A plain coach end (at +Y if `sign` is 1): buffer beam, coupler and
    the dark rubber bellows that joins it to the next coach."""
    end = sign * HALF_LENGTH
    return [
        box("end_buffer_beam", (0, end - sign * 0.05, BODY_BOTTOM_Z - 0.16), (2.9, 0.26, 0.32), materials["BufferBeam"], parts, bevel=0.03),
        box("end_coupler", (0, end + sign * 0.28, BODY_BOTTOM_Z - 0.18), (0.3, 0.56, 0.26), materials["Underframe"], parts, bevel=0.03),
        box("bellows", (0, end + sign * 0.14, 2.35), (2.3, 0.28, 2.3), materials["Rubber"], parts, bevel=0.1),
    ]


# -- underneath -----------------------------------------------------------------


def make_underframe(variant: Variant, materials: Materials, parts: bpy.types.Collection) -> list[bpy.types.Object]:
    layout = ((0.3, -3.9, 1.8, 2.2), (-0.2, -1.0, 2.2, 2.8), (0.25, 2.0, 1.9, 2.0), (-0.1, 4.2, 1.6, 1.2))
    if variant.pantograph:  # traction converter and transformer boxes
        layout = ((0.0, -3.6, 2.6, 3.0), (0.0, 0.2, 2.7, 3.6), (0.1, 3.8, 2.2, 2.0))
    dark = materials["Underframe"]
    boxes = [box("equipment", (x, y, 0.76), (w, length, 0.44), dark, parts, bevel=0.02) for x, y, w, length in layout]
    # Lids and handles on the equipment cases.
    for x, y, w, length in layout:
        for side in (-1, 1):
            boxes.append(box("equipment_lid", (x + side * (w / 2 + 0.006), y, 0.78), (0.012, length - 0.12, 0.34), materials["Seam"], parts))
            boxes.append(rod("equipment_handle", (x + side * (w / 2 + 0.03), y - 0.15, 0.82), (x + side * (w / 2 + 0.03), y + 0.15, 0.82), 0.01, materials["Steel"], parts))
    # Air reservoirs slung under the floor on each side, on straps.
    tanks = []
    for side in (1, -1):
        for y in (-2.0, 1.8):
            tanks.append(cylinder("air_tank", (side * 1.25, y, 0.66), 0.15, 1.6, "y", materials["BufferBeam"], parts, 16))
            for dy in (-0.55, 0.55):
                tanks.append(box("tank_strap", (side * 1.25, y + dy, 0.66), (0.33, 0.04, 0.33), dark, parts))
    # Cross members of the underframe between the bogies, and the brake
    # and main-reservoir pipes running the length of the coach.
    frame = [box("cross_member", (0, y, 0.9), (2.9, 0.12, 0.12), dark, parts) for y in (-5.2, -2.8, -0.4, 2.4, 5.2)]
    for x in (-0.75, -0.62, 0.9):
        frame.append(rod("underframe_pipe", (x, -HALF_LENGTH + 0.3, 0.86), (x, HALF_LENGTH - 0.3, 0.86), 0.025, dark, parts))
    return boxes + tanks + frame


def make_bogie(y: float, materials: Materials, parts: bpy.types.Collection, coach: bpy.types.Object, motored: bool) -> list[bpy.types.Object]:
    """A bogie's frame (joined into the coach) and its two wheelsets
    (separate objects named wheelset_*, so the app can turn them). A
    motored bogie carries a traction motor and gearcase on each axle."""
    frame: list[bpy.types.Object] = []
    bogie, steel = materials["Bogie"], materials["Steel"]
    for side in (1, -1):
        # Side frame: raised over the axle boxes, dipped in the middle.
        frame.append(box("side_frame", (side * 1.05, y, 0.58), (0.2, 1.7, 0.26), bogie, parts, bevel=0.03))
        for end in (-1, 1):
            frame.append(box("side_frame_end", (side * 1.05, y + end * 1.35, 0.68), (0.2, 1.1, 0.24), bogie, parts, bevel=0.03))
            frame.append(box("side_frame_step", (side * 1.05, y + end * 0.85, 0.63), (0.2, 0.3, 0.26), bogie, parts, bevel=0.02))
        # Secondary suspension: two large coil springs under the bolster.
        for dy in (-0.22, 0.22):
            frame.append(cylinder("secondary_spring", (side * 1.02, y + dy, 0.84), 0.11, 0.26, "z", steel, parts, 14))
            for k in range(4):
                frame.append(cylinder("spring_coil", (side * 1.02, y + dy, 0.74 + k * 0.065), 0.12, 0.018, "z", bogie, parts, 14))
        # Brake rigging along the bogie.
        frame.append(rod("brake_rod", (side * 0.92, y - 1.1, 0.46), (side * 0.92, y + 1.1, 0.46), 0.018, steel, parts))
        for dy in (-BOGIE_WHEELBASE / 2, BOGIE_WHEELBASE / 2):
            frame.append(box("axle_box", (side * 1.05, y + dy, WHEEL_RADIUS), (0.26, 0.34, 0.3), bogie, parts, bevel=0.03))
            frame.append(cylinder("axle_box_cover", (side * 1.19, y + dy, WHEEL_RADIUS), 0.11, 0.05, "x", steel, parts, 16))
            for ds in (-0.09, 0.09):
                frame.append(cylinder("spring", (side * 1.05, y + dy + ds, 0.8), 0.07, 0.26, "z", materials["Steel"], parts, 12))
            # Brake block against the wheel tread.
            toward_centre = -0.52 if dy > 0 else 0.52
            frame.append(box("brake_block", (side * (GAUGE / 2 + 0.03), y + dy + toward_centre, WHEEL_RADIUS), (0.12, 0.08, 0.3), materials["Underframe"], parts))
        damper = cylinder("damper", (side * 1.2, y, 0.62), 0.035, 0.42, "z", materials["Steel"], parts, 10)
        damper.rotation_euler = (math.radians(25), 0, 0)
        frame.append(damper)
        frame.append(cylinder("brake_cylinder", (side * 0.6, y, 0.55), 0.1, 0.35, "x", materials["Underframe"], parts, 12))
    frame.append(box("bolster", (0, y, 0.74), (2.3, 0.5, 0.22), bogie, parts, bevel=0.03))
    for dy in (-0.62, 0.62):
        frame.append(box("transom", (0, y + dy, 0.58), (1.9, 0.16, 0.16), bogie, parts))
    if motored:
        for dy in (-BOGIE_WHEELBASE / 2, BOGIE_WHEELBASE / 2):
            toward_centre = -0.42 if dy > 0 else 0.42
            frame.append(cylinder("traction_motor", (0.05, y + dy + toward_centre, 0.5), 0.27, 1.0, "x", bogie, parts, 18))
            frame.append(box("gearcase", (-0.62, y + dy + toward_centre * 0.55, 0.45), (0.14, 0.62, 0.42), bogie, parts, bevel=0.04))

    for index, dy in enumerate((-BOGIE_WHEELBASE / 2, BOGIE_WHEELBASE / 2)):
        name = f"wheelset_{'rear' if y < 0 else 'front'}_{index}"
        axle = cylinder(name, (0, y + dy, WHEEL_RADIUS), 0.085, GAUGE + 0.35, "x", materials["Bogie"], parts, 16)
        wheels = []
        for side in (1, -1):
            wheels.append(cylinder("wheel", (side * (GAUGE / 2 + 0.03), y + dy, WHEEL_RADIUS), WHEEL_RADIUS, WHEEL_WIDTH, "x", materials["Wheel"], parts, 32))
            wheels.append(cylinder("flange", (side * (GAUGE / 2 - 0.05), y + dy, WHEEL_RADIUS), WHEEL_RADIUS + 0.028, 0.025, "x", materials["Wheel"], parts, 32))
        join(axle, wheels)
        axle.parent = coach
    return frame


# -- build --------------------------------------------------------------------


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("cycles", default_set=True)
    addon_utils.enable("io_scene_gltf2", default_set=True)


def build_coach(variant: Variant, materials: Materials) -> bpy.types.Object:
    scene_collection = bpy.context.scene.collection
    coach_collection = bpy.data.collections.new(variant.name)
    cutters = bpy.data.collections.new(f"{variant.name}_cutters")
    parts = bpy.data.collections.new(f"{variant.name}_parts")
    for collection in (coach_collection, cutters, parts):
        scene_collection.children.link(collection)

    coach = make_shell(variant, materials, coach_collection)
    make_cutters(variant, materials, cutters)
    carve(coach, cutters)
    for cutter in list(cutters.objects):
        bpy.data.objects.remove(cutter)
    bpy.data.collections.remove(cutters)

    details = make_side_details(variant, materials, parts) + make_roof_details(variant, materials, parts)
    details += make_underframe(variant, materials, parts)
    details += make_cab_front(variant, materials, parts) if variant.cab else make_coach_end(1, materials, parts)
    details += make_coach_end(-1, materials, parts)
    for y in BOGIE_CENTRES:
        details += make_bogie(y, materials, parts, coach, motored=variant.pantograph)
    join(coach, details)
    for wheelset in [o for o in parts.objects if o.name.startswith("wheelset_")]:
        parts.objects.unlink(wheelset)
        coach_collection.objects.link(wheelset)
    bpy.data.collections.remove(parts)

    for obj in (coach, *coach.children):
        with bpy.context.temp_override(active_object=obj, selected_editable_objects=[obj], selected_objects=[obj]):
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
    return coach


def triangle_count(obj: bpy.types.Object) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def duplicate_coach(coach: bpy.types.Object) -> bpy.types.Object:
    """A linked copy of a coach and its wheelsets, for preview renders."""
    copy = coach.copy()
    bpy.context.scene.collection.objects.link(copy)
    for child in coach.children:
        child_copy = child.copy()
        child_copy.parent = copy
        bpy.context.scene.collection.objects.link(child_copy)
    return copy


def export_glb(coaches: list[bpy.types.Object], out: Path) -> None:
    objects = [o for coach in coaches for o in (coach, *coach.children)]
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in objects)
    bpy.context.view_layer.objects.active = coaches[0]
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )


# -- app export ---------------------------------------------------------------------

# The app draws up to a dozen coaches per train and many trains at once, so
# its copy of the model is cut down to a few materials per coach: each
# part's colour moves onto its vertices, and parts are grouped by how their
# surface behaves. Lamps and signs keep their own materials so the app can
# light them at night.
APP_MATERIAL_GROUPS: dict[str, tuple[float, float]] = {
    # name: (metallic, roughness)
    "Paint": (0.05, 0.45),
    "Metal": (0.8, 0.32),
}
METAL_FINISHES = frozenset({"Steel", "Chrome", "Frame", "BufferBeam", "Wheel", "Grille", "Tread", "Underframe", "Bogie"})
OWN_MATERIAL_FINISHES = frozenset({"Glass", "DestinationBoard", "Headlight", "AmberLight", "TailLight", "DestinationText"})
APP_LOD1_RATIO = {f"coach_{kind}_{livery}": ratio for kind, ratio in (("cab", 0.1), ("motor", 0.14), ("trailer", 0.16)) for livery in ("nonac", "ac")}


def app_group(finish_name: str) -> str:
    if finish_name in OWN_MATERIAL_FINISHES:
        return finish_name
    return "Metal" if finish_name in METAL_FINISHES else "Paint"


def app_materials() -> dict[str, bpy.types.Material]:
    """The app copy's materials: Paint and Metal take their colour from the
    vertices; the rest keep their original finish."""
    materials = {}
    for name, (metallic, roughness) in APP_MATERIAL_GROUPS.items():
        material = bpy.data.materials.new(f"app_{name}")
        bsdf = principled(material)
        bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        colour = material.node_tree.nodes.new("ShaderNodeVertexColor")
        colour.layer_name = "Col"
        material.node_tree.links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
        material.name = name
        materials[name] = material
    for name in OWN_MATERIAL_FINISHES:
        materials[name] = bpy.data.materials[name]
    return materials


def bake_to_vertex_colours(obj: bpy.types.Object, groups: dict[str, bpy.types.Material]) -> None:
    """Move every face's material colour onto its vertices (a "Col"
    attribute) and reassign it to its app material group."""
    mesh = obj.data
    colour = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    order = list(groups)
    slot_group, slot_colour = [], []
    for material in mesh.materials:
        name = material.name.split(".")[0]
        finish = FINISHES.get(name)
        slot_group.append(order.index(app_group(name)) if finish else order.index("Paint"))
        slot_colour.append((*finish.colour, 1.0) if finish else (1, 1, 1, 1))
    targets = []
    for poly in mesh.polygons:
        rgba = slot_colour[poly.material_index]
        for loop in poly.loop_indices:
            colour.data[loop].color = rgba
        targets.append(slot_group[poly.material_index])
    # Clearing the slots resets every face to the first one, so the new
    # groups go in first and the faces are pointed at them afterwards.
    mesh.materials.clear()
    for material in groups.values():
        mesh.materials.append(material)
    for poly, target in zip(mesh.polygons, targets, strict=True):
        poly.material_index = target


def app_coach(coach: bpy.types.Object, groups: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, bpy.types.Object]:
    """Full-detail and simplified copies of a coach for the app, wheelsets
    included, materials grouped."""
    base = coach.name
    full = coach.copy()
    full.data = coach.data.copy()
    full.parent = None
    full.location = (0, 0, 0)
    bpy.context.scene.collection.objects.link(full)
    wheels = []
    for child in coach.children:
        wheel = child.copy()
        wheel.data = child.data.copy()
        wheel.parent = None
        wheel.matrix_world = child.matrix_world @ Matrix.Translation(-coach.location)
        bpy.context.scene.collection.objects.link(wheel)
        wheels.append(wheel)
    join(full, wheels)
    bake_to_vertex_colours(full, groups)
    full.name = f"{base}_lod0"

    simple = full.copy()
    simple.data = full.data.copy()
    bpy.context.scene.collection.objects.link(simple)
    decimate = simple.modifiers.new("simplify", "DECIMATE")
    decimate.decimate_type = "COLLAPSE"
    decimate.ratio = APP_LOD1_RATIO[base]
    apply_modifiers(simple)
    simple.name = f"{base}_lod1"
    return full, simple


def export_app_glb(coaches: list[bpy.types.Object], out: Path) -> None:
    """The model as the app loads it: `<coach>_lod0` and `<coach>_lod1`
    for each coach, plus empties marking the cab's lamps (`lamp_top`,
    `lamp_left`, `lamp_right`) for the night headlight beams."""
    groups = app_materials()
    exported = []
    for coach in coaches:
        full, simple = app_coach(coach, groups)
        exported += [full, simple]
        print(f"{full.name}: {triangle_count(full):,} triangles; {simple.name}: {triangle_count(simple):,}")
    for name, location in LAMP_ANCHORS.items():
        marker = bpy.data.objects.new(name, None)
        marker.location = location
        bpy.context.scene.collection.objects.link(marker)
        exported.append(marker)
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in exported)
    bpy.context.view_layer.objects.active = exported[0]
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_vertex_color="ACTIVE",
        export_cameras=False,
        export_lights=False,
    )
    for obj in exported:
        bpy.data.objects.remove(obj)


# -- preview renders ----------------------------------------------------------------


def plain_material(name: str, colour: tuple[float, float, float], roughness: float = 0.9, metallic: float = 0.0) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    bsdf = principled(material)
    bsdf.inputs["Base Color"].default_value = (*colour, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return material


def add_stage() -> None:
    stage = bpy.data.collections.new("Stage")
    bpy.context.scene.collection.children.link(stage)
    ground = plain_material("Ground", (0.16, 0.15, 0.14))
    ballast = plain_material("Ballast", (0.11, 0.1, 0.095))
    sleeper = plain_material("Sleeper", (0.3, 0.29, 0.27))
    rail = plain_material("Rail", (0.4, 0.38, 0.36), roughness=0.35, metallic=0.9)
    box("ground", (0, -30, -0.35), (140, 220, 0.1), ground, stage)
    box("ballast", (0, -30, -0.22), (3.6, 220, 0.3), ballast, stage)
    for side in (1, -1):
        box("rail", (side * (GAUGE / 2 + 0.035), -30, -0.08), (0.07, 220, 0.16), rail, stage)
    for i in range(-230, 130):
        box("sleeper", (0, i * 0.6, -0.12), (2.75, 0.25, 0.1), sleeper, stage)


def setup_render(width: int, height: int, samples: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = True
        scene.cycles.device = "GPU"
    except (TypeError, ValueError):
        scene.cycles.device = "CPU"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.35

    world = bpy.data.worlds.new("Sky")
    if world.node_tree is None:
        world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(35)
    sky.sun_rotation = math.radians(210)
    world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08
    scene.world = world

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = math.radians(1.2)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(55), 0, math.radians(210))
    scene.collection.objects.link(sun)


def render_view(name: str, location: tuple[float, float, float], target: tuple[float, float, float], lens: float, out_dir: Path) -> Path:
    """Render from `location` towards `target`. A negative `lens` is an
    orthographic view `-lens` metres wide."""
    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new(name)
    if lens < 0:
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = -lens
    else:
        camera_data.lens = lens
    camera = bpy.data.objects.new(name, camera_data)
    scene.collection.objects.link(camera)
    camera.location = location
    camera.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    path = out_dir / f"{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="where to write the .glb")
    parser.add_argument("--app-out", type=Path, help="also write the app's cut-down .glb (two detail levels, few materials)")
    parser.add_argument("--renders", type=Path, help="write preview renders to this directory")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--views", nargs="+", metavar="NAME", help="render only these preview views")
    parser.add_argument("--rake", choices=("nonac", "ac"), default="nonac", help="which livery the preview renders show")
    args = parser.parse_args(argv)

    reset_scene()
    materials = make_materials()
    coaches = [build_coach(variant, materials) for variant in VARIANTS.values()]
    for coach in coaches:
        for obj in (coach, *coach.children):
            print(f"{obj.name}: {triangle_count(obj):,} triangles")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    export_glb(coaches, args.out)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    if args.app_out:
        args.app_out.parent.mkdir(parents=True, exist_ok=True)
        export_app_glb(coaches, args.app_out)
        print(f"wrote {args.app_out} ({args.app_out.stat().st_size / 1024:.0f} KB)")

    if args.renders:
        # Line the coaches up as a rake behind the cab car for the previews:
        # cab, motor, trailer, trailer, motor, as in a real unit.
        by_name = {coach.name: coach for coach in coaches}
        cab, motor, trailer = (by_name[f"coach_{kind}_{args.rake}"] for kind in ("cab", "motor", "trailer"))
        # The other livery's coaches all sit at the origin; keep them out of shot.
        for coach in coaches:
            if coach not in (cab, motor, trailer):
                for obj in (coach, *coach.children):
                    obj.hide_render = True
        rake = [cab, motor, trailer, duplicate_coach(trailer), duplicate_coach(motor)]
        for index, coach in enumerate(rake):
            coach.location.y = -index * (LENGTH + COACH_GAP)
        args.renders.mkdir(parents=True, exist_ok=True)
        add_stage()
        setup_render(1600, 900, args.samples)
        motor_y = -(LENGTH + COACH_GAP)
        views = {
            "rake": ((-10.5, 24.0, 6.0), (0, -18.0, 2.4), 30),
            "undercarriage": ((5.5, -3.0, 0.9), (0, -7.2, 0.6), 30),
            "front_hardware": ((1.8, 13.4, 0.8), (0, HALF_LENGTH, 0.6), 34),
            "front_reference": ((-6.2, 17.6, 3.1), (0.4, 8.8, 2.2), 36),
            "cab_profile": ((-14.0, 8.6, 2.3), (0, 8.6, 2.3), -6.5),
            "cab_front_ortho": ((0, 40.0, 2.2), (0, 0, 2.2), -5.5),
            "three_quarter_front": ((6.8, 18.6, 2.9), (0, 8.2, 2.0), 38),
            "front_close": ((1.9, 15.2, 2.3), (0, HALF_LENGTH, 2.1), 42),
            "side": ((15.5, 2.0, 2.1), (0, 2.0, 2.2), 28),
            "motor_roof": ((9.0, motor_y + 13.0, 7.5), (0, motor_y + 4.0, 4.2), 35),
            "lower_front_ortho": ((0, 40.0, 0.75), (0, 0, 0.75), -4.2),
            "lower_front_side": ((-14.0, HALF_LENGTH - 0.9, 0.9), (0, HALF_LENGTH - 0.9, 0.9), -3.4),
        }
        unknown = set(args.views or ()) - views.keys()
        if unknown:
            parser.error(f"unknown views: {', '.join(sorted(unknown))}")
        for name, (location, target, lens) in views.items():
            if args.views and name not in args.views:
                continue
            print(f"rendered {render_view(name, location, target, lens, args.renders)}")


if __name__ == "__main__":
    main()
