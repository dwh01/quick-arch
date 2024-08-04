"""Operators that change selection state and layer data,
many are not derived from CustomOperator"""
import math

import bpy
from bpy.props import EnumProperty, StringProperty, IntProperty, FloatProperty, BoolProperty
from .. import __package__ as base_package
from .custom import *
from .properties import face_tag_to_int, get_face_tag_enum
from ..object import create_object, Journal, wrap_id, delete_record, SelectionInfo, REPLAY_OP_ID
from ..mesh import ManagedMesh
from .dynamic_enums import qarch_asset_dir

lst_classes = [
    'QARCH_OT_create_object',
    'QARCH_OT_set_active_op',
    'QARCH_OT_redo_op',
    'QARCH_OT_rehide',
    'QARCH_OT_rebuild_object',
    'QARCH_OT_remove_operation',
    'QARCH_OT_add_face_tags',
    'QARCH_OT_clean_object',
    'QARCH_OT_child_operation',
]
lst_funcs = []


class QARCH_OT_create_object(bpy.types.Operator):
    """For operations without an object existing"""
    bl_idname = "qarch.create_object"
    bl_label = "Create new object"
    bl_options = {"REGISTER"}
    #bl_property = "props"

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

        # bpy.ops.mesh.select_mode(type="FACE", action='ENABLE')  # for some reason this must be done by hand?

        get_face_tag_enum(self, context)  # fill enum list
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
        descr = journal.describe(op_id)
        if len(descr):
            text = text + " " + descr
        # add enum tuple to list
        enum_rec = (wrap_id(op_id), text, descr, op_id)
        dct_Enums[op_id] = enum_rec

    lst_enum = [enum_rec]

    # add children to list
    for op_child in dct_op_tree[op_id]:
        lst_enum = lst_enum + build_op_enums(dct_op_tree, op_child, journal, level+1)

    return lst_enum

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
            op1 = next(iter(dct_op_tree.keys()))
            lst_enum = build_op_enums(dct_op_tree, op1, journal, 0)

    lst_enum.append(dct_Enums[-1])
    return lst_enum


class QARCH_OT_set_active_op(bpy.types.Operator):
    bl_idname = "qarch.set_active_op"
    bl_label = "Set Active Operation"
    bl_property = "enum_prop"

    enum_prop: EnumProperty(items=fill_enum_list, name='Active Operation', default=-1)

    @classmethod
    def poll(cls, context):
        return (context.object is not None) and (context.mode == "EDIT_MESH")

    def execute(self, context):
        print("activating ", self.enum_prop)
        op_id = int(self.enum_prop[2:])
        # store in object custom property
        set_obj_data(context.object, ACTIVE_OP_ID, op_id)

        journal = Journal(context.object)
        journal['adjusting'].clear()
        journal.flush()

        mm = ManagedMesh(context.object)
        mm.deselect_all()
        mm.set_op(op_id)
        mm.select_current()
        mm.to_mesh()
        mm.free()

        return {"FINISHED"}

    def draw(self, context):
        global dct_Enums
        row = self.layout.row()
        row.prop_menu_enum(self, "enum_prop")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

class QARCH_OT_redo_op(bpy.types.Operator):
    bl_idname = "qarch.redo_op"
    bl_label = "Redo Operation"
    bl_property = "enum_prop"

    enum_prop: EnumProperty(items=fill_enum_list, name='Active Operation', default=-1)

    @classmethod
    def poll(cls, context):
        return (context.object is not None) and (context.mode == "EDIT_MESH")

    def execute(self, context):
        print("redo ", self.enum_prop)
        op_id = int(self.enum_prop[2:])
        # store in object custom property
        set_obj_data(context.object, ACTIVE_OP_ID, op_id)

        journal = Journal(context.object)
        journal['adjusting'].clear()
        journal.flush()
        return replay_history(context, op_id, True)

    def draw(self, context):
        global dct_Enums
        row = self.layout.row()
        row.prop_menu_enum(self, "enum_prop")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class QARCH_OT_rehide(bpy.types.Operator):
    """For cleanup when deleted faces are showing"""
    bl_idname = "qarch.rehide"
    bl_label = "Rehide"
    bl_description = "Rehide deleted faces"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            return True
        return False

    def execute(self, context):
        active_op = get_obj_data(context.object, ACTIVE_OP_ID)
        journal = Journal(context.object)

        mm = ManagedMesh(context.object)
        mm.rehide()
        mm.to_mesh()
        mm.free()

        return {"FINISHED"}


class QARCH_OT_rebuild_object(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.rebuild_object"
    bl_label = "Rebuild"
    bl_description = "Rebuild object from script"
    bl_options = {"REGISTER"}

    stop_at: IntProperty(name="Stop at", default=-1, min=-1, description="-1 for full rebuild, otherwise stop after operation number")
    # someday maybe we can insert this into the header being drawn
    # user_cancel: BoolProperty(name="Cancel", default=False)

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        active_op = get_obj_data(context.object, ACTIVE_OP_ID)
        journal = Journal(context.object)

        mm = ManagedMesh(context.object)
        if active_op > -1:
            dct, lst = journal.child_ops(active_op)
            for op_id in lst:
                mm.set_op(op_id)
                mm.delete_current_verts()

            lst_sel_info = SelectionInfo(journal[active_op]['control_points'])
            print("set consistent by selecting ", lst_sel_info)
            mm.set_selection_info(lst_sel_info)
        else:
            mm.delete_all()
        mm.to_mesh()
        mm.free()

        if active_op == -1:
            start = 0
        else:
            start = active_op
        if self.stop_at == -1:
            end = journal['max_id']+1
        else:
            end = min(self.stop_at, journal['max_id']+1)

        for i_op in range(start, end):
            factor = int(100 * i_op / end)
            txt = "Rebuild {} of {}".format(i_op, end)
            context.scene.progress_indicator = factor
            context.scene.progress_indicator_text = txt
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            if wrap_id(i_op) in journal.jj:  # check for deleted operations
                set_obj_data(context.object, REPLAY_OP_ID, i_op)  # prevents child recursion
                replay_history(context, i_op)
        context.scene.progress_indicator = -1

        journal = Journal(context.object)
        journal['adjusting'] = []
        journal.flush()
        set_obj_data(context.object, REPLAY_OP_ID, -1)
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
        for vlist in mm.get_face_verts(sel_info):
            if len(vlist) >= 3:
                mm.new_face(vlist)

        mm.to_mesh()
        mm.free()

        set_obj_data(context.object, ACTIVE_OP_ID, -1)

        return {'FINISHED'}


class QARCH_OT_add_face_tags(bpy.types.Operator):
    """Add object tags"""
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


class QARCH_OT_select_tags(bpy.types.Operator):
    """Select by tags"""
    bl_idname = "qarch.select_tags"
    bl_label = "Select Tags"
    bl_description = "Select by face tags"
    bl_options = {"REGISTER", "UNDO"}
    bl_property = "tag_list"

    tag_list: StringProperty(name="Tag List", description="Comma separated tags to select")

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        sel_tags = [s.strip() for s in self.tag_list.split(",")]
        sel_ints = [face_tag_to_int(s) for s in sel_tags]

        mm = ManagedMesh(context)
        for face in mm.bm.faces:
            if face[mm.key_tag] in sel_ints:
                face.select_set(True)
        mm.bm.select_flush(True)
        mm.to_mesh()
        mm.free()

        return {'FINISHED'}


class QARCH_OT_clean_object(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.clean_object"
    bl_label = "Cleanup"
    bl_description = "Delete hidden faces"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return True
        return False

    def execute(self, context):

        mm = ManagedMesh(context.object)
        mm.cleanup()
        mm.to_mesh()
        mm.free()

        return {'FINISHED'}


def from_faces_linked(orig_mm, new_name, vertices, faces_linked):
    from ..object import upgrade_object, BT_INST_COLLECTION
    from ..mesh.geom import calc_face_uv
    """Convert bmesh faces to new mesh"""
    # https://blender.stackexchange.com/questions/289911/how-to-copy-a-few-faces-from-one-bmesh-to-another
    # set gets unique elements, list gets ordered elements

    # establishes a map between the new mesh vertex indices and
    # actual mesh vertex indices
    vmap = dict()
    for i, vert in enumerate(vertices):
        vmap[vert.index] = i

    coordinates = [v.co for v in vertices]

    # build faces with new indices
    faces = []
    for face in faces_linked:
        faces.append([vmap[v.index] for v in face.verts])

    # create a mesh from that
    mesh = bpy.data.meshes.new(name=new_name)
    mesh.from_pydata(coordinates, [], faces)
    uv = mesh.uv_layers.new(name='UVMap')

    obj = bpy.data.objects.new(name=new_name, object_data=mesh)
    orig_mm.obj.users_collection[0].objects.link(obj)

    upgrade_object(obj)
    # copy over instance sources
    col_sources = obj.name + BT_INST_COLLECTION
    old_sources = orig_mm.obj.name + BT_INST_COLLECTION
    for ob in bpy.data.collections[old_sources].objects:
        bpy.data.collections[col_sources].objects.link(ob)

    for mat in orig_mm.obj.data.materials:
        if mat.name not in mesh.materials:
            mesh.materials.append(mat)

    # add aux info
    mm2 = ManagedMesh(obj)
    uv_lay_old = orig_mm.bm.loops.layers.uv.active
    uv_lay_new = mm2.bm.loops.layers.uv.active
    for i_face, orig_face in enumerate(faces_linked):
        new_face = mm2.bm.faces[i_face]
        for k in ['key_tag', 'key_face_op', 'key_uv_rot', 'key_uv_orig', 'key_face_seq', 'key_elev', 'key_radial', 'key_uv']:
            lnew = getattr(mm2, k)
            lold = getattr(orig_mm, k)
            new_face[lnew] = orig_face[lold]
            new_face.material_index = orig_face.material_index
        # for iloop, old_loop in enumerate(orig_face.loops):
        #     new_loop = new_face.loops[iloop]
        #     new_loop[mm2.key_uv_w] = old_loop[orig_mm.key_uv_w]
        #     new_loop[uv_lay_new].uv = old_loop[uv_lay_old].uv
        calc_face_uv(new_face, mm2)

    for i_vert, orig_vert in enumerate(vertices):
        new_vert = mm2.bm.verts[vmap[orig_vert.index]]
        for k in ['key_op', 'key_pick', 'key_inst_rot', 'key_seq', 'key_inst_scale']:
            lnew = getattr(mm2, k)
            lold = getattr(orig_mm, k)
            new_vert[lnew] = orig_vert[lold]


    mm2.to_mesh()
    mm2.free()

    return obj

class QARCH_OT_child_operation(bpy.types.Operator):
    """Turn operation and children into a second child mesh"""
    # one can imagine keeping the script for the new mesh
    # but you need a way to cross reference to the control polygon
    # or a way to mark the starting state so it is not destroyed by a rebuild
    bl_idname = "qarch.child_operation"
    bl_label = "Make Child"
    bl_description = "Remove operation and create child mesh instead"
    bl_options = {"REGISTER"}
    bl_property = 'new_name'

    new_name: StringProperty(name="Child Name", description="Name of child object to create")

    @classmethod
    def poll(cls, context):
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            op_id = get_obj_data(context.object, ACTIVE_OP_ID)
            if op_id is not None:
                return op_id > -1
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        self.new_name = ""
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        active_op = get_obj_data(context.object, ACTIVE_OP_ID)
        journal = Journal(context.object)
        journal['adjusting'].clear()

        new_name = self.new_name
        if len(new_name) == 0:
            return {'FINISHED'}

        mm = ManagedMesh(context.object)
        mm.deselect_all()
        mm.select_operation(active_op)

        dct, lst = journal.child_ops(active_op)
        lst.append(active_op)

        vertices = [v for v in mm.bm.verts if v[mm.key_op] in lst]
        faces_linked = [f for f in mm.bm.faces if (f[mm.key_face_op] in lst) and (f[mm.key_tag] != -1)]

        obj = from_faces_linked(mm, new_name, vertices, faces_linked)
        obj.parent = context.object
        obj.matrix_parent_inverse = context.object.matrix_world.inverted()


        # the rest of this is identical to remove_operation
        sel_info = journal.get_sel_info(active_op)

        lst = delete_record(context.object, active_op)
        lst.append(active_op)

        mm = ManagedMesh(context.object)
        for op_id in lst:
            mm.set_op(op_id)
            mm.delete_current_verts()

        # remake faces
        for vlist in mm.get_face_verts(sel_info):
            if len(vlist) >= 3:
                mm.new_face(vlist)

        mm.to_mesh()
        mm.free()

        set_obj_data(context.object, ACTIVE_OP_ID, -1)

        return {'FINISHED'}

class QARCH_PT_faceinfo(bpy.types.Panel):
    bl_label = "Face Info"
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        from ..object import is_bt_object
        from .dynamic_enums import int_to_face_tag
        from .properties import int_to_uv_mode
        layout = self.layout

        if context.object:
            if is_bt_object(context.object):
                mm = ManagedMesh(context.object)
                sel_info = mm.get_selection_info()
                faces = mm.get_faces(sel_info)

                if len(faces) == 0:
                    row = layout.row()
                    row.label(text="No faces selected")

                elif len(faces) > 1:
                    row = layout.row()
                    row.label(text="{} faces selected".format(len(faces)))

                    row = layout.row()
                    lst_op = sel_info.op_list()
                    row.label(text="From operations: {}".format(lst_op))
                    row = layout.row()
                    row.operator("qarch.set_face_tag")
                    row = layout.row()
                    row.operator("qarch.set_face_radial")
                    row = layout.row()
                    row.operator("qarch.set_face_uv_mode")
                    row = layout.row()
                    row.operator("qarch.set_face_uv_rotate")
                    row = layout.row()
                    row.operator("qarch.set_face_uv_orig")
                    row = layout.row()
                    row.operator("qarch.set_face_elevation")
                    row = layout.row()
                    row.operator("qarch.set_face_material")


                else:
                    face = faces[0]
                    row = layout.row()
                    row.label(text="Op {} Face {}".format(face[mm.key_face_op], face[mm.key_face_seq]))
                    row = layout.row()
                    row.operator("qarch.set_face_tag", text="Tag {}".format(int_to_face_tag(face[mm.key_tag])))
                    row = layout.row()
                    v = face[mm.key_radial]
                    row.operator("qarch.set_face_radial", text="Radial [{:.3f}, {:.3f}, {:.3f}]".format(v.x, v.y, v.z))
                    row = layout.row()
                    row.operator("qarch.set_face_uv_mode", text="UV Mode {}".format(int_to_uv_mode(face[mm.key_uv])))
                    row = layout.row()
                    v = face[mm.key_uv_rot]
                    row.operator("qarch.set_face_uv_rotate", text="UV Rotation [{:.1f}, {:.1f}, {:.1f}]".format(math.degrees(v.x), math.degrees(v.y), math.degrees(v.z)))
                    row = layout.row()
                    v = face[mm.key_uv_orig]
                    row.operator("qarch.set_face_uv_orig", text="UV Origin [{:.3f}, {:.3f}, {:.3f}]".format(v.x, v.y, v.z))
                    row = layout.row()
                    row.operator("qarch.set_face_elevation", text="Elevation {:.2f}".format(face[mm.key_elev]))
                    row = layout.row()
                    mat_name = context.object.data.materials[face.material_index].name
                    row.operator("qarch.set_face_material", text=mat_name)


                mm.free()

            else:
                row = layout.row()
                row.label(text="Not a bt object")
        else:
            row = layout.row()
            row.label(text="No object selected")


class QARCH_PT_calculator(bpy.types.Panel):
    bl_idname = "QARCH_PT_calculator"
    bl_label = "Reference Sizes"
    bl_options = {'INSTANCED'}
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"

    def draw(self, context):
        addon_prefs = context.preferences.addons[base_package].preferences
        layout = self.layout
        addon_prefs.calc_prop.draw(context, layout)
