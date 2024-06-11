"""Geometry import/export operations"""
import bpy
from bpy.props import StringProperty, PointerProperty, BoolProperty, IntProperty, EnumProperty
from bpy.types import WindowManager
import bpy.utils.previews
import pathlib, os, json
from .custom import CustomOperator, replay_history
from .dynamic_enums import enum_categories, enum_category_items, enum_catalogs
from .dynamic_enums import BT_IMG_CAT, BT_IMG_DESC, BT_IMG_SCRIPT, BT_IMG_CURVE
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

# load script and apply to selected face
# load mesh from blend file and add to current mesh
# save active op and children to script file
def load_script(obj, sel_info, filepath):
    subset = import_record(filepath)

    first_op_id = merge_record(obj, subset, sel_info)
    if isinstance(first_op_id, str):
        return first_op_id

    replay_history(bpy.context, first_op_id)


def load_local_script(obj, sel_info, script_name):
    subset = json.loads(bpy.data.texts[script_name])

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
        set_obj_data(obj, ACTIVE_OP_ID, -1)
        return {'FINISHED'}

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "filepath")


class QARCH_OT_do_apply_script(bpy.types.Operator):
    bl_idname = "qarch.do_apply_script"
    bl_label = "Apply Script"
    bl_description = "Apply this script to selected faces"

    category_name: EnumProperty(items=enum_categories, name="Category")
    category_item: EnumProperty(items=enum_category_items, name="Scripts")

    def invoke(self, context, event):
        x, y = event.mouse_x, event.mouse_y
        context.window.cursor_warp(10, 10)

        def move_back(*args):
            bpy.context.window.cursor_warp(x, y)
        bpy.app.timers.register(move_back, first_interval=0.001)
        return self.execute(context)

    def execute(self, context):
        print("Apply {} {}".format(self.category_name, self.category_item))
        script_name = BT_IMG_SCRIPT + self.category_item

        preferences = context.preferences.addons['qarch'].preferences  # note: self is passed to functions
        style_name = preferences.build_style

        lst_cat = enum_catalogs(self, context)
        for e in lst_cat:
            if e[0]==style_name:
                filepath = e[2]
                break

        if script_name not in bpy.data.texts:  # not already loaded
            with bpy.data.libraries.load(str(filepath)) as (data_from, data_to):
                data_to.texts.append(script_name)

        obj = context.object
        op_id = -1

        mm = ManagedMesh(obj)
        sel_info = mm.get_selection_info()
        ret = load_local_script(obj, sel_info, script_name)
        if ret is not None:
            self.report({"ERROR_INVALID_CONTEXT"}, ret)
            return {'CANCELLED'}

        set_obj_data(obj, ACTIVE_OP_ID, -1)

        journal = Journal(obj)
        journal['adjusting'] = []
        journal.flush()

        return {'FINISHED'}



class QARCH_OT_apply_script(bpy.types.Operator):
    bl_idname = "qarch.apply_script"
    bl_label = "Apply Script"
    bl_description = "Select script to load onto face(s)"

    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    category_name: EnumProperty(items=enum_categories, name="Category")
    category_item: EnumProperty(items=enum_category_items, name="Scripts")

    show_scripts: BoolProperty(name="Show Scripts", default = True)

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # Search box to filter on name and common name (label)
        row = layout.row()
        row.prop(self, "search_text", icon='VIEWZOOM', text="")

        row = layout.row()
        row.prop_menu_enum(self, 'category_name')
        row = layout.row()
        row.template_icon_view(self, 'category_item', show_labels=True, scale=10)
        row = layout.row()
        op = row.operator("qarch.do_apply_script", text="Apply {}".format(self.category_item))
        op.category_name = self.category_name
        op.category_item = self.category_item

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return {'FINISHED'}


class QARCH_OT_do_add_instance(bpy.types.Operator):
    bl_idname = "qarch.do_add_instance"
    bl_label = "Add Object"
    bl_description = "Add instances of this object"

    category_name: StringProperty(name="Category")
    category_item: StringProperty(name="Object")

    def invoke(self, context, event):
        x, y = event.mouse_x, event.mouse_y
        context.window.cursor_warp(10, 10)

        def move_back(*args):
            bpy.context.window.cursor_warp(x, y)
        bpy.app.timers.register(move_back, first_interval=0.001)
        return self.execute(context)

    def execute(self, context):
        print("Add Instance {} {}".format(self.category_name, self.category_item))
        obj_name = self.category_item

        preferences = context.preferences.addons['qarch'].preferences  # note: self is passed to functions
        style_name = preferences.build_style

        lst_cat = enum_catalogs(self, context)
        for e in lst_cat:
            if e[0]==style_name:
                filepath = e[2]
                break

        if obj_name not in bpy.data.objects:  # not already loaded
            with bpy.data.libraries.load(str(filepath)) as (data_from, data_to):
                data_to.objects.append(obj_name)
            bpy.ops.ed.undo_push(message="Load Object")

        obj = bpy.data.objects[obj_name]
        try:
            coll = bpy.data.collections['BT_Instances']
        except Exception:
            coll = bpy.data.collections.new('BT_Instances')
            bpy.data.collections['Collection'].children.link(coll)
        coll.objects.link(obj)

        print("loaded {}, send to local_array operator".format(obj.name))

        return {'FINISHED'}


class QARCH_OT_add_instance(bpy.types.Operator):
    bl_idname = "qarch.add_instance"
    bl_label = "Add Instance"
    bl_description = "Select object to instance"

    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    category_name: EnumProperty(items=enum_categories, name="Category")
    category_item: EnumProperty(items=enum_category_items, name="Objects")

    show_scripts: BoolProperty(name="Show Scripts", default=False)

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # Search box to filter on name and common name (label)
        row = layout.row()
        row.prop(self, "search_text", icon='VIEWZOOM', text="")

        row = layout.row()
        row.prop_menu_enum(self, 'category_name')
        row = layout.row()
        row.template_icon_view(self, 'category_item', show_labels=True, scale=10)
        row = layout.row()
        op = row.operator("qarch.do_add_instance", text="Apply {}".format(self.category_item))
        print(self.category_name, self.category_item)
        op.category_name = self.category_name
        op.category_item = self.category_item

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return {'FINISHED'}

class QARCH_OT_open_catalogs(bpy.types.Operator):
    bl_idname = "qarch.open_catalogs"
    bl_label = "Open Catalogs"
    bl_description = "Open catalog directory"

    directory: StringProperty(name="Directory", description="Catalog directory", subtype="DIR_PATH")
    filepath: StringProperty(name="Filepath", description="Catalog blend file", subtype="FILE_PATH")
    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        from .dynamic_enums import qarch_asset_dir
        self.directory = str(qarch_asset_dir)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if len(self.filepath):
            return bpy.ops.wm.open_mainfile(filepath=self.filepath, display_file_selector=False)
        return {"FINISHED"}


class QARCH_OT_catalog_script(bpy.types.Operator):
    bl_idname = "qarch.catalog_script"
    bl_label = "Catalog Script"
    bl_description = "Add script file to catalog"

    filepath = StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")
    category_name: StringProperty(name="Category", description="Collection name (Doors, Windows, etc.)")
    category_item: StringProperty(name="Name", description="Name of script")
    description: StringProperty(name="Description", description="Description text")

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        txt_path = pathlib.Path(self.filepath)
        img_path = txt_path.with_suffix(".png")
        if img_path.exists():
            txt = bpy.data.texts.load(str(txt_path), internal=True)
            txt.name = self.category_item
            img = bpy.data.images.load(str(img_path))
            img.name = self.category_item
            img[BT_IMG_CAT] = BT_IMG_SCRIPT + self.category_name
            img[BT_IMG_DESC] = self.description
            img.use_fake_user = True

        else:
            self.report({"ERROR_INVALID_INPUT"}, "No example image found {}".format(img_path))
            return {"CANCELLED"}

        return {"FINISHED"}


class QARCH_OT_catalog_object(bpy.types.Operator):
    bl_idname = "qarch.catalog_object"
    bl_label = "Catalog Object"
    bl_description = "Add selected object to catalog"

    category_name: StringProperty(name="Category", description="Collection name (Doors, Windows, etc.)")
    category_item: StringProperty(name="Name", description="Name of object in catalog")
    description: StringProperty(name="Description", description="Description text")

    @classmethod
    def poll(cls, context):
        if context and context.active_object:
            if type(context.active_object.data) in [bpy.types.Curve, bpy.types.Mesh]:
                return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from ..mesh import draw
        img = draw(self.category_item)
        cat_name = self.category_name
        if type(context.active_object.data) is bpy.types.Curve:
            cat_name = BT_IMG_CURVE + cat_name
        img[BT_IMG_CAT] = cat_name
        img[BT_IMG_DESC] = self.description
        img.use_fake_user = True

        obj = context.active_object
        obj.name = self.category_item
        try:
            col = bpy.data.collections[self.category_name]
        except Exception:
            col = bpy.data.collections.new(self.category_name)
            bpy.data.collections['Collection'].children.link(col)

        if obj.name not in col.objects:
            col.objects.link(obj)

        return {"FINISHED"}

