"""Geometry import/export operations"""
import bpy
from bpy.props import StringProperty, PointerProperty
from .custom import CustomOperator, replay_history
from ..object import (
    export_record,
    get_obj_data,
    set_obj_data,
    ACTIVE_OP_ID,
    import_record,
    merge_record,
    Journal
    )

from ..mesh import ManagedMesh
from .properties import MeshImportProperty


# load script and apply to selected face
# load mesh from blend file and add to current mesh
# save active op and children to script file
def load_script(obj, sel_info, filepath):
    subset = import_record(filepath)

    first_op_id = merge_record(obj, subset, sel_info)
    if isinstance(first_op_id, str):
        return first_op_id

    replay_history(bpy.context, first_op_id)


class QARCH_OT_load_script(bpy.types.Operator):
    """Divide a face into patches"""
    bl_idname = "qarch.load_script"
    bl_label = "Load Script"
    bl_options = {"REGISTER"}

    filepath: StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        if context.object is not None:
            return get_obj_data(context.object, ACTIVE_OP_ID) is not None
        return True

    def invoke(self, context, event):
        wm = context.window_manager
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.object
        op_id = -1

        mm = ManagedMesh(obj)
        sel_info = mm.get_selection_info()
        ret = load_script(obj, sel_info, self.filepath)
        if ret is not None:
            self.report({"ERROR_INVALID_CONTEXT"}, ret)
            return {'CANCELLED'}

        set_obj_data(obj, ACTIVE_OP_ID, -1)

        journal = Journal(obj)
        journal['adjusting'] = []
        journal.flush()

        return {'FINISHED'}

    def draw(self, context):
        self.layout.prop(self, "filepath")


# not a CustomOperator, don't save export as history
class QARCH_OT_save_script(bpy.types.Operator):
    bl_idname = "qarch.save_script"
    bl_label = "Save Script"
    bl_options = {"REGISTER"}

    filepath: StringProperty(name="Filename", description="Script to save", subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        if not context.object:
            return False
        operation_id = get_obj_data(context.object, ACTIVE_OP_ID)
        if operation_id is None:
            return False
        return operation_id > -1

    def invoke(self, context, event):
        wm = context.window_manager
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.object
        operation_id = get_obj_data(obj, ACTIVE_OP_ID)
        export_record(obj, operation_id, self.filepath, True)
        return {'FINISHED'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "filepath")

# operator to load mesh