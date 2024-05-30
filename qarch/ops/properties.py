import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences
import math
from .custom import CustomPropertyBase
from collections import OrderedDict


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


GridDivideProperty = ArrayProperty


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
    is_relative_x: BoolProperty(name="Relative", default=False, description="Relative size (0-1) for x")
    size_y: FloatProperty(name="Size Y", default=1.0, unit="LENGTH", description="Face Y size")
    is_relative_y: BoolProperty(name="Relative", default=False, description="Relative size (0-1) for y")

    field_layout = [
        ['size_x', 'is_relative_x', 'size_y', 'is_relative_y'],
    ]

    topology_lock = []


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


def update_inset_enum(self, context):
    t = self.inset_type
    if t == 'NGON':
        self.use_ngon = True
        self.use_arch = False
    elif t == 'ARCH':
        self.use_ngon = False
        self.use_arch = True
    else:
        self.use_ngon = False
        self.use_arch = False

    # Redraw panel
    for region in context.area.regions:
        if region.type == "UI":
            region.tag_redraw()


class InsetPolygonProperty(CustomPropertyBase):
    inset_type_list = [
        ("NGON", "Regular Polygon", "N-sided polygon", 1),
        ("ARCH", "Arch", "Arch shape", 2),
        ("SELF", "Self Similar", "Current shape resized", 3),
        ]

    inset_type: EnumProperty(name="Inset Type", default="SELF", items=inset_type_list, update=update_inset_enum)

    # but need to use the update function of enum to toggle visibility of the shape pointers
    position: PointerProperty(name="Position", type=PositionProperty)
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    use_ngon: BoolProperty(name="Use NGon", description="Use n-gon method", default=False)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    use_arch: BoolProperty(name="Use Arch", description="Use arch method", default=False)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    extrude_distance: FloatProperty(name="Extrude Distance", default=0.0, unit="LENGTH", description="Extrude distance")
    add_perimeter: BoolProperty(name="Add Perimeter Points", description="Add points to perimeter to match if needed", default=False)
    thickness: FloatProperty(name="Frame Thickness", min=0, default=0.1, description="Polygon donut instead of solid face")

    field_layout = [
        ('', 'position'),
        ('', 'size'),
        ['inset_type'],
        ('use_ngon', 'poly'),
        ('use_arch', 'arch'),
        ['extrude_distance', 'add_perimeter'],
        ['thickness']
    ]

    topology_lock = ['use_ngon', 'use_arch', 'add_perimeter', 'thickness']


class SolidifyEdgesProperty(CustomPropertyBase):
    poly: PointerProperty(name="Cross Section", type=PolygonProperty, description="Cross-section to apply")
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    do_horizontal: BoolProperty(name="Do Horizontal", default=True, description="Solidify horizontal-ish edges")
    do_vertical: BoolProperty(name="Do Vertical", default=True, description="Solidify vertical-ish edges")
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)
    inset: FloatProperty(name="Inset Offset", description="Distance off edge", default=0)

    field_layout = [
        ('', 'poly'),
        ('', 'size'),
        ['do_horizontal', 'do_vertical'],
        ['z_offset', 'inset']
    ]
    topology_lock = ['sides']


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

    field_layout = [
        ['count_x', 'count_y'],
        ['margin_x', 'margin_y'],
        ['blade_angle', 'blade_thickness'],
        ['depth_thickness', 'depth_offset'],
        ['flip_xy', 'connect_louvers']
    ]

    topology_lock = ['count_x', 'count_y', 'flip_xy']


class InsetPolyProperty(CustomPropertyBase):  # demo case
    num_sides: IntProperty(name="Sides", min=3, default=4, description="Number of sides")

    field_layout = [
        ["num_sides"]
    ]

    topology_lock = []


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

    asset_path: StringProperty(name="Asset Path", subtype='FILE_PATH', )
    select_mode: EnumProperty(
        name="Selection Mode", description="How to handle multiple face selection",
        items=[('SINGLE','Single Faces','Each face gets separate property record'),
               ('GROUP','Group of Faces','Each face gets same property record'),
               ('REGION', 'Region', 'Treat as one big face')
               ], default='SINGLE',)
    user_tags: StringProperty(name="Face tags", description="Comma separated list of custom tags")

    def draw(self, context):
        layout = self.layout
        layout.label(text="Build Tools Preferences")
        layout.prop(self, "asset_path")
        layout.prop(self, "select_mode")
        layout.prop(self, "face_tags")


lst_FaceEnums = [
    ("DELETE", "Delete", "Delete face at end"),
    ("NOTHING", "Nothing", "No special tag"),
    ("WALL", "Wall", "Wall face"),
    ("GLASS", "Glass", "Glass face"),
    ("TRIM", "Trim", "Framing around door or window"),
    ("DOOR", "Door", "Face of door, may become vertex group"),
]

dct_hold_face_enums = OrderedDict()


def face_tag_to_int(s):
    global dct_hold_face_enums
    for i, e in enumerate(dct_hold_face_enums.keys()):
        if e == s:
            return i
    return None


def get_face_tag_enum(self, context):
    from ..object import Journal
    global lst_FaceEnums
    global dct_hold_face_enums

    lst_enum = []

    set_used = set()
    for e in lst_FaceEnums:
        if e[0] not in dct_hold_face_enums:
            dct_hold_face_enums[e[0]] = e
        set_used.add(e[0])
        lst_enum.append(e + (len(lst_enum)-1,))

    preferences = context.preferences
    addon_prefs = preferences.addons['qarch'].preferences
    user_tags = [s.strip() for s in addon_prefs.user_tags.split(",")]
    for s in user_tags:
        if s not in set_used:
            e = (s, s, "tag from user preferences")
            if s not in dct_hold_face_enums:
                dct_hold_face_enums[s] = e
            lst_enum.append(dct_hold_face_enums[s]+ (len(lst_enum)-1,))
            set_used.add(s)

    journal = Journal(context.object)
    obj_tags = [s.strip() for s in journal['face_tags']]
    for s in obj_tags:
        if s not in set_used:
            e = (s, s, "tag from user preferences")
            if s not in dct_hold_face_enums:
                dct_hold_face_enums[s] = e
            lst_enum.append(dct_hold_face_enums[s]+ (len(lst_enum)-1,))
            set_used.add(s)

    return lst_enum


uv_mode_list = [
        ('GLOBAL_XY', 'Global XY', 'Use real units projected to face'),
        ('FACE_XY', 'Face XY', 'Use face x/y in real units'),
        ('FACE_BBOX', 'Bounding Box', 'Set bounding box 0-1'),
        ('FACE_POLAR', 'FACE Polar', 'Use face polar coordinates from centroid'),
        ('NONE', 'None', 'Do not auto-calculate UV'),  # so we don't erase something the user did
    ]


def uv_mode_to_int(s):
    for i, e in enumerate(uv_mode_list):
        if e[0] == s:
            return i
    return 0


class FaceTagProperties(CustomPropertyBase):
    face_tag: EnumProperty(name='Face Tag', items=get_face_tag_enum, default=None, description="Face tag for selection")
    face_thickness: FloatProperty(name="Face Thickness", default=0, min=0, description="Wall thickness after finalization")
    face_uv_mode: EnumProperty(name="UV Mode", description="Method of UV assignment", items=uv_mode_list, default="GLOBAL_XY")

    field_layout = [
        ['face_tag'],
        ['face_thickness'],
        ['face_uv_mode']
    ]

    topology_lock = []


# order might matter
ops_properties = [
    FaceTagProperties,
    ArchShapeProperty,
    ArrayProperty,
    DirectionProperty,
    PositionProperty,
    SizeProperty,
    SplitFaceProperty,
    PolygonProperty,
    UnionPolygonProperty,
    InsetPolygonProperty,
    ExtrudeProperty,
    SweepProperty,
    SolidifyEdgesProperty,
    MakeLouversProperty,
    InsetPolyProperty,
    RoomProperty,  # --
    MeshImportProperty,
    BTAddonPreferences,

]
