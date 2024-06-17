import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty, StringProperty
from bpy.props import FloatVectorProperty, CollectionProperty
from bpy.types import AddonPreferences, FileAssetSelectParams, UserAssetLibrary
import math
from .custom import CustomPropertyBase
from collections import OrderedDict
from ..object import enum_oriented_material, enum_all_material
from .dynamic_enums import enum_catalogs, enum_categories, enum_category_items, enum_objects_or_curves
from .dynamic_enums import face_tag_to_int, int_to_face_tag, get_face_tag_enum


uv_mode_list = [
        ('GLOBAL_XY', 'Global XY', 'Use real units projected to face'),
        ('FACE_XY', 'Face XY', 'Use face x/y in real units'),
        ('FACE_BBOX', 'Bounding Box', 'Set bounding box 0-1'),
        ('FACE_POLAR', 'FACE Polar', 'Use face polar coordinates from centroid'),
        ('GLOBAL_YX', 'Global YX', 'Flip x and y, use real units projected to face'),
        ('FACE_YX', 'Face YX', 'Flip x and y, use real units'),
        ('ORIENTED', 'Oriented', 'Specify global rotation around origin for volumetrics'),
        ('NONE', 'None', 'Do not auto-calculate UV'),  # so we don't erase something the user did
    ]


def uv_mode_to_int(s):
    for i, e in enumerate(uv_mode_list):
        if e[0] == s:
            return i
    return 0


def int_to_uv_mode(i):
    return uv_mode_list[i][0]



class FaceTagProperty(CustomPropertyBase):
    tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for selection")
    field_layout = [['tag']]
    topology_lock = []


class FaceThicknessProperty(CustomPropertyBase):
    thickness: FloatProperty(name="Face Thickness", default=0, min=0, description="Wall thickness after finalization")
    field_layout = [['thickness']]
    topology_lock = []


class FaceUVModeProperty(CustomPropertyBase):
    uv_mode: EnumProperty(name="UV Mode", description="Method of UV assignment", items=uv_mode_list, default="GLOBAL_XY")
    field_layout = [['uv_mode']]
    topology_lock = []


class FaceUVOriginProperty(CustomPropertyBase):
    uv_origin: FloatVectorProperty(name="UV Origin", subtype="XYZ", description="Origin of UV coordinates")
    field_layout = [['uv_origin']]
    topology_lock = []


class FaceUVRotateProperty(CustomPropertyBase):
    uv_rotate: FloatVectorProperty(name="UV Rotation", subtype="XYZ", description="Rotation of UV coordinates")
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
    ]
    # has_keystone: BoolProperty(name="Keystone", default=False)
    arch_type: EnumProperty(name="Arch Type", items=arch_type_list, description="Type of arch", default="ROMAN")
    num_sides: IntProperty(name="Num Sides", min=2, default=12, description="Number of sides")

    field_layout = [
        ["num_sides"],
        ["arch_type"],
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
        ('', 'direction'),
        ('do_orbit', 'origin')
    ]

    topology_lock = ['count']


class PositionProperty(CustomPropertyBase):
    offset_x: FloatProperty(name="Offset X", default=0.0, unit="LENGTH", description="Face X position")
    is_relative_x: BoolProperty(name="Relative", default=False, description="Relative position (0-1) for x")
    offset_y: FloatProperty(name="Offset Y", default=0.0, unit="LENGTH", description="Face Y position")
    is_relative_y: BoolProperty(name="Relative", default=False, description="Relative position (0-1) for y")

    field_layout = [
        ['offset_x', 'is_relative_x', 'offset_y', 'is_relative_y'],
    ]

    topology_lock = []


class SizeProperty(CustomPropertyBase):
    size_x: FloatProperty(name="Size X", default=1.0, unit="LENGTH", description="Face X size")
    is_relative_x: BoolProperty(name="Relative", default=True, description="Relative size (0-1) for x")
    size_y: FloatProperty(name="Size Y", default=1.0, unit="LENGTH", description="Face Y size")
    is_relative_y: BoolProperty(name="Relative", default=True, description="Relative size (0-1) for y")

    field_layout = [
        ['size_x', 'is_relative_x', 'size_y', 'is_relative_y'],
    ]

    topology_lock = []


class GridDivideProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=0, default=1, description="Number of vertical rows")
    count_y: IntProperty(name="Y Count", min=0, default=1, description="Number of horizontal cols")
    offset: PointerProperty(name="offset", type=PositionProperty)

    field_layout = [
        ['count_x', 'count_y'],
        ('Offset Grid', 'offset'),
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

    field_layout = [
        ['num_sides', 'start_angle'],
    ]

    topology_lock = ['num_sides']


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
    style_name: EnumProperty(items=enum_catalogs, description="Style", default=0)
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


class UnionPolygonProperty(CustomPropertyBase):
    position: PointerProperty(name="Position", type=PositionProperty)
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    poly: PointerProperty(name="Poly", type=PolygonProperty)

    field_layout = [
        ('', 'position'),
        ('', 'size'),
        ('', 'poly'),
    ]

    topology_lock = []


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
    ('INSIDE', 'Inside', 'Clip and keep part inside old face', 3)
]


class InsetPolygonProperty(CustomPropertyBase):
    position: PointerProperty(name="Position", type=PositionProperty)
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    join: EnumProperty(name="Join", items=lst_join_enum, default="BRIDGE")
    add_perimeter: BoolProperty(name="Add Perimeter Points", description="Add points to perimeter to match if needed", default=False)
    extrude_distance: FloatProperty(name="Extrude Distance", default=0.0, unit="LENGTH", description="Extrude distance")
    frame_material: EnumProperty(name="Frame Material", items=enum_all_material)
    center_material: EnumProperty(name="Center Material", items=enum_all_material)

    shape_type: EnumProperty(name="Shape Type", default="SELF", items=shape_type_list)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    frame: FloatProperty(name="Frame Thickness", min=0, default=0.1, description="Polygon donut instead of solid face")
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    super_curve: PointerProperty(name="Super", type=SuperCurveProperty)
    resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")

    field_layout = [
        ('Position on Face', 'position'),
        ('Size of bounding box', 'size'),
        ['join'],
        ({'join': 'BRIDGE'}, 'add_perimeter'),
        ['shape_type'],
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


class SolidifyEdgesProperty(CustomPropertyBase):
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    side_list: StringProperty(name="Sides", description="Comma separated list of numbers, or empty for all")
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    inset: FloatProperty(name="Inset Offset", description="Distance off edge", default=0)
    face_tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for selection")
    frame_material: EnumProperty(name="Frame Material", items=enum_all_material)
    revolutions: IntProperty(name="Revolutions", description="If > 3, make a revolution of n steps instead of extrusion", default = 0)
    shape_type: EnumProperty(name="Shape Type", default="NGON", items=shape_type_list)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    frame: FloatProperty(name="Frame Thickness", min=0, default=0.1, description="Polygon donut instead of solid face")
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    super_curve: PointerProperty(name="Super", type=SuperCurveProperty)
    resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")

    # wouldn't it be nice to do "revolution" to make shaped columns along edges? in that case we wouldnt be
    # extruding the curve, we'd stretch it to fit the edge length and revolve it. Making corners match wouldn't
    # be possible in general (different sized ends) but the use case is for only one direction of edges so ok
    # advantage over mesh instances is the auto sizing if the edge changes length. FUTURE

    field_layout = [
        ('', 'size'),
        ['side_list'],
        ['z_offset', 'inset'],
        ['face_tag'],
        ['frame_material'],
        ['shape_type'],
        ({'shape_type': 'NGON'}, 'poly'),
        ({'shape_type': 'NGON'}, 'frame'),
        ({'shape_type': 'ARCH'}, 'arch'),
        ({'shape_type': 'SUPER'}, 'super_curve'),
        ({'shape_type': 'CURVE'}, 'local_object'),
        ({'shape_type': 'CATALOG'}, 'catalog_object'),
        ({'shape_type': {'CURVE', 'CATALOG', 'SUPER'}}, 'resolution'),
        ['revolutions'],
    ]

    topology_lock = ['shape_type', 'revolutions']


class ExtrudeProperty(CustomPropertyBase):
    distance: FloatProperty(name="Distance", default=0.1, unit="LENGTH", description="Extrude distance")
    steps: IntProperty(name="Steps", default=1, description="Number of steps along axis")
    on_axis: BoolProperty(name="On Axis", default=False, description="Direction other than normal")
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    align_end: BoolProperty(name="Align End", description="Align end face normal with axis", default=False)
    twist: FloatProperty(name="Twist Angle", default=0.0, unit="ROTATION", description="Degrees to rotate top")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')
    flip_normals: BoolProperty(name="Flip Normals", description="Flip normals on extruded faces", default=False)

    field_layout = [
        ['distance', 'steps'],
        ('on_axis','axis'),
        ['twist', 'align_end'],
        ('','size'),
        ['flip_normals'],
    ]

    topology_lock = ['steps', 'twist']


class SweepProperty(CustomPropertyBase):
    origin: PointerProperty(name="Origin", type=DirectionProperty)
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    angle: FloatProperty(name="Angle", default=math.pi, min=-2*math.pi, max=2*math.pi, unit="ROTATION", description="Sweep Angle")
    steps: IntProperty(name="Steps", min=1, default=8, description="Number of steps along axis")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')

    field_layout = [
        ('Rot Origin','origin'),
        ('Rot Axis','axis'),
        ['angle', 'steps'],
        ('','size'),
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
    face_tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for selection")

    field_layout = [
        ['count_x', 'count_y'],
        ['margin_x', 'margin_y'],
        ['blade_angle', 'blade_thickness'],
        ['depth_thickness', 'depth_offset'],
        ['flip_xy', 'connect_louvers'],
        ['face_tag']
    ]

    topology_lock = ['count_x', 'count_y', 'flip_xy']


class SimpleWindowProperty(CustomPropertyBase):  # demo case
    rel_x: FloatProperty(name="Relative X position", default = 0.5, description="X offset of window")
    width: FloatProperty(name="Absolute width", default = 1, description="Width of window")
    x_panes: IntProperty(name="X panes", min=1, default=2, description="Number of window panes across")
    y_panes: IntProperty(name="y panes", min=1, default=2, description="Number of window panes vertical")
    arch_height: FloatProperty(name="Arch", description="Arch height/width or 0 for flat top", default=0, min=0, max=1)

    field_layout = [
        ['rel_x','width'],
        ["x_panes","y_panes"],
        ["arch_height"]
    ]

    topology_lock = ['arch_height']


handle_side_enum = [
    ('LEFT', 'left', 'handle on left'),
    ('RIGHT', 'right', 'handle on right'),
]


class SimpleDoorProperty(CustomPropertyBase):
    rel_x: FloatProperty(name="Relative X position", default=0.5, description="X offset of door")
    handle_side: EnumProperty(items=handle_side_enum, name='Handle Side', default='LEFT')
    panel_depth: FloatProperty(name="Panel Depth", description='Raised panel bevel amount', default=0.025)

    field_layout = [
        ['rel_x', 'panel_depth'],
        ['handle_side']
    ]
    topology_lock = []


class SimpleRailProperty(CustomPropertyBase):
    rail_spacing: FloatProperty(name="Rail Spacing", default=0.2, description="Distance between vertical bars")

    field_layout = [
        ['rail_spacing']
    ]
    topology_lock = []


class ExtendGableProperty(CustomPropertyBase):
    soffit_width: FloatProperty(name="Soffit Width", default=0.1, description="Thickness of soffit")
    overhang: FloatProperty(name="Overhang", default=0.1, description="Extension past wall")

    field_layout = [
        ['soffit_width', 'overhang']
    ]
    topology_lock = []


class MeshImportProperty(CustomPropertyBase):
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    position: PointerProperty(name="Position", type=PositionProperty)
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    scale: FloatProperty(name="Scale Instance", description="Resize instance", default=1)
    rotation: FloatVectorProperty(name="Euler Rotation", subtype="EULER", description="Rotation of object")
    array: PointerProperty(name="Array", type=ArrayProperty)
    as_instance: BoolProperty(name="As Instance", default=True, description="Use instancing instead of merging mesh")

    field_layout = [
        ('First Offset', 'position'),
        ['rotation'],
        ['z_offset', 'scale'],
        ('as_instance', 'array'),
        ['local_object'],
    ]

    topology_lock = ['as_instance', 'mesh_type']


class FlipNormalProperty(CustomPropertyBase):
    toggle: BoolProperty(name="Toggle", description="Click to toggle")

    field_layout = [['toggle']]
    topology_lock = []


project_face_enum = [
    ('A2B', 'A to B', 'Outside of A to plane of B'),
    ('B2A', 'B to A', 'Outside of B to plane of A'),
    ('BRIDGE_AB', 'Bridge AB', 'Outside of A to outside of B'),
    ('BRIDGE_BA', 'Bridge BA', 'Outside of B to outside of A'),
]


class ProjectFaceProperty(CustomPropertyBase):
    mode: EnumProperty(name="Mode", items=project_face_enum, default="A2B")
    tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for new faces")

    field_layout = [['mode'],
                    ['tag']]

    topology_lock = ['mode']


class BuildFaceProperty(CustomPropertyBase):
    tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for new faces")
    flip_normal: BoolProperty(name="Flip normal", description="Flip normal direction")

    field_layout = [
        ['tag'],
        ['flip_normal']
    ]

    topology_lock = []

class BuildRoofProperty(CustomPropertyBase):
    height: FloatProperty(name="Height", description="Height to peak", default=2)

    field_layout = [['height']]
    topology_lock = []

class AssetLibProps(bpy.types.PropertyGroup):
    asset: CollectionProperty(name="Asset", description="Asset Name", type=bpy.types.AssetHandle)
    active: IntProperty(name="Index", description="Asset Index")

class BTAddonPreferences(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = "qarch"

    #user_script_path: StringProperty(name="User Script Path", subtype='FILE_PATH', description="Path to user generated scripts")
    user_tags: StringProperty(name="Face tags", description="Comma separated list of custom tags")
    select_mode: EnumProperty(
        name="Selection Mode", description="How to handle multiple face selection",
        items=[('SINGLE','Single Faces','Each face gets separate property record'),
               ('GROUP','Group of Faces','Each face gets same property record'),
               ('REGION', 'Region', 'Treat as one big face')
               ], default='SINGLE',)
    build_style: StringProperty(name="Build Styles", description="Comma separated list of styles")

    def draw(self, context):
        layout = self.layout
        layout.label(text="Build Tools Preferences")
        layout.prop(self, "user_tags")
        layout.prop(self, "select_mode")
        layout.prop(self, "build_style")


# order might matter
ops_properties = [
    FaceTagProperty,
    FaceThicknessProperty,
    FaceUVModeProperty,
    FaceUVOriginProperty,
    FaceUVRotateProperty,
    CalcUVProperty,
    ArchShapeProperty,
    CatalogObjectProperty,
    LocalObjectProperty,
    SuperCurveProperty,
    DirectionProperty,
    ArrayProperty,
    PositionProperty,
    SizeProperty,
    GridDivideProperty,
    SplitFaceProperty,
    PolygonProperty,
    UnionPolygonProperty,
    InsetPolygonProperty,
    ExtrudeProperty,
    SweepProperty,
    SolidifyEdgesProperty,
    MakeLouversProperty,
    SimpleWindowProperty,
    MeshImportProperty,
    BTAddonPreferences,
    OrientedMaterialProperty,
    FlipNormalProperty,
    ProjectFaceProperty,
    BuildFaceProperty,
    BuildRoofProperty,
    SimpleDoorProperty,
    SimpleRailProperty,
    ExtendGableProperty,
AssetLibProps
]
