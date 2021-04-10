import bpy
from bpy.props import EnumProperty, FloatProperty, BoolProperty


class RoofProperty(bpy.types.PropertyGroup):
    roof_types = [
        ("GABLE", "Gable", "", 1),
        ("HIP", "Hip", "", 2),
    ]
    type: EnumProperty(
        name="Roof Type",
        items=roof_types,
        default="GABLE",
        description="Type of roof to create",
    )

    thickness: FloatProperty(
        name="Thickness",
        min=0.01,
        max=1.0,
        default=0.1,
        unit="LENGTH",
        description="Thickness of roof hangs",
    )

    outset: FloatProperty(
        name="Outset",
        min=0.01,
        max=1.0,
        default=0.1,
        unit="LENGTH",
        description="Outset of roof hangs",
    )

    height: FloatProperty(
        name="Height",
        min=0.01,
        max=10.0,
        default=1,
        unit="LENGTH",
        description="Height of entire roof",
    )

    def draw(self, context, layout):

        layout.separator()
        col = layout.column(align=True)
        col.prop(self, "type", text="")
        col.prop(self, "thickness")
        col.prop(self, "outset")
        col.prop(self, "height")
