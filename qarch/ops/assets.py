"""Geometry import/export operations"""
import bpy
from bpy.props import StringProperty, PointerProperty
from .custom import CustomOperator, replay_history
from ..object import (
    export_record,
    get_obj_data,
    ACTIVE_OP_ID,
    import_record,
    merge_record
    )

from ..mesh import ManagedMesh
from .properties import MeshImportProperty, ScriptImportProperty


# load script and apply to selected face
# load mesh from blend file and add to current mesh
# save active op and children to script file
def load_script(obj, face_sel_info, op_id, prop_dict):
    filepath = prop_dict['filepath']
    subset = import_record(filepath)

    if len(face_sel_info):
        control_points = [t[ManagedMesh.OPSEQ] for t in face_sel_info]
        control_op = face_sel_info[0][ManagedMesh.OPID]
    else:
        control_points = []
        control_op = -1

    merge_record(obj, subset, control_points, control_op)
    replay_history(bpy.context, control_op)


class QARCH_OT_load_script(CustomOperator):
    """Divide a face into patches"""
    bl_idname = "qarch.load_script"
    bl_label = "Load Script"
    bl_options = {"REGISTER"}
    bl_property = "props"

    props: PointerProperty(name="Script", type=ScriptImportProperty)
    function = load_script


# not a CustomOperator, don't save export as history
class QARCH_OT_save_script(bpy.types.Operator):
    bl_idname = "qarch.save_script"
    bl_label = "Save Script"
    bl_options = {"REGISTER"}

    filepath: StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        if not context.object:
            return False
        operation_id = get_obj_data(context.object, ACTIVE_OP_ID)
        return operation_id > -1

    def invoke(self, context, event):
        wm = context.window_manager
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.object
        operation_id = get_obj_data(obj, ACTIVE_OP_ID)
        export_record(obj, operation_id, self.filepath, True)

    def draw(self, context):
        self.layout.prop(self.filepath)

# operator to load mesh