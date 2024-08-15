"""History Journal
Routines to get/set the history dictionary associated with an object
and to import/export chunks of the history
"""
import bpy
import json
import copy
import pathlib
from collections import defaultdict

from .utils import get_obj_data, JOURNAL_PROP_NAME, SelectionInfo, wrap_id, unwrap_id, TopologyInfo

#  https://stackoverflow.com/questions/13249415/how-to-implement-custom-indentation-when-pretty-printing-with-the-json-module
#  with updates to allow a user class to be its own wrapper
from _ctypes import PyObj_FromPtr
import re

class NoIndent(object):
    """ Value wrapper. """
    def __init__(self, value):
        self.value = value

    def json_compact(self, sort_keys):
        return json.dumps(self.value, sort_keys=sort_keys)


class MyEncoder(json.JSONEncoder):
    FORMAT_SPEC = '@@{}@@'
    regex = re.compile(FORMAT_SPEC.format(r'(\d+)'))

    def __init__(self, **kwargs):
        # Save copy of any keyword argument values needed for use here.
        self.__sort_keys = kwargs.get('sort_keys', None)
        super(MyEncoder, self).__init__(**kwargs)

    def default(self, obj):
        compact = hasattr(obj, 'json_compact')
        return (self.FORMAT_SPEC.format(id(obj)) if compact
                else super(MyEncoder, self).default(obj))

    def encode(self, obj):
        format_spec = self.FORMAT_SPEC  # Local var to expedite access.
        json_repr = super(MyEncoder, self).encode(obj)  # Default JSON.

        # Replace any marked-up object ids in the JSON repr with the
        # value returned from the json.dumps() of the corresponding
        # wrapped Python object.
        for match in self.regex.finditer(json_repr):
            # see https://stackoverflow.com/a/15012814/355230
            id = int(match.group(1))
            no_indent = PyObj_FromPtr(id)
            json_obj_repr = no_indent.json_compact(self.__sort_keys)
            # Replace the matched id string with json formatted representation
            # of the corresponding Python object.
            json_repr = json_repr.replace(
                            '"{}"'.format(format_spec.format(id)), json_obj_repr)

        return json_repr

def object_hook(d):
    from .utils import TopologyInfo
    if isinstance(d, dict):
        dkeys = set(d.keys())
        t = TopologyInfo.blank_dict()
        tkeys = set(t.keys())

        if len(dkeys)==len(tkeys):
            if len(dkeys.difference(tkeys))==0:
                topo = TopologyInfo()
                topo.from_dict(d)
                return topo
    return d


class Journal:
    """Encapsulate the history function"""
    def __init__(self, obj):
        self.obj = obj
        self.jj = get_journal(obj)
        self.controlled = self.jj['controlled']

    def __getitem__(self, item):
        if isinstance(item, int):
            key = wrap_id(item)
        elif isinstance(item, str):
            key = item
        else:
            raise TypeError("Expected int or str")

        return self.jj[key]

    def __setitem__(self, key, value):
        if isinstance(key, int):
            key = wrap_id(key)
        elif isinstance(key, str):
            pass
        else:
            raise TypeError("Expected int")
        self.jj[key] = value

    def ancestors(self, op_id):
        """Get chain of operations leading to this one"""
        if op_id > -1:
            inf = self.get_sel_info(op_id)
            parents = inf.op_list()
            if len(parents) == 0:
                parents = [-1]
            lst = []
            for p_id in parents:
                cur_ancestors = self.ancestors(p_id)
                # avoid duplicates
                for a_id in cur_ancestors:
                    if a_id not in lst:
                        lst.append(a_id)
        else:
            lst = []
        lst.append(op_id)
        return lst

    def child_ops(self, op_id):
        """Tree or list of child operations"""
        dct = {}
        lst = []
        for c_id in self.controlled[wrap_id(op_id)]:
            c_dict, c_list = self.child_ops(c_id)
            dct[c_id] = c_dict
            lst.append(c_id)
            lst = lst + c_list
        return dct, lst

    def controlled_list(self, op_id):
        """Get list of child ops controlled by this one"""
        lst = self.controlled.get(wrap_id(op_id), [])
        # strip out duplicates
        lst2 = []
        for op in lst:
            if op not in lst2:
                lst2.append(op)
        return lst2

    def delete_record(self, operation_id, flush=True):
        parents = self.parents(operation_id)

        dct_children, lst_children = self.child_ops(operation_id)
        lst_children.insert(0, operation_id)

        lst_children.reverse()  # doesn't matter, but remove lowest level first
        for op_id in lst_children:
            # test for existence because ops with multiple parents can lead to double attempt to delete
            if wrap_id(op_id) in self.jj['controlled']:
                del self.jj['controlled'][wrap_id(op_id)]
            if wrap_id(op_id) in self.jj:
                del self.jj[wrap_id(op_id)]

        for parent_id in parents:
            lst = self['controlled'][wrap_id(parent_id)]
            lst.remove(operation_id)

        # remove trailing count if we deleted the last operations
        # op_max = self.jj['max_id']
        # while wrap_id(op_max) not in self.jj:
        #     op_max = op_max - 1
        # self.jj['max_id'] = op_max
        self.jj = compact(self.jj)

        if flush:
            self.flush()
        return lst_children

    def describe(self, op_id):
        record = self.jj[wrap_id(op_id)]
        t = record.get('description', '')
        return t

    def set_description(self, txt):
        self.jj['description'] = txt

    def flush(self):
        """Save changes to text block"""
        set_journal(self.obj, self.jj)

    def get_operator(self, op_id):
        record = self.jj[wrap_id(op_id)]
        assert "QARCH_OT_" == record['op_name'][:9], "unknown operator"
        opname = record['op_name'][9:]
        op = getattr(getattr(bpy.ops, "qarch"), opname)
        return op

    def get_sel_info(self, op_id):
        record = self[op_id]
        inf = SelectionInfo(record['control_points'])
        return inf

    def make_op_tree(self, start_ops):
        """Tree of common ancestors to start_ops"""
        dct_ops = defaultdict(list)
        for op_start in start_ops:
            lst_ancestor = self.ancestors(op_start)
            # force roots to appear even if this is the only op in the list
            dct_ops[lst_ancestor[0]] = []
            for i in range(1, len(lst_ancestor)):
                p_id = lst_ancestor[i - 1]
                c_id = lst_ancestor[i]
                dct_ops[p_id].append(c_id)

            lst_child = self.controlled_list(op_start)
            for c_id in lst_child:
                if "QARCH_OT_set" in self.jj[wrap_id(c_id)]['op_name']:
                    dct_ops[op_start].append(c_id)
                    # have to include children with no faces
                    # you can never click on set_tag operation, for instance
        return dct_ops

    def new_record(self, sel_info, op_name):
        rec = blank_record()

        new_id = self.jj['max_id'] + 1
        rec['op_id'] = new_id
        rec['op_name'] = op_name
        rec['control_points'] = sel_info.to_dict()

        self.jj['max_id'] = new_id
        self.jj[wrap_id(new_id)] = rec

        # update control dictionary
        c_dict = self.jj['controlled']
        op_list = sel_info.op_list()
        if len(op_list) == 0:
            op_list = [-1]
        for control_op in op_list:
            c_key = wrap_id(control_op)
            if c_key not in c_dict:
                c_dict[c_key] = []
            c_dict[c_key].append(new_id)
        c_dict[wrap_id(new_id)] = []

        return rec

    def op_name(self, op_id):
        record = self.jj[wrap_id(op_id)]
        opname = record['op_name'][9:]
        return opname

    def op_label(self, op_id):
        # retrieve friendly label for operator
        record = self.jj[wrap_id(op_id)]
        opname = record['op_name']
        op = getattr(bpy.types, opname)
        return op.bl_label

        # this seems to be a bpy_struct
        # useful info?
        #  "class _BPyOpsSubModOp" has
        #  idname()->..OT_.., get_rna_type(), _func (string function name)
        #  and in module rna_info.py there is a utility get_py_class_from_rna(rna_type)

        # print(op.bl_rna)
        # print(op.bl_rna_get_subclass()) -- requires a type argument
        # print(op.bl_rna_get_subclass_py())

    def operator(self, op_id):
        record = self.jj[wrap_id(op_id)]
        opname = record['op_name']
        op = getattr(bpy.types, opname)
        return op

    def parents(self, op_id):
        """Get controlling operations leading to this one"""
        if op_id > -1:
            inf = self.get_sel_info(op_id)
            parents = inf.op_list()
        else:
            parents = []
        return parents

    def set_sel_info(self, op_id, inf):
        record = self[op_id]
        record['control_points'] = inf.to_dict()


def blank_journal():
    """Return start of a journal dictionary with minimum keys"""
    journal = {
        'max_id': -1,  # add 1 to get next operation id
        'controlled': {wrap_id(-1):[]},  # map operation to children
        'adjusting': [],  # using adjust last panel on these op ids
        'face_tags': [],  # face tags for this object
        'version': "0.1",  # reserved for compatibility over time
        'description': ""  # object description
    }
    return journal


def blank_record():
    """Return record dictionary for filling out"""
    # mostly here as a reference
    # to support export and import, there needs to be a mesh independent way to specify vertices:
    #    in control points we combine mesh data (op_id, sequence_id) to uniquely identify the verts we want
    record = {
        'op_id': 0,  # sequential id
        'op_name': '',  # operator name for ability to restart the operator
        'properties': {},  # operator properties as run
        'control_points': {},  # selection info dict
        'gen_info': TopologyInfo.blank_dict(),  # set this for topology updates
    }
    return record


def get_block(obj):
    """Find the text block associated with the object"""
    record_name = get_obj_data(obj, JOURNAL_PROP_NAME)

    try:
        text_block = bpy.data.texts[record_name]
    except Exception:
        text_block = bpy.data.texts.new(record_name)
    return text_block


def get_journal(obj):
    """Retrieve dictionary"""
    if obj is None:
        return blank_journal()

    text_block = get_block(obj)
    return parse_block(text_block)


def set_journal(obj, journal):
    """Store dictionary"""
    text_block = get_block(obj)
    update_block(text_block, journal)

def append_operation(parent_op, face_sequence, dct_master, dct_child, postfix=''):
    """Insert an operation into a journal dictionary"""
    sel_info = SelectionInfo()
    sel_info.add_faces(parent_op, face_sequence)
    sel_info.set_mode('GROUP')
    for update_op in range(0, dct_child['max_id'] + 1):
        wrap = wrap_id(update_op)
        if wrap in dct_child:
            rec = dct_child[wrap]
            rec['description'] = rec.get('description', wrap) + postfix
    new_op_id = merge_record_dct(dct_master, dct_child, sel_info)
    return dct_master, new_op_id

def export_record(obj, operation_id, filename, do_screenshot, imagefile, description, style=[]):
    """Select operation and children and export to text file"""
    from ..mesh import draw
    dct_subset = extract_record(obj, operation_id, description)
    dct_subset['style'] = list(style)

    text = json.dumps(dct_subset, cls=MyEncoder, indent=4)

    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'w') as outfile:
        outfile.write(text)

    if do_screenshot:  # assume current window is all set up for us
        img = draw(file_path.stem)
        # save
        img.save(filepath=imagefile)


def extract_record_journal(journal, operation_id, description):
    dct_subset = blank_journal()  # the bit to store
    new_id_number = 0  # renumbering stored operations from zero
    dct, lst = journal.child_ops(operation_id)
    lst.sort()
    queued_operations = lst
    queued_operations.sort()
    dct_new_ids = {-1:-1}  # as we come across them, assign new ids to operations

    parents = journal.parents(operation_id)
    for p_id in parents:  # all parents now point to root
        dct_new_ids[p_id] = -1

    queued_operations.insert(0, operation_id)

    for old_id in queued_operations:
        if old_id in dct_new_ids:  # previously observed id
            op_id = dct_new_ids[old_id]
        else:
            op_id = new_id_number
            new_id_number = new_id_number + 1
            dct_new_ids[old_id] = op_id

    for old_id in queued_operations:
        op_id = dct_new_ids[old_id]
        record = copy.deepcopy(journal[old_id])
        record['op_id'] = op_id
        inf = SelectionInfo(record['control_points'])
        inf.renumber_ops(dct_new_ids)
        record['control_points'] = inf.to_dict()

        # this works because we work top down in processing
        parents = journal.parents(old_id)
        for control_op in parents:
            new_control = dct_new_ids[control_op]
            if wrap_id(new_control) not in dct_subset['controlled']:
                dct_subset['controlled'][wrap_id(new_control)] = []
            dct_subset['controlled'][wrap_id(new_control)].append(op_id)

        dct_subset['controlled'][wrap_id(op_id)] = []  # prepare for children of this operation

        dct_subset[wrap_id(op_id)] = record  # store in subset

    dct_subset['max_id'] = new_id_number - 1
    dct_subset['description'] = description
    return dct_subset


def extract_record(obj, operation_id, description):
    """Get dict ready for file export or cut-paste"""
    journal = Journal(obj)
    return extract_record_journal(journal, operation_id, description)


def delete_record(obj, operation_id):
    """Removes instructions for all trailing operations, returns op ids so verts can be deleted"""
    journal = Journal(obj)
    return journal.delete_record(operation_id)


def import_record(filename):
    """Return dictionary of operations that can be merged with current record"""
    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'r') as infile:
        text = infile.read()

    return json.loads(text, object_hook=object_hook)


def merge_record_dct(dct_master, dct_operation, sel_info):
    first_op_id = dct_master['max_id'] + 1  # we will return this so the system can build from here down
    top_op = sel_info.op_list()[0]
    dct_new_id = {-1: top_op}  # map id changes

    for old_id in range(0, dct_operation['max_id']+1):
        op_str = wrap_id(old_id)
        if op_str not in dct_operation:
            continue
        record = dct_operation[op_str]

        if old_id in dct_new_id:  # have we seen this before?
            op_id = dct_new_id[old_id]
        else:
            op_id = dct_master['max_id'] + 1
            dct_master['max_id'] = op_id
            dct_new_id[old_id] = op_id

        # this record can be overwritten and inserted into journal
        record['op_id'] = op_id
        if op_id == first_op_id:
            old_inf = SelectionInfo(record['control_points'])
            # is the vertex count compatible? We should test more but usually we apply to one face or to
            # similar faces
            if old_inf.mode in ['SINGLE', 'REGION']:
                if sel_info.mode not in ['SINGLE', 'REGION']:
                    print("Mismatch {} {}".format(old_inf.mode, sel_info.mode))
                    print(old_inf.to_dict(), sel_info.to_dict())
                    return "Topology mismatch with selection mode, expect single or region"
            else:
                vtest1 = old_inf.face_list(old_inf.op_list()[0])
                vtest2 = sel_info.face_list(sel_info.op_list()[0])
                if (len(vtest1) != len(vtest2)) and (len(vtest1) > 1):
                    print("Mismatch face count {} {}".format(len(vtest1), len(vtest2)))
                    return "Topology mismatch with selection face count, expected {}".format(len(vtest1))

            inf = sel_info
        else:
            inf = SelectionInfo(record['control_points'])
            if inf.op_list()[0] == -1:
                inf = sel_info
            else:
                inf.renumber_ops(dct_new_id)
        record['control_points'] = inf.to_dict()

        for control_op in inf.op_list():
            new_control = control_op  # inf already renumbered
            if wrap_id(new_control) not in dct_master['controlled']:
                dct_master['controlled'][wrap_id(new_control)] = []
            dct_master['controlled'][wrap_id(new_control)].append(op_id)

        if wrap_id(op_id) not in dct_master['controlled']:
            dct_master['controlled'][wrap_id(op_id)] = []  # prepare for children
        dct_master[wrap_id(op_id)] = record

    return first_op_id


def merge_record(obj, dct_operation, sel_info):
    """Add dictionary steps, but replace control points and control operations as indicated
    return operation id
    """
    journal = get_journal(obj)
    first_op_id = merge_record_dct(journal, dct_operation, sel_info)
    set_journal(obj, journal)

    return first_op_id


def splice_operation( dct_master, dct_insert, insert_as_op, new_control_ids, postfix=''):
    """Takes the insert_as_op and splices rec before it, making rec the new parent of insert_as_op"""
    rec = dct_master[wrap_id(insert_as_op)]
    cp = rec['control_points']
    parent_op, face_sequence = next(iter(cp['faces'].items()))
    dct_head, dct_tail = split_operations(dct_master, insert_as_op)
    dct_master, new_op_id = append_operation(unwrap_id(parent_op), face_sequence, dct_head, dct_insert, postfix)
    dct_master[wrap_id(new_op_id)]['control_points'] = cp  # keep flags and mode

    dct_full, new_op = append_operation(new_op_id, new_control_ids, dct_master, dct_tail, '')
    return dct_full

def split_operations(dct_master, split_op):
    """Make two dicts so that an operation can be inserted before split_op"""
    journal = Journal(None)
    journal.jj = dct_master
    journal.controlled = dct_master['controlled']

    dct_split = extract_record_journal(journal, split_op, dct_master[wrap_id(split_op)]['description'])
    lst_children = journal.delete_record(split_op, flush=False)
    return journal.jj, dct_split


def parse_block(text_block):
    """Read dictionary in json format"""
    lines = [line.body for line in text_block.lines]
    txt = "\n".join(lines)
    if len(txt) and txt[0] == "{":
        journal = json.loads(txt, object_hook=object_hook)
    else:
        journal = blank_journal()
    return journal


def compact(journal):
    dct_remap = {}
    shift = 0
    new_max = -1
    for i in range(journal['max_id'] + 1):
        if wrap_id(i) in journal:
            dct_remap[i] = i - shift
            if shift > 0:
                rec = journal[wrap_id(i)]
                rec["op_id"] = dct_remap[i]
                journal[wrap_id(dct_remap[i])] = rec
                del journal[wrap_id(i)]
                journal['controlled'][wrap_id(dct_remap[i])] = journal['controlled'][wrap_id(i)]
                del journal['controlled'][wrap_id(i)]

                new_faces = {}
                new_flags = {}
                new_verts = {}
                for k, v in rec['control_points']['faces'].items():
                    kk = unwrap_id(k)
                    j = dct_remap[kk]
                    new_faces[wrap_id(j)] = v
                    new_flags[wrap_id(j)] = rec['control_points']['flags'].get(k, 0)
                    new_verts[wrap_id(j)] = rec['control_points']['verts'].get(k, [])
                    c_list = journal['controlled'][wrap_id(j)]
                    c_list = [o for o in c_list if o != i]
                    c_list.append(dct_remap[i])
                    c_list.sort()
                    journal['controlled'][wrap_id(j)] = c_list

                rec['control_points']['faces'] = new_faces
                rec['control_points']['flags'] = new_flags
                rec['control_points']['verts'] = new_verts
            new_max = dct_remap[i]
        else:
            shift = shift + 1
    journal['max_id'] = new_max
    return journal


def update_block(text_block, journal):
    """Store dictionary in json format"""
    text_block.clear()
    text = json.dumps(journal, cls=MyEncoder, indent=4)
    text_block.write(text)



