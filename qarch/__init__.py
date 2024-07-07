import bpy
from .core import register_core, unregister_core
from .utils import FaceMap, bmesh_from_active_object
from .ops import register_ops, unregister_ops
from .object import get_obj_data, ACTIVE_OP_ID

from .ops.state import QARCH_PT_faceinfo, QARCH_PT_calculator  # must register at end

bl_info = {
    "name": "Quick Arch",
    "author": "Lucky Kadam (luckykadam94@gmail.com)",
    "version": (1, 3, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Toolshelf > Quick Arch",
    "description": "Architectural Tools",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Mesh",
}


class QARCH_PT_mesh_tools(bpy.types.Panel):
    bl_label = "Quick Arch Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Quick Arch"

    def draw(self, context):
        layout = self.layout
        preferences = context.preferences
        addon_prefs = preferences.addons['qarch'].preferences
        row = layout.row(align=True)
        row.prop(addon_prefs, "select_mode")

        row = layout.row(align=True)
        row.operator("qarch.create_object")
        row.operator("qarch.rebuild_object")

        row = layout.row(align=True)
        row.operator("qarch.set_active_op")
        if context.object:
            active = get_obj_data(context.object, ACTIVE_OP_ID)
            if (active is not None) and (active > -1):
                row.alert = True
                row.label(text="Active = {}".format(active))

        row = layout.row(align=True)
        row.operator("qarch.redo_op")
        row.operator("qarch.remove_operation")

        row = layout.row(align=True)
        row.operator("qarch.calc_uvs")
        row.operator("qarch.clean_object")

        row = layout.row(align=True)
        row.operator("qarch.inset_polygon")


class QARCH_PT_plan_level(bpy.types.Panel):
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_label = "Plan Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Quick Arch"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("qarch.plan_inset_walls")
        row.operator("qarch.plan_feature")
        row = layout.row(align=True)
        row.operator("qarch.set_plan_floor")
        row.operator("qarch.extrude_walls")

        # Draw Operators
        # ``````````````
        # col = layout.column(align=True)
        # row = col.row(align=True)
        # row.operator("qarch.add_floorplan")
        # row = col.row(align=True)
        # row.operator("qarch.add_floors")
        # row.operator("qarch.add_roof")
        # row = col.row(align=True)
        # row.operator("qarch.add_terrace")
        # row.operator("qarch.add_roof_top")
        #
        # col = layout.column(align=True)
        # row = col.row(align=True)
        # row.operator("qarch.add_window")
        # row.operator("qarch.add_door")
        # col.operator("qarch.add_multigroup")
        #
        # row = layout.row(align=True)
        # row.operator("qarch.add_balcony")
        # row.operator("qarch.add_stairs")
        #
        # row = layout.row(align=True)
        # row.operator("qarch.add_asset", icon="ADD")


class QARCH_PT_hi_level(bpy.types.Panel):
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_label = "Macro Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Quick Arch"
    # bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("qarch.apply_script")
        row.operator("qarch.import_mesh")
        row = layout.row(align=True)
        row.operator("qarch.add_window")
        row = layout.row(align=True)
        row.operator("qarch.add_door")
        row.operator("qarch.add_portico")
        row = layout.row(align=True)
        row.operator("qarch.add_deck")
        row.operator("qarch.add_rail")
        row = layout.row(align=True)
        row.operator("qarch.build_roof")
        row.operator("qarch.extend_gable")
        row = layout.row(align=True)
        row.operator("qarch.add_dormer")


class QARCH_PT_low_level(bpy.types.Panel):
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_label = "Detail Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Quick Arch"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.operator("qarch.solidify_edges")
        row = layout.row(align=True)
        row.operator("qarch.split_face")
        row.operator("qarch.grid_divide")
        row = layout.row(align=True)
        row.operator("qarch.extrude_fancy")
        row.operator("qarch.extrude_sweep")
        row = layout.row(align=True)
        row.operator("qarch.project_face")
        row.operator("qarch.build_face")
        row = layout.row(align=True)
        row.operator("qarch.make_louvers")
        row.operator("qarch.perpendicular_face")
        row = layout.row(align=True)
        row.operator("qarch.set_oriented_mat")
        row.operator("qarch.flip_normal")



class QARCH_PT_catalog(bpy.types.Panel):
    bl_label = "Catalog"
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("qarch.open_catalogs", text="Open catalogs")
        row.operator("qarch.scan_catalogs", text="Reload catalogs")
        row = layout.row(align=True)
        row.operator("qarch.catalog_script", text="Catalog script")
        row.operator("qarch.catalog_curve", text="Catalog curve")
        row = layout.row(align=True)
        row.operator("qarch.catalog_mesh", text="Catalog mesh")


classes = (QARCH_PT_mesh_tools, QARCH_PT_plan_level, QARCH_PT_hi_level, QARCH_PT_low_level, QARCH_PT_faceinfo,
           QARCH_PT_catalog, QARCH_PT_calculator)


def register():
    register_core()
    register_ops()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    unregister_core()
    unregister_ops()
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    import os

    os.system("clear")

    # -- custom unregister for script watcher
    for tp in dir(bpy.types):
        if "QARCH_" in tp:
            bpy.utils.unregister_class(getattr(bpy.types, tp))

    register()
