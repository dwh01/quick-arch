import bpy
from collections import defaultdict

import rna_info
from ..object import get_obj_data, set_obj_data, ACTIVE_OP_ID
from ..object import Journal
from ..mesh import ManagedMesh
import struct


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
    function(obj, control_op, control_points, op_id, prop_dict)

    override single_face if operator takes a region selection to work on
    """
    single_face = True

    def check_topology(self, props, prop_dict):
        """are we changing topology?"""
        for pname, val in prop_dict.items():
            rna = props.bl_rna.properties[pname]
            if isinstance(rna, bpy.types.PropertyGroup):
                if self.check_topology(getattr(props, pname), val):
                    return True
            elif pname in props.topology_lock:
                if val != getattr(props, pname):
                    return True
        return False

    def draw(self, context):
        """Simple case, override if needed
        Passes draw_locked flag in context to make some fields read only
        """
        should_lock = False
        journal, record = self.get_active_record(context)
        if journal is not None:
            should_lock = len(journal.controlled_list(record['op_id'])) > 0

        self.props.draw(context, self.layout, should_lock)

    def execute(self, context):
        obj = context.object
        if obj is not None:  # for create object operation this IS None!
            active_op = get_obj_data(obj, ACTIVE_OP_ID)
        else:
            active_op = -1

        # get control points from journal or context object
        journal = Journal(obj)
        print("execute: {} active, {} adjusting".format(active_op, journal['adjusting']))
        if active_op > -1:
            lst_controlled = self.execute_active(obj, journal, active_op)
            if lst_controlled == {'CANCELLED'}:
                return {'CANCELLED'}
            for child_id in lst_controlled:
                replay_history(context, child_id)
            # just in case children change state, but we want adjust-last to work properly
            set_obj_data(obj, ACTIVE_OP_ID, active_op)
            self.set_operation_consistent(obj, journal[active_op])
        else:
            self.execute_faceloop(obj, journal)
        print("Execute Finished")
        return {"FINISHED"}

    def execute_active(self, obj, journal, active_op):
        if active_op > -1:
            record = journal[active_op]
            lst_sel_info = self.set_operation_consistent(obj, record)
            topo_change = self.check_topology(self.props, record['properties'])
        else:
            assert False, "Call only when an op is active"

        if active_op in journal['adjusting']:
            record['properties'] = self.props.to_dict()
            journal.flush()

        print("execute_active {} active {} adjusting".format(active_op, journal['adjusting']))

        lst_controlled = journal.controlled_list(active_op)
        # if topology is changing, delete all the old verts so we don't get weird faces left over
        if topo_change:
            num_children = len(lst_controlled)
            if num_children > 0:
                self.report({"ERROR_INVALID_INPUT"}, "Topology change could delete verts that children depend on")
                return {"CANCELLED"}

            # changing number of verts, better destroy them plus faces to avoid errors
            mm = ManagedMesh(obj)
            mm.set_op(active_op)
            mm.delete_current_verts()
            mm.to_mesh()
            mm.free()

            self.report({"WARNING"}, "Topology change forced face reconstruction")

        # selection state is not guaranteed
        # so operator implementations should rely on finding the control points
        self.function(obj, lst_sel_info, active_op, record['properties'])

        return lst_controlled

    def execute_faceloop(self, obj, journal):
        """Apply new operation to one or more faces"""
        mm = ManagedMesh(obj)
        sel_info = mm.get_selection_info()
        mm.free()

        by_faces = defaultdict(list)
        for inf in sel_info:
            if self.single_face:  # separate all faces
                by_faces[len(by_faces)].append(inf)
            else:  # allow connected faces; only faces within one operation can be connected (because 1 control_op)
                by_faces[inf[mm.OPID]].append(inf)

        if len(by_faces) == 0:  # handle the no faces selected operations
            by_faces[-1] = [[-1, []]]

        lst_adjusting = journal['adjusting']
        print("execute_faceloop {} adjusting".format(journal['adjusting']))
        for i_face, face_sel_info in enumerate(by_faces.values()):
            mm = ManagedMesh(obj)  # we don't hold this open because we may be altering the mesh
            mm.deselect_all()
            mm.set_selection_info(face_sel_info)
            mm.to_mesh()
            mm.free()

            if len(face_sel_info):
                control_op = face_sel_info[0][mm.OPID]
            else:
                control_op = -1

            if len(lst_adjusting) <= i_face:
                record = journal.new_record(control_op, self.bl_idname)
                op_id = record['op_id']
                print("face selection {} made new op {}".format(face_sel_info, op_id))
                journal['adjusting'].append(op_id)
            else:
                op_id = lst_adjusting[i_face]
                record = journal[op_id]
                face_sel_info = record['control_points']
                print("face selection {} adjusting op {}".format(face_sel_info, op_id))
            record['control_points'] = face_sel_info
            record['properties'] = self.props.to_dict()
            journal.flush()
            # selection state is not guaranteed
            # so operator implementations should rely on finding the control points
            self.function(obj, face_sel_info, op_id, record['properties'])

        #journal.flush()

    @staticmethod
    def get_active_record(context):
        obj = context.object
        if obj is not None:  # for create object operation this IS None!
            active_op = get_obj_data(obj, ACTIVE_OP_ID)
            if (active_op is not None) and (active_op > -1):  # reload values from journal
                journal = Journal(obj)
                record = journal[active_op]
                return journal, record
        return None, None

    @ classmethod
    def is_face_selected(cls, context):
        """Used for some poll routines"""
        if (context.object is None) or (context.mode != "EDIT_MESH"):
            return False

        obj = context.object
        if obj is not None:
            mm = ManagedMesh(obj)
            sel_info = mm.get_selection_info()
            if len(sel_info) == 0:
                return False
            if sel_info[0][mm.OPID] == -1:
                return len(sel_info[0][mm.OPSEQ]) > 2
            return True

        return False

    def invoke(self, context, event):
        """Initialize operator with history (not called by adjust-last panel)"""
        obj = context.object
        journal, record = self.get_active_record(context)
        loaded = False
        if record is not None:
            # do we load properties from record?
            if self.test_operation_consistent(obj, record):
                self.props.from_dict(record['properties'])
                loaded = True
                journal['adjusting'] = [record['op_id']]
            else:
                journal['adjusting'] = []
        elif obj is not None:
            journal = Journal(obj)
            journal['adjusting'] = []
        journal.flush()

        active = -1
        if record:
            active = record['op_id']
        print("Invoke {} active, {} adjusting, loaded {}".format(active, journal['adjusting'], loaded))
        if ('UNDO' not in self.bl_options) and (not loaded):  # no adjust last panel to pop up
            wm = context.window_manager
            return wm.invoke_props_dialog(self)

        # otherwise we call execute now
        return self.execute(context)

    @classmethod
    def poll(cls, context):
        """Most of our operations should happen in edit mode, if not, customize in derived class"""
        return (context.object is not None) and (context.mode == "EDIT_MESH")

    @staticmethod
    def set_operation_consistent(obj, record):
        """Make selection state correct for this operation to execute"""
        lst_sel_info = record['control_points']

        mm = ManagedMesh(obj)
        mm.set_selection_info(lst_sel_info)
        mm.to_mesh()
        mm.free()

        return lst_sel_info

    @staticmethod
    def test_operation_consistent(obj, record):
        """Make sure selection state of mesh matches what this operation needs"""
        active_op = record['op_id']
        # test that selected vertices belong to this operation's control operation
        # else turn off active_op because user clicked away
        mm = ManagedMesh(obj)
        lst_sel_info = mm.get_selection_info()
        mm.free()  # without update

        if (len(lst_sel_info) == 0) and (len(record['control_points']) > 0):
            print("No selection but control points expected")
            return False  # some ops expect no selected points

        sel_ops = set([t[mm.OPID] for t in lst_sel_info])
        if len(sel_ops) > 1:
            print("Multiple operation points selected")
            set_obj_data(obj, ACTIVE_OP_ID, -1)
            return False  # stored ops only ever have one operation id

        elif (len(lst_sel_info) > 0) and lst_sel_info[0][mm.OPID] != active_op:
            print("Wrong operation points selected")
            set_obj_data(obj, ACTIVE_OP_ID, -1)
            return False  # the wrong points are selected

        return True


def replay_history(context, active_op):
    """Read opid from journal and call the appropriate operator"""
    obj = context.object

    set_obj_data(obj, ACTIVE_OP_ID, active_op)

    journal = Journal(obj)
    record = journal[active_op]
    CustomOperator.set_operation_consistent(obj, record)

    op = journal.get_operator(active_op)

    op('INVOKE_DEFAULT')