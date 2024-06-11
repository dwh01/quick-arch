import copy

import bpy
from mathutils import Vector, Euler
from collections import defaultdict, OrderedDict
import itertools
import json
import rna_info
from ..object import get_obj_data, set_obj_data, ACTIVE_OP_ID, REPLAY_OP_ID
from ..object import Journal, merge_record, SelectionInfo, TopologyInfo, wrap_id
from ..mesh import ManagedMesh
import struct

_do_debug = True
def debug_print(s):
    if _do_debug:
        print(s)

class CustomPropertyBase(bpy.types.PropertyGroup):
    """Set up common routines with simple layout and to/from dict methods
    derived class needs 2 class member variables:
    1) field_layout which is nested list of rows of fields to display
    [[field_1, field2],[field_3]...]
    except a tuple means the first field is a boolean that toggles visibility of the second (pointer usually)

    2) topology_lock which is a list of fields that could be read only once child operations exist
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
            row = col
            if isinstance(pname, dict):  # reference previously drawn attribute
                toggle_param, value = next(iter(pname.items()))
                if isinstance(value, set):
                    if getattr(self, toggle_param) not in value:
                        return
                elif getattr(self, toggle_param) != value:
                    return
            elif (pname != "") and hasattr(self, pname):  # boolean to draw here
                row = col.row(align=True)
                row.prop(self, pname)
                if not getattr(self, pname):
                    return
            else:  # draw label for next section
                row = col.row(align=True)
                row.label(text=pname)

            prop = getattr(self, pointer)
            if hasattr(prop, 'to_dict'):
                prop.draw(context, col, lock)
            else:
                row.prop(self, pointer)

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
                    if pname == "category_item":  # preview
                        row.template_icon_view(self, pname, show_labels=True, scale_popup=10)
                    else:
                        row.prop_menu_enum(self, pname)
                else:
                    row.prop(self, pname)

    def from_dict(self, d):
        """Helper for loading persistent data"""
        for k, v in d.items():
            if isinstance(v, dict):
                getattr(self, k).from_dict(v)
            else:
                rna = self.bl_rna.properties[k]
                if isinstance(rna, bpy.types.EnumProperty): # handle dynamic enums
                    if v not in ['', 'N\A', '0']:
                        try:
                            setattr(self, k, v)
                        except Exception:  # no longer available?
                            pass
                else:
                    if isinstance(v, tuple):
                        if isinstance(getattr(self, k), Euler):
                            v = Euler(v)
                        else:
                            v = Vector(v)
                    setattr(self, k, v)

    def to_dict(self):
        """Helper for saving persistent data"""
        d = {}
        for row_list in self.field_layout:
            if isinstance(row_list, tuple):
                pname, pointer = row_list
                if (type(pname) is not dict) and (pname != ""):
                    if hasattr(self, pname):
                        d[pname] = getattr(self, pname)  # boolean toggle
                prop = getattr(self, pointer)
                if hasattr(prop, 'to_dict'):
                    d[pointer] = prop.to_dict()
                else:  # simple property toggled by boolean
                    d[pointer] = prop
            else:
                for pname in row_list:
                    d[pname] = getattr(self, pname)
                    if isinstance(d[pname], Vector):
                        d[pname] = tuple(d[pname])
                    elif isinstance(d[pname], Euler):
                        d[pname] = tuple(d[pname])

        return d


class CustomOperator(bpy.types.Operator):
    """Geometry operations support for history
    derived class needs a member called function to do the work
    which takes (self, obj, SelectionInfo, op_id, prop_dict) and returns TopologyInfo
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

    def draw(self, context):
        """Simple case, override if needed
        Passes draw_locked flag in context to make some fields read only
        """
        should_lock = self.draw_locked(context)
        self.props.draw(context, self.layout, False)  # should_lock)

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
        op_id = self.active_id

        preferences = context.preferences
        self.addon_prefs = preferences.addons['qarch'].preferences  # note: self is passed to functions

        prop_dict = self.props.to_dict()
        debug_print("Execute {} {} props {}".format(self.bl_idname, op_id, self.props.to_dict()))

        if len(self.adjusting_ids):  # in a redo loop with the user
            n_region = len(self.adjusting_ids)
            selections = [
                SelectionInfo(self.journal[adj_id]['control_points']) for adj_id in self.adjusting_ids
            ]
        elif op_id > -1:  # was invoked on an existing op
            n_region = 1
            selections = [self.active_sel_info]
        else:  # new op
            selections = self.divide_selections(self.initial_sel_info)
            n_region = len(selections)

        for i_region in range(n_region):
            sel_info = selections[i_region]

            if i_region < len(self.adjusting_ids):  # during adjust loop, need to track all the new op ids
                cur_op_id = self.adjusting_ids[i_region]
                debug_print("  Execute op {} i_region {} adjusting {} sel={}".format(op_id, i_region, cur_op_id, sel_info))
            else:
                if op_id == -1:
                    cur_op_id = self.new_record(sel_info)
                    debug_print("  Execute new op {} and add to adjusting, sel={}".format(cur_op_id, sel_info))
                else:
                    cur_op_id = op_id
                    debug_print("  Execute existing op {} and add to adjusting, sel={}".format(cur_op_id, sel_info))
                self.adjusting_ids.append(cur_op_id)
                self.journal.flush()
            # child operations list
            lst_controlled = self.journal.controlled_list(cur_op_id)

            topo_change = self.test_topology(cur_op_id)
            if topo_change:
                # if len(lst_controlled) > 0:
                #     self.report({"ERROR_INVALID_INPUT"}, "Topology change could delete verts that children depend on")
                #     self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                #     return {"CANCELLED"}
                #
                # else:  # delete old geometry so the mesh doesn't get corrupted
                debug_print("    Removing old verts because of topo change")
                self.remove_verts(cur_op_id)

            # selection state is not guaranteed
            # so operator implementations should rely on finding the control points
            ret = self.function(self.obj, sel_info, cur_op_id, prop_dict)
            if ret == {'CANCELLED'}:
                print("cancelled by function")
                self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                return {'CANCELLED'}
            else:
                self.journal[cur_op_id]['gen_info'] = ret.to_dict()  # topology info

            # this first so compound operations can add children, which might need to be updated by the write_props call
            lst_controlled = self.ensure_children(cur_op_id)

            self.write_props_to_journal(cur_op_id)  # includes a journal flush
            debug_print("    Write props {}".format(cur_op_id))

            # this so that if we changed face count, child control points can be intelligently updated
            if len(lst_controlled) > 0:
                if self.update_topology(ret, cur_op_id) == False:
                    print("cancelled by topology")
                    self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                    self.report({"ERROR_INVALID_INPUT"}, "Topology change could not be handled")
                    return {'CANCELLED'}
                else:
                    self.journal.flush()  # push updates so replay will use them

            for child_id in lst_controlled:  # compound operations can have children on first pass
                ret = replay_history(context, child_id)
                if ret == {'CANCELLED'}:
                    print("cancelled by child {}".format(child_id))
                    self.initial_journal.flush()  # blender undo will not fix the text record, so we do it
                    return {'CANCELLED'}

            # before next loop, reload journal to include child changes
            self.journal = Journal(self.obj)
            self.set_adjusting(context, self.adjusting_ids)

        self.journal.flush()  # pushes self.adjusting_ids for the redo-loop
        self.initial_journal = self.journal  # just in case
        # for poll = edit mode, don't care what is selected
        # many ops need a face selected, this should make sure it happens
        # but if not, override restore state
        if len(self.adjusting_ids) == 0:
            restore_op = -1
        else:
            restore_op = self.adjusting_ids[0]
        self.restore_state(restore_op, context)
        return {"FINISHED"}

    def get_adjusting(self, context):
        # from .dynamic_enums import qarch_asset_dir
        # tmpfile = qarch_asset_dir / "temp/adjusting.txt"
        # if not tmpfile.exists():
        #     with open(tmpfile, "w") as f:
        #         f.write("[]")
        # with open(tmpfile, "r") as f:
        #     line = f.readline()
        #     lst = eval(line)
        lst = self.journal['adjusting']
        #print("get adjusting",lst)
        return lst

    def set_adjusting(self, context, lst):
        # from .dynamic_enums import qarch_asset_dir
        # tmpfile = qarch_asset_dir / "temp/adjusting.txt"
        # with open(tmpfile, "w") as f:
        #     line = str(lst)
        #     f.write(line)
        self.journal['adjusting'] = lst
        self.journal.flush()
        #print("set adjusting", lst)

    def get_state(self, context):
        """Setup internal variables to help us"""
        self.obj = context.object
        self.context = context

        if context.object is None:
            self.active_id = -1
            self.adjusting_ids = []
            self.replay_id = -1
            self.journal = None
            self.initial_journal = None
            self.initial_sel_info = SelectionInfo()
            self.active_sel_info = None

        else:
            self.active_id = get_obj_data(self.obj, ACTIVE_OP_ID)
            self.replay_id = get_obj_data(self.obj, REPLAY_OP_ID)
            self.journal = Journal(self.obj)
            self.initial_journal = Journal(self.obj)
            possible = self.get_adjusting(context)
            # because adjusting lives outside the undo context, sometimes the journal has
            # rolled back to where these ids don't exist
            self.adjusting_ids = [op_id for op_id in possible if wrap_id(op_id) in self.journal.jj]
            # print(" accepted", self.adjusting_ids, " from ", possible)

            mm = ManagedMesh(self.obj)
            self.initial_sel_info = mm.get_selection_info()
            mm.free()

            if self.active_id > -1:
                self.active_sel_info = SelectionInfo(self.journal[self.active_id]['control_points'])


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
                return True

        return False

    def invoke(self, context, event):
        """Initialize operator with history (not called by adjust-last panel)"""
        self.get_state(context)
        if self.active_id > -1:  # an operation was selected for revision, load the parameters
            op_id = self.active_id
        else:  # a new operation is being invoked
            op_id = -1

        # adjusting used within the execute loop undo call back cycle, if we hit invoke, clear it
        # because it was left over from a parent execution loop
        if len(self.adjusting_ids):
            print("inv clear adjusting")
            self.adjusting_ids.clear()
            self.set_adjusting(context, self.adjusting_ids)

        if op_id > -1:
            debug_print("Invoke op {} {} read props".format(op_id, self.bl_idname))
            self.read_props_from_journal(op_id)
        else:
            if not self.is_face_selected(context):  # don't start with relative size, confusing to see nothing
                if 'size' in self.props.to_dict():
                    self.props.size.is_relative_x = False
                    self.props.size.is_relative_y = False

            debug_print("Invoke op {} new props".format(self.bl_idname))
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
            # test that this is the kind of object we manage
            return get_obj_data(context.object, ACTIVE_OP_ID) is not None
        return False

    def read_props_from_journal(self, op_id):
        # override this function in Compound Operator to read child properties too
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

    def restore_state(self, op_id, context):
        if self.obj:
            set_obj_data(self.obj, ACTIVE_OP_ID, -1)

            mm = ManagedMesh(self.obj)
            mm.rehide()  # hidden faces can't be selected
            if op_id > -1:
                mm.select_operation(op_id)  # select current operation faces
            mm.to_mesh()

            if not self.poll(context):  # well then, better select the way it was before; this unhides as needed
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

    def update_topology(self, gen_info, cur_op_id):
        """Try to fix control points, return false if unable"""
        try:
            old_record = self.initial_journal[cur_op_id]
        except Exception:
            return True
        old_gen = TopologyInfo(from_dict=old_record['gen_info'])

        if not old_gen.is_compatible(gen_info):
            print("update topo failed because of topology mismatch")
            print(old_gen, gen_info)
            return False

        if old_gen.is_same_as(gen_info):
            return True

        lst_controlled = self.journal.controlled_list(cur_op_id)
        for child in lst_controlled:
            rec = self.journal[child]
            sel_info = SelectionInfo(rec['control_points'])
            flist = sel_info.face_list(cur_op_id)
            old_gen.warp_to(gen_info, cur_op_id, sel_info)
            rec['control_points'] = sel_info.to_dict()

        return True

    def write_props_to_journal(self, op_id):
        """Update properties in record and flush journal"""
        # override this function in Compound Operator to alter child properties too
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal.flush()


def copy_faces(self, obj, sel_info, op_id, prop_dict):
    """Used by compound operator to make points the children can build from"""
    mm = ManagedMesh(obj)

    mm.set_op(op_id)
    mm.delete_current_verts()

    sel_bmv = mm.get_face_verts(sel_info)
    dct_done = {}
    gen_info = TopologyInfo(from_keys=["all"])
    for lst in sel_bmv:
        vlist = []
        for v in lst:
            key = (v[mm.key_op], v[mm.key_seq])
            if key in dct_done:
                vnew = dct_done[key]
            else:
                vnew = mm.new_vert(v.co)
                dct_done[key] = vnew
            vlist.append(vnew)
        face = mm.new_face(vlist)
        gen_info.add("all")

    for face in mm.get_faces(sel_info):
        mm.delete_face(face)

    mm.to_mesh()
    mm.free()

    return gen_info


class CompoundOperator(CustomOperator):
    """Inserts a sequence like you would load from a script"""
    function = copy_faces  # this just copies the selected verts and gives the copy our operation id
    delete_control_face = True  # override if you need to leave the control face in place

    def ensure_children(self, op_id):
        """Called by invoke to make sure the child script is in place"""
        lst_controlled = self.journal.controlled_list(op_id)
        if len(lst_controlled) == 0:  # first time called
            script = self.get_script()
            subset = json.loads(script)

            # Points were just generated for us to attach to. Find them
            mm = ManagedMesh(self.obj)
            mm.deselect_all()
            mm.select_operation(op_id)
            child_sel_info = mm.get_selection_info()
            mm.free()

            # add the script
            first_op_id = merge_record(self.obj, subset, child_sel_info)

            self.journal = Journal(self.obj)  # update our copy
            lst_controlled = self.journal.controlled_list(op_id)

        return lst_controlled

    def get_descent_id(self, op_id, levels):
        """Often will need to skip down a few levels"""
        for i in range(levels):
            lst = self.journal.controlled_list(op_id)
            op_id = lst[0]
        return op_id

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        assert False, "implement this function"
        return ""


def set_operation_consistent(obj, op_id):
    """Make selection state correct for this operation to execute"""
    journal = Journal(obj)
    sel_info = journal.get_sel_info(op_id)
    debug_print("set {} consistent by selecting {}".format(op_id, sel_info))

    mm = ManagedMesh(obj)
    mm.set_selection_info(sel_info)
    mm.to_mesh()
    mm.free()

    return sel_info


def replay_history(context, active_op, undo=False):
    """Read opid from journal and call the appropriate operator"""
    obj = context.object
    set_obj_data(obj, ACTIVE_OP_ID, active_op)
    set_operation_consistent(obj, active_op)  # prevent poll failure

    journal = Journal(obj)
    op = journal.get_operator(active_op)
    debug_print("replay {} undo={}".format(active_op, undo))
    ret = op('INVOKE_DEFAULT', undo)

    set_obj_data(obj, ACTIVE_OP_ID, -1)
    return ret
