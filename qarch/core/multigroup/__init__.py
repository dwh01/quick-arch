import bpy

from .multigroup_ops import QARCH_OT_add_multigroup
from .multigroup_props import MultigroupProperty

classes = (MultigroupProperty, QARCH_OT_add_multigroup)


def register_multigroup():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_multigroup():
    for cls in classes:
        bpy.utils.unregister_class(cls)
