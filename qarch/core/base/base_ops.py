import bpy, bmesh
from bpy.props import EnumProperty
from .base_props import FaceDivisionProperty
from .base_types import face_divide
from ...utils import managed_bmesh_edit, managed_bmesh
import json
from itertools import chain

def parse_record(text_block):
    """Read dictionary in json format"""
    lines = [line.body for line in text_block.lines]
    txt = "\n".join(lines)
    if len(txt) and txt[0] == "{":
        journal = json.loads(txt)
    else:
        journal = {'max_id':-1, 'controlled':{}, 'last_op':('',[],-1)}
    return journal


def write_record(text_block, journal):
    """Store dictionary in json format"""
    text_block.clear()
    text = json.dumps(journal, indent=4)
    text_block.write(text)


def get_block(context):
    obj = bpy.context.object  # select active object

    if obj is None:
        return None

    try:  # user can rename objects, so store our name here
        record_name = obj["record_name"]
    except Exception:
        return None

    try:
        text_block = bpy.data.texts[record_name]
    except Exception:
        text_block = bpy.data.texts.new(record_name)
    return text_block


def get_sel_opid(context):
    if not context.object:
        return None

    if context.mode == "EDIT_MESH":
        bm_func = managed_bmesh_edit
    else:
        bm_func = managed_bmesh
    with bm_func(context.object) as bm:
        key_opid = bm.verts.layers.int['opid']
        for vert in bm.verts:
            if vert.select:
                opid = vert[key_opid]
                return opid
    return None


def deselect_all(context):
    if context.object is None:
        return

    if context.mode == "EDIT_MESH":
        bm_func = managed_bmesh_edit
    else:
        bm_func = managed_bmesh
    with bm_func(context.object) as bm:
        for face in bm.faces:
            face.select_set(False)
        for vert in bm.verts:
            vert.select_set(False)
        bm.select_flush(False)


def set_selected(context, control_points):
    if context.mode == "EDIT_MESH":
        bm_func = managed_bmesh_edit
    else:
        bm_func = managed_bmesh
    with bm_func(context.object) as bm:
        bm.verts.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(False)
        for vert in bm.verts:
            vert.select_set(False)
        bm.select_flush(False)
        for idx_list in control_points:
            for idx in idx_list:
                bm.verts[idx].select_set(True)
        bm.select_flush(True)


def delete_op_verts(context, opid):
    if context.mode == "EDIT_MESH":
        bm_func = managed_bmesh_edit
    else:
        bm_func = managed_bmesh
    with bm_func(context.object) as bm:
        key = bm.verts.layers.int['opid']
        remove_verts = [v for v in bm.verts if v[key]==opid]
        bmesh.ops.delete(bm, geom=remove_verts, context="VERTS")


class QARCH_OT_select_op(bpy.types.Operator):
    bl_idname = "qarch.select_op"
    bl_label = "Select By Operation"
    bl_options = {"REGISTER"}
    bl_property = "enum_prop"

    def fill_item_list(self, context):
        opid = get_sel_opid(context)
        if opid is None:
            return []
        text_block = get_block(context)
        journal = parse_record(text_block)

        oplist = []
        cur = opid
        while cur is not None:
            str_op = f'op{cur}'
            current_rec = journal[str_op]
            enum_rec = (str_op, str_op + " " + current_rec['op_name'], "", cur)
            oplist.append(enum_rec)
            parent_ops = current_rec['control_ops']
            if len(parent_ops):
                cur = parent_ops[0]
            else:
                cur = None
        oplist.sort(key=lambda a: a[-1])
        return oplist
    enum_prop: EnumProperty(items=fill_item_list, name='Operations', default=None)
    setup_edit: bpy.props.BoolProperty(name="Enable Edit", default=False)

    @classmethod
    def poll(cls, context):
        """Most of our operations should happen in edit mode"""
        if context.object is not None and context.mode == "EDIT_MESH":
            opid = get_sel_opid(context)
            if opid is not None:
                return True
        return False

    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self)
        # context.window_manager.invoke_search_popup(self)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        if self.enum_prop is None:
            opid = -1
        else:
            opid = int(self.enum_prop[2:])  # self.op_list string is op1, op2, etc

        if self.setup_edit:
            context.object['bt_data'] = str({'opid':opid})  # prep for edit
        else:
            context.object['bt_data'] = '{}'

        if context.mode == "EDIT_MESH":
            bm_func = managed_bmesh_edit
        else:
            bm_func = managed_bmesh
        with bm_func(context.object) as bm:
            bm.verts.ensure_lookup_table()
            key_opid = bm.verts.layers.int['opid']
            for face in bm.faces:
                face.select_set(False)
            bm.select_flush(False)
            for vert in bm.verts:
                vert.select_set(vert[key_opid] == opid)
            bm.select_flush(True)
        return {"FINISHED"}


class CustomOperator(bpy.types.Operator):
    def find_or_create(self, context):
        """See if this is a redo or new action"""
        text_block = get_block(context)
        assert text_block is not None, "Select an object"

        obj = context.object
        journal = parse_record(text_block)
        opts = eval(context.object['bt_data'])
        if 'opid' in opts:
            opid = opts['opid'] # forced redo of this op
            #if opts.get('load',False):  # use stored properties moved to invoke
            #    self.props.from_dict(journal[f'op{opid}']['properties'])
            return text_block, journal, opid
        else:
            opid = None

        if context.mode == "EDIT_MESH":
            bm_func = managed_bmesh_edit
        else:
            bm_func = managed_bmesh
        with bm_func(obj) as bm:
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()

            control_points = [  # where this operation will be applied
                [v.index for v in face.verts] for face in bm.faces if face.select
            ]
            if len(control_points)==0:  # called programmatically with control points selected
                control_points = [[v.index for v in bm.verts if v.select]]

            op_key = bm.verts.layers.int["opid"]

            control_ops = [  # which operations made the control vertices
                v[op_key] for v in bm.verts if v.select
            ]

        # a bit of magic to trap the adjust-last-operation panel redo
        if opid is None:
            last_name, last_control, last_id = journal['last_op']
            if last_name == self.bl_idname and (len(last_control) == len(control_points)):
                s1 = set(chain.from_iterable(last_control))
                s2 = set(chain.from_iterable(control_points))
                s3 = s1 ^ s2
                if len(s3) == 0:
                    opid = last_id

        if opid is None:
            max_id = journal.get('max_id', 0)
            opid = max_id + 1  # increment id number
            journal['max_id'] = opid
            journal['last_op'] = self.bl_idname, control_points, opid
            op_record = {
                'opid': opid,
                'control_points': control_points,
                'control_ops': list(set(control_ops)),  # like parents of the faces being operated on
                'op_name': self.bl_idname,  # so we can call this operator again
                'properties': self.props.to_dict()
            }
            json_key = "op{}".format(opid)  # JSON number keys converted to strings, so let's always look for a string
            journal[json_key] = op_record
            journal['controlled'][json_key] = []

        return text_block, journal, opid

    def check_topology(self, props, prop_dict):
        """are we changing topology?"""
        print("check", props)
        print(props.topology_lock)
        for pname, val in prop_dict.items():
            rna = props.bl_rna.properties[pname]
            print(pname, val)
            print(rna)
            if isinstance(rna, bpy.types.PropertyGroup):
                rval = self.check_topology(getattr(props, pname), val)
                if rval:
                    return True
            elif pname in props.topology_lock:
                if val != getattr(props, pname):
                    return True
        return False

    def record(self, context):
        """Record action"""
        text_block, journal, opid = self.find_or_create(context)
        json_key = "op{}".format(opid)  # JSON number keys converted to strings, so let's always look for a string
        b_topo = self.check_topology(self.props, journal[json_key]['properties'])
        journal[json_key]['properties'] = self.props.to_dict()
        control_ops = journal[json_key]['control_ops']
        control_points = journal[json_key]['control_points']

        for parent in control_ops:
            p_key = "op{}".format(parent)
            if opid not in journal['controlled'][p_key]:
                journal['controlled'][p_key].append(opid)

        write_record(text_block, journal)

        return opid, journal['controlled'][json_key], control_points, b_topo

    @classmethod
    def update(cls, context, opid):
        """Read opid from journal and call the appropriate operator"""
        connected_ops = []  # track ripple effects so we can update those as well
        text_block = get_block(context)
        if text_block is None:
            return connected_ops

        journal = parse_record(text_block)
        json_key = "op{}".format(opid)
        op_record = journal[json_key]

        set_selected(context, op_record['control_points'])

        # operator by name.execute
        context.object['bt_data'] = str({'opid':opid, 'load':True})
        assert "QARCH_OT_" == op_record['op_name'][:9], "unknown operator"
        opname = op_record['op_name'][9:]
        op = getattr(getattr(bpy.ops, "qarch"), opname)
        # same object, should still be in edit mode
        # no way to pass in the properties, so we set the load flag in bt_data
        op('INVOKE_DEFAULT')


    @classmethod
    def create_from_script(cls, script_name):
        text_block = bpy.data.texts[script_name]
        # need new object, set as context, then call all operations in sequence
        pass

    def invoke(self, context, event):
        if context.object is not None:
            old_state = eval(context.object['bt_data'])
            opid = old_state.get('opid', None)
            if opid is not None:  # reload values from journal; only happens with button push, not adjust last panel
                text_block = get_block(context)
                journal = parse_record(text_block)
                self.props.from_dict(journal[f'op{opid}']['properties'])
        return self.execute(context)

    def execute(self, context):
        old_state = context.object['bt_data']

        # record now while we have the face selection to act on
        opid, controlled, control_points, b_topo = self.record(context)

        # to re-edit, we select the operation result, not the input face
        # so make sure the right control points are selected in case it matters
        # ie, we don't want to delete the wrong faces
        set_selected(context, control_points)
        # if topology is changing, delete all the old verts so we don't get weird faces left over
        if b_topo:
            assert len(controlled) == 0, "Topology change is deleting verts that children depend on"
            delete_op_verts(context, opid)

        self.function(context, opid)  # pass opid so new vertices can be tagged

        # first time, controlled will be empty, but after user keeps editing
        # connected ops are those whose control points depend on this operation
        # and if we re-execute, those need to be updated
        for child_id in controlled:
            # within the update, another operator execute is called
            # but the connection flows one direction, so loops should not happen
            CustomOperator.update(context, child_id)

        # who knows what state child operations leave us in
        # reset so we can use the live update feature
        set_selected(context, control_points)
        context.object['bt_data'] = old_state
        return {"FINISHED"}

    def draw(self, context):
        """Simple case, override if needed"""
        if context.object is not None:
            text_block, journal, opid = self.find_or_create(context)
            # if any children depend on us, don't change vertex count
            self.locked = len(journal['controlled'][f'op{opid}']) > 0
        self.props.draw(context, self.layout)

    @classmethod
    def poll(cls, context):
        """Most of our operations should happen in edit mode"""
        return context.object is not None and context.mode == "EDIT_MESH"


class QARCH_OT_face_divide(CustomOperator):
    """Divide a face into patches"""

    bl_idname = "qarch.face_divide"
    bl_label = "Divide Face"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=FaceDivisionProperty)

    function = face_divide

