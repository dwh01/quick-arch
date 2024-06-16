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
        return self.controlled.get(wrap_id(op_id), [])

    def describe(self, op_id):
        record = self.jj[wrap_id(op_id)]
        t = record.get('description', '')
        return t

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
        print("new rec", self.jj['max_id'], list(self.jj.keys()))
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
    text_block = get_block(obj)
    return parse_block(text_block)


def set_journal(obj, journal):
    """Store dictionary"""
    text_block = get_block(obj)
    update_block(text_block, journal)


def export_record(obj, operation_id, filename, do_screenshot, imagefile, description):
    """Select operation and children and export to text file"""
    from ..mesh import draw
    dct_subset = extract_record(obj, operation_id, description)

    text = json.dumps(dct_subset, indent=4)

    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'w') as outfile:
        outfile.write(text)

    if do_screenshot:  # assume current window is all set up for us
        img = draw(file_path.stem)
        # save
        img.save(filepath=imagefile)


def extract_record(obj, operation_id, description):
    """Get dict ready for file export or cut-paste"""
    journal = Journal(obj)

    dct_subset = blank_journal()  # the bit to store
    new_id_number = 0  # renumbering stored operations from zero
    queued_operations = [operation_id]
    dct_new_ids = {-1:-1}  # as we come across them, assign new ids to operations

    parents = journal.parents(operation_id)
    for p_id in parents:  # all parents now point to root
        dct_new_ids[p_id] = -1

    while len(queued_operations):
        old_id = queued_operations.pop(0)
        # add children to end of queue for breadth first, to head for depth first
        # don't think it matters much
        queued_operations = queued_operations + journal['controlled'][wrap_id(old_id)]

        if old_id in dct_new_ids:  # previously observed id
            op_id = dct_new_ids[old_id]
        else:
            op_id = new_id_number
            new_id_number = new_id_number + 1
            dct_new_ids[old_id] = op_id

        record = copy.deepcopy(journal[old_id])
        record['op_id'] = op_id
        inf = SelectionInfo(record['control_points'])
        inf.renumber_ops(dct_new_ids)
        record['control_points'] = inf.to_dict()

        # this works because we work top down in processing
        parents = journal.parents(old_id)
        for control_op in parents:
            new_control = dct_new_ids[control_op]
            dct_subset['controlled'][wrap_id(new_control)].append(op_id)

        dct_subset['controlled'][wrap_id(op_id)] = []  # prepare for children of this operation

        dct_subset[wrap_id(op_id)] = record  # store in subset

    dct_subset['max_id'] = new_id_number - 1
    dct_subset['description'] = description
    return dct_subset


def delete_record(obj, operation_id):
    """Removes instructions for all trailing operations, returns op ids so verts can be deleted"""
    journal = Journal(obj)
    parents = journal.parents(operation_id)

    dct_children, lst_children = journal.child_ops(operation_id)
    lst_children.insert(0, operation_id)

    lst_children.reverse()  # doesn't matter, but remove lowest level first
    for op_id in lst_children:
        del journal.jj['controlled'][wrap_id(op_id)]
        del journal.jj[wrap_id(op_id)]

    for parent_id in parents:
        lst = journal['controlled'][wrap_id(parent_id)]
        lst.remove(operation_id)

    journal.flush()
    return lst_children


def import_record(filename):
    """Return dictionary of operations that can be merged with current record"""
    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'r') as infile:
        text = infile.read()

    return json.loads(text)


def merge_record(obj, dct_operation, sel_info):
    """Add dictionary steps, but replace control points and control operations as indicated
    return operation id
    """
    journal = get_journal(obj)
    first_op_id = journal['max_id'] + 1  # we will return this so the system can build from here down
    top_op = sel_info.op_list()[0]
    dct_new_id = {-1:top_op}  # map id changes

    for old_id in range(0, dct_operation['max_id']+1):
        op_str = wrap_id(old_id)
        record = dct_operation[op_str]

        if old_id in dct_new_id:  # have we seen this before?
            op_id = dct_new_id[old_id]
        else:
            op_id = journal['max_id'] + 1
            journal['max_id'] = op_id
            dct_new_id[old_id] = op_id

        # this record can be overwritten and inserted into journal
        record['op_id'] = op_id
        if op_id == first_op_id:
            old_inf = SelectionInfo(record['control_points'])
            # is the vertex count compatible? We should test more but usually we apply to one face or to
            # similar faces
            vtest1 = old_inf.face_list(old_inf.op_list()[0])
            vtest2 = sel_info.face_list(sel_info.op_list()[0])
            if len(vtest1) != len(vtest2):
                return "Topology mismatch with selection vertex count"  # TODO make it possible

            inf = sel_info
        else:
            inf = SelectionInfo(record['control_points'])
            inf.renumber_ops(dct_new_id)
        record['control_points'] = inf.to_dict()

        print("merged = ")
        print(record)

        for control_op in inf.op_list():
            new_control = control_op  # inf already renumbered
            if wrap_id(new_control) not in journal['controlled']:
                journal['controlled'][wrap_id(new_control)] = []
            journal['controlled'][wrap_id(new_control)].append(op_id)

        journal['controlled'][wrap_id(op_id)] = []  # prepare for children

        journal[wrap_id(op_id)] = record

    set_journal(obj, journal)

    return first_op_id


def parse_block(text_block):
    """Read dictionary in json format"""
    lines = [line.body for line in text_block.lines]
    txt = "\n".join(lines)
    if len(txt) and txt[0] == "{":
        journal = json.loads(txt)
    else:
        journal = blank_journal()
    return journal


def update_block(text_block, journal):
    """Store dictionary in json format"""
    text_block.clear()
    text = json.dumps(journal, indent=4)
    text_block.write(text)



