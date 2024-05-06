import bpy
from .base_props import FaceDivisionProperty
from .base_types import face_divide


class QARCH_OT_face_divide(bpy.types.Operator):
    """Divide a face into patches"""

    bl_idname = "qarch.face_divide"
    bl_label = "Divide Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=FaceDivisionProperty)

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.mode == "EDIT_MESH"

    def execute(self, context):
        face_divide(context, self)
        return {"FINISHED"}

    def draw(self, context):
        self.props.draw(context, self.layout)