import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty, StringProperty
from bpy.props import FloatVectorProperty, CollectionProperty
from bpy.types import AddonPreferences, FileAssetSelectParams, UserAssetLibrary
import math
import json
import pathlib
from .. import __package__ as base_package
from .custom import CustomPropertyBase
from collections import OrderedDict
from ..object import enum_oriented_material, enum_all_material, enum_plan_material, enum_nonplan_material, enum_plan_wall_material, enum_plan_floor_material
from .dynamic_enums import enum_styles, enum_categories, enum_category_items, enum_objects_or_curves
from .dynamic_enums import face_tag_to_int, int_to_face_tag, get_face_tag_enum

# order might matter for registration
lst_classes = [
    'FaceTagProperty',
    'FaceMaterialProperty',
    'FaceElevationProperty',
    'FaceUVModeProperty',
    'FaceUVOriginProperty',
    'FaceRadialProperty',
    'FaceUVRotateProperty',
    'CalcUVProperty',
    'ArchShapeProperty',
    'CatalogObjectProperty',
    'LocalObjectProperty',
    'SuperCurveProperty',
    'DirectionProperty',
    'ArrayProperty',
    'PositionProperty',
    'SizeProperty',
    'GridDivideProperty',
    'SplitFaceProperty',
    'PolygonProperty',
    'InsetPolygonProperty',
    'PerpendicularFaceProperty',
    'ExtrudeProperty',
    'SweepProperty',
    'DashedProperty',
    'SolidifyEdgesProperty',
    'MakeLouversProperty',
    'CatalogScriptProperty',
    'SimpleWindowProperty',
    'MeshImportProperty',
    'OrientedMaterialProperty',
    'FlipNormalProperty',
    'ProjectFaceProperty',
    'BuildFaceProperty',
    'BuildRoofProperty',
    'BuildStairsProperty',
    'SimpleDoorProperty',
    'SimplePorticoProperty',
    'SimpleRailProperty',
    'DeckProperty',
    'ExtendGableProperty',
    'DormerProperty',
    'NicheProperty',
    'QuoinDivideProperty',
    'PlanInsetWallsProperty',
    'PlanFeatureProperty',
    'PlanFloorProperty',
    'CalculatorProperty',
    'BTAddonPreferences',
    'LatticeProperty',
    'StyleNameProperty',
    'QARCH_UL_Styles',
    'UnionPolyProperty'
]

lst_funcs = [
    'uv_mode_to_int',
    'int_to_uv_mode'
]

uv_mode_list = [
        ('GLOBAL_XY', 'Global XY', 'Use real units projected to face'),
        ('FACE_XY', 'Face XY', 'Use face x/y in real units'),
        ('FACE_BBOX', 'Bounding Box', 'Set bounding box 0-1'),
        ('FACE_POLAR', 'FACE Polar', 'Use face polar coordinates from centroid'),
        ('GLOBAL_YX', 'Global YX', 'Flip x and y, use real units projected to face'),
        ('FACE_YX', 'Face YX', 'Flip x and y, use real units'),
        ('ORIENTED', 'Oriented', 'Specify global rotation around origin for volumetrics'),
        ('ORIENTED_PLAN', 'Plan', 'Floor plan oriented material'),
        ('ORIENTED_SPIN', 'Rotatable', 'Rotatable in plane only (uses euler z only)'),
        ('NONE', 'None', 'Do not auto-calculate UV'),  # so we don't erase something the user did
    ]


def uv_mode_to_int(s):
    for i, e in enumerate(uv_mode_list):
        if e[0] == s:
            return i
    return 0


def int_to_uv_mode(i):
    return uv_mode_list[i][0]


# FYI, to access defaults, you can do ExtendGableProperty.__annotations__['soffit_width'].keywords['default']
class FaceTagProperty(CustomPropertyBase):
    tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for selection")
    field_layout = [['tag']]
    topology_lock = []


class FaceMaterialProperty(CustomPropertyBase):
    material: EnumProperty(name='Material', items=enum_all_material, description="Material name")
    field_layout = [['material']]
    topology_lock = []


class FaceElevationProperty(CustomPropertyBase):
    elevation: FloatProperty(name="Face Elevation", default=0, min=0, description="Floor height above plan")
    field_layout = [['elevation']]
    topology_lock = []


class FaceUVModeProperty(CustomPropertyBase):
    uv_mode: EnumProperty(name="UV Mode", description="Method of UV assignment", items=uv_mode_list, default="GLOBAL_XY")
    field_layout = [['uv_mode']]
    topology_lock = []


class FaceUVOriginProperty(CustomPropertyBase):
    uv_origin: FloatVectorProperty(name="UV Origin", subtype="XYZ", description="Origin of UV coordinates")
    field_layout = [['uv_origin']]
    topology_lock = []


class FaceRadialProperty(CustomPropertyBase):
    radial: FloatVectorProperty(name="Face Y", subtype="XYZ", description="Y direction of face coordinates")
    field_layout = [['radial']]
    topology_lock = []


class FaceUVRotateProperty(CustomPropertyBase):
    uv_rotate: FloatVectorProperty(name="UV Rotation", subtype="EULER", description="Rotation of UV coordinates")
    field_layout = [['uv_rotate']]
    topology_lock = []


class CalcUVProperty(CustomPropertyBase):
    override_origin: BoolProperty(name="Override origin", default=False)
    origin: FloatVectorProperty(name="Origin", description="UV origin", subtype="XYZ")
    override_mode: BoolProperty(name="Override origin", default=False)
    mode: EnumProperty(name="UV Mode", description="Method of UV assignment", items=uv_mode_list, default="GLOBAL_XY")

    field_layout = [
        ['origin', 'override_origin'],
        ['mode', 'override_mode']
    ]

    topology_lock = []


class OrientedMaterialProperty(CustomPropertyBase):
    material: EnumProperty(name='Material', items=enum_oriented_material, description="Material name")
    field_layout = [['material']]
    topology_lock = []


class ArchShapeProperty(CustomPropertyBase):
    arch_type_list = [
        ("JACK", "Jack", "Flat", 1),
        ("ROMAN", "Roman", "Round/Oval (1 pt)", 2),
        ("GOTHIC", "Gothic", "Gothic pointed (2 pt)", 3),
        ("OVAL", "Oval", "Victorian oval (3 pt)", 4),
        ("TUDOR", "Tudor", "Tudor pointed (4 pt)", 5),
        ('SQUARE', "Square (0 pt)", "Flat", 6),
        ('TRIANGLE', "Triangle (0 pt)", "Triangle", 7),
        ("DUTCH", "Dutch", "Rounded S-Curve (3 pt)", 8),
        ("ARABIC", "Arabic", "Pointed S-Curve (4 pt)", 9),
    ]
    # has_keystone: BoolProperty(name="Keystone", default=False)
    arch_type: EnumProperty(name="Arch Type", items=arch_type_list, description="Type of arch", default="ROMAN")
    step_size: FloatProperty(name="Step Size", min=0.01, default=0.06, description="Step size, should match brick row height")
    drop_length: FloatProperty(name="Drop Length", min=0, default=0, description="Vertical side length below arch")
    keystone: BoolProperty(name="Keystone", default=False, description="Add keystone")
    key_width: FloatProperty(name="Keystone Width", description="Width at top of arch", default= 0.85)
    key_above: FloatProperty(name="Keystone Above", description="Rise above arch this much", default= 0)
    key_below: FloatProperty(name="Keystone Below", description="Fall below arch this much", default= 0)
    key_material: EnumProperty(name="Keystone Material", items=enum_nonplan_material)

    field_layout = [
        ["step_size", "drop_length"],
        ["arch_type"],
        ['keystone'],
        [{'keystone': True}, 'key_width'],
        [{'keystone': True}, 'key_above', 'key_below'],
        [{'keystone': True}, 'key_material'],
    ]

    topology_lock = ['arch_type', 'num_sides']


class DirectionProperty(CustomPropertyBase):
    x: FloatProperty(name="X", default=0.0, unit="LENGTH", description="X value")
    y: FloatProperty(name="Y", default=0.0, unit="LENGTH", description="Y value")
    z: FloatProperty(name="Z", default=1.0, unit="LENGTH", description="Z value")

    field_layout = [
        ['x','y','z']
    ]

    topology_lock = []


class ArrayProperty(CustomPropertyBase):
    count: IntProperty(name="Count", min=1, default=1, description="Number of items")
    direction: PointerProperty(name="Direction", type=DirectionProperty)
    spacing: FloatProperty(name="Spacing", default = 1.0, description="Distance between copies")
    do_orbit: BoolProperty(name="Use Orbit", default=False, description="Orbit a point instead of straight line")
    origin: PointerProperty(name="Origin", type=DirectionProperty, description="Orbit origin")

    field_layout = [
        ['count', 'spacing'],
        ['direction'],
        ['do_orbit'],
        [{'do_orbit': True}, 'origin']
    ]

    topology_lock = ['count']


class PositionProperty(CustomPropertyBase):
    offset_x: FloatProperty(name="Offset X", default=0.0, unit="LENGTH", description="Face X position")
    is_relative_x: BoolProperty(name="Relative", default=False, description="Relative position (0-1) for x")
    offset_y: FloatProperty(name="Offset Y", default=0.0, unit="LENGTH", description="Face Y position")
    is_relative_y: BoolProperty(name="Relative", default=False, description="Relative position (0-1) for y")
    center_x: BoolProperty(name="Center X", default=False, description="Center position for x")
    center_y: BoolProperty(name="Center Y", default=False, description="Center position for y")

    field_layout = [
        ['offset_x', 'is_relative_x', 'center_x'],
        ['offset_y', 'is_relative_y', 'center_y'],
    ]

    topology_lock = []


class SizeProperty(CustomPropertyBase):
    size_x: FloatProperty(name="Size X", default=1.0, unit="LENGTH", description="Face X size")
    is_relative_x: BoolProperty(name="Relative", default=True, description="Relative size (0-1) for x")
    size_y: FloatProperty(name="Size Y", default=1.0, unit="LENGTH", description="Face Y size")
    is_relative_y: BoolProperty(name="Relative", default=True, description="Relative size (0-1) for y")
    is_ratio_yx: BoolProperty(name="Ratio to X", default=False, description="Ratio y/x")

    field_layout = [
        ['size_x', 'is_relative_x'],
        ['size_y', 'is_relative_y', 'is_ratio_yx'],
    ]

    topology_lock = []


class GridDivideProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=0, default=1, description="Number of vertical rows")
    count_y: IntProperty(name="Y Count", min=0, default=1, description="Number of horizontal cols")
    offset: PointerProperty(name="Offset Grid", type=PositionProperty)
    define_size: BoolProperty(name="Define step size", default=False, description="Use fixed size step instead of even distribution")
    size: PointerProperty(name="Step Size", type=SizeProperty)

    field_layout = [
        ['count_x', 'count_y'],
        ['offset'],
        ['define_size'],
        [{'define_size': True}, 'size']
    ]

    topology_lock = ['count_x', 'count_y']


class SplitFaceProperty(CustomPropertyBase):
    cut_items = [
        ('POINT', 'To Point', 'Cut between existing points'),
        ('X', 'X Cut', 'Cut in x direction'),
        ('Y', 'Y Cut', 'Cut in y direction')
    ]
    from_point: IntProperty(name="From Point", min=0, description="Cut line origin point index")
    to_point: IntProperty(name="To Point", min=0, default=2, description="Cut line origin point end")
    cut_type: EnumProperty(name="Cut Type", description="Cut direction", items=cut_items, default='POINT')

    field_layout = [
        ['from_point', 'to_point'],
        ['cut_type']
    ]

    topology_lock = ['from_point', 'cut_type', 'to_point']


class PolygonProperty(CustomPropertyBase):
    num_sides: IntProperty(name="Polygon Sides", default=4, min=3, description="Polygon number of sides")
    start_angle: FloatProperty(name="Start Angle", default=-45.0/180*math.pi, min=-math.pi, max=math.pi, unit="ROTATION", description="Rotation of polygon")
    total_angle: FloatProperty(name="Total Angle", default=math.pi*2, unit="ROTATION", description="360 for full circle, 180 for half, etc.")
    field_layout = [
        ['num_sides', 'start_angle'],
        ['total_angle']
    ]

    topology_lock = ['num_sides', 'total_angle']


class SuperCurveProperty(CustomPropertyBase):
    start_angle: FloatProperty(name="Start Angle", default=0, min=-math.pi, max=math.pi, unit="ROTATION", description="Rotation of shape")
    x: FloatProperty(name='x', description='cos frequency', default=1, min=0.1)
    sx: FloatProperty(name='sx', description='cos scale', default=1, min=0.1)
    px: FloatProperty(name='px', description='cos power', default=1, min=0.1)
    y: FloatProperty(name='y', description='sin frequency', default=1, min=0.1)
    sy: FloatProperty(name='sy', description='sin scale', default=1, min=0.1)
    py: FloatProperty(name='py', description='sin power', default=1, min=0.1)
    pn: FloatProperty(name='pn', description='power normalizer', default=1, min=0.1)

    field_layout = [
        ['x', 'y'],
        ['sx','sy'], # a,b
        ['px','py','pn'], # exponents
        ['start_angle']
    ]

    topology_lock = ['num_sides']


class CatalogObjectProperty(CustomPropertyBase):
    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    style_name: EnumProperty(items=enum_styles, description="Style", default=0)
    category_name: EnumProperty(items=enum_categories, name="Category", default=0)
    category_item: EnumProperty(items=enum_category_items, name="Objects", default=0)
    show_scripts: BoolProperty(name="Show Scripts", default=False)
    show_curves: BoolProperty(name="Show Curves", default=False)
    rotate: FloatVectorProperty(name="Rotation", subtype="EULER", description="Rotation of coordinates")

    field_layout = [
        ['style_name'],
        ['category_name'],
        ['search_text'],
        ['category_item'],
        ['rotate']
    ]

    topology_lock = ['category_item']
    previews = ['category_item']


class LocalObjectProperty(CustomPropertyBase):
    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    object_name: EnumProperty(items=enum_objects_or_curves, name="Object", default=0)
    show_curves: BoolProperty(name="Show Curves", default=False)
    rotate: FloatVectorProperty(name="Rotation", subtype="EULER", description="Rotation of coordinates")

    field_layout = [
        ['search_text', 'object_name'],
        ['rotate']
    ]

    topology_lock = ['object_name']


shape_type_list = [
    ("SELF", "Self Similar", "Current shape resized", 0),
    ("NGON", "Regular Polygon", "N-sided polygon", 1),
    ("ARCH", "Arch", "Arch shape", 2),
    ("SUPER", "Super-curve", "Asymmetric curve", 3),
    ("CURVE", "Local Curve", "Curve from this blend file", 4),
    ("CATALOG", "Catalog Curve", "Curve from catalog file", 5),
    ]


lst_join_enum = [
    ('BRIDGE', 'Bridge', 'Connect new shape to old outline, replace old face', 0),
    ('FREE', 'Free', 'Float disconnected over old face', 1),
    ('OUTSIDE', 'Outside', 'Clip and keep part outside old face', 2),
    ('INSIDE', 'Inside', 'Clip and keep part inside old face', 3),
    ('INSIDE_BRIDGE', 'Inside Bridge', 'Clip and bridge to part inside old face', 4),
    ('PARTITION', 'Partition', 'Cut control poly into parts', 5),
    ('UNION', 'Union', 'Merge with control poly', 6),
    ('DIFFERENCE', 'Subtract', 'Cut and remove from control poly', 7)
]


class InsetPolygonProperty(CustomPropertyBase):
    position: PointerProperty(name="Position on Face", type=PositionProperty)
    size: PointerProperty(name="Size of bounding box", type=SizeProperty, description="Bounding box size")
    join: EnumProperty(name="Join", items=lst_join_enum, default="BRIDGE")
    add_perimeter: BoolProperty(name="Add Perimeter Points", description="Add points to perimeter to match if needed", default=False)
    extrude_distance: FloatProperty(name="Extrude Distance", default=0.0, unit="LENGTH", description="Extrude distance")
    frame_material: EnumProperty(name="Frame Material", items=enum_nonplan_material)
    center_material: EnumProperty(name="Center Material", items=enum_nonplan_material)
    del_source: BoolProperty(name="Delete Source", description="Remove starting faces", default=False)
    shape_type: EnumProperty(name="Shape Type", default="SELF", items=shape_type_list)
    by_inset: BoolProperty(name="By Insert", description="Inset thickness instead of scale and position", default=False)
    thickness: FloatProperty(name="Thickness", default=0)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    frame: FloatProperty(name="Frame Thickness", min=0, default=0, description="Polygon donut instead of solid face")
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    super_curve: PointerProperty(name="Super", type=SuperCurveProperty)
    resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")

    field_layout = [
        ['position'],
        ['size'],
        ['join'],
        ({'join': {'BRIDGE','INSIDE_BRIDGE'}}, 'add_perimeter'),
        ({'join': {'FREE', 'OUTSIDE', 'INSIDE'}}, 'del_source'),
        ['shape_type'],
        ({'shape_type': 'SELF'}, 'by_inset'),
        ({'shape_type': 'SELF', 'by_inset': True}, 'thickness'),
        ({'shape_type': 'NGON'}, 'poly'),
        ({'shape_type': 'ARCH'}, 'arch'),
        ({'shape_type': {'NGON', 'ARCH'}}, 'frame'),
        ({'shape_type': {'NGON', 'ARCH'}}, 'frame_material'),
        ({'shape_type': 'SUPER'}, 'super_curve'),
        ({'shape_type': 'CURVE'}, 'local_object'),
        ({'shape_type': 'CATALOG'}, 'catalog_object'),
        ({'shape_type': {'CURVE', 'CATALOG', 'SUPER'}}, 'resolution'),
        ['center_material', 'extrude_distance']
    ]

    topology_lock = ['shape_type', 'join', 'frame']


class PerpendicularFaceProperty(CustomPropertyBase):
    position: PointerProperty(name="Position", type=PositionProperty)
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    rotation: FloatProperty(name="Z Rotation", default=0, min=-math.pi, max=math.pi, unit="ROTATION", description="Rotation around perpendicular axis")
    offset_z: FloatProperty(name="Z Offset", default=0)
    material: EnumProperty(name="Center Material", items=enum_nonplan_material)
    del_source: BoolProperty(name="Delete Source", description="Remove starting faces", default=False)

    field_layout = [
        ['position'],
        ['size'],
        ['rotation', 'offset_z'],
        ['material'],
        ['del_source']
    ]

    topology_lock = []


class DashedProperty(CustomPropertyBase):
    dash_offset: FloatProperty(name="Offset", description="Offset to first dash", default=0)
    dash_length: FloatProperty(name="Length", description="Dash length", default=.1)
    dash_spacing: FloatProperty(name="Spacing", description="Spacing between dashes", default=.0)

    field_layout = [
        ['dash_length'],
        ['dash_offset', 'dash_spacing']
    ]

    topology_lock = []


class SolidifyEdgesProperty(CustomPropertyBase):
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    side_list: StringProperty(name="Sides", description="Comma separated list of numbers, or empty for all")
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    by_inset: BoolProperty(name="By Insert", description="Inset thickness instead of scale and position", default=False)
    thickness: FloatProperty(name="Thickness", default=0)
    inset: FloatProperty(name="Inset Offset", description="Distance off edge", default=0)

    frame_material: EnumProperty(name="Frame Material", items=enum_nonplan_material)
    revolutions: IntProperty(name="Revolutions", description="If > 3, make a revolution of n steps instead of extrusion", default = 0)
    shape_type: EnumProperty(name="Shape Type", default="NGON", items=shape_type_list)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    frame: FloatProperty(name="Frame Thickness", min=0, default=0.1, description="Polygon donut instead of solid face")
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    super_curve: PointerProperty(name="Super", type=SuperCurveProperty)
    resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")
    dashed: BoolProperty(name="Dashed", description="Dashed instead of solid", default=False)
    dash_info: PointerProperty(name="Dash Settings", type=DashedProperty)
    del_source: BoolProperty(name="Delete Source", description="Remove starting faces", default=False)

    field_layout = [
        ['size'],
        ['side_list'],
        ['z_offset', 'inset'],
        ['del_source'],
        ['frame_material'],
        ['shape_type'],
        ({'shape_type': 'NGON'}, 'poly'),
        ({'shape_type': 'NGON'}, 'frame'),
        ({'shape_type': 'SELF'}, 'by_inset'),
        ({'shape_type': 'SELF', 'by_inset': True}, 'thickness'),
        ({'shape_type': 'ARCH'}, 'arch'),
        ({'shape_type': 'SUPER'}, 'super_curve'),
        ({'shape_type': 'CURVE'}, 'local_object'),
        ({'shape_type': 'CATALOG'}, 'catalog_object'),
        ({'shape_type': {'CURVE', 'CATALOG', 'SUPER'}}, 'resolution'),
        ['revolutions'],
        ('dashed', 'dash_info'),
    ]

    topology_lock = ['shape_type', 'revolutions', 'dashed']


class ExtrudeProperty(CustomPropertyBase):
    distance: FloatProperty(name="Distance", default=0.1, unit="LENGTH", description="Extrude distance")
    steps: IntProperty(name="Steps", default=1, description="Number of steps along axis")
    on_axis: BoolProperty(name="On Axis", default=False, description="Direction other than normal")
    both_directions: BoolProperty(name="Both Directions", default=False, description="Extrude in both directions")
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    align_end: BoolProperty(name="Align End", description="Align end face normal with axis", default=False)
    twist: FloatProperty(name="Twist Angle", default=0.0, unit="ROTATION", description="Degrees to rotate top")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')
    flip_normals: BoolProperty(name="Flip Normals", description="Flip normals on extruded faces", default=False)
    side_material: EnumProperty(name="Side Material", items=enum_nonplan_material)
    center_material: EnumProperty(name="Center Material", items=enum_nonplan_material)
    keep_y: BoolProperty(name="Keep Y", description="Keep face y orientation instead of using extrude direction", default=False)
    del_source: BoolProperty(name="Delete Source", description="Remove starting faces", default=False)

    field_layout = [
        ['distance', 'steps'],
        ['both_directions'],
        ['flip_normals', 'on_axis'],
        [{'on_axis': True}, 'axis'],
        [{'on_axis': True}, 'align_end'],
        ['twist'],
        ['size'],
        ['del_source', 'keep_y'],
        ['side_material'],
        ['center_material']
    ]

    topology_lock = ['steps', 'twist']


class SweepProperty(CustomPropertyBase):
    origin: PointerProperty(name="Origin", type=DirectionProperty)
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    angle: FloatProperty(name="Angle", default=math.pi, min=-2*math.pi, max=2*math.pi, unit="ROTATION", description="Sweep Angle")
    steps: IntProperty(name="Steps", min=1, default=8, description="Number of steps along axis")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')
    side_material: EnumProperty(name="Side Material", items=enum_nonplan_material)
    center_material: EnumProperty(name="Center Material", items=enum_nonplan_material)
    y_up: BoolProperty(name="Y up", description="Make new faces y orientation up of using extrude direction", default=False)

    field_layout = [
        ['origin'],
        ['axis'],
        ['angle', 'steps'],
        ['size'],
        ['side_material'],
        ['center_material'],
        ['y_up']
    ]

    topology_lock = ['steps']


class MakeLouversProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=1, default=1, description="Number of vertical divisions")
    count_y: IntProperty(name="Y Count", min=2, default=10, description="Number of blades in each louver")
    margin_x: FloatProperty(name="X Margin", min=0.0, default=0.03, unit="LENGTH", description="Space on sides of louvers")
    margin_y: FloatProperty(name="Y Margin", min=0.0, default=0.03, unit="LENGTH",
                            description="Space above and below louvers")
    blade_angle: FloatProperty(name="Blade Angle", min=-90.0, max=90, default=-45.0/180*math.pi, unit="ROTATION", description="Degrees, 0 for horizontal")
    blade_thickness: FloatProperty(name="Blade Thickness", min=0.0, default=0.003, unit="LENGTH", description="Single blade thickness")
    depth_thickness: FloatProperty(name="Depth Thickness", min=0.0, default=0.03, unit="LENGTH", description="Depth thickness of louvers")
    depth_offset: FloatProperty(name="Depth Offset", default=0.03, unit="LENGTH", description="Out of plane offset (from face)")
    flip_xy: BoolProperty(name="Flip xy", default=False, description="Change orientation")
    connect_louvers: BoolProperty(name="Connected", default=False, description="Connect to make bellows")
    material: EnumProperty(name="Material", items=enum_nonplan_material)
    del_source: BoolProperty(name="Delete Source", description="Remove starting faces", default=False)

    field_layout = [
        ['count_x', 'count_y'],
        ['margin_x', 'margin_y'],
        ['blade_angle', 'blade_thickness'],
        ['depth_thickness', 'depth_offset'],
        ['flip_xy', 'connect_louvers'],
        ['material'],
        ['del_source']
    ]

    topology_lock = ['count_x', 'count_y', 'flip_xy']


window_sash_enum = [
    ('Picture', 'Picture', 'Single section fixed window'),
    ('Casement', 'Casement', 'Lower section swings open'),
    ('French', 'French Door', 'Double casement full height'),
    ('Sliding', 'Sliding', 'Sideways slide in plain, picture in arches'),
    ('Hung', 'Hung', 'Vertical slide'),
]


class CatalogScriptProperty(CustomPropertyBase):
    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    style_name: EnumProperty(items=enum_styles, description="Style", default=0)
    category_name: EnumProperty(items=enum_categories, name="Category", default=0)
    category_item: EnumProperty(items=enum_category_items, name="Objects", default=0)
    show_scripts: BoolProperty(name="Show Scripts", default=True)
    show_curves: BoolProperty(name="Show Curves", default=False)

    field_layout = [
        ['style_name'],
        ['category_name'],
        ['search_text'],
        ['category_item'],
    ]

    topology_lock = ['category_item']
    previews = ['category_item']


class SimpleWindowProperty(CustomPropertyBase):  # demo case
    window_count: IntProperty(name="Window Count", min=1, max=3, default=1, description="Number of window sections across")
    center_higher: FloatProperty(name="Raise Center", default=0, description="Adjust center of 3 windows")
    size: PointerProperty(type=SizeProperty, name="Window Size")
    position: PointerProperty(type=PositionProperty, name="Window Position")
    wall_thickness: FloatProperty(name="Wall Thickness", default=0.2, min=0.1)
    outer_width: FloatProperty(name="Outer Frame Width", default=0.17, description="Width of outer frame")
    trim_width: FloatProperty(name="Trim Width", default=0.075, min=0)
    inner_protrude: FloatProperty(name="Inner Trim Protrude", default=0)
    frame_protrude: FloatProperty(name="Frame Protrude", default=0)
    lintel_protrude: FloatProperty(name="Lintel Protrude", default=0.02, min=0)
    sill_protrude: FloatProperty(name="Sill Protrude", default=0.04, min=0)
    pane_size: FloatProperty(name="Pane size", default=0.2)
    muntin_angle: FloatProperty(name="Muntin Angle", default=0, unit='ROTATION')
    sash: EnumProperty(name="Sash Type", items=window_sash_enum, default='Hung')
    outer_arch_type: EnumProperty(name="Outer Arch Type", items=ArchShapeProperty.arch_type_list, default='JACK')
    inner_arch_type: EnumProperty(name="Inner Arch Type", items=ArchShapeProperty.arch_type_list, default='JACK')
    outer_key: BoolProperty(name="Outer Key", default=False, description="Add keystone to outer")
    inner_key: BoolProperty(name="Inner Key", default=False, description="Add keystone to inner")
    top_gap: FloatProperty(name="Frieze Gap", description="Minimum space between outer arch and inner arch at top")
    max_outer_arch: FloatProperty(name="Limit outer arch", default=2, description="Max outer arch ratio h/w")
    max_inner_arch: FloatProperty(name="Limit inner arch", default=2, description="Max inner arch ratio h/w")
    # lookup stuff
    show_scripts: BoolProperty(name="scripts", default=True)
    search_text: StringProperty(name="search", default="Left_Shutter")
    category_name: StringProperty(name="category", default="Shutters")
    shutters: EnumProperty(name="Shutters", items=enum_category_items)
    # materials
    trim_material: EnumProperty(name="Trim Material", items=enum_nonplan_material)
    outer_material: EnumProperty(name="Outer Frame Material", items=enum_nonplan_material)
    key_material: EnumProperty(name="Keystone Material", items=enum_nonplan_material)
    shutter_material: EnumProperty(name="Shutter Material", items=enum_nonplan_material)
    frieze_material: EnumProperty(name="Frieze Material", items=enum_nonplan_material)
    hide_outer_sides: BoolProperty(name="Hide Sides", default=False, description="Make outer top and bottom only")

    field_layout = [
        ['size'],
        ['position'],
        ["wall_thickness", "trim_width", 'outer_width'],
        ['frame_protrude', 'lintel_protrude'],
        ['inner_protrude', 'sill_protrude'],
        ['pane_size', 'muntin_angle'],
        ['sash'],
        ['outer_arch_type', 'outer_key'],
        ['inner_arch_type', 'inner_key'],
        ['max_outer_arch', 'max_inner_arch'],
        ['window_count', 'top_gap'],
        [{'window_count': 1}, 'center_higher'],
        [{'window_count': 1}, 'shutters'],
        [{'window_count': 1}, 'shutter_material'],
        ['trim_material', 'frieze_material'],
        ['outer_material', 'hide_outer_sides'],
        ['key_material']
    ]

    topology_lock = ['window_count', 'sash', 'shutters', 'outer_key', 'inner_key']
    previews = ['shutters']


door_type_enum = [
    ('Left', 'Left', 'Single Left Hinge'),
    ('Right', 'Right', 'Single Right Hinge'),
    ('French', 'French Door', 'Double door'),
    ('Sliding', 'Sliding', 'Double, offset for sliding')
]


class SimpleDoorProperty(CustomPropertyBase):
    size: PointerProperty(type=SizeProperty, name="Window Size")
    position: PointerProperty(type=PositionProperty, name="Window Position")
    wall_thickness: FloatProperty(name="Wall Thickness", default=0.2, min=0.1)
    trim_width: FloatProperty(name="Trim Width", default=0.075, min=0)
    frame_protrude: FloatProperty(name="Frame Protrude", default=0)
    open_in: BoolProperty(name="Open In", default=True, description="Open in or out")
    door_type: EnumProperty(name="Door Type", items=door_type_enum, default='Left')
    arch_type: EnumProperty(name="Arch Type", items=ArchShapeProperty.arch_type_list, default='JACK')

    knob: PointerProperty(name="Knob", type=CatalogObjectProperty)
    hinges: PointerProperty(name="Hinge", type=CatalogObjectProperty)
    finish: PointerProperty(name="Finish", type=CatalogScriptProperty)

    field_layout = [
        ['door_type'],
        ['arch_type'],
        ['size'],
        ['position'],
        ['wall_thickness', 'frame_protrude'],
        ['open_in', 'trim_width'],
        ['knob'],
        ['hinges'],
        ['finish']
    ]
    topology_lock = ['door_type', 'finish']
    previews = []


class SimplePorticoProperty(CustomPropertyBase):
    width: FloatProperty(name="Width", min=0.5, default=2, description="Width of portico")
    height: FloatProperty(name="Height", default=0.5, min=0, description="Height of roof peak above soffit")
    soffit: FloatProperty(name="Soffit", default=0.2, min=0, description="Height of soffit")
    depth: FloatProperty(name="Depth", default=0.5, min=0.152, description="Overhang depth of portico")

    field_layout = [
        ['width'],
        ['height', 'soffit'],
        ['depth']
    ]
    topology_lock = []


class SimpleRailProperty(CustomPropertyBase):
    rail_spacing: FloatProperty(name="Rail Spacing", default=0.15, description="Distance between vertical bars")
    post_size: FloatProperty(name="Post Width", default=0.152, description="Width of corner posts")
    vert_size: FloatProperty(name="Vertical Rail Width", default=0.03, description="Width of vertical rails")
    turned: BoolProperty(name="Fancy verticals", description="Use curve revolution instead of square", default=False)

    field_layout = [
        ['rail_spacing'],
        ['vert_size'],
        ['turned'],
        ['post_size']
    ]
    topology_lock = []


class ExtendGableProperty(CustomPropertyBase):
    soffit_width: FloatProperty(name="Soffit Width", default=0.2, description="Thickness of soffit")
    overhang: FloatProperty(name="Overhang", default=0.1, description="Extension past wall")

    field_layout = [
        ['soffit_width', 'overhang']
    ]
    topology_lock = []


class DormerProperty(CustomPropertyBase):
    offset_x: FloatProperty(name="Offset X", default=0, description="Offset from center of face")
    octagon_window: BoolProperty(name="Octagon Window", default=False, description="Toggle octagor or square window")

    field_layout = [
        ['offset_x'],
        ['octagon_window'],
    ]
    topology_lock = []


class DeckProperty(CustomPropertyBase):
    size: PointerProperty(name="Size", type=SizeProperty)
    position: PointerProperty(name="Position", type=PositionProperty)
    elevation: FloatProperty(name="Elevation", description="Height above base", default=0)
    sides: IntProperty(name="Sides", description="Polygon sides", default=4)
    roof: BoolProperty(name="Add Roof", description="Add roof, edit extrude direction to attach to wall", default=False)

    field_layout = [
        ['position'],
        ['size'],
        ['sides', 'elevation'],
        ['roof']
    ]
    topology_lock = ['roof']


class LatticeProperty(CustomPropertyBase):
    angle_1: FloatProperty(name="Angle 1", unit="ROTATION", description="Angle of front slats", default=math.pi / 4,
                           min= 0, max=math.pi / 2)
    angle_2: FloatProperty(name="Angle 2", unit="ROTATION", description="Angle of back slats", default=math.pi / 4,
                           min=0, max=math.pi / 2)
    separation: FloatProperty(name="Separation", description="Front to back offset", default=0)
    width: FloatProperty(name="Slat width", description="Width of slats", default=0.01)
    depth: FloatProperty(name="Slat depth", description="Depth of slats", default=0.01)
    spacing: FloatProperty(name="Slat spacing", description="Spacing of slats", default=0.1)
    material: EnumProperty(name="Material", items=enum_nonplan_material, description="Material for new faces")

    field_layout = [
        ['angle_1', 'angle_2'],
        ['separation', 'spacing'],
        ['width', 'depth'],
        ['material']
    ]

    topology_lock = ['spacing']


class MeshImportProperty(CustomPropertyBase):
    use_catalog: BoolProperty(name="From Catalog", default=False)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    position: PointerProperty(name="First Offset", type=PositionProperty)
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    scale: FloatProperty(name="Scale Instance", description="Resize instance", default=1)
    rotation: FloatVectorProperty(name="Euler Rotation", subtype="EULER", description="Rotation of object")
    array: PointerProperty(name="Array", type=ArrayProperty)
    as_instance: BoolProperty(name="As Instance", default=True, description="Use instancing instead of merging mesh")

    field_layout = [
        ['position'],
        ['rotation'],
        ['z_offset', 'scale'],
        ['as_instance', 'use_catalog'],
        [{'as_instance': True}, 'array'],
        ({'use_catalog': True}, 'catalog_object'),
        ({'use_catalog': False}, 'local_object'),
    ]

    topology_lock = ['as_instance', 'mesh_type']


class FlipNormalProperty(CustomPropertyBase):
    toggle: BoolProperty(name="Toggle", description="Click to toggle")

    field_layout = [['toggle']]
    topology_lock = []


class ProjectFaceProperty(CustomPropertyBase):
    target: IntProperty(name='Target', description='Face defining projection plane', default=0)
    material: EnumProperty(name="Material", items=enum_nonplan_material, description="Material for new faces")
    bridge: BoolProperty(name='Bridge', description="Bridge to target", default=False)
    hip: BoolProperty(name='Hip', description="Hip join around bend", default=False)

    field_layout = [['target'],
                    ['bridge', 'hip'],
                    ['material']]

    topology_lock = ['bridge']


class BuildFaceProperty(CustomPropertyBase):
    material: EnumProperty(name="Material", items=enum_nonplan_material, description="Material for new faces")
    flip_normal: BoolProperty(name="Flip normal", description="Flip normal direction")

    field_layout = [
        ['material'],
        ['flip_normal']
    ]

    topology_lock = []


class UnionPolyProperty(CustomPropertyBase):
    material: EnumProperty(name="Material", items=enum_nonplan_material, description="Material for new face")
    radial: PointerProperty(name="Y direction", type=DirectionProperty)

    field_layout = [
        ['material'],
        ['radial']
    ]

    topology_lock = []


class BuildRoofProperty(CustomPropertyBase):
    slope: FloatProperty(name="Slope", description="Tangent slope", default=0.6)
    hip: BoolProperty(name="Hip", description="Make hip roof instead of shed roof", default=True)
    shed_side: IntProperty(name="High side", description="Face side for top of shed", default=0)
    gable_sides: StringProperty(name="Gable sides", description="Comma separated list of numbers, or empty for none")
    wall_material: EnumProperty(name="Wall Material", items=enum_nonplan_material, description="Material for gable walls")

    field_layout = [
        ['slope', 'hip'],
        [{'hip': True}, 'gable_sides'],
        [{'hip': False}, 'shed_side'],
        ['wall_material'],
    ]
    topology_lock = ['hip']


stair_shape_type_list = [
    ("NGON", "Regular Polygon", "N-sided polygon", 0),
    ("CURVE", "Local Curve", "Curve from this blend file", 1),
    ("CATALOG", "Catalog Curve", "Curve from catalog file", 2),
    ]


class BuildStairsProperty(CustomPropertyBase):
    position: PointerProperty(name="Position on Face", type=PositionProperty)
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    rotation: FloatVectorProperty(name="Euler Rotation", subtype="EULER", description="Rotation of object")
    curved: BoolProperty(name="Curved", default=False, description="Curved or straight")
    curve_left: BoolProperty(name="Curve Left", default=True, description="Curve to left or right on the way up")
    open_riser: BoolProperty(name="Open Risers", default=False, description="Open or closed between steps")
    radius: FloatProperty(name="Radius", default=1, description="Inside radius for curved stairs")
    w_tread: FloatProperty(name="Step Width", default=0.9, description="Width of steps")
    d_tread: FloatProperty(name="Tread Depth", default=0.2, description="Size of step front to back")
    thickness: FloatProperty(name="Tread Thickness", default=0.03, description="Thickness of step material")
    overhang: FloatProperty(name="Tread Overhang", default=0, description="Step overhang past riser")
    height: FloatProperty(name="Height", default = 2.9, description="Overall height of stairs")
    h_tread: FloatProperty(name="Riser Height", default = 0.15, description="Height of each step")
    rotation: FloatProperty(name="Rotation", default=0, description="Rotation of stairs", unit="ROTATION")
    min_support: FloatProperty(name="Support", default=0.1, description="Thickness of support under steps")

    rails: BoolProperty(name="Add railings", default=False, description="Add handrails")
    right_rail: BoolProperty(name="Right Rail", default=False, description="Add Right handrail")
    left_rail: BoolProperty(name="Left Rail", default=False, description="Add Left handrail")
    revolutions: IntProperty(name="Revolutions", description="If > 3, make a revolution of n steps for balusters", default=0)
    rail_type: EnumProperty(name="Shape Type", default="NGON", items=stair_shape_type_list)
    rail_poly: PointerProperty(name="Poly", type=PolygonProperty)
    rail_local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    rail_catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    rail_resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")
    rail_ht: FloatProperty(name="Rail Height", default=1, description="Handrail height")
    rail_inset: FloatProperty(name="Rail Inset", default=0, description="Handrail inset from edge")
    rail_size: PointerProperty(name="Rail Size", type=SizeProperty)

    balusters: BoolProperty(name="Balusters", default=False, description="Add faces for balusters under handrail")

    bottom_rail: BoolProperty(name="Bottom Rail", default=False, description="Add bottom rail under balusters")
    bot_rail_ht: FloatProperty(name="Bottom Rail Height", default=.1, description="Bottom rail height")
    bot_rail_w: FloatProperty(name="Bottom Rail Width", default=.05, description="Bottom rail width")
    bot_rail_d: FloatProperty(name="Bottom Rail Depth", default=.05, description="Bottom rail depth")

    tread_material: EnumProperty(items=enum_nonplan_material, name="Tread material", description="Material for steps")
    riser_material: EnumProperty(items=enum_nonplan_material, name="Riser material", description="Material for risers")
    support_material: EnumProperty(items=enum_nonplan_material, name="Support material", description="Material for supports")
    rail_material: EnumProperty(items=enum_nonplan_material, name="Rail material", description="Material for handrail")

    field_layout = [
        ['position'],
        ['z_offset', 'rotation'],
        ['height', 'h_tread'],
        ['w_tread', 'd_tread'],
        ['thickness', 'open_riser'],
        ['overhang'],
        ['curved', 'curve_left'],
        ['radius', 'min_support'],
        ['rails', 'balusters', 'bottom_rail'],
        ({'rails': True}, 'left_rail', 'right_rail'),
        ({'rails': True}, 'rail_ht', 'rail_inset'),
        ({'rails': True}, 'rail_type'),
        ({'rails': True}, 'rail_size'),
        ({'rail_type': 'NGON', 'rails': True}, 'rail_poly'),
        ({'rail_type': 'CURVE', 'rails': True}, 'rail_local_object'),
        ({'rail_type': 'CATALOG', 'rails': True}, 'rail_catalog_object'),
        ({'rails': True, 'rail_type': {'CATALOG', 'CURVE'}}, 'rail_resolution'),
        ({'bottom_rail': True}, 'bot_rail_ht'),
        ({'bottom_rail': True}, 'bot_rail_w', 'bot_rail_d'),
        ['tread_material'],
        ['riser_material'],
        ['support_material'],
        ['rail_material']
    ]

    topology_lock = ['height', 'h_tread']


class NicheProperty(CustomPropertyBase):
    position: PointerProperty(name="Position on Face", type=PositionProperty)
    size: PointerProperty(name="Size of bounding box", type=SizeProperty, description="Bounding box size")
    add_perimeter: BoolProperty(name="Add Perimeter Points", description="Add points to perimeter to match if needed",
                                default=False)
    frame_bricks: FloatProperty(name="Frame Bricks", default=1, description="Thickness of frame in bricks")
    brick_ht: FloatProperty(name="Brick Height", min=0.01, default=0.05, description="Brick height")
    brick_len: FloatProperty(name="Brick Len", min=0.01, default=0.17, description="Brick length")
    recess: FloatProperty(name="Recess", default=0.2, unit="LENGTH", description="Recess back distance")
    keystone: BoolProperty(name="Keystone", default=False, description="Add Keystone")
    arch_type: EnumProperty(name="Arch Type", items=ArchShapeProperty.arch_type_list, default='ROMAN')

    field_layout = [
        ['arch_type'],
        ['position'],
        ['size'],
        ['brick_ht', 'brick_len'],
        ['frame_bricks', 'recess'],
        ['add_perimeter', 'keystone']
    ]

    topology_lock = []


class QuoinDivideProperty(CustomPropertyBase):
    tooth_height: FloatProperty(name="Tooth Height", default=1, description="Height in bricks")
    long_width: FloatProperty(name="Long Width", default=1, description="Long tooth size in bricks")
    short_width: FloatProperty(name="Short Width", default=0.5, description="Short tooth size in bricks")
    start_long: BoolProperty(name="Start Long", description="First tooth long or short", default=True)
    left_side: BoolProperty(name="Left Side", description="Inset from left or right", default=True)
    inset: FloatProperty(name="Inset", default=0, description="Inset from edge in bricks")


    field_layout = [
        ['tooth_height', 'inset'],
        ['long_width', 'short_width'],
        ['start_long', 'left_side']
    ]

    topology_lock = ['left_side']


class PlanInsetWallsProperty(CustomPropertyBase):
    side_list: StringProperty(name="Sides", description="Comma separated list of numbers, or empty for all")
    thickness: FloatProperty(name="Thickness", description="Wall thickness", default=0.1)
    material: EnumProperty(items=enum_plan_wall_material, name="Wall type", description="Wall type to insert")

    field_layout = [
        ['side_list'],
        ['thickness'],
        ['material']
    ]

    topology_lock = []


class PlanFeatureProperty(CustomPropertyBase):
    material: EnumProperty(items=enum_plan_material, name="Feature", description="Wall feature to insert")
    offset: FloatProperty(name="Offset", description="Offset from end of wall segment", min=0, default=0)
    size: FloatProperty(name="Width", description="Size of feature", min=0, default=1)
    flip_x: BoolProperty(name="Flip X", description="Flip left/right", default=False)
    flip_y: BoolProperty(name = "Flip Y", description="Flip inside/outside", default=False)

    field_layout = [
        ['material'],
        ['offset', 'size'],
        ['flip_x', 'flip_y']
    ]

    topology_lock = []  # note, we will use ensure_children to delete any children rather than lock this


class PlanFloorProperty(CustomPropertyBase):
    material: EnumProperty(items=enum_plan_floor_material, name="Feature", description="Wall feature to insert")
    rotation: FloatProperty(name="Rotate Floor", default = 0, unit="ROTATION", description="Rotate floor UV direction")
    elevation: FloatProperty(name="Elevation", description="Offset from plan elevation", default=0)


    field_layout = [
        ['material'],
        ['rotation', 'elevation'],
    ]

    topology_lock = []


dimension_dict = {}
dimension_enum = []


def load_dimensions():
    from .dynamic_enums import qarch_asset_dir
    global dimension_enum, dimension_dict
    p = qarch_asset_dir / "default/dimensions.txt"
    txt = p.read_text()
    lst = txt.split("\n")
    lst = [line.split(",") for line in lst]
    for row in lst:
        if len(row)==4:
            e = (row[0], row[0], '')
            dimension_enum.append(e)
            dimension_dict[row[0]] = {'width': float(row[1]), 'height': float(row[2]), 'gap': float(row[3])}


load_dimensions()
updating = 0


def update_calculator_ref(self, context):
    global updating
    updating = 2  # each triggered update will decrement this to prevent loops
    self.open_x = self.calc_open_x()
    self.open_y = self.calc_open_y()


def update_open_x(self, context):
    global updating
    if updating > 0:
        updating -= 1
    else:
        updating = 1
        self.n_x = self.calc_n_x()


def update_open_y(self, context):
    global updating
    if updating > 0:
        updating -= 1
    else:
        updating = 1
        self.n_y = self.calc_n_y()



def update_n_x(self, context):
    global updating
    if updating > 0:
        updating -= 1
    else:
        updating = 1
        self.open_x = self.calc_open_x()


def update_n_y(self, context):
    global updating
    if updating > 0:
        updating -= 1
    else:
        updating = 1
        self.open_y = self.calc_open_y()


class CalculatorProperty(bpy.types.PropertyGroup):
    ref_dimension: EnumProperty(items=dimension_enum, name="Reference", description="Object for size calculations",
                                default="brick", update=update_calculator_ref)
    n_x: FloatProperty(name="Num wide", default=1, min=0, update=update_n_x)
    n_y: FloatProperty(name="Num high", default=1, min=0, update=update_n_y)
    open_x: FloatProperty(name="Width", description="num * (width + gap)", min=0, update=update_open_x)
    open_y: FloatProperty(name="Height", description="num * (height + gap)", min=0, update=update_open_y)

    def draw(self, context, layout):
        row = layout.row(align=True)
        row.prop_menu_enum(self, 'ref_dimension', text=self.ref_dimension)
        row = layout.row(align=True)
        dat = dimension_dict[self.ref_dimension]
        row.label(text="width {width:.3f}, height {height:.3f}, gap {gap:.3f}".format(**dat))
        row = layout.row(align=True)
        row.prop(self, 'n_x')
        row.prop(self, 'n_y')
        row = layout.row(align=True)
        row.prop(self, 'open_x')
        row.prop(self, 'open_y')

    def calc_open_x(self):
        dat = dimension_dict[self.ref_dimension]
        ref = self.ref_dimension
        if ('door' in ref) or ('window' in ref):  # trim both sides
            return (dat['width'] + 2*dat['gap']) * self.n_x
        return (dat['width'] + dat['gap']) * self.n_x - dat['gap']  # remove final gap (mortar)

    def calc_open_y(self):
        dat = dimension_dict[self.ref_dimension]
        ref = self.ref_dimension
        if 'door' in ref:  # top trim
            return (dat['height'] + dat['gap']) * self.n_y
        elif 'window' in ref:  # trim both sides
            return (dat['height'] + 2 * dat['gap']) * self.n_y
        return (dat['height'] + dat['gap']) * self.n_y - dat['gap']  # remove final gap (mortar)

    def calc_n_x(self):
        dat = dimension_dict[self.ref_dimension]
        ref = self.ref_dimension
        if ('door' in ref) or ('window' in ref):  # trim both sides
            return self.open_x / (dat['width'] + 2*dat['gap'])
        return (self.open_x + dat['gap']) / (dat['width'] + dat['gap'])

    def calc_n_y(self):
        dat = dimension_dict[self.ref_dimension]
        ref = self.ref_dimension
        if 'door' in ref:  # top trim
            return self.open_y / (dat['height'] + dat['gap'])
        elif 'window' in ref:  # trim both sides
            return self.open_y / (dat['height'] + 2 * dat['gap'])
        return (self.open_y - dat['gap']) / (dat['height'] + dat['gap'])


class BTAddonPreferences(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = base_package

    user_tags: StringProperty(name="Face tags", description="Comma separated list of custom tags")
    select_mode: EnumProperty(
        name="Selection Mode", description="How to handle multiple face selection",
        items=[('SINGLE','Single Faces','Each face gets separate property record'),
               ('GROUP','Group of Faces','Each face gets same property record'),
               ('REGION', 'Region', 'Treat as one big face')
               ], default='SINGLE',)
    # build_style: StringProperty(name="Build Styles", description="Comma separated list of styles")  # keep?
    # storage for use by the calculator panel
    calc_prop: PointerProperty(type=CalculatorProperty)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Build Tools Preferences")
        layout.prop(self, "user_tags")
        layout.prop(self, "select_mode")
        # layout.prop(self, "build_style")

class StyleNameProperty(bpy.types.PropertyGroup):
    group: StringProperty(name="Group")
    style: StringProperty(name="Style")
    active: BoolProperty(name="Active")


class QARCH_UL_Styles(bpy.types.UIList):
    """Demo UIList."""
    bl_idname = "QARCH_UL_Styles"

    # https://sinestesia.co/blog/tutorials/using-uilists-in-blender/
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # Make sure your code supports all 3 layout types
        row = layout.row()
        if self.layout_type in {'DEFAULT'}:
            row.label(text=item.group)
            row.label(text=item.style)
        else:  # {'COMPACT','GRID'}
            row.label(text=item.style)
        row.prop(item, 'active', text="")
