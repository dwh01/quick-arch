import bpy
import bmesh
import mathutils
import struct
from contextlib import contextmanager
from ..object import VERT_OP_ID, VERT_OP_SEQUENCE
from collections import defaultdict

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
    OPID, OPSEQ = 0, 1  # order in sel_info pairs

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

        # tracking as we add
        self.cur_seq = 0
        self.existing = {}

    def set_op(self, op_id):
        self.op_id = op_id
        self.cur_seq = 0
        self.existing = {}
        for v in self.bm.verts:
            if op_id == v[self.key_op]:
                self.existing[v[self.key_seq]] = v

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

    def delete_face(self, face):
        try:
            bmesh.ops.delete(self.bm, geom=[face], context='FACES_ONLY')
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
        if self.bm is None:
            return [(-1, [])]
        lst_sel_info = []
        for f in self.bm.faces:
            if f.select:
                sel_seq = [v[self.key_seq] for v in f.verts]
                sel_op = f.verts[0][self.key_op]
                lst_sel_info.append([sel_op, sel_seq])
        if len(lst_sel_info) == 0:
            sel_seq = []
            sel_op = -1
            for v in self.bm.verts:
                if v.select:
                    sel_op = v[self.key_op]
                    sel_seq.append(v[self.key_seq])
            lst_sel_info.append([sel_op, sel_seq])
        return lst_sel_info

    def _sel_info_to_test(self, lst_sel_info):
        test = defaultdict(list)
        for inf in lst_sel_info:
            lst = test[inf[self.OPID]]
            lst = lst + inf[self.OPSEQ]
            test[inf[self.OPID]] = lst

        # use sets to avoid duplicates
        dct_sets = {}
        for op_id, lst_seq in test.items():
            dct_sets[op_id] = set(lst_seq)

        return dct_sets

    def get_sel_verts(self, sel_op_seq):
        if self.bm is None:
            return []

        dct_sets = self._sel_info_to_test(sel_op_seq)

        dct_found = {}
        for v in self.bm.verts:
            if v[self.key_op] in dct_sets:
                if v[self.key_seq] in dct_sets[v[self.key_op]]:
                    dct_found[(v[self.key_op], v[self.key_seq])] = v

        rval = []
        for op, lst in sel_op_seq:
            cur = []
            for i in lst:
                if (op,i) in dct_found:
                    cur.append(dct_found[(op,i)])
            rval.append(cur)

        return rval

    def set_selection_info(self, sel_op_seq):
        if self.bm is None:
            return

        self.deselect_all()
        # identify by just operation and sequence
        # use set for quick hash lookup
        dct_sets = self._sel_info_to_test(sel_op_seq)

        for v in self.bm.verts:
            if v[self.key_op] in dct_sets:
                if v[self.key_seq] in dct_sets[v[self.key_op]]:
                    v.select_set(True)

        self.bm.select_flush(True)

    def select_operation(self, op_id):
        if self.bm is None:
            return
        for v in self.bm.verts:
            inf = v[self.key_op]
            if inf == op_id:
                v.select_set(True)
        self.bm.select_flush(True)

    def select_current(self):
        """Select current operation verts"""
        self.select_operation(self.op_id)

    def new_vert(self, v):
        if self.cur_seq in self.existing:
            bmv = self.existing[self.cur_seq]
            bmv.co = v
        else:
            bmv = self.bm.verts.new(v)
        bmv[self.key_op] = self.op_id
        bmv[self.key_seq] = self.cur_seq
        self.cur_seq += 1
        return bmv

    def new_face(self, vlist):
        face = self.find_face_by_bmvert(vlist)
        if face is None:
            face = self.bm.faces.new(vlist)
        return face