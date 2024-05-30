import bpy
import bmesh
import mathutils
import struct
from contextlib import contextmanager
from ..object import VERT_OP_ID, VERT_OP_SEQUENCE
from ..object import FACE_THICKNESS, FACE_CATEGORY, FACE_UV_MODE, FACE_UV_ORIGIN, FACE_OP_ID, FACE_OP_SEQUENCE
from ..object import SelectionInfo

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

        else:
            self.key_op = None
            self.key_seq = None
            self.key_tag = None
            self.key_thick = None
            self.key_uv = None
            self.key_uv_orig = None
            self.key_face_seq = None
            self.key_face_op = None

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

    def cube(self, x, y, z):
        mat = mathutils.Matrix.Identity(4)
        mat[0][0] = x
        mat[1][1] = y
        mat[2][2] = z
        res = bmesh.ops.create_cube(self.bm, size=1, matrix=mat, calc_uvs=False)
        for bmv in res['verts']:
            bmv[self.key_op] = self.op_id
            bmv[self.key_seq] = self.cur_seq
            self.cur_seq += 1
        return res['verts']

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
        return self.find_face_by_bmvert(vlist)

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

    def get_faces(self, sel_info):
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

    def new_vert(self, v):
        if self.cur_seq in self.existing:
            bmv = self.existing[self.cur_seq]
            bmv.co = v
            # print("existing vert at {} {}".format(self.cur_seq, v))
        else:
            bmv = self.bm.verts.new(v)
            bmv[self.key_op] = self.op_id
            bmv[self.key_seq] = self.cur_seq
        self.cur_seq += 1

        return bmv

    def new_face(self, vlist, uv_origin=None, uv_mode=None):
        from ..ops import uv_mode_to_int
        cat = 0
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
                    cat = face[self.key_tag]
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
                print("new face cur={}, exist={}".format(self.cur_face_seq, self.existing_face))
                print("face found by bmvert?")

        if cat==-1:
            print("face {} {} cat {}".format(face[self.key_face_op], face[self.key_face_seq], cat))
        face[self.key_tag] = cat
        # if face[self.key_tag] == -1:  # was deleted, maybe that op was erased and we are rebuilding
        #    face[self.key_tag] = 0  # otherwise, replay will set this back to -1 with a delete request

        if uv_origin is not None:
            face[self.key_uv_orig] = uv_origin
        if uv_mode is not None:
            uv_int = uv_mode_to_int(uv_mode)
            face[self.key_uv] = uv_int

        self.cur_face_seq += 1
        return face

    def vert_list(self, sel_info):
        """Flat list of free verts with no repeats"""
        lst = []

        for vert in self.bm.verts:
            op = vert[self.key_op]
            seq = vert[self.key_seq]
            if seq in sel_info.vert_list(op):
                lst.append(vert)

        return lst
