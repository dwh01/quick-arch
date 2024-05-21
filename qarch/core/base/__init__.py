import bpy

from .base_ops import QARCH_OT_face_divide, QARCH_OT_select_op

from .base_props import (
    ArchShapeProperty,
    BayProperties,
    DividersProperty,
    ExtrusionSimpleProperty,
    ExtrusionTwistProperty,
    FaceDivisionProperty,
    FrameShapeProperty,
    LouversProperty,
    RoomProperty)

classes = (
    ArchShapeProperty,
    BayProperties,
    DividersProperty,
    ExtrusionSimpleProperty,
    ExtrusionTwistProperty,
    FaceDivisionProperty,
    FrameShapeProperty,
    LouversProperty,
    RoomProperty,
    QARCH_OT_face_divide,
    QARCH_OT_select_op,
)


def register_base():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_base():
    for cls in classes:
        bpy.utils.unregister_class(cls)