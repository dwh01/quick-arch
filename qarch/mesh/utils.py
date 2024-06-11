import bpy
import bmesh
import mathutils
import struct
from contextlib import contextmanager
from ..object import VERT_OP_ID, VERT_OP_SEQUENCE, BT_INST_PICK, BT_INST_SCALE, BT_INST_ROT
from ..object import FACE_THICKNESS, FACE_CATEGORY, FACE_UV_MODE, FACE_UV_ORIGIN, FACE_OP_ID, FACE_OP_SEQUENCE, FACE_UV_ROTATE
from ..object import SelectionInfo, LOOP_UV_W

from collections import defaultdict
import itertools

@contextmanager
def managed_bm(obj):
    is_edit = False
    if bpy.context.mode == 'EDIT_MESH':
        is_edit = True
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)

    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    try:
        yield bm
    finally:
        if is_edit:
            bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        else:
            bm.to_mesh(obj.data)
    bm.free()


class ManagedMesh:
    """Wraps bmesh with utility functions"""

    def __init__(self, obj):
        self.obj = obj
        self.op_id = None

        self.is_edit = False
        if bpy.context.mode == 'EDIT_MESH':
            self.is_edit = True
            try:
                self.bm = bmesh.from_edit_mesh(obj.data)
            except AttributeError:
                self.bm = None
        else:
            self.bm = bmesh.new()
            self.bm.from_mesh(obj.data)

        if self.bm:
            self.bm.faces.ensure_lookup_table()
            self.bm.verts.ensure_lookup_table()

            self.key_op = self.bm.verts.layers.int[VERT_OP_ID]
            self.key_seq = self.bm.verts.layers.int[VERT_OP_SEQUENCE]
            self.key_tag = self.bm.faces.layers.int[FACE_CATEGORY]
            self.key_thick = self.bm.faces.layers.float[FACE_THICKNESS]
            self.key_uv = self.bm.faces.layers.int[FACE_UV_MODE]
            self.key_uv_orig = self.bm.faces.layers.float_vector[FACE_UV_ORIGIN]
            self.key_face_seq = self.bm.faces.layers.int[FACE_OP_SEQUENCE]
            self.key_face_op = self.bm.faces.layers.int[FACE_OP_ID]
            self.key_uv_w = self.bm.loops.layers.float[LOOP_UV_W]
            self.key_uv_rot = self.bm.faces.layers.float_vector[FACE_UV_ROTATE]
            self.key_pick = self.bm.verts.layers.int[BT_INST_PICK]
            self.key_inst_rot = self.bm.verts.layers.float_vector[BT_INST_ROT]
            self.key_inst_scale = self.bm.verts.layers.float_vector[BT_INST_SCALE]

        else:
            self.key_op = None
            self.key_seq = None
            self.key_tag = None
            self.key_thick = None
            self.key_uv = None
            self.key_uv_orig = None
            self.key_face_seq = None
            self.key_face_op = None
            self.key_uv_w = None
            self.key_uv_rot = None
            self.key_pick = None
            self.key_inst_rot = None
            self.key_inst_scale = None

            # tracking as we add
        self.cur_seq = 0
        self.existing = {}
        self.cur_face_seq = 0
        self.existing_face = {}

    def set_op(self, op_id):
        self.op_id = op_id
        self.cur_seq = 0
        self.existing = {}
        for v in self.bm.verts:
            if op_id == v[self.key_op]:
                self.existing[v[self.key_seq]] = v
        for f in self.bm.faces:
            if op_id == f[self.key_face_op]:
                self.existing_face[f[self.key_face_seq]] = f

    def free(self):
        if self.bm:
            self.bm.free()
        self.bm = None

    def to_mesh(self):
        if self.bm is None:
            return
        if self.is_edit:
            bmesh.update_edit_mesh(self.obj.data, loop_triangles=True)
        else:
            self.bm.to_mesh(self.obj.data)

    def cleanup(self):
        lst_del = [
            face for face in self.bm.faces if face[self.key_tag]==-1
        ]
        print("deleting {} faces".format(len(lst_del)))
        bmesh.ops.delete(self.bm, geom=lst_del, context="FACES_ONLY")
        print("creating wall thickness")
        self.create_wall_thickness()


    def cube(self, x, y, z, tag=None):
        verts = [(0,0,0),(0,y,0),(x,y,0),(x,0,0),
                 (0,0,z),(x,0,z),(x,y,z),(0,y,z)]
        verts = [mathutils.Vector(v) - mathutils.Vector((x/2,y/2,z/2)) for v in verts]
        flist = [(0,1,2,3),(4,5,6,7),(0,3,5,4),(1,0,4,7),(2,1,7,6),(3,2,6,5)]
        mat = mathutils.Matrix.Identity(4)
        bm_verts = [self.new_vert(v) for v in verts]
        faces = []
        for f in flist:
            vlist = [bm_verts[i] for i in f]
            face = self.new_face(vlist, tag=tag)
            faces.append(face)
        return bm_verts, faces

    def delete_all(self):
        """Clear mesh"""
        bmesh.ops.delete(self.bm, geom=list(self.bm.verts), context='VERTS')

    def delete_current_verts(self):
        """Delete verts matching current operation"""
        if self.bm is None:
            return

        if self.op_id is None:
            return

        lst_del = [v for v in self.bm.verts if v[self.key_op] == self.op_id]
        bmesh.ops.delete(self.bm, geom=lst_del, context='VERTS')

        self.cur_seq = 0
        self.existing = {}

    def delete_face(self, face):
        try:
            face.hide = True
            face[self.key_tag] = -1  # delete tag, just in case user un-hides by accident
        except Exception:
            pass

    def deselect_all(self):
        if self.bm is None:
            return
        for face in self.bm.faces:
            face.select_set(False)
        for vert in self.bm.verts:
            vert.select_set(False)
        self.bm.select_flush(False)

    def find_face_by_bmvert(self, vlist):
        if len(vlist) < 3:
            return None
        face = None

        for test_face in vlist[0].link_faces:
            b_found = True
            b_order = True
            for i, v in enumerate(test_face.verts):
                if v not in vlist:
                    b_found = False
                    break
                if v is not vlist[i]:
                    b_order = False
            if b_found:
                if b_order:
                    face = test_face
                    break
        return face

    def find_face_by_smart_vec(self, sv_list):
        vlist = [sv.bm_vert for sv in sv_list]
        if len(vlist) < 3:
            return None

        if vlist[0] is None:
            vlist = [sv.co3 for sv in sv_list]
            return self.find_face_by_vectors(vlist)
        else:
            return self.find_face_by_bmvert(vlist)

    def find_face_by_vectors(self, vlist):
        def t_func(v):
            return round(v.x, 6), round(v.y, 6), round(v.z, 6)

        check_list = [t_func(v) for v in vlist]
        for face in self.bm.faces:
            if len(face.verts) != len(check_list):
                continue
            b_ok = True
            test_list = [t_func(v.co) for v in face.verts]
            for a, b in zip(check_list, test_list):
                if a != b:
                    b_ok = False
                    break
            if b_ok:
                return face
        return None

    def get_selection_info(self):
        """Return current selected vert info"""
        sel_info = SelectionInfo()
        if self.bm is None:
            return SelectionInfo()

        set_verts_in_faces = set()
        self.bm.verts.ensure_lookup_table()

        dct_skip = {}
        for f in self.bm.faces:
            sel_op = f[self.key_face_op]
            if f.select:
                sel_info.add_face(sel_op, f[self.key_face_seq])
                for v in f.verts:
                    set_verts_in_faces.add(v.index)
            else:
                dct_skip[sel_op] = True

        for op in sel_info.op_list():
            if op not in dct_skip:
                sel_info.flag_op(op, sel_info.ALL_FACES)

        lst_flat = self.get_face_verts_flat(sel_info)
        lst_flat = set(lst_flat)
        dct_skip = {}
        for v in self.bm.verts:
            if v.index in set_verts_in_faces:
                continue

            sel_op = v[self.key_op]
            if v.select:
                sel_info.add_vert(sel_op, v[self.key_seq])
            else:
                dct_skip[sel_op] = True

        for op in sel_info.op_list():
            if op not in dct_skip:
                sel_info.flag_op(op, sel_info.ALL_VERTS)

        return sel_info

    def get_face_attrs(self, face):
        from ..ops.properties import int_to_face_tag, int_to_uv_mode
        dct = {}
        dct[self.key_tag] = int_to_face_tag(face[self.key_tag])
        dct[self.key_thick] = face[self.key_thick]
        dct[self.key_uv_rot] = face[self.key_uv_rot]
        dct[self.key_uv_orig] = face[self.key_uv_orig]
        dct[self.key_uv] = int_to_uv_mode(face[self.key_uv])

        return dct

    def get_faces(self, sel_info):
        """Return selected bmfaces"""
        lst_face = []
        for face in self.bm.faces:
            op = face[self.key_face_op]
            seq = face[self.key_face_seq]
            if seq in sel_info.face_list(op):
                lst_face.append(face)
        return lst_face

    def get_face_verts(self, sel_info):
        """Return verts sorted in lists by face
        expects a ManagedMesh object"""
        lst_bmv = []
        for face in self.bm.faces:
            op = face[self.key_face_op]
            seq = face[self.key_face_seq]
            if seq in sel_info.face_list(op):
                vlist= [v for v in face.verts]
                lst_bmv.append(vlist)
        return lst_bmv

    def get_face_verts_flat(self, sel_info):
        lst_bmv = []
        for face in self.bm.faces:
            op = face[self.key_face_op]
            seq = face[self.key_face_seq]
            if seq in sel_info.face_list(op):
                for v in face.verts:
                    if v not in lst_bmv:
                        lst_bmv.append(v)
        return lst_bmv

    def get_free_verts(self, sel_info):
        lst_bmv = []
        for v in self.bm.verts:
            op = v[self.key_op]
            sel = sel_info.vert_list(op)
            if v[self.key_seq] in sel:
                lst_bmv.append(v)
        return lst_bmv

    def rehide(self):
        """Hide faces marked for deletion"""
        for face in self.bm.faces:
            cat = face[self.key_tag]
            if cat == -1:
                face.hide = True

    def set_face_attrs(self, face, dct):
        from ..ops.properties import face_tag_to_int, uv_mode_to_int

        for key, value in dct.items():
            if isinstance(value, str):
                if key == self.key_uv:
                    value = uv_mode_to_int(value)
                elif key == self.key_tag:
                    value = face_tag_to_int(value)

            face[key] = value
            if key == self.key_tag:
                if -1 < value < len(self.obj.data.materials):
                    face.material_index = value

    def set_facesel_attr(self, sel_info, key, value):
        faces = self.get_faces(sel_info)
        for face in faces:
            if face.is_valid:
                self.set_face_attrs(face, {key: value})


    def set_selection_info(self, sel_info):
        """Make selection state match sel_info"""
        if self.bm is None:
            return

        self.deselect_all()

        for face in self.bm.faces:
            op = face[self.key_face_op]
            sel = sel_info.face_list(op)
            if face[self.key_face_seq] in sel:
                face.hide = False
                face.select_set(True)

        self.bm.select_flush(True)

        vlist = self.get_free_verts(sel_info)
        for v in vlist:
            v.select_set(True)

    def select_operation(self, op_id):
        """Select all verts for operation, does not deselect first"""
        if self.bm is None:
            return
        for v in self.bm.verts:
            inf = v[self.key_op]
            if inf == op_id:
                v.select_set(True)
        self.bm.select_flush(True)

    def get_current(self):
        """Returns bmverts for current op_id"""
        lst_cur = []
        for v in self.bm.verts:
            if self.op_id == v[self.key_op]:
                lst_cur.append(v)
        return lst_cur

    def select_current(self):
        """Select current operation verts, deselects others"""
        self.deselect_all()
        self.select_operation(self.op_id)

    def instance_on_vert(self, bmv, pick, rot, scale):
        bmv[self.key_pick] = pick
        bmv[self.key_inst_rot] = rot
        bmv[self.key_inst_scale] = scale

    def new_vert(self, v):
        if self.cur_seq in self.existing:
            bmv = self.existing[self.cur_seq]
            bmv.co = v
            # print("existing vert at {} {}".format(self.cur_seq, v))
        else:
            bmv = self.bm.verts.new(v)
            bmv[self.key_op] = self.op_id
            bmv[self.key_seq] = self.cur_seq
        bmv[self.key_pick] = -1  # turn off instancing
        self.cur_seq += 1

        return bmv

    def new_face(self, vlist, uv_origin=None, uv_mode=None, thickness=None, tag="NOTHING"):
        from ..ops import uv_mode_to_int, face_tag_to_int

        face = None
        if self.cur_face_seq in self.existing_face:
            face = self.existing_face[self.cur_face_seq]
            if not face.is_valid:
                face = None
            else:
                # no access to change verts, delete and remake if needed
                old_vlist = [v for v in face.verts]
                match = True
                for a, b in zip(old_vlist, vlist):
                    if a is not b:
                        match = False
                        break
                if not match:
                    del self.existing_face[self.cur_face_seq]
                    print("true delete face {} {}".format(face[self.key_face_op], face[self.key_face_seq]))
                    bmesh.ops.delete(self.bm, geom=[face], context='FACES_ONLY')
                    face = None

        if face is None:
            face = self.find_face_by_bmvert(vlist)
            if face is None:
                face = self.bm.faces.new(vlist)
                self.existing_face[self.cur_face_seq] = face
                face[self.key_face_op] = self.op_id
                face[self.key_face_seq] = self.cur_face_seq
            else:
                #print("new face cur={}, exist={}".format(self.cur_face_seq, self.existing_face))
                print("face found by bmvert?")

        if tag is not None:
            tag = face_tag_to_int(tag)
            face[self.key_tag] = tag
            if -1 < tag < len(self.obj.data.materials):
                face.material_index = tag

        if uv_origin is not None:
            face[self.key_uv_orig] = uv_origin
        if uv_mode is not None:
            uv_int = uv_mode_to_int(uv_mode)
            face[self.key_uv] = uv_int
        if thickness is not None:
            face[self.key_thick] = thickness

        self.cur_face_seq += 1
        return face

    def thick_faces(self, sel_info):
        sel_faces = self.get_faces(sel_info)
        if len(sel_faces)==0:
            sel_faces = self.bm.faces

        lst_thick = []
        for face in sel_faces:
            if face[self.key_thick] != 0:
                lst_thick.append(face)
        return lst_thick

    def vert_list(self, sel_info):
        """Flat list of free verts with no repeats"""
        lst = []

        for vert in self.bm.verts:
            op = vert[self.key_op]
            seq = vert[self.key_seq]
            if seq in sel_info.vert_list(op):
                lst.append(vert)

        return lst