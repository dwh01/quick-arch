import bpy

from .floorplan_types import create_floorplan
from .floorplan_props import FloorplanProperty

from ..base.base_ops import CustomOperator, deselect_all


class QARCH_OT_add_floorplan(bpy.types.Operator):
    """Create a starting building floorplan"""

    bl_idname = "qarch.add_floorplan"
    bl_label = "Create Floorplan"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=FloorplanProperty)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        create_floorplan(context, self.props)
        # opid, controlled, parent_id, b_topo = self.record(context)

        return {"FINISHED"}

    #def draw(self, context):
    #    self.props.draw(context, self.layout)
