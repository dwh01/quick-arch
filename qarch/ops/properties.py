import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty, StringProperty, FloatVectorProperty
from bpy.types import AddonPreferences
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


class ArrayProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=0, default=1, description="Number of vertical rows")
    count_y: IntProperty(name="Y Count", min=0, default=1, description="Number of horizontal cols")

    field_layout = [
        ['count_x', 'count_y'],
    ]

    topology_lock = ['count_x', 'count_y']


class DirectionProperty(CustomPropertyBase):
    x: FloatProperty(name="X", default=0.0, unit="LENGTH", description="X value")
    y: FloatProperty(name="Y", default=0.0, unit="LENGTH", description="Y value")
    z: FloatProperty(name="Z", default=1.0, unit="LENGTH", description="Z value")

    field_layout = [
        ['x','y','z']
    ]

    topology_lock = []


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
    category_name: EnumProperty(items=enum_categories, name="Category", default=0)
    category_item: EnumProperty(items=enum_category_items, name="Objects", default=0)
    show_scripts: BoolProperty(name="Show Scripts", default=False)
    show_curves: BoolProperty(name="Show Curves", default=False)
    rotate: FloatVectorProperty(name="Rotation", subtype="XYZ", description="Rotation of coordinates")

    field_layout = [
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
    rotate: FloatVectorProperty(name="Rotation", subtype="XYZ", description="Rotation of coordinates")

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
        ({'shape_type': 'NGON'}, 'frame'),
        ({'shape_type': 'ARCH'}, 'arch'),
        ({'shape_type': 'SUPER'}, 'super_curve'),
        ({'shape_type': 'CURVE'}, 'local_object'),
        ({'shape_type': 'CATALOG'}, 'catalog_object'),
        ({'shape_type': {'CURVE', 'CATALOG', 'SUPER'}}, 'resolution'),
        ({'shape_type': {'NGON', 'ARCH'}}, 'frame_material'),
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

    shape_type: EnumProperty(name="Shape Type", default="NGON", items=shape_type_list)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    frame: FloatProperty(name="Frame Thickness", min=0, default=0.1, description="Polygon donut instead of solid face")
    local_object: PointerProperty(name="Curve", type=LocalObjectProperty)
    catalog_object: PointerProperty(name="Catalog", type=CatalogObjectProperty)
    super_curve: PointerProperty(name="Super", type=SuperCurveProperty)
    resolution: IntProperty(name="Resolution", min=1, default=4, description="Curve resolution")

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
    ]

    topology_lock = ['shape_type']


class ExtrudeProperty(CustomPropertyBase):
    distance: FloatProperty(name="Distance", default=0.1, min=0, unit="LENGTH", description="Extrude distance")
    steps: IntProperty(name="Steps", default=1, description="Number of steps along axis")
    on_axis: BoolProperty(name="On Axis", default=False, description="Direction other than normal")
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    align_end: BoolProperty(name="Align End", description="Align end face normal with axis", default=False)
    twist: FloatProperty(name="Twist Angle", default=0.0, unit="ROTATION", description="Degrees to rotate top")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')

    field_layout = [
        ['distance', 'steps'],
        ('on_axis','axis'),
        ['twist', 'align_end'],
        ('','size'),
    ]

    topology_lock = ['steps', 'twist']


class SweepProperty(CustomPropertyBase):
    origin: PointerProperty(name="Origin", type=DirectionProperty)
    axis: PointerProperty(name="Axis", type=DirectionProperty)
    angle: FloatProperty(name="Angle", default=math.pi, min=-2*math.pi, max=2*math.pi, unit="ROTATION", description="Sweep Angle")
    steps: IntProperty(name="Steps", min=1, default=8, description="Number of steps along axis")
    size: PointerProperty(name='End Size', type=SizeProperty, description='Scale result face to this size')

    field_layout = [
        ('','origin'),
        ('','axis'),
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
    x_panes: IntProperty(name="X panes", min=1, default=2, description="Number of window lites across")
    y_panes: IntProperty(name="y panes", min=1, default=2, description="Number of window lites vertical")

    field_layout = [
        ["x_panes","y_panes"]
    ]

    topology_lock = ["x_panes","y_panes"]


class NewObjectProperty(CustomPropertyBase):
    name: StringProperty(name="Name", description="Name of new object")
    collection: StringProperty(name="Collection", description="Destination collection")

    field_layout = [
        ['name', 'collection']
    ]

    topology_lock = []


class RoomProperty(CustomPropertyBase):
    offset_x: FloatProperty(name="Offset X", default=0.0, unit="LENGTH", description="Placement along wall")
    size_x: FloatProperty(name="Size X", min=0, default=10.0, unit="LENGTH", description="Size along wall")
    depth: FloatProperty(name="Depth", min=0, default=10.0, unit="LENGTH", description="Extrusion distance")
    wall_thickness: FloatProperty(name="Wall Thickness", min=0, default=0.1, unit="LENGTH", description="Wall thickness")
    has_floor: BoolProperty(name="Floor", default=False)
    floor_thickness: FloatProperty(name="Floor Thickness", default=.1, unit="LENGTH", description="Floor thickness")
    has_turret: BoolProperty(name="Turret", default=False, description="Make turret (can wrap around corner)")
    turret_sides: IntProperty(name="Turret Sides", min=4, default=8, description="Number of sides in full circle")

    field_layout = [
        ['offset_x', 'size_x'],
        ['depth', 'wall_thickness'],
        ['has_floor', 'floor_thickness'],
        ['has_turret', 'turret_sides']
    ]

    topology_lock = ['has_turret', 'turret_sides']


class MeshImportProperty(CustomPropertyBase):
    filepath: StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")
    obj_name: StringProperty(name="Object", description="Object Name")
    position: PointerProperty(name="Position", type=PositionProperty)
    array: PointerProperty(name="Array", type=ArrayProperty)

    field_layout = [
        ['filepath', 'obj_name'],
        ('','position'),
        ('','array')
    ]

    topology_lock = ['filepath', 'obj_name']


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
    build_style: EnumProperty(items=enum_catalogs, name="Build Style", description="Catalog name")

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
    ArrayProperty,
    DirectionProperty,
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
    RoomProperty,  # --
    MeshImportProperty,
    BTAddonPreferences,
    OrientedMaterialProperty,
]
