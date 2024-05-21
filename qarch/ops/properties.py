import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty, StringProperty
import math
from .custom import CustomPropertyBase


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
        ["arch_type"]
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


class InsetPolygonProperty(CustomPropertyBase):
    # TODO enum ngon, arch, or self-similar
    # but need to use the update function of enum to toggle visibility of the shape pointers
    position: PointerProperty(name="Position", type=PositionProperty)
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    use_ngon: BoolProperty(name="Use NGon", description="Use n-gon method", default=True)
    poly: PointerProperty(name="Poly", type=PolygonProperty)
    use_arch: BoolProperty(name="Use Arch", description="Use arch method", default=True)
    arch: PointerProperty(name="Arch", type=ArchShapeProperty)
    extrude_distance: FloatProperty(name="Extrude Distance", default=0.0, unit="LENGTH", description="Extrude distance")
    add_perimeter: BoolProperty(name="Add Perimeter Points", description="Add points to perimeter to match if needed", default=False)

    field_layout = [
        ('', 'position'),
        ('', 'size'),
        ('use_ngon', 'poly'),
        ('use_arch', 'arch'),
        ['extrude_distance', 'add_perimeter']
    ]

    topology_lock = ['use_ngon', 'use_arch', 'add_perimeter']

class SolidifyEdgesProperty(CustomPropertyBase):
    edge_items = [
        ("TOP", "Top", "Within 45 degrees of up", 1),
        ("BOTTOM", "Bottom", "Within 45 degrees of bottom", 2),
        ("LEFT", "Left", "Within 45 degrees of left", 4),
        ("RIGHT", "Right", "Within 45 degrees of right", 8),
        ("INSIDE", "Inside", "Only interior of selected region", 16),
        ("OUTSIDE", "Outside", "Only outside of selected region", 32),
    ]
    section: PointerProperty(name="Section", type=PolygonProperty, description="Cross-section to apply")
    size: PointerProperty(name="Size", type=SizeProperty, description="Bounding box size")
    sides: EnumProperty(name="Sides", description="Sides to solidify", items=edge_items, options={'ENUM_FLAG'},
                        default={'TOP', 'BOTTOM', 'LEFT', 'RIGHT'})
    z_offset: FloatProperty(name="Z Offset", description="Out of plane offset", default=0)

    field_layout = [
        ('', 'section'),
        ('', 'size'),
        ('', 'sides'),
        ['z_offset']
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


class FrameShapeProperty(CustomPropertyBase):
    lintel_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH", description="Vertical thickness of lintel")
    lintel_side: FloatProperty(name="Side Extension", min=0.0, default=0, unit="LENGTH", description="Extend lintel past frame sides")
    lintel_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    lintel_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")
    arched_lintel: BoolProperty(name="Arched Lintel", default=False)
    lintel_arch_prop: PointerProperty(name="Top Arch", type=ArchShapeProperty)

    side_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH", description="Horizontal thickness of sides")
    side_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    side_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")

    sill_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH",  description="Vertical thickness of sill")
    sill_side: FloatProperty(name="Side Extension", min=0.0, default=0, unit="LENGTH", description="Extend sill past frame sides")
    sill_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    sill_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")
    arched_sill: BoolProperty(name="Arched Sill", default=False)
    sill_arch_prop: PointerProperty(name="Bottom Arch", type=ArchShapeProperty)

    front_recess: FloatProperty(name="Recess", default=.1, unit="LENGTH", description="Inset interior of frame (from wall)")
    inner_thickness: FloatProperty(name="Inner Thickness", min=0.0, default=0.01, unit="LENGTH", description="Panel thickness inside frame")

    field_layout = [
        "Top",
        ["lintel_thickness", "lintel_side"],
        ["lintel_front", "lintel_back"],
        ("arched_lintel", "lintel_arch_prop"),
        "Sides",
        ["side_thickness"],
        ["side_front", "side_back"],
        "Bottom",
        ["sill_thickness", "sill_side"],
        ["sill_front", "sill_back"],
        ("arched_sill", "sill_arch_prop"),
        "Inside",
        ["front_recess", "arched_sill"]
    ]

    topology_lock = ['arched_lintel', 'arched_sill']


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


class ScriptImportProperty(CustomPropertyBase):
    filepath: StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")
    field_layout = [
        ['filepath']
    ]

    topology_lock = ['filepath']


# order might matter
ops_properties = [
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
    FrameShapeProperty,  # --
    RoomProperty,  # --
    MeshImportProperty,
    ScriptImportProperty,
]
