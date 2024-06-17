import bpy

from .properties import ops_properties, uv_mode_list, uv_mode_to_int
from .dynamic_enums import face_tag_to_int, int_to_face_tag, BT_CATALOG_SRC, load_previews, file_type, from_path, BT_IMG_DESC

from .assets import (
    QARCH_OT_load_script,
    QARCH_OT_save_script,
    QARCH_OT_apply_script,
    QARCH_OT_catalog_script,
    QARCH_OT_catalog_curve,
    QARCH_OT_open_catalogs,
    # QARCH_OT_catalog_object,
    QARCH_OT_scan_catalogs,
    # QARCH_OT_load_object,
#register_assets, unregister_assets
)

from .state import (
    QARCH_OT_set_active_op,
    QARCH_OT_create_object,
    QARCH_OT_rebuild_object,
    QARCH_OT_remove_operation,
    QARCH_OT_add_face_tags,
    QARCH_OT_select_tags,
    QARCH_OT_redo_op,
    QARCH_OT_clean_object,
)
from .geom import (
    QARCH_OT_union_polygon,
    QARCH_OT_inset_polygon,
    QARCH_OT_grid_divide,
    QARCH_OT_split_face,
    QARCH_OT_extrude_fancy,
    QARCH_OT_extrude_sweep,
    QARCH_OT_solidify_edges,
    QARCH_OT_make_louvers,
    QARCH_OT_set_face_tag,
    QARCH_OT_set_face_uv_orig,
    QARCH_OT_set_face_thickness,
    QARCH_OT_set_face_uv_mode,
    QARCH_OT_set_face_uv_rotate,
    QARCH_OT_calc_uvs,
    QARCH_OT_set_oriented_mat,
    QARCH_OT_import_mesh,
    QARCH_OT_flip_normal,
    QARCH_OT_project_face,
    QARCH_OT_extrude_walls,
    QARCH_OT_build_face,
    QARCH_OT_build_roof,
)
from .compound import QARCH_OT_add_window, QARCH_OT_add_door, QARCH_OT_add_rail, QARCH_OT_extend_gable

classes = (
    QARCH_OT_load_script,
    QARCH_OT_save_script,
    QARCH_OT_set_active_op,
    QARCH_OT_create_object,
    QARCH_OT_union_polygon,
    QARCH_OT_inset_polygon,
    QARCH_OT_grid_divide,
    QARCH_OT_split_face,
    QARCH_OT_extrude_fancy,
    QARCH_OT_extrude_sweep,
    QARCH_OT_solidify_edges,
    QARCH_OT_make_louvers,
    QARCH_OT_add_window,
    QARCH_OT_add_door,
    QARCH_OT_rebuild_object,
    QARCH_OT_remove_operation,
    QARCH_OT_set_face_tag,
    QARCH_OT_set_face_uv_orig,
    QARCH_OT_set_face_thickness,
    QARCH_OT_set_face_uv_mode,
    QARCH_OT_set_face_uv_rotate,
    QARCH_OT_add_face_tags,
    QARCH_OT_select_tags,
    QARCH_OT_redo_op,
    QARCH_OT_calc_uvs,
    QARCH_OT_set_oriented_mat,
    QARCH_OT_apply_script,
    QARCH_OT_catalog_script,
    QARCH_OT_catalog_curve,
    QARCH_OT_open_catalogs,
    # QARCH_OT_catalog_object,
    QARCH_OT_clean_object,
    QARCH_OT_import_mesh,
    QARCH_OT_flip_normal,
    QARCH_OT_project_face,
    QARCH_OT_extrude_walls,
    QARCH_OT_build_face,
    QARCH_OT_scan_catalogs,
    QARCH_OT_build_roof,
    QARCH_OT_add_rail,
    QARCH_OT_extend_gable,
    # QARCH_OT_load_object
)

from bpy.app.handlers import persistent
@persistent
def pre_undo_handler(*args):
    print("pre undo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def post_undo_handler(*args):
    print("post undo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def pre_redo_handler(*args):
    print("pre redo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def post_redo_handler(*args):
    print("post deps", args)
    bpy.context.window_manager.print_undo_steps()

def register_ops():
    for cls in ops_properties:
        bpy.utils.register_class(cls)
    for cls in classes:
        bpy.utils.register_class(cls)

    # bpy.app.handlers.undo_pre.append(pre_undo_handler)
    # bpy.app.handlers.undo_post.append(post_undo_handler)
    # bpy.app.handlers.depsgraph_update_post.append(post_redo_handler)

    #register_assets()

def unregister_ops():
    for cls in ops_properties:
        bpy.utils.unregister_class(cls)
    for cls in classes:
        bpy.utils.unregister_class(cls)

    #unregister_assets()
