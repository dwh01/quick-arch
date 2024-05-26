import bpy

from .properties import ops_properties
from .assets import QARCH_OT_load_script, QARCH_OT_save_script
from .state import QARCH_OT_set_active_op, QARCH_OT_create_object, QARCH_OT_rebuild_object, QARCH_OT_remove_operation
from .geom import (
    QARCH_OT_union_polygon,
    QARCH_OT_inset_polygon,
    QARCH_OT_grid_divide,
    QARCH_OT_split_face,
    QARCH_OT_extrude_fancy,
    QARCH_OT_extrude_sweep,
    QARCH_OT_solidify_edges,
    QARCH_OT_make_louvers,
)
from .compound import QARCH_OT_add_window

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
    QARCH_OT_rebuild_object,
    QARCH_OT_remove_operation,
)


def register_ops():
    for cls in ops_properties:
        bpy.utils.register_class(cls)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_ops():
    for cls in ops_properties:
        bpy.utils.unregister_class(cls)
    for cls in classes:
        bpy.utils.unregister_class(cls)

