"""History Journal
Routines to get/set the history dictionary associated with an object
and to import/export chunks of the history
"""
import bpy
import json
import copy
import pathlib
from collections import defaultdict

from .utils import get_obj_data, JOURNAL_PROP_NAME

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
            record = self.jj[wrap_id(op_id)]
            lst = self.ancestors(record['control_op'])
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

    def flush(self):
        """Save changes to text block"""
        set_journal(self.obj, self.jj)

    def get_operator(self, op_id):
        record = self.jj[wrap_id(op_id)]
        assert "QARCH_OT_" == record['op_name'][:9], "unknown operator"
        opname = record['op_name'][9:]
        op = getattr(getattr(bpy.ops, "qarch"), opname)
        return op

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

            return dct_ops

    def new_record(self, control_op, op_name):
        rec = blank_record()
        new_id = self.jj['max_id'] + 1
        rec['op_id'] = new_id
        rec['control_op'] = control_op
        rec['op_name'] = op_name

        self.jj['max_id'] = new_id
        self.jj[wrap_id(new_id)] = rec

        # update control dictionary
        c_key = wrap_id(control_op)
        c_dict = self.jj['controlled']
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


def blank_journal():
    """Return start of a journal dictionary with minimum keys"""
    journal = {
        'max_id': -1,  # add 1 to get next operation id
        'controlled': {},  # map operation to children
        'adjusting': [],  # using adjust last panel on these op ids
    }
    return journal


def blank_record():
    """Return record dictionary for filling out"""
    # mostly here as a reference
    # to support export and import, there needs to be a mesh independent way to specify vertices:
    #    we combine mesh data (op_id, sequence_id) to uniquely identify the verts we want
    #    but we keep in separate lists because set(control_ops) tells us how many and which parents we have
    record = {
        'op_id': 0,  # sequential id
        'op_name': '',  # operator name for ability to restart the operator
        'properties': {},  # operator properties as run
        'control_points': [],  # vertex sequence numbers
        'control_op': -1,       # operation that created control_points
        'compound_count': 0  # set this for compound operations to know how many following ops are auto-inserted
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


def export_record(obj, operation_id, filename, do_screenshot):
    """Select operation and children and export to text file"""
    dct_subset = extract_record(obj, operation_id)

    text = json.dumps(dct_subset, indent=4)

    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'w') as outfile:
        outfile.write(text)

    if do_screenshot:  # assume current window is all set up for us
        bpy.ops.screen.screenshot_area(file_path.with_suffix(".png"))


def extract_record(obj, operation_id):
    """Get dict ready for file export or cut-paste"""
    journal = get_journal(obj)

    dct_subset = blank_journal()  # the bit to store
    new_id_number = 0  # renumbering stored operations from zero
    queued_operations = [operation_id]
    dct_new_ids = {}  # as we come across them, assign new ids to operations

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

        # this works because we work top down in processing
        # -1 will represent the root when we import this into another object
        control_op = dct_new_ids.get(record['control_op'], -1)
        record['control_op'] = control_op

        if control_op > -1:  # update parent control map to show this relationship
            dct_subset['controlled'][wrap_id(control_op)].append(op_id)

        dct_subset['controlled'][wrap_id(op_id)] = []  # prepare for children of this operation

        dct_subset[wrap_id(op_id)] = record  # store in subset

    dct_subset['max_id'] = new_id_number - 1
    return dct_subset


def delete_record(obj, operation_id):
    """Removes instructions for all trailing operations, returns op ids so verts can be deleted"""
    journal = get_journal(obj)
    parent_id = journal[wrap_id(operation_id)]['control_op']

    dct_children, lst_children = journal.child_ops(operation_id)
    lst_children.insert(0, operation_id)

    lst_children.reverse()  # doesn't matter, but remove lowest level first
    for op_id in lst_children:
        del journal['controlled'][wrap_id(op_id)]
        del journal[wrap_id(op_id)]

    lst = journal['controlled'][wrap_id(parent_id)]
    lst.remove(operation_id)

    set_journal(obj, journal)
    return lst_children


def import_record(filename):
    """Return dictionary of operations that can be merged with current record"""
    file_path = pathlib.Path(filename)
    with open(file_path.with_suffix(".txt"), 'r') as infile:
        text = infile.read()

    return json.loads(text)


def merge_record(obj, dct_operation, new_control_points, new_control_op):
    """Add dictionary steps, but replace control points and control operations as indicated
    return operation id
    """
    journal = get_journal(obj)
    dct_new_id = {}  # map id changes
    first_op_id = journal['max_id']+1  # we will return this so the system can build from here down

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
        if record['control_op'] == -1:  # root operation
            control_op = new_control_op
            record['control_points'] = new_control_points
        else:
            control_op = dct_new_id[record['control_op']]
        record['control_op'] = control_op

        if control_op > -1:  # object creation has no parent, else update parent map
            journal['controlled'][wrap_id(control_op)].append(op_id)

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


# these last two functions are because json turns integer keys into strings
# we don't want to forget and get confused why 1 != "1"
def unwrap_id(op_str):
    return int(op_str[2:])


def wrap_id(op_id):
    return f'op{op_id}'
