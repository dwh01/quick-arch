import bpy
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty, EnumProperty
import math

# set up common routines with simple layout and to/from dict methods
# the clamped accessor is here instead of inside individual properties
# get value as prop.clamped(name) instead of prop.name
# why? imagine a window frame inside a wall
#   the window location is adjusted up so that it doesn't fit
#   but the clamp on height is updated so when we re-build the window, it fits
#   the user can still see the intended height in the properties panel
#   if we move the window back down, the clamp is adjusted and the window grows to the original size
class CustomPropertyBase(bpy.types.PropertyGroup):
    def draw(self, context, layout):
        """Requires a field_layout list to be defined"""
        col = layout.column(align=True)
        for row_list in self.field_layout:
            if isinstance(row_list, str):
                if row_list == "---":
                    layout.separator()
                    col = layout.column(align=True)
                else:
                    col.label(text=row_list)
            else:
                self.draw_row_list(context, col, row_list)

    def draw_row_list(self, context, col, row_list):
        if isinstance(row_list, tuple):  # boolean toggle for pointer
            pname, pointer = row_list
            row = col.row(align=True)
            if pname != "":
                row.prop(self, pname)
                if not getattr(self, pname):
                    return
            getattr(self, pointer).draw(context, col)

        else:
            row = col.row(align=True)

            for pname in row_list:
                rna = self.bl_rna.properties[pname]
                if isinstance(rna, bpy.types.EnumProperty):
                    row.label(text=getattr(self, pname))
                    row.prop_menu_enum(self, pname)
                else:
                    row.prop(self, pname)

    def to_dict(self):
        """Helper for saving persistent data"""
        d = {}
        for row_list in self.field_layout:
            if isinstance(row_list, tuple):
                pname, pointer = row_list
                if pname != "":
                    d[pname] = getattr(self, pname)
                d[pointer] = getattr(self, pointer).to_dict()
            else:
                for pname in row_list:
                    d[pname] = getattr(self, pname)

        if hasattr(self, "clamp_dict"):
            d["_clamp_"] = self.clamp_dict
        return d

    def from_dict(self, d):
        """Helper for loading persistent data"""
        for k, v in d:
            if k == "_clamp_":
                self.clamp_dict = v
            elif isinstance(v, dict):
                getattr(self, k).from_dict(v)
            else:
                setattr(self, k, v)

    def set_clamp(self, name, min_val, max_val):
        """Apply updatable limits to a specific value"""
        if not hasattr(self, "clamp_dict"):
            self.clamp_dict = {}
        self.clamp_dict[name] = (min_val, max_val)

    def clamped(self, name):
        """Getter that uses variable limits"""
        if not hasattr(self, "clamp_dict"):
            return self[name]

        val = self[name]
        min_val, max_val = self.clamp_dict[name]
        if min_val is not None:
            val = max(min_val, val)
        if max_val is not None:
            val = min(max_val, val)
        return val


class ArchShapeProperty(CustomPropertyBase):
    arch_type_list = [
        ("JACK", "Jack", "Flat", 1),
        ("ROMAN", "Roman", "Round/Oval (1 pt)", 2),
        ("GOTHIC", "Gothic", "Gothic pointed (2 pt)", 3),
        ("OVAL", "Oval", "Victorian oval (3 pt)", 4),
        ("TUDOR", "Tudor", "Tudor pointed (4 pt)", 5),
    ]
    arch_height: FloatProperty(name="Arch Height", default=.5, unit="LENGTH", description="Height of arch")
    has_keystone: BoolProperty(name="Keystone", default=False)
    arch_type: EnumProperty(name="Arch Type", items=arch_type_list, description="Type of arch", default="ROMAN")

    field_layout = [
        ["arch_height", "has_keystone"],
        ["arch_type"]
    ]


class BayProperties(CustomPropertyBase):
    side_count: IntProperty(name="Sides Count", min=2, default=3, description="Number of sides on bay")
    depth: FloatProperty(name="Depth", default=1, unit="LENGTH", description="Out of plane max distance")
    has_floor: BoolProperty(name="Floor", default=False)
    floor_thickness: FloatProperty(name="Floor Thickness", default=.1, unit="LENGTH", description="Floor thickness")

    field_layout = [
        ['side_count', 'depth'],
        ['has_floor', 'floor_thickness'],
    ]


class DividersProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=0, default=1, description="Number of vertical dividers")
    count_y: IntProperty(name="Y Count", min=0, default=1, description="Number of horizontal dividers")
    thickness_x: FloatProperty(name="X Width", min=0.0, default=0.03, unit="LENGTH", description="Width of vertical dividers")
    thickness_y: FloatProperty(name="Y Width", min=0.0, default=0.03, unit="LENGTH", description="Width of horizontal dividers")
    depth_thickness: FloatProperty(name="Depth Thickness", min=0.0, default=0.03, unit="LENGTH", description="Depth thickness of dividers")
    depth_offset: FloatProperty(name="Depth Offset", default=0.03, unit="LENGTH", description="Out of plane offset (from face)")
    num_sides: IntProperty(name="Sides Count", min=3, default=4, description="Number of sides for cross section polygon")

    field_layout = [
        ['count_x', 'count_y'],
        ['thickness_x', 'thickness_y'],
        ['depth_thickness', 'depth_offset'],
        ['num_sides']
    ]


class ExtrusionSimpleProperty(CustomPropertyBase):
    distance: FloatProperty(name="Distance", default=0.1, min=0, unit="LENGTH", description="Extrude distance")
    taper_x: FloatProperty(name="Scale X", default=1, unit="NONE", description="Scale x of top face")
    taper_y: FloatProperty(name="Scale Y", default=1, min=0, unit="NONE", description="Scale y of top face")

    field_layout = [
        ['distance'],
        ['taper_x', 'taper_y'],
    ]


class ExtrusionTwistProperty(CustomPropertyBase):
    def twist_update(self, context):
        # when not on norm, we flatten extruded top to face the extrude direction
        # like a chimney from a roof
        # but twist with small steps could lead to early portions intersecting other geometry
        # so only extrude normal when using twist
        if self.twist_angle != 0:
            self.axis = "NORM"

    axis_list = [  # Z used mainly to make a vertical chimney on a sloped roof
        ("NORM", "Normal", "Face Normal", 1),
        ("X", "X", "World X", 2),
        ("Y", "Y", "World Y", 3),
        ("Z", "Z", "World Z", 4),
    ]
    distance: FloatProperty(name="Distance", default=0.1, min=0, unit="LENGTH", description="Extrude distance")
    axis: EnumProperty(name="Axis", items=axis_list, description="Direction of extrude", default="NORM")
    taper_x: FloatProperty(name="Scale X", default=1, unit="NONE", description="Scale x of top face")
    taper_y: FloatProperty(name="Scale Y", default=1, min=0, unit="NONE", description="Scale y of top face")
    # twist + taper + non-axial seems like a BAD combination, enforce normal in custom update function
    twist_angle: FloatProperty(name="Twist Angle", default=0.0, unit="ROTATION", description="Degrees to rotate top",
                               update = twist_update)
    steps: IntProperty(name="Steps", default=1, min=1, description="Extrusion steps")

    field_layout = [
        ['distance'],
        ['axis'],
        ['taper_x', 'taper_y'],
        ['twist_angle', 'steps']
    ]


class FaceDivisionProperty(CustomPropertyBase):
    offset_x: FloatProperty(name="Horizontal Offset", default=0.0, min=0, unit="LENGTH", description="Offset along face base")
    offset_y: FloatProperty(name="Vertical Offset", default=0.0, min=0, unit="LENGTH", description="Offset along face sides")
    size_x: FloatProperty(name="Horizontal Size", default=1.0, min=0, unit="LENGTH", description="Size along face base")
    size_y: FloatProperty(name="Vertical Size", default=1.0, min=0, unit="LENGTH", description="Size along face sides")
    inner_sides: IntProperty(name="Inner Sides", default=4, min=3, description="Inner face number of sides")
    extrude_distance: FloatProperty(name="Extrude Distance", default=0.0, unit="LENGTH", description="Extrude distance")

    field_layout = [
        ['offset_x', 'offset_y'],
        ['size_x', 'size_y'],
        ['inner_sides', 'extrude_distance'],
    ]


class FrameShapeProperty(CustomPropertyBase):
    lintel_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH", description="Vertical thickness of lintel")
    lintel_side: FloatProperty(name="Side Extension", min=0.0, default=0, unit="LENGTH", description="Extend lintel past frame sides")
    lintel_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    lintel_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")
    arched_lintel: BoolProperty(name="Arched Lintel", default=False)
    lintel_arch_prop: PointerProperty(type=ArchShapeProperty)

    side_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH", description="Horizontal thickness of sides")
    side_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    side_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")

    sill_thickness: FloatProperty(name="Thickness", min=0.0, default=.1, unit="LENGTH",  description="Vertical thickness of sill")
    sill_side: FloatProperty(name="Side Extension", min=0.0, default=0, unit="LENGTH", description="Extend sill past frame sides")
    sill_front: FloatProperty(name="Front Extrude", default=0, unit="LENGTH", description="Distance to extrude in front of wall")
    sill_back: FloatProperty(name="Back Extrude", default=0, unit="LENGTH", description="Distance to extrude in back of wall")
    arched_sill: BoolProperty(name="Arched Sill", default=False)
    sill_arch_prop: PointerProperty(type=ArchShapeProperty)

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
        ["front_recess", "inner_thickness"]
    ]


class LouversProperty(CustomPropertyBase):
    count_x: IntProperty(name="X Count", min=0, default=1, description="Number of vertical divisions")
    count_y: IntProperty(name="Y Count", min=0, default=10, description="Number of blades in each louver")
    margin_x: FloatProperty(name="X Margin", min=0.0, default=0.03, unit="LENGTH", description="Space on sides of louvers")
    connect_louvers: BoolProperty(name="Connected", default=False, description="Connect to make bellows")
    blade_angle: FloatProperty(name="Blade Angle", min=-90.0, max=90, default=-45.0/180*math.pi, unit="ROTATION", description="Degrees, 0 for horizontal")
    blade_thickness: FloatProperty(name="Blade Thickness", min=0.0, default=0.003, unit="LENGTH", description="Single blade thickness")
    depth_thickness: FloatProperty(name="Depth Thickness", min=0.0, default=0.03, unit="LENGTH", description="Depth thickness of louvers")
    depth_offset: FloatProperty(name="Depth Offset", default=0.03, unit="LENGTH", description="Out of plane offset (from face)")
    flip_xy: BoolProperty(name="Flip xy", default=False, description="Change orientation")

    field_layout = [
        ['count_x', 'count_y'],
        ['margin_x', 'connect_louvers'],
        ['blade_angle', 'blade_thickness'],
        ['depth_thickness', 'depth_offset'],
        ['flip_xy']
    ]


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


# order might matter
base_classes = [
    ArchShapeProperty,
    BayProperties,
    DividersProperty,
    ExtrusionSimpleProperty,
    ExtrusionTwistProperty,
    FaceDivisionProperty,
    FrameShapeProperty,
    LouversProperty,
    RoomProperty,
    ]
