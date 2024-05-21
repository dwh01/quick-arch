"""Operators that change geometry"""
import bpy
from .custom import CustomOperator
from .properties import *
from ..mesh import (
    union_polygon,
    inset_polygon,
    grid_divide,
    split_face,
    extrude_fancy,
    extrude_sweep,
    solidify_edges,
    make_louvers
)


class QARCH_OT_union_polygon(CustomOperator):
    """Divide a face into regular patches"""

    bl_idname = "qarch.union_polygon"
    bl_label = "Add Polygon"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=UnionPolygonProperty)

    function = union_polygon

    def check_topology(self, props, prop_dict):
        return True  # any change can cause vertex count to change


class QARCH_OT_inset_polygon(CustomOperator):
    """Divide a face into regular patches"""

    bl_idname = "qarch.inset_polygon"
    bl_label = "Inset Polygon"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=InsetPolygonProperty)

    function = inset_polygon

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_grid_divide(CustomOperator):
    """Divide a face into regular patches"""

    bl_idname = "qarch.grid_divide"
    bl_label = "Grid Divide Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=GridDivideProperty)

    function = grid_divide

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_split_face(CustomOperator):
    """Divide a face into regular patches"""

    bl_idname = "qarch.split_face"
    bl_label = "Line Divide Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=SplitFaceProperty)

    function = split_face

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_extrude_fancy(CustomOperator):
    """Extrude in normal direction"""

    bl_idname = "qarch.extrude_fancy"
    bl_label = "Extrude Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=ExtrudeProperty)

    function = extrude_fancy

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_extrude_sweep(CustomOperator):
    """Sweep face"""

    bl_idname = "qarch.extrude_sweep"
    bl_label = "Sweep Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=SweepProperty)

    function = extrude_sweep

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_solidify_edges(CustomOperator):
    """Turn edges into solids"""

    bl_idname = "qarch.solidify_edges"
    bl_label = "Solidify Edges"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=SolidifyEdgesProperty)

    function = solidify_edges

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)  # maybe we don't need a whole face, allow just edges?


class QARCH_OT_make_louvers(CustomOperator):
    """Add louver or stair type geometry"""

    bl_idname = "qarch.make_louvers"
    bl_label = "Make Louvers"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=MakeLouversProperty)

    function = make_louvers

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


geom_classes = (
    QARCH_OT_union_polygon,
    QARCH_OT_inset_polygon,
    QARCH_OT_grid_divide,
    QARCH_OT_split_face,
    QARCH_OT_extrude_fancy,
    QARCH_OT_extrude_sweep,
    QARCH_OT_solidify_edges,
    QARCH_OT_make_louvers,
)