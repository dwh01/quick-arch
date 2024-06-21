"""Object utilities
Create new objects
Get/Set object data
"""
import bpy
import uuid
import json, math
import itertools, functools
from .materials import import_bt_materials

# custom layer names
FACE_CATEGORY = 'bt_face_cat'
FACE_THICKNESS = 'bt_face_thick'
FACE_UV_MODE = 'bt_uv_mode'
FACE_UV_ORIGIN = 'bt_uv_origin'
FACE_UV_ROTATE = 'bt_uv_rot'
FACE_OP_ID = 'bt_face_op'
FACE_OP_SEQUENCE = 'bt_face_seq'
VERT_OP_ID = 'bt_op_id'
VERT_OP_SEQUENCE = 'bt_sequence'
LOOP_UV_W = 'bt_uv_w'
UV_MAP = "UVMap"
BT_INST_PICK = 'bt_inst_pick'  # vertex data layer for instancer index
BT_INST_ROT = 'bt_inst_rot'    # vertex data layer for instancer rotation
BT_INST_SCALE = 'bt_inst_scale'  # vertex data layer for instancer scale

# custom data field for object
BT_OBJ_DATA = 'bt_data'

# things stored in object data
ACTIVE_OP_ID = "op_id"  # used to force re-editing of old operation and replay of sequences
REPLAY_OP_ID = "replay_id"
JOURNAL_PROP_NAME = "journal_name"  # object custom property name

BT_IMPORT_COLLECTION = "BT_Imported"  # collection for imported objects
BT_INST_COLLECTION = "_sources"  # append to object name to get instancer collection name


def is_bt_object(obj):
    return hasattr(obj, BT_OBJ_DATA)


def get_bt_collection():
    try:
        col = bpy.data.collections[BT_IMPORT_COLLECTION]
    except Exception:
        col = bpy.data.collections.new(BT_IMPORT_COLLECTION)
        bpy.data.collections['Collection'].children.link(col)
    col.hide_viewport = True
    return col

def get_instance_collection(obj):
    col_name = obj.name + BT_INST_COLLECTION
    try:
        col = bpy.data.collections[col_name]
    except Exception:
        col = bpy.data.collections.new(col_name)
        get_bt_collection().children.link(col)
    return col

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
        self.sel_vert = {}
        self.op_flag = {}
        self.mode = 'SINGLE'

        if from_dict is not None:
            self.from_dict(from_dict)

        elif (other is not None) and (copy_op is not None):
            key = wrap_id(copy_op)
            self.sel_face[key] = other.sel_face.get(key, [])
            self.sel_vert[key] = other.sel_vert.get(key, [])
            self.op_flag[key] = other.op_flag.get(key, self.NORMAL)

    def __repr__(self):
        return "SelectionInfo(" + str(self.to_dict()) + ")"

    def add_face(self, op_id, seq_id):
        key = wrap_id(op_id)
        if key not in self.sel_face:
            self.sel_face[key] = []
        self.sel_face[key].append(seq_id)

    def add_faces(self, op_id, face_list):
        key = wrap_id(op_id)
        if key not in self.sel_face:
            self.sel_face[key] = []
        self.sel_face[key] += face_list

    def add_vert(self, op_id, seq_id):
        key = wrap_id(op_id)
        if key not in self.sel_vert:
            self.sel_vert[key] = []
        self.sel_vert[key].append(seq_id)

    def count_faces(self):
        """Number of faces total"""
        c = 0
        for v in self.sel_face.values():
            c = c + len(v)
        return c

    def count_ops(self):
        """Number of operations"""
        return len(self.sel_face)

    def count_verts(self):
        """Number of verts not part of a face"""
        c = 0
        for v in self.sel_vert.values():
            c = c + len(v)
        return c

    def face_list(self, op_id):
        """List of face sequence not bmesh index"""
        return self.sel_face.get(wrap_id(op_id), [])

    def flag_op(self, op_id, code):
        key = wrap_id(op_id)
        self.op_flag[key] = code | self.op_flag.get(key, 0)

    def from_dict(self, d):
        self.sel_face = d['faces']
        self.sel_vert = d.get('verts', [])
        self.op_flag = d['flags']
        self.mode = d.get('mode', 'SINGLE')

    def get_flag(self, op_id):
        return self.op_flag.get(wrap_id(op_id), self.NORMAL)

    def get_mode(self):
        return self.mode

    def includes(self, op_id, face_seq_id):
        lst = self.sel_face[op_id]
        if face_seq_id in lst:
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
                if a != b:
                    return False
        return True

    def op_list(self):
        """List of controlling op ids"""
        lst = [unwrap_id(k) for k in self.sel_face.keys()]
        return lst

    def replace_sequence(self, op, face_list):
        self.sel_face[wrap_id(op)] = face_list

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
        d = {'faces': self.sel_face, 'verts':self.sel_vert, 'flags': self.op_flag, 'mode': self.mode}
        return d

    def vert_list(self, op_id):
        return self.sel_vert.get(wrap_id(op_id),[])


class TopologyInfo:
    def __init__(self, from_dict=None, from_keys=None, op_id=None):
        self.ranges = {}
        self.moduli = {}
        self.seq = 0
        if from_keys is not None:
            for k in from_keys:
                self.ranges[k] = []
                self.moduli[k] = 0
        elif from_dict is not None:
            self.from_dict(from_dict)

    def __str__(self):
        return str(self.to_dict())

    def json_compact(self, sort_keys):
        return json.dumps(self.to_dict(), sort_keys=sort_keys)

    @classmethod
    def blank_dict(cls):
        t = TopologyInfo()
        return t.to_dict()

    def add(self, k, n=1):
        if n < 1:
            return
        if len(self.ranges[k]):
            lst = self.ranges[k]
            lst.sort(key=lambda l:l[0])

            last_group = self.ranges[k][-1]
            last_group.sort()

            if self.seq == 1+last_group[-1]:
                last_group[-1] = self.seq + n-1
            else:
                self.ranges[k].append([self.seq, self.seq+n-1])
        else:
            self.ranges[k].append([self.seq, self.seq+n-1])
        self.seq = self.seq + n

    def count(self):
        max_val = -1
        for lst_range in self.ranges.values():
            limits = lst_range[-1]
            max_val = max(max_val, limits[1])
        return max_val + 1

    def from_dict(self, d):
        self.ranges = d['ranges']
        self.moduli = d['moduli']

    def get_range_sequence(self, key, f_range):
        range_list = self.ranges[key]
        if len(range_list)==0:
            return []
        n_range = round(len(range_list)*f_range)
        if n_range > len(range_list)-1:
            n_range = len(range_list)-1

        # print(n_range, "vs", int(math.floor(len(range_list) * f_range)))  # better to round then floor?

        limits = range_list[int(n_range)]
        return list(range(limits[0], limits[1]+1))

    def is_compatible(self, other):
        for k in self.ranges.keys():
            if k not in other.ranges:
                return False
        return True

    def is_same_as(self, other):
        for k, lst_range in self.ranges.items():
            if k not in other.ranges:
                return False
            if self.moduli.get(k,0) != other.moduli.get(k,0):
                return False
            if len(lst_range) != len(other.ranges[k]):
                return False
            for pair in zip(lst_range, other.ranges[k]):
                if (pair[0][0] != pair[1][0]) or (pair[0][1] != pair[1][1]):
                    return False

        return True

    def map_sequence(self, key, f_range, d_pos, f_pos):
        lst_range = self.ranges[key]
        if len(lst_range)==0:
            return None

        n_range = round(len(lst_range) * f_range)
        if n_range > len(lst_range)-1:
            n_range = len(lst_range)-1

        limits = lst_range[int(n_range)]
        span = limits[1]-limits[0]
        if d_pos is None:
            seq = round(span * f_pos) + limits[0]
        else:
            m = self.moduli[key]
            seq = d_pos * m + round(f_pos * m)
        if seq > limits[1]:
            seq = limits[1]

        return seq

    def set_modulus(self, key, m):
        self.moduli[key] = m

    def test_full_key(self, key, lst_seq):
        set_test = set(lst_seq)
        old_range_list = self.ranges[key]
        range_full = []
        for limits in old_range_list:
            b_full = True
            for i in range(limits[0], limits[1]+1):
                if i not in set_test:
                    b_full = False
                    break
            range_full.append(b_full)
        all_full = functools.reduce(lambda a,b: a and b, range_full, True)
        return all_full, range_full

    def to_dict(self):
        d = {'ranges': self.ranges, 'moduli': self.moduli}
        return d

    def address(self, face_seq):
        for key, range_list in self.ranges.items():
            for i, range_info in enumerate(range_list):
                min_seq = range_info[0]
                max_seq = range_info[1]
                if min_seq <= face_seq <= max_seq:
                    range_base = i / len(range_list)  # fractional position of range in key range list

                    if min_seq == max_seq:  # full set
                        addr = (key, range_base)
                    else:
                        m = self.moduli.get(key, 0)
                        if m == 0:
                            m = (max_seq - min_seq)

                        mod_rem = (face_seq - min_seq) % m
                        mod_div = int(math.floor((face_seq - min_seq) / m))

                        mod_base = mod_div / (max_seq - min_seq)  # fractional position of "row" in array
                        seq_base = mod_rem / m  # fractional position of column in row
                        addr = (key, range_base, mod_base, seq_base)
                        return addr
        return None

    def sequence(self, addr):
        if len(addr)==2:
            key, range_base = addr
            mod_base = 0
            seq_base = 0
        else:
            key, range_base, mod_base, seq_base = addr
        range_list = self.ranges[key]
        i = int(math.floor(range_base * len(range_list)))
        if i > len(range_list):
            print("above range count")
            return None
        range_info = range_list[i]
        min_seq = range_info[0]
        max_seq = range_info[1]
        m = self.moduli.get(key, 0)
        if m == 0:
            m = max(1, max_seq - min_seq)

        mod_div = mod_base * m
        mod_rem = seq_base * m

        row_start = mod_div * m + min_seq
        s = int(mod_rem + row_start)
        if min_seq <= s <= max_seq:
            return s
        print("not between", min_seq, s, max_seq)
        return None


    def warp_to(self, other, op_id, sel_info):
        """Convert face_list in current topology to values in other topology"""
        # for example, we select a set of faces (maybe frame from inset) and extrude with steps
        # we should be able to scale position based on which pillar we are in,
        # which row of the pillar, and which side of that row
        # assuming the extrusions are done sequentially on faces
        # we have numbering groups 1-n*m, where n is sides and m is steps
        # store n in the modulus number
        # keep the top faces in their own key since often top faces are used for other things
        old_face_seq = sel_info.face_list(op_id)
        new_face_seq = []

        for key in self.ranges:
            all_full, range_full = self.test_full_key(key, old_face_seq)
            for i, range_info in enumerate(self.ranges[key]):
                is_full = range_full[i]
                if is_full:
                    f_range = i/len(self.ranges[key])
                    lst = other.get_range_sequence(key, f_range)
                    new_face_seq.extend(lst)
                else:
                    for face_seq in range(range_info[0], range_info[1]+1):
                        if face_seq in old_face_seq:
                            addr = self.address(face_seq)
                            if addr is not None:
                                s = other.sequence(addr)
                                if s is not None:
                                    new_face_seq.append(s)

        print("before warp {} {}".format(op_id, old_face_seq))
        print("after warp {}".format(new_face_seq))
        sel_info.replace_sequence(op_id, new_face_seq)


def create_instancing_nodes(obj):
    col_name = obj.name + BT_INST_COLLECTION
    try:
        col_sources = bpy.data.collections[col_name]
    except Exception:
        col_sources = bpy.data.collections.new(col_name)
        collection = get_bt_collection()
        collection.children.link(col_sources)

    mod = obj.modifiers.new(name="Geometry Nodes", type='NODES')
    node_group = bpy.data.node_groups.new('GN_'+obj.name, 'GeometryNodeTree')
    mod.node_group = node_group

    inNode = node_group.nodes.new('NodeGroupInput')
    outNode = node_group.nodes.new('NodeGroupOutput')
    joinNode = node_group.nodes.new('GeometryNodeJoinGeometry')
    colNode = node_group.nodes.new('GeometryNodeCollectionInfo')
    pickNode = node_group.nodes.new('GeometryNodeInputNamedAttribute')
    pickNode.label = "Instance index"
    rotNode = node_group.nodes.new('GeometryNodeInputNamedAttribute')
    rotNode.label = "Instance rotation"
    scaleNode = node_group.nodes.new('GeometryNodeInputNamedAttribute')
    scaleNode.label = "Instance scale"
    instNode = node_group.nodes.new('GeometryNodeInstanceOnPoints')
    compareNode = node_group.nodes.new('FunctionNodeCompare')
    sepNode = node_group.nodes.new('GeometryNodeSeparateGeometry')


    instNode.inputs['Pick Instance'].default_value = True

    colNode.inputs['Separate Children'].default_value = True
    colNode.inputs['Collection'].default_value = col_sources

    pickNode.data_type = 'INT'
    pickNode.inputs['Name'].default_value = BT_INST_PICK

    rotNode.data_type = 'FLOAT_VECTOR'
    rotNode.inputs['Name'].default_value = BT_INST_ROT

    scaleNode.data_type = 'FLOAT_VECTOR'
    scaleNode.inputs['Name'].default_value = BT_INST_SCALE

    compareNode.data_type = 'INT'
    compareNode.operation = 'EQUAL'
    compareNode.inputs['B'].default_value = -1

    sepNode.domain = 'POINT'

    node_group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    node_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    node_group.links.new(inNode.outputs['Geometry'], joinNode.inputs['Geometry'])
    node_group.links.new(joinNode.outputs['Geometry'], outNode.inputs['Geometry'])

    node_group.links.new(inNode.outputs['Geometry'], sepNode.inputs['Geometry'])
    node_group.links.new(sepNode.outputs['Inverted'], instNode.inputs['Points'])
    node_group.links.new(instNode.outputs['Instances'], joinNode.inputs['Geometry'])

    node_group.links.new(colNode.outputs['Instances'], instNode.inputs['Instance'])
    node_group.links.new(pickNode.outputs[4], instNode.inputs['Instance Index'])
    node_group.links.new(rotNode.outputs['Attribute'], instNode.inputs['Rotation'])
    node_group.links.new(scaleNode.outputs[0], instNode.inputs['Scale'])

    node_group.links.new(pickNode.outputs['Attribute'], compareNode.inputs['A'])
    node_group.links.new(compareNode.outputs['Result'], sepNode.inputs['Selection'])


    w = inNode.width * 1.25
    h = colNode.height * 1.25
    inNode.location = (-3 * w, 0)
    colNode.location = (-2 * w, 2 * h)
    pickNode.location = (-2 * w, 1 * h)
    rotNode.location = (-2 * w, -1 * h)
    scaleNode.location = (-2 * w, -2 * h)
    compareNode.location = (-1 * w, -2 * h)
    sepNode.location = (0 * w, -2 * h)
    instNode.location = (1 * w, -0.5 * h)
    joinNode.location = (2 * w, 0)
    outNode.location = (3 * w, 0)


def create_object(collection, name):
    """Create object and initialize layers, etc
    Return object
    """
    # hide import here to prevent load sequence conflicts
    from .journal import get_block, update_block, blank_journal
    from .materials import tag_to_material
    from ..ops import dynamic_enums

    import_bt_materials()  # only imports if the materials aren't here

    # empty mesh object
    mesh = bpy.data.meshes.new(name)
    uv = mesh.uv_layers.new(name='UVMap')
    v = mesh.vertices.add(1)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)

    # create custom property on object
    upgrade_object(obj)

    return obj


def upgrade_object(obj):
    """Add data to make an external object into one bt can handle"""
    from .journal import get_block, update_block, blank_journal
    from .materials import tag_to_material
    from ..ops import dynamic_enums
    from ..mesh import ManagedMesh

    import_bt_materials()  # only import

    # create custom property on object
    obj[BT_OBJ_DATA] = "{}"

    # protect against name changes and collisions
    unique_str = str(uuid.uuid4())
    journal_name = "{}{}".format(obj.name,unique_str)
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
    key = obj.data.attributes.new(FACE_UV_ROTATE, 'FLOAT_VECTOR', 'FACE')
    key = obj.data.attributes.new(FACE_OP_SEQUENCE, 'INT', 'FACE')
    key = obj.data.attributes.new(FACE_OP_ID, 'INT', 'FACE')
    key = obj.data.attributes.new(LOOP_UV_W, 'FLOAT', 'CORNER')

    attribute_values = [-1]
    key = obj.data.attributes.new(VERT_OP_ID, 'INT', 'POINT')
    key.data.foreach_set("value", attribute_values)
    key = obj.data.attributes.new(BT_INST_PICK, 'INT', 'POINT')
    key.data.foreach_set("value", attribute_values)

    key = obj.data.attributes.new(VERT_OP_SEQUENCE, 'INT', 'POINT')
    key = obj.data.attributes.new(BT_INST_ROT, 'FLOAT_VECTOR', 'POINT')
    key = obj.data.attributes.new(BT_INST_SCALE, 'FLOAT_VECTOR', 'POINT')

    # default materials for visualization
    lst = dynamic_enums.lst_FaceEnums
    for i in range(1, len(lst)):
        tag = lst[i][0]
        matname = tag_to_material(tag)
        obj.data.materials.append(bpy.data.materials[matname])

    # instancer
    create_instancing_nodes(obj)
    if len(obj.data.polygons):  # almost everything can default to 0, but we need to identify faces
        mm = ManagedMesh(obj)
        for face in mm.bm.faces:
            face[mm.key_face_seq] = face.index
        for vert in mm.bm.verts:
            vert[mm.key_seq] = vert.index
        mm.to_mesh()
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





