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
    import_mesh,
    flip_normals,
    project_face,
    extrude_walls,
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

    def invoke(self, context, event):
        # ensure that we are looking for curves
        self.props.local_object.show_curves = True
        self.props.catalog_object.show_curves = True
        lst = enum_categories(self.props, context)
        if len(lst) and (self.props.catalog_object.category_name in ['', '0', 'N/A']):
            pick = min(1, len(lst))
            self.props.catalog_object.category_name = lst[pick][0]

        if not self.is_face_selected(context):
            if self.props.join != 'FREE':
                self.props.join = 'FREE'
                self.props.shape_type = 'NGON'
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

    def invoke(self, context, event):
        # ensure that we are looking for curves
        self.props.local_object.show_curves = True
        self.props.catalog_object.show_curves = True
        lst = enum_categories(self.props, context)
        if len(lst) and (self.props.catalog_object.category_name in ['', '0', 'N/A']):
            pick = min(1, len(lst))
            self.props.catalog_object.category_name = lst[pick][0]

        return super().invoke(context, event)


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
        lst_faces = mm.get_faces(mm.get_selection_info())
        for face in lst_faces:
            org = face[mm.key_uv_orig]
            break
        if org is not None:
            self.props.uv_origin = org
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
        lst_faces = mm.get_faces(mm.get_selection_info())
        for face in lst_faces:
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


class QARCH_OT_import_mesh(CustomOperator):
    """Turn edges into solids"""

    bl_idname = "qarch.import_mesh"
    bl_label = "Import Mesh"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=MeshImportProperty)

    function = import_mesh

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)

    def invoke(self, context, event):
        lst = enum_categories(self.props, context)
        if len(lst) and (self.props.catalog_object.category_name in ['', '0', 'N/A']):
            pick = min(1, len(lst))
            self.props.catalog_object.category_name = lst[pick][0]

        return super().invoke(context, event)

class QARCH_OT_flip_normal(CustomOperator):
    """Select by tags"""
    bl_idname = "qarch.flip_normal"
    bl_label = "Flip Normal"
    bl_description = "Flip face normals"
    bl_options = {"REGISTER", "UNDO"}

    function = flip_normals

    props: PointerProperty(type=FlipNormalProperty)

    @classmethod
    def poll(cls, context):
        return cls.is_face_selected(context)


class QARCH_OT_project_face(CustomOperator):
    """Select by tags"""
    bl_idname = "qarch.project_face"
    bl_label = "Project Face"
    bl_description = "Project face onto plane"
    bl_options = {"REGISTER", "UNDO"}

    function = project_face

    props: PointerProperty(type=ProjectFaceProperty)

    @classmethod
    def poll(cls, context):
        if cls.is_face_selected(context):
            mm = ManagedMesh(context.object)
            sel_info = mm.get_selection_info()
            return 2 == sel_info.count_faces()


class QARCH_OT_extrude_walls(CustomOperator):
    """Select by tags"""
    bl_idname = "qarch.extrude_walls"
    bl_label = "Wall Extrude"
    bl_description = "Make tagged walls have thickness"
    bl_options = {"REGISTER", "UNDO"}

    function = extrude_walls

    props: PointerProperty(type=FlipNormalProperty)



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
    QARCH_OT_flip_normal,
    QARCH_OT_project_face,
    QARCH_OT_extrude_walls
)