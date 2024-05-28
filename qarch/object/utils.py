"""Object utilities
Create new objects
Get/Set object data
"""
import bpy
import uuid
import json
import itertools

# custom layer names
FACE_CATEGORY = 'bt_face_cat'
FACE_THICKNESS = 'bt_face_thick'
FACE_UV_MODE = 'bt_uv_mode'
FACE_UV_ORIGIN = 'bt_uv_origin'
VERT_OP_ID = 'bt_op_id'
VERT_OP_SEQUENCE = 'bt_sequence'

# custom data field for object
BT_OBJ_DATA = 'bt_data'

# things stored in object data
ACTIVE_OP_ID = "op_id"  # used to force re-editing of old operation and replay of sequences
REPLAY_OP_ID = "replay_id"
JOURNAL_PROP_NAME = "journal_name"  # object custom property name


# these two functions are because json turns integer keys into strings
# we don't want to forget and get confused why 1 != "1"
def unwrap_id(op_str):
    return int(op_str[2:])


def wrap_id(op_id):
    return f'op{op_id}'


class SelectionInfo:
    """Hide details of selection from other code"""
    NORMAL = 0    # codes op for selection
    ALL_FACES = 1
    ALL_VERTS = 2

    def __init__(self, from_dict=None, other=None, copy_op=None):
        self.sel_face = {}
        self.op_flag = {}
        self.mode = 'SINGLE'

        if from_dict is not None:
            self.from_dict(from_dict)

        elif (other is not None) and (copy_op is not None):
            key = wrap_id(copy_op)
            self.sel_face[key] = other.sel_face.get(key, [])
            self.op_flag[key] = other.op_flag.get(key, self.NORMAL)

    def __repr__(self):
        return "SelectionInfo(" + str(self.to_dict()) + ")"

    def add_face(self, op_id, seq_list):
        key = wrap_id(op_id)
        if not key in self.sel_face:
            self.sel_face[key] = []
        self.sel_face[key].append(seq_list)

    def add_vert(self, op_id, seq_id):
        key = wrap_id(op_id)
        if not key in self.sel_face:
            self.sel_face[key] = []
        self.sel_face[key].append([seq_id])

    def count_faces(self):
        """Number of faces total"""
        c = 0
        for v in self.sel_face.values():
            for l in v:
                if len(l) >= 3:
                    c = c + 1
        return c

    def count_ops(self):
        """Number of operations"""
        return len(self.sel_face)

    def count_verts(self):
        """Number of verts not part of a face"""
        c = 0
        for v in self.sel_face.values():
            for l in v:
                if len(l) < 3:
                    c = c + 1
        return c

    def face_list(self, op_id):
        """List of lists, inner values are sequence id of the verts not bmesh index"""
        return self.sel_face.get(wrap_id(op_id), [])

    def flag_op(self, op_id, code):
        key = wrap_id(op_id)
        self.op_flag[key] = code | self.op_flag.get(key, 0)

    def from_dict(self, d):
        self.sel_face = d['faces']
        self.op_flag = d['flags']
        self.mode = d.get('mode', 'SINGLE')

    def get_flag(self, op_id):
        return self.op_flag.get(wrap_id(op_id), self.NORMAL)

    def get_mode(self):
        return self.mode

    def get_face_verts(self, mm):
        """Return verts sorted in lists by face
        expects a ManagedMesh object"""
        lst_bmv = []
        map_verts = {}
        for v in mm.bm.verts:
            if wrap_id(v[mm.key_op]) in self.sel_face:
                t = (v[mm.key_op], v[mm.key_seq])
                map_verts[t] = v

        for k, lst in self.sel_face.items():
            for slist in lst:
                lst = [map_verts[(unwrap_id(k), i)] for i in slist]
                lst_bmv.append(lst)
        return lst_bmv

    def includes(self, op_id, seq_id):
        for lst in self.sel_face[op_id]:
            for vlist in lst:
                if seq_id in vlist:
                    return True
        return False

    def matches(self, other):
        """Test if selection info is the same"""
        for k, v in self.sel_face.items():
            if not k in other.sel_face:
                return False
            v2 = other.sel_face[k]
            if len(v) != len(v2):
                return False
            for a, b in zip(v, v2):
                for i in a:
                    if i not in b:
                        return False
        return True

    def op_list(self):
        """List of controlling op ids"""
        lst = [unwrap_id(k) for k in self.sel_face.keys()]
        return lst

    def renumber_ops(self, dct_new):
        tmp = self.sel_face
        self.sel_face = {}
        for k, v in tmp.items():
            op_id = unwrap_id(k)
            self.sel_face[wrap_id(dct_new[op_id])] = v

        tmp = self.op_flag
        self.op_flag = {}
        for k, v in tmp.items():
            op_id = unwrap_id(k)
            self.op_flag[wrap_id(dct_new[op_id])] = v

    def set_mode(self, mode):
        self.mode = mode

    def to_dict(self):
        d = {'faces': self.sel_face, 'flags': self.op_flag, 'mode':self.mode}
        return d

    def vert_list(self):
        """Flat list of (op,sequence) with no repeats"""
        lst = []
        for k, vlists in self.sel_face.items():
            for v in vlists:
                tups = [(unwrap_id(k), i) for i in v if (unwrap_id(k), i) not in lst]
                lst = lst+tups

        return lst


def create_object(collection, name):
    """Create object and initialize layers, etc
    Return object
    """
    # hide import here to prevent load sequence conflicts
    from .journal import get_block, update_block, blank_journal

    # empty mesh object
    mesh = bpy.data.meshes.new(name)
    v = mesh.vertices.add(1)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)

    # create custom property on object
    obj[BT_OBJ_DATA] = "{}"

    # protect against name changes and collisions
    unique_str = str(uuid.uuid4())
    journal_name = f"{name}{unique_str}"
    set_obj_data(obj, JOURNAL_PROP_NAME, journal_name)

    # create the block
    update_block(get_block(obj), blank_journal())

    # no operation will match -1
    set_obj_data(obj, ACTIVE_OP_ID, -1)
    set_obj_data(obj, REPLAY_OP_ID, -1)

    # setup layers for mesh based data
    key = obj.data.attributes.new(FACE_CATEGORY, 'INT', 'FACE')
    key = obj.data.attributes.new(FACE_UV_MODE, 'INT', 'FACE')
    key = obj.data.attributes.new(FACE_THICKNESS, 'FLOAT', 'FACE')
    key = obj.data.attributes.new(FACE_UV_ORIGIN, 'FLOAT_VECTOR', 'FACE')

    key = obj.data.attributes.new(VERT_OP_ID, 'INT', 'POINT')
    attribute_values = [-1]
    key.data.foreach_set("value", attribute_values)
    key = obj.data.attributes.new(VERT_OP_SEQUENCE, 'INT', 'POINT')

    return obj


def get_obj_data(obj, field):
    """Return object data field, or None"""
    try:
        obj_dict = json.loads(obj[BT_OBJ_DATA])
    except KeyError:
        return None
    return obj_dict.get(field, None)


def set_obj_data(obj, field, data):
    """Store data in object data. Uses json to parse dictionary."""
    obj_dict = json.loads(obj[BT_OBJ_DATA])
    obj_dict[field] = data
    obj[BT_OBJ_DATA] = json.dumps(obj_dict)





