"""Geometry import/export operations"""
import copy

import bpy
from bpy.props import StringProperty, PointerProperty, BoolProperty, EnumProperty
import bpy.utils.previews
import pathlib, os, json, uuid, shutil
from .custom import CustomOperator, replay_history
from .dynamic_enums import enum_categories, enum_category_items, qarch_asset_dir, load_previews, enum_catalogs
from .dynamic_enums import BT_IMG_CAT, BT_IMG_DESC, BT_IMG_CURVE, BT_IMG_MESH, file_type, to_path, script_name, curve_name, mesh_name
from ..object import (
    export_record,
    get_obj_data,
    set_obj_data,
    ACTIVE_OP_ID,
    import_record,
    merge_record,
    Journal
    )
from .properties import AssetLibProps
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
    subset = json.loads(bpy.data.texts[script_name].as_string())

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

    filepath: StringProperty(name="Filename", description="Script to save", subtype="FILE_PATH", default=str(qarch_asset_dir))

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


class QARCH_OT_apply_script(bpy.types.Operator):
    bl_idname = "qarch.apply_script"
    bl_label = "Apply Script"
    bl_description = "Select script to load onto face(s)"
    bl_options = {'REGISTER', 'UNDO'}

    search_text: StringProperty(name="Search", description="Press enter to filter by substring")
    style_name: EnumProperty(name="Style", items=enum_catalogs, description="Style")
    category_name: EnumProperty(items=enum_categories, name="Category", default=0)
    category_item: EnumProperty(items=enum_category_items, name="Scripts")
    apply: BoolProperty(name="Apply to Selection", default = False)
    show_scripts: BoolProperty(name="Show Scripts", default = True)
    show_curves: BoolProperty(name="Show Scripts", default = False)

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # Search box to filter on name and common name (label)
        row = layout.row()
        row.prop(self, "search_text", icon='VIEWZOOM', text="")

        row = layout.row()
        row.prop_menu_enum(self, 'style_name')
        row.label(text=self.style_name)
        row = layout.row()
        row.prop_menu_enum(self, 'category_name')
        row.label(text=self.category_name)
        row = layout.row()
        row.template_icon_view(self, 'category_item', show_labels=True, scale=10)
        row = layout.row()
        row.prop(self, 'apply')

    def invoke(self, context, event):
        return self.execute(context)
        # wm = context.window_manager
        # wm.invoke_popup(self)
        # return {'RUNNING_MODAL'}

    def execute(self, context):
        if self.apply:
            wm = context.window_manager
            print("Apply {} {}".format(self.category_name, self.category_item))
            script_path = self.category_item
            if script_path == "0":
                return {'FINISHED'}

            script_path = pathlib.Path(script_path)
            ftype, script_name = file_type(script_path.stem)

            if script_name not in bpy.data.texts:  # not already loaded
                text_obj = bpy.data.texts.load(str(script_path))
                text_obj.name = script_name

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
    bl_description = "Save current operation to catalog"
    bl_options = {"REGISTER", "UNDO"}

    # file_path: StringProperty(name="Filename", description="Script to load", subtype="FILE_PATH")
    style_name: StringProperty(name="Style", description="Style name (default, scifi, etc.)")
    category_name: StringProperty(name="Category", description="Collection name (Doors, Windows, etc.)")
    description: StringProperty(name="Description", description="Description text")
    category_item: StringProperty(name="Name", description="Name of script")


    @classmethod
    def poll(cls, context):
        if not context.object:
            return False
        operation_id = get_obj_data(context.object, ACTIVE_OP_ID)
        if operation_id is None:
            return False
        return operation_id > -1

    def invoke(self, context, event):
        # self.xy = event.mouse_x, event.mouse_y
        self.category_item = ""
        return self.execute(context)

    def execute(self, context):
        if (len(self.category_name)== 0) or (len(self.category_item)== 0) or (len(self.style_name)==0):
            return {"FINISHED"}

        style = self.style_name
        category = self.category_name
        name = self.category_item

        # cur_text_path = pathlib.Path(self.file_path)
        # cur_img_path = cur_text_path.with_suffix(".png")

        qual_name = script_name(name)
        txt_path = to_path(style, category, qual_name)
        img_path = txt_path.with_suffix(".png")

        img_path.parent.mkdir(parents=True, exist_ok=True)

        obj = context.object
        operation_id = get_obj_data(obj, ACTIVE_OP_ID)
        export_record(obj, operation_id, str(txt_path), True, str(img_path), self.description)
        set_obj_data(obj, ACTIVE_OP_ID, -1)

        # shutil.copy(str(cur_text_path), str(txt_path))
        # if cur_img_path.exists():
        #     shutil.copy(str(cur_img_path), str(img_path))

        # context.window.cursor_warp(10, 10)
        # def move_back(*args):
        #     bpy.context.window.cursor_warp(*self.xy)
        #
        # bpy.app.timers.register(move_back, first_interval=0.001)

        return {"FINISHED"}


class QARCH_OT_catalog_curve(bpy.types.Operator):
    bl_idname = "qarch.catalog_curve"
    bl_label = "Catalog Curve"
    bl_description = "Export curve to catalog"
    bl_options = {"REGISTER", "UNDO"}

    style_name: StringProperty(name="Style", description="Style name (default, scifi, etc.)")
    category_name: StringProperty(name="Category", description="Collection name (Doors, Windows, etc.)")
    description: StringProperty(name="Description", description="Description text")
    category_item: StringProperty(name="Name", description="Name of object in catalog")

    @classmethod
    def poll(cls, context):
        if context and context.active_object:
            if type(context.active_object.data) in [bpy.types.Curve]:
                return True
        return False

    def invoke(self, context, event):
        self.category_item = ""
        return self.execute(context)

    def execute(self, context):
        from ..mesh import draw, curve_to_text
        if (len(self.category_name)== 0) or (len(self.category_item)== 0) or (len(self.style_name)==0):
            return {"FINISHED"}

        cat_name = self.category_name
        qual_name = curve_name(self.category_item)
        txt_file = to_path(self.style_name, self.category_name, qual_name)
        img_file = txt_file.with_suffix(".png")
        img_file.parent.mkdir(parents=True, exist_ok=True)

        img = draw(self.category_item)
        img.save(filepath=str(img_file))

        obj = context.active_object
        txt = curve_to_text(obj, self.description)
        txt_file = to_path(self.style_name, self.category_name, curve_name(self.category_item))
        txt_file.write_text(txt)

        return {"FINISHED"}



class QARCH_OT_catalog_mesh(bpy.types.Operator):
    bl_idname = "qarch.catalog_mesh"
    bl_label = "Catalog Mesh"
    bl_description = "Export mesh to catalog without materials"
    bl_options = {"REGISTER", "UNDO"}

    style_name: StringProperty(name="Style", description="Style name (default, scifi, etc.)")
    category_name: StringProperty(name="Category", description="Collection name (Doors, Windows, etc.)")
    description: StringProperty(name="Description", description="Description text")
    category_item: StringProperty(name="Name", description="Name of object in catalog")

    @classmethod
    def poll(cls, context):
        if context and context.active_object:
            if type(context.active_object.data) in [bpy.types.Mesh]:
                return True
        return False

    def invoke(self, context, event):
        self.category_item = ""
        return self.execute(context)

    def execute(self, context):
        from ..mesh import draw
        if (len(self.category_name)== 0) or (len(self.category_item)== 0) or (len(self.style_name)==0):
            return {"FINISHED"}

        cat_name = self.category_name
        qual_name = mesh_name(self.category_item)
        txt_file = to_path(self.style_name, self.category_name, qual_name)
        img_file = txt_file.with_suffix(".png")
        img_file.parent.mkdir(parents=True, exist_ok=True)

        img = draw(self.category_item)
        img.save(filepath=str(img_file))

        obj = context.active_object
        bpy.ops.export_mesh.stl(filepath=str(txt_file), check_existing=False, filter_glob='*.stl', use_selection=True)

        return {"FINISHED"}


def load_catalog():  # for asset view
    lst = []
    filepath = qarch_asset_dir / "blender_assets.cats.txt"
    with open(filepath, "r") as cat:
        lines = cat.readlines()

    for line in lines:
        line.strip()
        if line[-1] == '\n':
            line = line[:-1]
        if len(line)==0:
            continue
        if line[0]=="#":
            continue
        if line.startswith('VERSION'):
            continue

        parts = line.split(":")
        lst.append(parts)
    print(lst)
    return lst


def append_catalog(uid, pth, name):  # for asset view
    filepath = qarch_asset_dir / "blender_assets.cats.txt"
    with open(filepath, "a") as cat:
        cat.writelines([f'{uid}:{pth}:{name}\n'])


class QARCH_OT_scan_catalogs(bpy.types.Operator):
    """Force loading of catalog because it can affect the undo stack"""
    bl_idname = "qarch.scan_catalogs"
    bl_label = "Scan Catalogs"
    bl_description = "Search for catalog files"

    def execute(self, context):
        load_previews(True)
        return {'FINISHED'}

# unused classes that might be good in the future
# this pushes an object into asset catalog, but from current file. you have to be in library file to be useful
class QARCH_OT_catalog_object(bpy.types.Operator):
    bl_idname = "qarch.catalog_object"
    bl_label = "Catalog Object"
    bl_description = "Add selected object to asset catalog"

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

    def asset_execute(self, context):
        """This method when the asset_template_view becomes useful"""
        obj = context.active_object
        obj.name = self.category_item
        obj.asset_mark()
        obj.asset_generate_preview()
        obj.asset_data.description = self.description
        obj.asset_data.tags.new(self.category_name)
        # asset_data.author

        cat = load_catalog()
        for parts in cat:
            uid, pth, name = parts[0], parts[1], parts[2]
            if name == self.category_name:
                obj.asset_data.catalog_id = uid
                return {"FINISHED"}

        uid = str(uuid.uuid4())
        pth = self.category_name
        name = self.category_name

        append_catalog(uid, pth, name)
        obj.asset_data.catalog_id = uid
        return {"FINISHED"}


    def execute(self, context):
        from ..mesh import draw
        img = draw(self.category_item)
        cat_name = self.category_name
        if type(context.active_object.data) is bpy.types.Curve:
            cat_name = BT_IMG_CURVE + cat_name
        img[BT_IMG_CAT] = cat_name
        img[BT_IMG_DESC] = self.description
        img.use_fake_user = True
        img.pack()

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



# experimental asset shelf that pops up under the right conditions
class VIEW3D_AST_qarch_objects(bpy.types.AssetShelf):
    bl_space_type = "VIEW_3D"
    bl_idname = "VIEW3D_AST_my_asset_shelf"
    show_names = True
    asset_library_reference='CUSTOM'

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.mode == 'EDIT')

    @classmethod
    def asset_poll(cls, asset):
        print("asset poll", asset)
        return asset.id_type in {'CURVE', 'OBJECT'}
        cat = load_catalog()
        for uid, pth, name in cat:
            if asset.catalog_id == uid:
                return True
        return False

# use the asset library system to load objects
# but there is no filtering support except to pick library (and type name search text)
# so this is not as good as template_icon where we can filter for categories like Doors
class QARCH_OT_load_object(bpy.types.Operator):
    """Divide a face into patches"""
    bl_idname = "qarch.load_object"
    bl_label = "Load Object"
    bl_options = {"REGISTER","UNDO"}

    props: PointerProperty(type=AssetLibProps)


    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        workspace = context.workspace
        activate_op_props, drag_op_props = self.layout.template_asset_view("LoadObject",
                                        workspace, "asset_library_reference",
                                        self.props, "asset",
                                        self.props, "active",
                                        filter_id_types={'filter_object'},
                                        # display_options={'NO_LIBRARY'},
                                        activate_operator='asset.print_selected_assets')
        # activate_operator='qarch.load_object' causes undo stack to grow, must send to another operator

# used to make sure the qarch asset directory is known to blender
class QARCH_OT_add_library(bpy.types.Operator):
    """For cleanup when old faces are left behind"""
    bl_idname = "qarch.add_library"
    bl_label = "Add Library"
    bl_description = "Add asset library path to preferences"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        b_found = False
        for lib in context.preferences.filepaths.asset_libraries:
            if lib.name == 'qarch':
                print("found")
                b_found = True
                break

        if not b_found:
            bpy.ops.preferences.asset_library_add()
            lib = context.preferences.filepaths.asset_libraries[-1]
            lib.name = "qarch"
            lib.path = str(qarch_asset_dir)
            print("added")

        #scan_builtin_styles()
        return self.execute(context)

# just a demonstration of the context.asset after picking with the template_asset_view
class PrintSelectedAssets(bpy.types.Operator):
    bl_idname = "asset.print_selected_assets"
    bl_label = "Print Selected Assets"

    @classmethod
    def poll(cls, context):
        return context.asset

    def execute(self, context):
        if context.asset:
            print("print execute")
            print(context.asset)
            asset_representation = context.asset
            print(f"{asset_representation.full_path=}")
            print(f"{asset_representation.full_library_path=}")
            print(f"{asset_representation.id_type=}")
            print(f"{asset_representation.name=}")
            # This will be None if the asset is not located in current file :
            print(f"{asset_representation.local_id=}")


        return {"FINISHED"}


def display_button(self, context):
    self.layout.operator(PrintSelectedAssets.bl_idname)


addon_keymaps = []
def register_assets():
    bpy.utils.register_class(PrintSelectedAssets)
    #bpy.types.ASSETBROWSER_MT_editor_menus.append(display_button)

    # bpy.utils.register_class(VIEW3D_AST_qarch_objects)
    # # Asset Shelf
    # wm = bpy.context.window_manager
    # km = wm.keyconfigs.addon.keymaps.new(name="Asset Shelf")
    # kmi = km.keymap_items.new("asset.print_selected_assets", "LEFTMOUSE", "CLICK")
    # addon_keymaps.append((km, kmi))


def unregister_assets():
    # wm = bpy.context.window_manager
    # for km, km1 in addon_keymaps:
    #     wm.keyconfigs.addon.keymaps.remove(km)

    #bpy.types.ASSETBROWSER_MT_editor_menus.remove(display_button)
    bpy.utils.unregister_class(PrintSelectedAssets)
    # bpy.utils.unregister_class(VIEW3D_AST_qarch_objects)