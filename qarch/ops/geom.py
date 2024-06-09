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
    make_louvers,
    set_face_property,
    ManagedMesh,
    calc_uvs,
    set_oriented_material,
)
from ..object import get_obj_data, ACTIVE_OP_ID, material_best_mode


class QARCH_OT_union_polygon(CustomOperator):
    """Divide a face into regular patches"""

    bl_idname = "qarch.union_polygon"
    bl_label = "Add Polygon"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=UnionPolygonProperty)

    function = union_polygon


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

    def invoke(self, context, event):
        # ensure that we are looking for curves
        self.props.local_object.show_curves = True
        self.props.catalog_object.show_curves = True
        lst = enum_categories(self.props, context)
        pick = min(1, len(lst))
        #print(lst, pick)
        #self.props.catalog_object.category_name = lst[pick][0]

        return super().invoke(context, event)


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



class QARCH_OT_set_face_tag(CustomOperator):
    bl_idname = "qarch.set_face_tag"
    bl_label = "Face Tag"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=FaceTagProperty)

    function = set_face_property

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        tag = None
        for face in mm.bm.faces:
            if face.select:
                tag = face[mm.key_tag]
                break
        if tag is not None:
            self.props.tag = int_to_face_tag(tag)
        mm.free()

        return super().invoke(context, event)


class QARCH_OT_set_face_thickness(CustomOperator):
    bl_idname = "qarch.set_face_thickness"
    bl_label = "Face Thickness"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=FaceThicknessProperty)

    function = set_face_property

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        thick = None
        for face in mm.bm.faces:
            if face.select:
                thick = face[mm.key_thick]
                break

        if thick is not None:
            self.props.thickness = thick
        mm.free()

        return super().invoke(context, event)


class QARCH_OT_set_face_uv_mode(CustomOperator):
    bl_idname = "qarch.set_face_uv_mode"
    bl_label = "UV Mode"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=FaceUVModeProperty)

    function = set_face_property

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        mode = None
        for face in mm.bm.faces:
            if face.select:
                mode = face[mm.key_uv]
                break
        if mode is not None:
            self.props.uv_mode = int_to_uv_mode(mode)
        mm.free()

        return super().invoke(context, event)


class QARCH_OT_set_face_uv_orig(CustomOperator):
    bl_idname = "qarch.set_face_uv_orig"
    bl_label = "UV Origin"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=FaceUVOriginProperty)

    function = set_face_property

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        org = None
        for face in mm.bm.faces:
            if face.select:
                org = face[mm.key_uv_orig]
                break
        if org is not None:
            self.props.uv_orig = org
        mm.free()

        return super().invoke(context, event)


class QARCH_OT_set_face_uv_rotate(CustomOperator):
    bl_idname = "qarch.set_face_uv_rotate"
    bl_label = "UV Rotate"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=FaceUVRotateProperty)

    function = set_face_property

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        rot = None
        for face in mm.bm.faces:
            if face.select:
                rot = face[mm.key_uv_rot]
                break
        if rot is not None:
            self.props.uv_rotate = rot
        mm.free()

        return super().invoke(context, event)


class QARCH_OT_calc_uvs(CustomOperator):
    """Select by tags"""
    bl_idname = "qarch.calc_uvs"
    bl_label = "Calc UV"
    bl_description = "Calculate UV coordinates"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=CalcUVProperty)

    function = calc_uvs


class QARCH_OT_set_oriented_mat(CustomOperator):
    bl_idname = "qarch.set_oriented_mat"
    bl_label = "Oriented Material"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=OrientedMaterialProperty)

    function = set_oriented_material

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        # if this is not a replay, replace defaults with what is in the face now
        mm = ManagedMesh(context.object)
        midx = None
        for face in mm.bm.faces:
            if face.select:
                midx = face.material_index
                break
        if midx is not None:
            mname = context.object.data.materials[midx].name
            if material_best_mode(mname) == 'ORIENTED':
                self.props.material = mname
        mm.free()

        return super().invoke(context, event)


geom_classes = (
    QARCH_OT_union_polygon,
    QARCH_OT_inset_polygon,
    QARCH_OT_grid_divide,
    QARCH_OT_split_face,
    QARCH_OT_extrude_fancy,
    QARCH_OT_extrude_sweep,
    QARCH_OT_solidify_edges,
    QARCH_OT_make_louvers,
    QARCH_OT_set_face_uv_orig,
    QARCH_OT_set_face_uv_mode,
    QARCH_OT_set_face_thickness,
    QARCH_OT_set_face_tag,
    QARCH_OT_calc_uvs,
    QARCH_OT_set_oriented_mat,
)