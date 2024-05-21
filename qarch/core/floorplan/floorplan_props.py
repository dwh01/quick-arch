import bpy
from bpy.props import FloatProperty
from ..base.base_props import CustomPropertyBase

class FloorplanProperty(bpy.types.PropertyGroup): #CustomPropertyBase):

    width: FloatProperty(
        name="Width",
        min=0.01,
        max=100.0,
        default=4,
        unit="LENGTH",
        description="Base Width of floorplan",
    )

    length: FloatProperty(
        name="Length",
        min=0.01,
        max=100.0,
        default=4,
        unit="LENGTH",
        description="Base Length of floorplan",
    )

    #def draw(self, context, layout):
    #    row = layout.row(align=True)
    #    row.prop(self, "width")
    #    row.prop(self, "length")
    field_layout = [
        ["width", "length"]
    ]

    topology_lock = []