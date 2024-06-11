import bpy
from .core import register_core, unregister_core
from .utils import FaceMap, bmesh_from_active_object
from .ops import register_ops, unregister_ops
from .object import get_obj_data, ACTIVE_OP_ID

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
        row = layout.row(align=True)
        row.operator("qarch.create_object")
        row.operator("qarch.rebuild_object")

        row = layout.row(align=True)
        row.operator("qarch.set_active_op")
        row.operator("qarch.save_script")

        if context.object:
            active = get_obj_data(context.object, ACTIVE_OP_ID)
            if (active is not None) and (active > -1):
                row.alert = True
                row = layout.row(align=True)
                row.label(text="Active = {}".format(active))

        row = layout.row(align=True)
        row.operator("qarch.redo_op")
        row.operator("qarch.remove_operation")

        row = layout.row(align=True)
        row.operator("qarch.calc_uvs")
        row.operator("qarch.add_face_tags")

        row = layout.row(align=True)
        row.operator("qarch.clean_object")

        row = layout.row(align=True)
        row.operator("qarch.apply_script")
        row.operator("qarch.load_script")
        row = layout.row(align=True)
        row.operator("qarch.import_mesh")


        # Draw Operators
        # ``````````````
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("qarch.add_floorplan")
        row = col.row(align=True)
        row.operator("qarch.add_floors")
        row.operator("qarch.add_roof")
        row = col.row(align=True)
        row.operator("qarch.add_terrace")
        row.operator("qarch.add_roof_top")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("qarch.add_window")
        row.operator("qarch.add_door")
        col.operator("qarch.add_multigroup")

        row = layout.row(align=True)
        row.operator("qarch.add_balcony")
        row.operator("qarch.add_stairs")

        row = layout.row(align=True)
        row.operator("qarch.add_asset", icon="ADD")



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
        row.operator("qarch.inset_polygon")
        row = layout.row(align=True)
        row.operator("qarch.split_face")
        row.operator("qarch.grid_divide")
        row = layout.row(align=True)
        row.operator("qarch.extrude_fancy")
        row.operator("qarch.extrude_sweep")
        row.operator("qarch.extrude_walls")
        row = layout.row(align=True)
        row.operator("qarch.make_louvers")
        row.operator("qarch.solidify_edges")
        row = layout.row(align=True)
        row.operator("qarch.add_window")
        row = layout.row(align=True)
        row.operator("qarch.set_face_tag")
        row.operator("qarch.set_face_thickness")
        row = layout.row(align=True)
        row.operator("qarch.set_face_uv_mode")
        row.operator("qarch.set_face_uv_orig")
        row = layout.row(align=True)
        row.operator("qarch.set_face_uv_rotate")
        row.operator("qarch.set_oriented_mat")
        row = layout.row(align=True)
        row.operator("qarch.flip_normal")
        row.operator("qarch.project_face")


if bpy.app.version < (4,0,0):
    class QARCH_PT_material_tools(bpy.types.Panel):

        bl_label = "Face Maps"
        bl_parent_id = "QARCH_PT_mesh_tools"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Quick Arch"
        bl_options = {"DEFAULT_CLOSED"}

        # @classmethod
        # def poll(cls, context):
        #     obj = context.object
        #     return obj and obj.type == "MESH"

        def draw(self, context):
            layout = self.layout

            ob = context.object

            if len(ob.face_maps) == 0:
                layout.label(text="No Face Maps found")
                return

            facemap = ob.face_maps.active

            rows = 2
            if facemap:
                rows = 4

            # layout.label(text="Face Maps")

            row = layout.row()
            args = ob, "face_maps", ob.face_maps, "active_index"
            row.template_list("QARCH_UL_fmaps", "", *args, rows=rows)

            col = row.column(align=True)
            col.operator("object.face_map_add", icon="ADD", text="")
            col.operator("object.face_map_remove", icon="REMOVE", text="")
            # col.separator()
            # col.operator("qarch.face_map_clear", icon="TRASH", text="")

            if ob.face_maps and (ob.mode == "EDIT" and ob.type == "MESH"):
                row = layout.row()

                sub = row.row(align=True)
                sub.operator("object.face_map_assign", text="Assign")
                sub.operator("object.face_map_remove_from", text="Remove")

                sub = row.row(align=True)
                sub.operator("object.face_map_select", text="Select")
                sub.operator("object.face_map_deselect", text="Deselect")

            # if ob.face_maps:
            #     face_map_index = ob.face_maps.active_index
            #     face_map_material = ob.facemap_materials[face_map_index]

                # layout.label(text="UV Mapping")

                # col = layout.column()
                # row = col.row(align=True)
                # row.alignment = "LEFT"
                # row.prop(face_map_material, "auto_map", text="Auto")
                # row.prop(face_map_material, "uv_mapping_method", text="")

                # layout.label(text="Material")
                # layout.operator("qarch.create_facemap_material")
                # layout.template_ID_preview(face_map_material, "material", hide_buttons=True)
else:  # blender 4
    class QARCH_PT_material_tools(bpy.types.Panel):

        bl_label = "Face Maps"
        bl_parent_id = "QARCH_PT_mesh_tools"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Quick Arch"
        bl_options = {"DEFAULT_CLOSED"}

        # @classmethod
        # def poll(cls, context):
        #     obj = context.object
        #     return obj and obj.type == "MESH"

        def draw(self, context):
            layout = self.layout

            ob = context.object
            if ob.type == "MESH":
                me = ob.data
            else:
                return

            with bmesh_from_active_object(context) as bm:
                key = bm.faces.layers.int[FaceMap.FACEMAP.name]
                used = set()
                for face in bm.faces:
                    used.add(face[key])
                used = list(used)
                used.sort()

            rows = len(used)

            if (ob.mode == "EDIT") and (ob.type == "MESH"):
                for face_map in used:
                    if face_map > 0:
                        layout.label(text=FaceMap(face_map).name)
                        row = layout.row()

                        sub = row.row(align=True)
                        sub.operator("qarch.create_facemap_material", text="New Material").var_face_map = face_map
                        sub.operator("qarch.face_map_assign", text="Assign").var_face_map = face_map

                        sub = row.row(align=True)
                        sub.operator("qarch.face_map_select", text="Select").var_face_map = face_map
                        sub.operator("qarch.face_map_deselect", text="Deselect").var_face_map = face_map

class QARCH_PT_settings(bpy.types.Panel):
    bl_label = "Settings"
    bl_parent_id = "QARCH_PT_mesh_tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(context.scene.qarch_settings, "libpath")

        preferences = context.preferences
        addon_prefs = preferences.addons['qarch'].preferences
        # col.prop(addon_prefs, "user_tag")
        col.prop(addon_prefs, "select_mode")
        col.prop(addon_prefs, "build_style")

        row = layout.row(align=True)
        row.operator("qarch.open_catalogs", text="Open catalogs")
        row = layout.row(align=True)
        row.operator("qarch.catalog_script", text="Catalog script")
        row.operator("qarch.catalog_object", text="Catalog object")


classes = (QARCH_PT_mesh_tools, QARCH_PT_low_level, QARCH_PT_material_tools, QARCH_PT_settings)


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
