"""Operators that change selection state and layer data,
many are not derived from CustomOperator"""
import bpy
from bpy.props import PointerProperty, EnumProperty, StringProperty, FloatProperty
from .custom import *
from .properties import face_tag_to_int
from ..object import create_object, Journal, wrap_id, delete_record, SelectionInfo
from ..mesh import ManagedMesh


class QARCH_OT_create_object(bpy.types.Operator):
    """For operations without an object existing"""
    bl_idname = "qarch.create_object"
    bl_label = "Create new object"
    bl_options = {"REGISTER"}
    #bl_property = "props"

    #props: PointerProperty(name="Object", type=NewObjectProperty)
    name: StringProperty(name="Name", description="Name of new object", default="BT_object")
    collection: StringProperty(name="Collection", description="Destination collection", default="Collection")

    @classmethod
    def poll(cls, context):
        return True

    # def draw(self, context):
    #     """Simple case, override if needed
    #     Passes draw_locked flag in context to make some fields read only
    #     """
    #     should_lock = False
    #     self.props.draw(context, self.layout, should_lock)

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        try:
            collection = bpy.data.collections[self.collection]
        except Exception:
            collection = bpy.data.collections.new(self.collection)
            bpy.context.scene.collection.children.link(collection)

        # de-select other objects
        if context.mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        obj = create_object(collection, self.name)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        # enter edit mode to start making things
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


dct_Enums = {-1: (wrap_id(-1), "None", "", -1)}

def build_op_enums(dct_op_tree, op_id, journal, level):
    """Format enums indented by level"""
    global dct_Enums

    if op_id in dct_Enums:
        enum_rec = dct_Enums[op_id]
    else:
        # indented id
        text = str(op_id)
        text = text.rjust(2 * level + len(text)) + " "
        text = text + journal.op_label(op_id)

        # add enum tuple to list
        enum_rec = (wrap_id(op_id), text, "", op_id)
        dct_Enums[op_id] = enum_rec

    lst_enum = [enum_rec]

    # add children to list
    for op_child in dct_op_tree[op_id]:
        lst_enum = lst_enum + build_op_enums(dct_op_tree, op_child, journal, level+1)

    return lst_enum



class QARCH_OT_set_active_op(bpy.types.Operator):
    bl_idname = "qarch.set_active_op"
    bl_label = "Set Active Operation"
    bl_options = {"REGISTER"}
    bl_property = "enum_prop"

    def fill_enum_list(self, context):
        global dct_Enums

        obj = context.object
        lst_enum = []
        if obj is not None:
            mm = ManagedMesh(obj)
            lst_sel_info = mm.get_selection_info()
            mm.free()
            if lst_sel_info.count_faces():
                journal = Journal(obj)
                dct_op_tree = journal.make_op_tree(lst_sel_info.op_list())

                lst_enum = build_op_enums(dct_op_tree, 0, journal, 0)

        lst_enum.append(dct_Enums[-1])
        return lst_enum

    enum_prop: EnumProperty(items=fill_enum_list, name='Active Operation', default=-1)

    @classmethod
    def poll(cls, context):
        return (context.object is not None) and (context.mode == "EDIT_MESH")

    def execute(self, context):
        print("activating ", self.enum_prop)
        op_id = int(self.enum_prop[2:])
        # store in object custom property
        set_obj_data(context.object, ACTIVE_OP_ID, op_id)

        mm = ManagedMesh(context.object)
        mm.deselect_all()
        mm.set_op(op_id)
        mm.select_current()
        mm.to_mesh()
        mm.free()

        journal = Journal(context.object)
        journal['adjusting'].clear()
        journal.flush()

        return {"FINISHED"}

    def draw(self, context):
        global dct_Enums
        # update enum value if the active object has changed
        if context.object:
            active_op = get_obj_data(context.object, ACTIVE_OP_ID)
            if active_op in dct_Enums:
                display_item = dct_Enums[active_op][1]
            else:
                display_item = dct_Enums[-1][1]

            row = self.layout.row()
            row.label(text="Active: " + display_item)
        row = self.layout.row()
        # row.props_enum(self, "enum_prop")
        row.prop_menu_enum(self, "enum_prop")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

class QARCH_OT_rebuild_object(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.rebuild_object"
    bl_label = "Rebuild"
    bl_description = "Rebuild object from script"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return True
        return False

    def execute(self, context):
        active_op = get_obj_data(context.object, ACTIVE_OP_ID)
        journal = Journal(context.object)
        dct, lst = journal.child_ops(active_op)

        mm = ManagedMesh(context.object)
        for op_id in lst:
            mm.set_op(op_id)
            mm.delete_current_verts()

        if active_op > -1:
            lst_sel_info = SelectionInfo(journal[active_op]['control_points'])
            print("set consistent by selecting ", lst_sel_info)
            mm.set_selection_info(lst_sel_info)
        mm.to_mesh()
        mm.free()

        if active_op == -1:
            lst_tops = journal.controlled_list(-1)
            for op in lst_tops:
                replay_history(context, op)
        else:
            replay_history(context, active_op)
        return {'FINISHED'}

class QARCH_OT_remove_operation(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.remove_operation"
    bl_label = "Remove Op"
    bl_description = "Remove operation and child features"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return op_id > -1
        return False

    def execute(self, context):
        active_op = get_obj_data(context.object, ACTIVE_OP_ID)
        journal = Journal(context.object)
        journal['adjusting'].clear()
        sel_info = journal.get_sel_info(active_op)

        lst = delete_record(context.object, active_op)
        lst.append(active_op)

        mm = ManagedMesh(context.object)
        for op_id in lst:
            mm.set_op(op_id)
            mm.delete_current_verts()

        # remake faces
        for vlist in sel_info.get_face_verts(mm):
            if len(vlist) >= 3:
                mm.new_face(vlist)

        mm.to_mesh()
        mm.free()

        set_obj_data(context.object, ACTIVE_OP_ID, -1)

        return {'FINISHED'}


class QARCH_OT_add_face_tags(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.add_face_tags"
    bl_label = "Add Face Tags"
    bl_description = "Add object specific tags"
    bl_options = {"REGISTER"}
    bl_property = "tag_list"

    tag_list: StringProperty(name="Tag List", description="Comma separated tags to add")

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        self.tag_list = ""
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        new_tags = [s.strip() for s in self.tag_list.split(",")]
        journal = Journal(context.object)
        tags = journal['face_tags']

        b_dirty = False
        for s in new_tags:
            i = face_tag_to_int(s)
            if i is None:
                tags.append(s)
                b_dirty = True

        if b_dirty:
            journal.flush()
        return {'FINISHED'}