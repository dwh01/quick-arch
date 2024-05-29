import copy

import bpy
from collections import defaultdict
import itertools
import json
import rna_info
from ..object import get_obj_data, set_obj_data, ACTIVE_OP_ID, REPLAY_OP_ID
from ..object import Journal, merge_record, SelectionInfo
from ..mesh import ManagedMesh
import struct

_do_debug = True
def debug_print(s):
    if _do_debug:
        print(s)

class CustomPropertyBase(bpy.types.PropertyGroup):
    """Set up common routines with simple layout and to/from dict methods
    derived class needs two class member variables:
    1) field_layout which is nested list of rows of fields to display
    [[field_1, field2],[field_3]...]
    except a tuple means the first field is a boolean that toggles visibility of the second (pointer usually)

    2) topology_lock which is a list of fields that should be read only once child operations exist
    because we can't change the number of vertices safely. Changing position is ok.
    """
    def draw(self, context, layout, lock=False):
        """Requires a field_layout list to be defined"""
        col = layout.column(align=True)
        for row_list in self.field_layout:
            if isinstance(row_list, str):
                if row_list == "---":
                    layout.separator()
                    col = layout.column(align=True)
                else:
                    col.label(text=row_list)
            else:
                self.draw_row_list(context, col, row_list, lock)

    def draw_row_list(self, context, col, row_list, lock):
        if isinstance(row_list, tuple):  # boolean toggle for pointer
            pname, pointer = row_list
            row = col.row(align=True)
            if pname != "":
                row.prop(self, pname)
                if not getattr(self, pname):
                    return
            else:
                row.label(text=pname)
                row = col.row(align=True)
            getattr(self, pointer).draw(context, col, lock)

        else:
            row = col.row(align=True)
            pop_row = row  # used so we can push a locked layout for some fields
            for pname in row_list:
                row = pop_row

                if lock and (pname in self.topology_lock):
                    row = row.column(align=True)
                    row.enabled = False

                rna = self.bl_rna.properties[pname]
                if isinstance(rna, bpy.types.EnumProperty):
                    row.label(text=getattr(self, pname))
                    row.prop_menu_enum(self, pname)
                else:
                    row.prop(self, pname)

    def from_dict(self, d):
        """Helper for loading persistent data"""
        for k, v in d.items():
            if isinstance(v, dict):
                getattr(self, k).from_dict(v)
            else:
                setattr(self, k, v)

    def to_dict(self):
        """Helper for saving persistent data"""
        d = {}
        for row_list in self.field_layout:
            if isinstance(row_list, tuple):
                pname, pointer = row_list
                if pname != "":
                    d[pname] = getattr(self, pname)
                d[pointer] = getattr(self, pointer).to_dict()
            else:
                for pname in row_list:
                    d[pname] = getattr(self, pname)
        return d


class CustomOperator(bpy.types.Operator):
    """Geometry operations support for history
    derived class needs a member called function to do the work:
    function(obj, sel_info, op_id, prop_dict)

    override set consistent
    """
    # invoke checks object custom data for "replay" or "active"
    # if found, load properties and selection info from journal
    # and resets "adjusting" in the journal
    #
    # execute loops through selected faces
    # if adjusting, use that op id, load selection info
    # else if replay or active, make it adjusting and use that op_id and selection info
    #  clear active id (one time flag to load the properties)
    # else make new id and add to adjusting. Use current selection on mesh and store to new record
    # then test consistent:
    #   if the desired selection doesn't work because verts changed, can we upgrade?
    # call function
    # replay child loop (sets replay flag, clears replay flag after call)
    # restore adjusting in case children changed it
    # if we are user invoked, the prop dialog will continue to call
    # execute where we will see the adjusting value

    def control_points_match(self, sel_info, control_info, op_id):
        """if the selection is the active op, that's ok, else must match control"""
        sel_ops = sel_info.op_list()
        if (len(sel_ops) == 1) and (op_id == sel_ops[0]):
            return True
        return control_info.matches(sel_info)

    def draw(self, context):
        """Simple case, override if needed
        Passes draw_locked flag in context to make some fields read only
        """
        should_lock = self.draw_locked(context)
        self.props.draw(context, self.layout, should_lock)

    def draw_locked(self, context):
        """True means lock topology changing variables because children exist"""
        should_lock = False
        self.get_state(context)
        if self.active_id > -1:
            op_id = self.active_id
        elif len(self.adjusting_ids):
            op_id = self.adjusting_ids[0]
        else:
            op_id = -1
        if op_id > -1:
            should_lock = len(self.journal.controlled_list(op_id)) > 0
        return should_lock

    def divide_selections(self, initial_sel_info):
        """Separate to single faces"""
        lst = []
        if self.addon_prefs.select_mode == 'SINGLE':
            for op in initial_sel_info.op_list():
                for f in initial_sel_info.face_list(op):
                    sel = SelectionInfo()
                    sel.add_face(op, f)
                    sel.set_mode(self.addon_prefs.select_mode)
                    lst.append(sel)
        elif self.addon_prefs.select_mode == 'GROUP':
            initial_sel_info.set_mode(self.addon_prefs.select_mode)
            lst = [initial_sel_info]
        else:
            initial_sel_info.set_mode(self.addon_prefs.select_mode)
            lst = [initial_sel_info]
        return lst

    def ensure_children(self, op_id):
        """A compound operator uses this to merge the script on the first call"""
        return self.journal.controlled_list(op_id)

    def execute(self, context):
        self.get_state(context)
        if self.replay_id > -1:
            op_id = self.replay_id
        elif self.active_id > -1:
            op_id = self.active_id
        else:
            op_id = -1

        preferences = context.preferences
        self.addon_prefs = preferences.addons['qarch'].preferences  # note: self is passed to functions

        debug_print(f"Execute: Active {self.active_id}, Replay {self.replay_id}, op_id {op_id}")

        prop_dict = self.props.to_dict()
        selections = self.divide_selections(self.initial_sel_info)
        for i_region in range(len(selections)):
            sel_info = selections[i_region]

            debug_print("i_region {} sel_info {}".format(i_region, sel_info))

            if i_region < len(self.adjusting_ids):  # during adjust loop, need to track all the new op ids
                cur_op_id = self.adjusting_ids[i_region]
                debug_print("adjusting_ids[{}]={}".format(i_region, cur_op_id))
                sel_info = self.set_operation_consistent(cur_op_id)

            else:
                if op_id == -1:
                    cur_op_id = self.new_record(sel_info)
                    debug_print("Execute new op {} and add to adjusting".format(cur_op_id))
                else:
                    cur_op_id = op_id
                self.adjusting_ids.append(cur_op_id)

            # child operations list
            lst_controlled = self.journal.controlled_list(cur_op_id)

            topo_change = self.test_topology(cur_op_id)
            if topo_change:
                if len(lst_controlled) > 0:
                    self.report({"ERROR_INVALID_INPUT"}, "Topology change could delete verts that children depend on")
                    self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                    return {"CANCELLED"}

                else:  # delete old geometry so the mesh doesn't get corrupted
                    debug_print("Removing old verts because of topo change")
                    self.remove_verts(cur_op_id)

            debug_print("{} function({}, {})".format(self.bl_idname, sel_info, cur_op_id))

            # selection state is not guaranteed
            # so operator implementations should rely on finding the control points
            ret = self.function(self.obj, sel_info, cur_op_id, prop_dict)
            if ret == {'CANCELLED'}:
                self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                return {'CANCELLED'}

            lst_controlled = self.ensure_children(cur_op_id)  # this is so compound operations can add children
            self.write_props_to_journal(cur_op_id)  # includes a journal flush, after ensure children for compound operators

            for child_id in lst_controlled:  # compound operations can have children on first pass
                self.set_operation_consistent(child_id)  # otherwise child poll failure might prevent invoke
                ret = replay_history(context, child_id)
                if ret == {'CANCELLED'}:
                    self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                    return {'CANCELLED'}

            # before next loop, reload journal to include child changes
            self.journal = Journal(self.obj)
            self.journal.jj['adjusting'] = self.adjusting_ids

        self.journal.flush()
        debug_print("restoring state")
        self.restore_state()
        return {"FINISHED"}

    def get_state(self, context):
        """Setup internal variables to help us"""
        self.obj = context.object
        if context.object is None:
            self.active_id = -1
            self.adjusting_ids = []
            self.replay_id = -1
            self.journal = None
            self.initial_journal = None
            self.initial_sel_info = SelectionInfo()

        else:
            self.active_id = get_obj_data(self.obj, ACTIVE_OP_ID)
            self.replay_id = get_obj_data(self.obj, REPLAY_OP_ID)
            self.journal = Journal(self.obj)
            self.initial_journal = Journal(self.obj)
            self.adjusting_ids = self.journal['adjusting']

            mm = ManagedMesh(self.obj)
            self.initial_sel_info = mm.get_selection_info()

    @ classmethod
    def is_face_selected(cls, context):
        """Used for some poll routines"""
        if (context.object is None) or (context.mode != "EDIT_MESH"):
            return False
        if get_obj_data(context.object, ACTIVE_OP_ID) is None:
            return False

        obj = context.object
        if obj is not None:
            mm = ManagedMesh(obj)
            sel_info = mm.get_selection_info()
            ops = sel_info.op_list()
            if len(ops) == 0:
                return False
            faces_list = sel_info.face_list(ops[0])
            if len(faces_list):
                return len(faces_list[0]) > 2
            print(sel_info)

        return False

    def invoke(self, context, event):
        """Initialize operator with history (not called by adjust-last panel)"""
        self.get_state(context)
        if self.replay_id > -1:  # a child operation is being executed, load the parameters
            op_id = self.replay_id

        elif self.active_id > -1:  # an operation was selected for revision, load the parameters
            op_id = self.active_id
            if not self.test_operation_consistent(op_id):  # probably meant to reset active id
                set_obj_data(self.obj, ACTIVE_OP_ID, -1)
                self.active_id = -1
                op_id = -1

        else:  # a new operation is being invoked
            op_id = -1

        debug_print(f"Invoke: Active {self.active_id}, Replay {self.replay_id}, op_id {op_id}")
        # adjusting used within the execute loop undo call back cycle, if we hit invoke, clear it
        if len(self.adjusting_ids):
            self.adjusting_ids.clear()
            self.journal.flush()

        if op_id > -1:
            self.read_props_from_journal(op_id)
            self.set_operation_consistent(op_id)
        else:
            if 'UNDO' not in self.bl_options:  # no adjust last panel to pop up
                wm = context.window_manager
                return wm.invoke_props_dialog(self)

        # otherwise we call execute now
        return self.execute(context)

    def new_record(self, sel_info):
        record = self.journal.new_record(sel_info, self.bl_idname)
        op_id = record['op_id']
        self.journal.flush()

        return op_id

    @classmethod
    def poll(cls, context):
        """Most of our operations should happen in edit mode, if not, customize in derived class"""
        if (context.object is not None) and (context.mode == "EDIT_MESH"):
            return get_obj_data(context.object, ACTIVE_OP_ID) is not None
        return False

    def read_props_from_journal(self, op_id):
        # override this function in Compound Operator to read child properties too
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

    def restore_state(self):
        if self.obj:
            set_obj_data(self.obj, REPLAY_OP_ID, self.replay_id)
            set_obj_data(self.obj, ACTIVE_OP_ID, self.active_id)
            if self.initial_sel_info.count_faces() or self.initial_sel_info.count_verts():
                print("Restore selection to {}".format(self.initial_sel_info))
                mm = ManagedMesh(self.obj)
                mm.set_selection_info(self.initial_sel_info)
                mm.to_mesh()
                mm.free()

    def remove_verts(self, op_id):
        mm = ManagedMesh(self.obj)
        mm.set_op(op_id)
        mm.select_operation(op_id)
        mm.delete_current_verts()
        mm.to_mesh()
        mm.free()

    def set_operation_consistent(self, op_id):
        """Make selection state correct for this operation to execute"""
        sel_info = self.journal.get_sel_info(op_id)
        if debug_print:
            print("set {} consistent by selecting {}".format(op_id, sel_info))

        mm = ManagedMesh(self.obj)
        mm.set_selection_info(sel_info)
        mm.to_mesh()
        mm.free()

        return sel_info

    def test_operation_consistent(self, op_id):
        """Make sure selection state of mesh matches what this operation needs"""
        # test that selected vertices belong to this operation's control operation
        # else turn off active_op because user clicked away
        if op_id == -1:
            return True
        mm = ManagedMesh(self.obj)
        lst_sel_info = mm.get_selection_info()
        mm.free()  # without update

        sel_control = self.journal.get_sel_info(op_id)
        debug_print("testing consistent {}".format(op_id))
        b_ok = self.control_points_match(lst_sel_info, sel_control, op_id)
        if not b_ok:
            debug_print("Expected {} != Test {}".format(sel_control, lst_sel_info))
        return b_ok

    def test_topology(self, op_id):
        """are we changing topology?"""
        prop_dict = self.journal[op_id]['properties']
        return self.topology_check_recursive(self.props, prop_dict)

    @staticmethod
    def topology_check_recursive(props, prop_dict):
        for pname, val in prop_dict.items():
            rna = props.bl_rna.properties[pname]
            if isinstance(rna, bpy.types.PropertyGroup):
                if CustomOperator.topology_check_recursive(getattr(props, pname), val):
                    return True
            elif pname in props.topology_lock:
                if val != getattr(props, pname):
                    return True
        return False

    def write_props_to_journal(self, op_id):
        """Update properties in record and flush journal"""
        # override this function in Compound Operator to alter child properties too
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal.flush()


def copy_points(self, obj, sel_info, op_id, prop_dict):
    """Used by compound operator to make points the children can build from"""
    mm = ManagedMesh(obj)

    mm.set_op(op_id)
    mm.delete_current_verts()

    sel_bmv = sel_info.get_face_verts(mm)
    set_done = set()
    for lst in sel_bmv:
        for v in lst:
            if v in set_done:
                continue
            vnew = mm.new_vert(v.co)
            set_done.add(v)

        mm.to_mesh()

    mm.free()

    return [[op_id, list(range(len(set_done)))]]


class CompoundOperator(CustomOperator):
    """Inserts a sequence like you would load from a script"""
    function = copy_points  # this just copies the selected verts and gives the copy our operation id
    delete_control_face = True  # override if you need to leave the control face in place

    def ensure_children(self, op_id):
        """Called by invoke to make sure the child script is in place"""
        lst_controlled = self.journal.controlled_list(op_id)
        if len(lst_controlled) == 0:  # first time called
            script = self.get_script()
            subset = json.loads(script)

            # Points were just generated for us to attach to. Find them
            mm = ManagedMesh(self.obj)
            mm.set_op(op_id)
            mm.select_operation(op_id)
            child_sel_info = mm.get_selection_info()
            mm.free()

            # add the script
            first_op_id = merge_record(self.obj, subset, child_sel_info)

            self.journal = Journal(self.obj)  # update our copy
            lst_controlled = self.journal.controlled_list(op_id)

        return lst_controlled

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        assert False, "implement this function"
        return ""


def replay_history(context, active_op, undo=False):
    """Read opid from journal and call the appropriate operator"""
    obj = context.object
    set_obj_data(obj, REPLAY_OP_ID, active_op)

    journal = Journal(obj)
    op = journal.get_operator(active_op)
    debug_print("replay {}".format(active_op))
    ret = op('INVOKE_DEFAULT', undo)

    set_obj_data(obj, REPLAY_OP_ID, -1)
    return ret
