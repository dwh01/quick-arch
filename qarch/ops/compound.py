import bpy
from .custom import CompoundOperator
from .properties import SimpleWindowProperty, PointerProperty, SimpleDoorProperty, SimpleRailProperty, SimplePorticoProperty
from .properties import ExtendGableProperty, DormerProperty, DeckProperty
from ..object import Journal, get_obj_data, ACTIVE_OP_ID, SelectionInfo, wrap_id, merge_record_dct, MyEncoder, delete_record
from ..mesh import ManagedMesh, SmartPoly, CoordSys, _common_start
from mathutils import Vector
import math
import json
import pathlib

# registration and module init info
lst_classes = [
    'QARCH_OT_add_window',
    'QARCH_OT_add_door',
    'QARCH_OT_add_portico',
    'QARCH_OT_add_rail',
    'QARCH_OT_add_deck',
    'QARCH_OT_extend_gable',
    'QARCH_OT_add_dormer',
]
lst_funcs = []

class QARCH_OT_add_window(CompoundOperator):
    bl_idname = "qarch.add_window"
    bl_label = "Add Window"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleWindowProperty)

    def ensure_children(self, op_id):
        """Called by invoke to make sure the child script is in place"""
        lst_controlled = self.journal.controlled_list(op_id)
        if len(lst_controlled) > 0:  # not first time called
            # if we swap in/out, it changes child count
            # we must remove children and start over
            old_arch = self.journal[op_id]['properties']['arch_height']
            old_sash = self.journal[op_id]['properties']['sash']
            old_shutter = self.journal[op_id]['properties']['shutter']
            if (old_arch != self.props.arch_height) or (old_sash != self.props.sash) or (old_shutter != self.props.shutter):
                print("reset window", op_id)
                adj = self.journal['adjusting']

                first_child = self.journal.controlled_list(op_id)[0]
                lst = delete_record(self.obj, first_child)
                mm = ManagedMesh(self.obj)
                for child_op_id in lst:
                    mm.set_op(child_op_id)
                    mm.delete_current_verts()

                sel_info = SelectionInfo(from_dict=self.journal[op_id]['control_points'])
                faces = mm.get_faces(sel_info)
                for face in faces:
                    face.hide = False  # make selectable
                mm.to_mesh()
                mm.free()

                self.journal = Journal(self.obj)  # reload
                self.journal['adjusting'] = adj
                self.journal.flush()
            bpy.ops.ed.undo_push(message="Reset Add Window Children")

        return super().ensure_children(op_id)

    def get_script(self):
        """Script to position and create frame and window"""
        from .dynamic_enums import from_path, script_name, file_type
        divide_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Position_Feature')

        if self.props.arch_height > 0.1:
            frame_text = self.get_catalog_script(self.context, 'default', 'Windows', 'Standard_Arched_Window')
            inner_text = ""
            shutter_text = ""
        else:
            frame_text = self.get_catalog_script(self.context, 'default', 'Windows', 'Small_Window_Frame')
            if self.props.sash:
                inner_text = self.get_catalog_script(self.context, 'default', 'Windows', 'Sash_Window_Panes')
            else:
                inner_text = self.get_catalog_script(self.context, 'default', 'Windows', 'Large_Window_Fixed')
            if self.props.shutter:
                shutter_text = self.get_catalog_script(self.context, 'default', 'Windows', 'Shutters')
            else:
                shutter_text = ""

        dct_master = json.loads(divide_text)

        sel_info = SelectionInfo()
        sel_info.add_face(0, 1)  # add middle faces of divide
        sel_info.set_mode('GROUP')
        dct_frame = json.loads(frame_text)
        if shutter_text != "":  # don't delete the face we need because that would make poll fail
            rec = dct_frame["op3"]
            del dct_frame["op3"]
            dct_frame['controlled']["op0"] = [1]
            del dct_frame['controlled']["op3"]
            dct_frame['max_id'] = 2  # <-- this is why we can't have shutter with arch, we would wipe out the arch
        frame_op_id = merge_record_dct(dct_master, dct_frame, sel_info)

        if shutter_text != "":
            sel_info = SelectionInfo()
            sel_info.add_face(1, 1)  # add middle faces of divide
            sel_info.set_mode('GROUP')
            dct_shutter = json.loads(shutter_text)
            shutter_id = merge_record_dct(dct_master, dct_shutter, sel_info)
            # reinsert record - seems like an append function is needed to hide this
            # next_id = dct_master['max_id'] + 1
            # dct_master[wrap_id(next_id)] = rec
            # rec['control_points']['faces'] = {wrap_id(frame_op_id+1): [0]}
            # dct_master['controlled'][wrap_id(frame_op_id)].append(next_id)
            # dct_master['controlled'][wrap_id(next_id)]=[]
            # dct_master['max_id'] = next_id

        # for arch we're done, but for others
        if inner_text != "":
            sel_info = SelectionInfo()
            sel_info.add_face(frame_op_id+1, 0)  # inset base for window
            sel_info.set_mode('GROUP')
            dct_inner = json.loads(inner_text)
            inner_op_id = merge_record_dct(dct_master, dct_inner, sel_info)

        for k in range(dct_master['max_id']+1):
            v = dct_master[wrap_id(k)]
            #print(k, v['op_name'], list(v['control_points']['faces'].keys()))

        script_text = json.dumps(dct_master, cls=MyEncoder, indent=4)
        return script_text

    def child_count(self, arch_height, sash, shutter):
        # used by topology test to look for user added stuff
        if arch_height < 0.1:
            if not sash:
                if not shutter:
                    ct = 11
                else:
                    ct = 15
            else:
                if not shutter:
                    ct = 20
                else:
                    ct = 20  # 24 if we allowed shutters
        else:
            ct = 15
        return ct

    def recordset(self, op_id):
        dct_records = {}
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()
        # for i, c in enumerate(lst_c):
        #     print(i, c, self.journal.op_label(c), list(self.journal[c]['control_points']['faces'].keys()))

        # lst_c is depth first
        if self.props.arch_height < 0.1:
            if not self.props.sash:
                if not self.props.shutter:
                    ops = ['position', 'frame size', 'midline', 'frame', 'delete wall',
                           'glass size', 'glass frame', 'glass offset', 'delete reference', 'panes', 'mullions']

                else:
                    ops = ['position', 'frame size', 'midline', 'frame',  # 'delete wall',
                           'extend outside', 'shutter base', 'shutter frame', 'louvers', 'delete shutter base',
                           'glass size', 'glass frame', 'glass offset', 'delete reference', 'panes', 'mullions']
            else:
                if not self.props.shutter:
                    ops = ['position', 'frame size', 'midline', 'frame', 'delete wall',
                           'split sash', 'sash 1', 'sash 2', 'sash 1 frame', 'sash 2 frame',
                           'glass 1', 'glass 2', 'delete 1', 'delete 2', 'delete 3', 'delete 4',
                           'panes', 'mullions', 'panes 2', 'mullions2']
                else:
                    ops = ['position', 'frame size', 'midline', 'frame',  # 'delete wall',
                           'extend outside', 'shutter base', 'shutter frame', 'louvers', 'delete shutter base',
                           'split sash', 'sash 1', 'sash 2', 'sash 1 frame', 'sash 2 frame',
                           'glass 1', 'glass 2', 'delete 1', 'delete 2', 'delete 3', 'delete 4',
                           'panes', 'mullions', 'panes 2', 'mullions2']
        else:
            # if not self.props.shutter:
            ops = ['position', 'frame size', 'midline', 'frame', 'delete wall',
                   'arch cut', 'arch midline', 'delete arch wall', 'arch frame',
                   'glass size', 'glass frame', 'glass offset', 'delete reference', 'panes', 'mullions'
                   ]
            # else:
            #     ops = ['position', 'frame size', 'midline', 'frame',  # 'delete wall',
            #            'extend outside', 'shutter base', 'shutter frame', 'louvers', 'delete shutter base',
            #            'arch cut', 'arch midline', 'delete arch wall', 'arch frame',
            #            'glass size', 'glass frame', 'glass offset', 'delete reference', 'panes', 'mullions'
            #            ]

        for i, txt in enumerate(ops):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
            #print(i, j, txt)

        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple/Arched Window"

        window_w = {'SMALL': 0.63, 'STANDARD': 0.81, 'LARGE': 1.26}[self.props.window_size]
        window_h = {'SMALL': 0.90, 'STANDARD': 1.20, 'LARGE': 1.98}[self.props.window_size]
        trim_w = {'SMALL': 0.076, 'STANDARD': 0.076, 'LARGE': 0.1}[self.props.window_size]
        frame_width = window_w + 2 * trim_w
        frame_ht = window_h + 2 * trim_w

        # we use wall size to position window vertically
        mm = ManagedMesh(self.obj)
        sel_info = self.journal.get_sel_info(op_id)
        faces = mm.get_faces(sel_info)
        poly = SmartPoly(CoordSys(mm, faces[0]), pt_list=faces[0], break_link=True)
        mm.free()
        if abs(poly.coord_sys.ydir[2]) > abs(poly.coord_sys.xdir[2]):
            wall_ht = poly.box_size.y
        else:
            wall_ht = poly.box_size.x
        top = 2.04 + trim_w  # try to line up with door tops
        base = top - frame_ht
        if self.props.arch_height > 0.1:
            base = base - self.props.arch_height
            if base < 0.6:  # center if too low
                base = (wall_ht - frame_ht - self.props.arch_height) / 2
        elif base < 0.6:  # center if too low
            base = (wall_ht - frame_ht) / 2

        child_rec = dct_records['position']
        child_rec['properties']['offset']['offset_x'] = self.props.offset_x
        child_rec['properties']['size']['size_x'] = frame_width

        child_rec = dct_records['frame size']
        child_rec['properties']['size']['size_y'] = frame_ht
        child_rec['properties']['offset']['offset_y'] = base

        child_rec = dct_records['frame']
        child_rec['properties']['size']['size_y'] = self.props.wall_thickness
        child_rec['properties']['size']['size_x'] = trim_w
        child_rec['properties']['inset'] = -trim_w/2

        child_rec = dct_records['midline']
        child_rec['properties']['extrude_distance'] = -self.props.wall_thickness/2
        if self.props.arch_height > 0.1:
            child_rec['properties']['size']['size_y'] = -trim_w  # no top trim
        else:
            child_rec['properties']['size']['size_y'] = -2 * trim_w
        child_rec['properties']['size']['size_x'] = -2 * trim_w
        child_rec['properties']['position']['offset_x'] = trim_w
        child_rec['properties']['position']['offset_y'] = trim_w

        # grid divide for panes
        child_rec = dct_records['panes']
        child_rec['properties']['count_x'] = self.props.x_panes - 1
        child_rec['properties']['count_y'] = self.props.y_panes - 1

        if self.props.sash:
            child_rec = dct_records['panes 2']
            child_rec['properties']['count_x'] = self.props.x_panes - 1
            child_rec['properties']['count_y'] = self.props.y_panes - 1

        if self.props.arch_height > 0.1:
            child_rec = dct_records['arch cut']
            child_rec['properties']['size']['size_y'] = self.props.arch_height
            ratio = self.props.arch_height/(0.5*frame_width)
            if ratio > 1:
                child_rec['properties']['arch']['arch_type'] = 'GOTHIC'
            elif ratio == 1:
                child_rec['properties']['arch']['arch_type'] = 'ROMAN'
            elif ratio > 0.5:
                child_rec['properties']['arch']['arch_type'] = 'OVAL'
            else:
                child_rec['properties']['arch']['arch_type'] = 'TUDOR'

            child_rec = dct_records['arch midline']
            child_rec['properties']['extrude_distance'] = -self.props.wall_thickness / 2

            child_rec = dct_records['arch frame']
            child_rec['properties']['size']['size_y'] = self.props.wall_thickness
            child_rec['properties']['size']['size_x'] = trim_w
            child_rec['properties']['inset'] = -trim_w / 2

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)  # after reading props since the records change based on selections

        child_rec = dct_records['panes']
        self.props.x_panes = child_rec['properties']['count_x'] + 1
        self.props.y_panes = child_rec['properties']['count_y'] + 1

        child_rec = dct_records['position']
        self.props.offset_x = child_rec['properties']['offset']['offset_x']

        # if self.props.arch_height > 0: not needed because the arch type is hidden from user

    def test_topology(self, op_id):
        # arch or no arch could break other children (manual entry in space above window)
        # don't erase and rebuild if any descendants other than those we made
        # check comes before ensure children and write_props
        dct, lst = self.journal.child_ops(op_id)
        num_children = len(lst)
        if num_children == 0:
            return False  # no problems

        old_ht = self.journal[op_id]['properties']['arch_height']
        old_sash = self.journal[op_id]['properties']['sash']
        old_shutter = self.journal[op_id]['properties']['shutter']
        changed = (old_ht < 0.1) != (self.props.arch_height < 0.1)
        if changed:
            if num_children != self.child_count(old_ht, old_sash, old_shutter):
                print("children", num_children, self.child_count(old_ht, old_sash, old_shutter))
                return True

        if changed:  # erase children and start over
            print("changed compound, delete children")
            self.delete_children(op_id)
        return False


class QARCH_OT_add_door(CompoundOperator):
    bl_idname = "qarch.add_door"
    bl_label = "Add Door"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleDoorProperty)

    def ensure_children(self, op_id):
        """Called by invoke to make sure the child script is in place"""
        lst_controlled = self.journal.controlled_list(op_id)
        if len(lst_controlled) > 0:  # not first time called
            # if we swap in/out, it changes child count
            # we must remove children and start over
            old_open = self.journal[op_id]['properties']['open_in']
            old_finish = self.journal[op_id]['properties']['finish']
            if (old_open != self.props.open_in) or (old_finish != self.props.finish):
                print("reset door", op_id)
                adj = self.journal['adjusting']

                first_child = self.journal.controlled_list(op_id)[0]
                lst = delete_record(self.obj, first_child)
                mm = ManagedMesh(self.obj)
                for child_op_id in lst:
                    mm.set_op(child_op_id)
                    mm.delete_current_verts()
                # make sure compound faces exists
                # mm.select_operation(op_id)
                # print(mm.get_selection_info().to_dict())
                mm.to_mesh()
                mm.free()

                self.journal = Journal(self.obj)  # reload
                self.journal['adjusting'] = adj
                self.journal.flush()

        return super().ensure_children(op_id)

    def get_script(self):
        """Merges door frame, in or out door, and door finish scripts"""
        from .dynamic_enums import from_path, script_name, file_type
        divide_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Position_Feature')
        frame_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Std_Door_Frame_ext')
        if self.props.open_in:
            door_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Std_Door_In_Hinge_Left')
        else:
            door_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Std_Door_Out_Hinge_Left')
        finish_file = self.props.finish
        if len(finish_file) > 3:
            category, style, s_name = from_path(pathlib.Path(finish_file))
            finish_text = self.get_catalog_script(self.context, style, category, s_name)

        else:  # plain
            finish_text = ""

        dct_master = json.loads(divide_text)

        sel_info = SelectionInfo()
        sel_info.add_face(0, 1)  # add middle faces of divide
        sel_info.set_mode('GROUP')
        dct_frame = json.loads(frame_text)
        frame_op_id = merge_record_dct(dct_master, dct_frame, sel_info)

        sel_info = SelectionInfo()
        sel_info.add_face(frame_op_id + 1, 0)  # link to face in center of wall
        sel_info.flag_op(frame_op_id+1, sel_info.ALL_FACES)
        sel_info.set_mode('GROUP')
        dct_door = json.loads(door_text)
        door_op_id = merge_record_dct(dct_master, dct_door, sel_info)

        if finish_text != "":
            # op 8/0 and op 16/4 are the door faces for open-in, add 1 to op for open-out (starts with flip normal)
            # frame_op_id is 1
            if self.props.open_in:
                offset = 1
            else:
                offset = 0
            sel_info = SelectionInfo()

            sel_info.add_face(6 + offset + frame_op_id, 4)  # add first side of door
            sel_info.set_mode('SINGLE')  # so user can change the finish individually later
            dct_finish = json.loads(finish_text)
            finish_op_id = merge_record_dct(dct_master, dct_finish, sel_info)

            if self.props.open_in:
                offset = 1
            else:
                offset = 0
            sel_info = SelectionInfo()

            sel_info.add_face(13 + offset + frame_op_id, 0)  # add last side of door
            sel_info.set_mode('SINGLE')  # so user can change the finish individually later
            dct_finish = json.loads(finish_text)
            finish_op_id2 = merge_record_dct(dct_master, dct_finish, sel_info)

        script_text = json.dumps(dct_master, cls=MyEncoder, indent=4)
        return script_text

    def recordset(self, op_id):
        dct_c, lst_c = self.journal.child_ops(op_id)
        #print("children of {}".format(op_id))
        lst_c.sort()
        # for i, c in enumerate(lst_c):
        #     print(i, self.journal.op_label(c), c)
        # ops
        #   0 grid divide (center doors)  size.size_x for frame width
        #     1 grid divide (door height) size.size_y for frame height
        #       2 inset polygon (center in thickness)  extrude_distance
        #       3 face tag (delete start poly)
        #         4 solidify edges (frame opening)  size.size_y
        #         [add 1 to these for inward door, 5 would be flip normal]
        #           5 inset polygon (door size)
        #             6 solidify edges (trim door stop)
        #             7 extrude (door thickness)
        #             8 oriented (wood door)
        #             9=8 oriented duplicate
        #               10 solidify edges (hinges)  side_list
        #               11 inset polygon (handle position)  position.offset_x
        #                  12 extrude (handle mount)
        #                     13 import mesh (inside handle)  category_item
        #                  14 import mesh (outside handle)  category_item
        #             15 flip_normal (flip door face)
        #
        # we did not include any of the finish operations, those will not be customizable from the compound operator
        # for reference they are children of 15 and 8
        dct_records = {}
        for i, txt in enumerate(['frame width', 'frame height', 'center in thickness', 'delete start poly',
                                 'frame opening', 'door size', 'trim door stop', 'door thickness', 'wood door',
                                 'wood door', 'hinges', 'handle position', 'handle mount', 'outside handle',
                                 'inside handle', 'flip door face', ]):

            if self.props.open_in and i > 4:
                i = i + 1
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt

        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Door Macro"

        trim_width = 0.076
        handle_pos = 0.72 / 2 - 0.06  # standard
        child_rec = dct_records['frame width']
        child_rec['properties']['offset']['offset_x'] = self.props.offset_x
        if self.props.width == 'NARROW':
            child_rec['properties']['size']['size_x'] = 0.526 + trim_width * 2
            handle_pos = 0.52 / 2 - 0.06
        elif self.props.width == 'STANDARD':
            child_rec['properties']['size']['size_x'] = 0.726 + trim_width * 2
        elif self.props.width == 'WIDE':
            trim_width = 0.1
            handle_pos = 0.92 / 2 - 0.06
            child_rec['properties']['size']['size_x'] = 0.926 + trim_width * 2

        child_rec = dct_records['frame height']
        child_rec['properties']['size']['size_y'] = 2.04 + trim_width

        child_rec = dct_records['center in thickness']
        child_rec['properties']['extrude_distance'] = -self.props.wall_thickness / 2

        child_rec = dct_records['frame opening']
        child_rec['properties']['size']['size_y'] = self.props.wall_thickness

        child_rec = dct_records['hinges']
        child_rec2 = dct_records['handle position']

        if self.props.open_in:
            if self.props.left_hinge:
                child_rec['properties']['side_list'] = "1"
                child_rec2['properties']['position']['offset_x'] = -handle_pos
            else:
                child_rec['properties']['side_list'] = "3"
                child_rec2['properties']['position']['offset_x'] = handle_pos
        else:
            if self.props.left_hinge:
                child_rec['properties']['side_list'] = "3"
                child_rec2['properties']['position']['offset_x'] = handle_pos
            else:
                child_rec['properties']['side_list'] = "1"
                child_rec2['properties']['position']['offset_x'] = -handle_pos

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])
        # dct_records = self.recordset(op_id)


class QARCH_OT_add_portico(CompoundOperator):
    bl_idname = "qarch.add_portico"
    bl_label = "Add Portico"
    bl_description = "Apply to section over door"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimplePorticoProperty)

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        style = 'default'
        category = 'Doors'
        script_name = "Portico"
        script_text = self.get_catalog_script(self.context, style, category, script_name)
        return script_text

    def recordset(self, op_id):
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()
        lst = []
        for c in lst_c:  # we extruded 2 faces at once, so all remaining ops show up double in the list
            if c not in lst:
                lst.append(c)
        lst_c = lst
        # for i, c in enumerate(lst_c):
        #     print(i, c, self.journal.op_label(c), list(self.journal[c]['control_points']['faces'].keys()))

        dct_records = {}
        ops = ['soffit', 'triangle', 'extrude depth', 'orient roof', 'material roof',
               'inset facing', 'recess facing', 'pad 1', 'pad 2', 'flip 1', 'flip 2', 'extrude post']
        for i, txt in enumerate(ops):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Railing"

        dct_records = self.recordset(op_id)

        child_rec = dct_records['soffit']
        child_rec['properties']['size']['size_x'] = self.props.width
        child_rec['properties']['size']['size_y'] = self.props.soffit

        child_rec = dct_records['triangle']
        child_rec['properties']['size']['size_y'] = self.props.height

        child_rec = dct_records['extrude depth']
        child_rec['properties']['distance'] = self.props.depth

        child_rec = dct_records['pad 1']
        child_rec['properties']['position']['offset_y'] = self.props.depth - 0.152

        child_rec = dct_records['pad 2']
        child_rec['properties']['position']['offset_y'] = self.props.depth - 0.152
        child_rec['properties']['position']['offset_x'] = self.props.width - 0.152

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)
        # in case user edited these directly, we can learn the values
        child_rec = dct_records['soffit']
        self.props.width = child_rec['properties']['size']['size_x']
        self.props.soffit = child_rec['properties']['size']['size_y']

        child_rec = dct_records['triangle']
        self.props.height = child_rec['properties']['size']['size_y']

        child_rec = dct_records['extrude depth']
        self.props.depth = child_rec['properties']['distance']


class QARCH_OT_add_rail(CompoundOperator):
    bl_idname = "qarch.add_rail"
    bl_label = "Add Railing"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleRailProperty)

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        # or load one from the catalog
        style = 'default'
        category = 'Railings'
        script_name = "Simple_Railings"
        script_text = self.get_catalog_script(self.context, style, category, script_name)
        return script_text

    def recordset(self, op_id):
        dct_c, lst_c = self.journal.child_ops(op_id)
        # for c in lst_c:
        #     print(self.journal.op_label(c))
        lst_c.sort()
        ops = ['root operation', 'corner post', 'top and bottom rail', 'space verticals', 'verticals',
               'clear between', 'extend rail down']
        dct_records = {}
        for i, txt in enumerate(ops):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Railing"

        dct_records = self.recordset(op_id)

        child_rec = dct_records['corner post']
        child_rec['properties']['size']['size_x'] = self.props.post_size
        child_rec['properties']['size']['size_y'] = self.props.post_size

        child_rec = dct_records['space verticals']
        child_rec['properties']['size']['size_x'] = self.props.rail_spacing

        child_rec = dct_records['verticals']
        if self.props.turned:
            child_rec['properties']['size']['size_y'] = 1
            child_rec['properties']['size']['is_relative_y'] = True
            child_rec['properties']['shape_type'] = 'CATALOG'
            child_rec['properties']['revolutions'] = 6
        else:
            child_rec['properties']['size']['size_y'] = self.props.vert_size
            child_rec['properties']['size']['is_relative_y'] = False
            child_rec['properties']['shape_type'] = 'NGON'

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)
        child_rec = dct_records['corner post']
        self.props.post_size = child_rec['properties']['size']['size_x']

        child_rec = dct_records['space verticals']
        self.props.rail_spacing = child_rec['properties']['size']['size_x']

        child_rec = dct_records['verticals']
        self.props.vert_size = child_rec['properties']['size']['size_x']
        if child_rec['properties']['shape_type'] == 'CATALOG':
            self.props.turned = True
        else:
            self.props.turned = False


class QARCH_OT_add_deck(CompoundOperator):
    bl_idname = "qarch.add_deck"
    bl_label = "Add Deck"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Add deck or balcony, apply to horizontal surface"

    props: PointerProperty(type=DeckProperty)

    def ensure_children(self, op_id):
        """Called by invoke to make sure the child script is in place"""
        lst_controlled = self.journal.controlled_list(op_id)
        if len(lst_controlled) > 0:  # not first time called
            # if we swap in/out, it changes child count
            # we must remove children and start over
            old_roof = self.journal[op_id]['properties'].get('roof', False)
            if old_roof != self.props.roof:
                print("reset deck", op_id)
                adj = self.journal['adjusting']

                first_child = self.journal.controlled_list(op_id)[0]
                lst = delete_record(self.obj, first_child)
                mm = ManagedMesh(self.obj)
                for child_op_id in lst:
                    mm.set_op(child_op_id)
                    mm.delete_current_verts()

                sel_info = SelectionInfo(from_dict=self.journal[op_id]['control_points'])
                faces = mm.get_faces(sel_info)
                for face in faces:
                    face.hide = False  # make selectable
                mm.to_mesh()
                mm.free()

                self.journal = Journal(self.obj)  # reload
                self.journal['adjusting'] = adj
                self.journal.flush()
            bpy.ops.ed.undo_push(message="Reset Add Deck Children")

        return super().ensure_children(op_id)

    @classmethod
    def poll(cls, context):
        # because each gable has a unique direction
        if cls.is_face_selected(context):
            mm = ManagedMesh(context.object)
            sel_info = mm.get_selection_info()
            faces = mm.get_faces(sel_info)
            if faces[0].normal[2] > 0.99:
                return True

        return False

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        # or load one from the catalog
        style = 'default'
        category = 'Decks'
        script_name = "Deck_Base"
        script_text = self.get_catalog_script(self.context, style, category, script_name)
        if self.props.roof:
            roof_text = self.get_catalog_script(self.context, style, category, 'Deck_Roof')
            dct_master = json.loads(script_text)

            sel_info = SelectionInfo()
            sel_info.add_face(0, 0)  # add middle faces of divide
            sel_info.set_mode('GROUP')
            dct_roof = json.loads(roof_text)
            roof_op_id = merge_record_dct(dct_master, dct_roof, sel_info)

            script_text = json.dumps(dct_master, cls=MyEncoder, indent=4)

        return script_text

    def recordset(self, op_id):
        dct_c, lst_c = self.journal.child_ops(op_id)
        # for c in lst_c:
        #     print(self.journal.op_label(c))
        lst_c.sort()
        ops = ['inset clipped', 'prep rail', 'delete prep', 'extrude']
        if self.props.roof:
            ops = ops + ['raise roof', 'soffit', 'roof']
        dct_records = {}
        for i, txt in enumerate(ops):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Railing"

        dct_records = self.recordset(op_id)

        child_rec = dct_records['inset clipped']
        child_rec['properties']['size'] = self.props.size.to_dict()
        child_rec['properties']['position'] = self.props.position.to_dict()
        child_rec['properties']['extrude_distance'] = self.props.elevation
        child_rec['properties']['poly']['num_sides'] = self.props.sides
        child_rec['properties']['poly']['start_angle'] = -math.pi/self.props.sides

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)

        child_rec = dct_records['inset clipped']
        self.props.size.from_dict(child_rec['properties']['size'])
        self.props.position.from_dict(child_rec['properties']['position'])
        self.props.elevation = child_rec['properties']['extrude_distance']
        self.props.sides = child_rec['properties']['poly']['num_sides']


class QARCH_OT_extend_gable(CompoundOperator):
    bl_idname = "qarch.extend_gable"
    bl_label = "Extend Gable"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Extend hip face to gable, single or region required"

    props: PointerProperty(type=ExtendGableProperty)

    @classmethod
    def poll(cls, context):
        # because each gable has a unique direction
        if cls.is_face_selected(context):
            #mode = context.preferences.addons['qarch'].preferences.select_mode
            #if mode in {'SINGLE', 'REGION'}:
            return True
        return False

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # this script is not generally applicable because it has a globally set direction vector
        # so we remove it from the catalog and only have it here
        script_text = """{
            "max_id": 5,
            "controlled": {
                "op-1": [
                    0,
                    4
                ],
                "op0": [
                    1
                ],
                "op1": [
                    2
                ],
                "op2": [
                    3,
                    5
                ],
                "op3": [],
                "op4": [],
                "op5": []
            },
            "adjusting": [],
            "face_tags": [],
            "version": "0.1",
            "op0": {
                "op_id": 0,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.0,
                    "steps": 1,
                    "on_axis": true,
                    "axis": {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0
                    },
                    "twist": 0.0,
                    "align_end": true,
                    "size": {
                        "size_x": 1.0,
                        "is_relative_x": true,
                        "size_y": 1.0,
                        "is_relative_y": true
                    },
                    "flip_normals": false,
                    "side_material": "BT_Roof",
                    "center_material": "BT_Wall"
                },
                "control_points": {
                    "faces": {
                        "op-1": [
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "REGION"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [
                                0,
                                2
                            ]
                        ],
                        "Tops": [
                            [
                                3,
                                3
                            ]
                        ]
                    },
                    "moduli": {
                        "Sides": 3,
                        "Tops": 0
                    }
                }
            },
            "op1": {
                "op_id": 1,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0,
                        "is_relative_x": false,
                        "center_x": true,
                        "offset_y": 0.0,
                        "is_relative_y": false
                    },
                    "size": {
                        "size_x": -0.20000000298023224,
                        "is_relative_x": false,
                        "size_y": -0.10000000149011612,
                        "is_relative_y": false
                    },
                    "join": "BRIDGE",
                    "add_perimeter": false,
                    "shape_type": "SELF",
                    "poly": {
                        "num_sides": 4,
                        "start_angle": -0.7853981852531433
                    },
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN"
                    },
                    "frame": 0.10000000149011612,
                    "frame_material": "BT_Brass",
                    "super_curve": {
                        "x": 1.0,
                        "y": 1.0,
                        "sx": 1.0,
                        "sy": 1.0,
                        "px": 1.0,
                        "py": 1.0,
                        "pn": 1.0,
                        "start_angle": 0.0
                    },
                    "local_object": {
                        "search_text": "",
                        "object_name": "0",
                        "rotate": [
                            0.0,
                            0.0,
                            0.0
                        ]
                    },
                    "catalog_object": {
                        "style_name": "default",
                        "category_name": "Decks",
                        "search_text": "",
                        "category_item": "0",
                        "rotate": [
                            0.0,
                            0.0,
                            0.0
                        ]
                    },
                    "resolution": 4,
                    "center_material": "BT_Brick",
                    "extrude_distance": 0.0
                },
                "control_points": {
                    "faces": {
                        "op0": [
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Bridge": [
                            [
                                1,
                                3
                            ]
                        ],
                        "Center": [
                            [
                                0,
                                0
                            ]
                        ],
                        "Frame": []
                    },
                    "moduli": {
                        "Bridge": 0,
                        "Center": 0,
                        "Frame": 0
                    }
                }
            },
            "op2": {
                "op_id": 2,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.10000000149011612,
                    "steps": 1,
                    "on_axis": false,
                    "axis": {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0
                    },
                    "twist": 0.0,
                    "align_end": false,
                    "size": {
                        "size_x": 1.0,
                        "is_relative_x": true,
                        "size_y": 1.0,
                        "is_relative_y": true
                    },
                    "flip_normals": false,
                    "side_material": "BT_Roof",
                    "center_material": "BT_Trim"
                },
                "control_points": {
                    "faces": {
                        "op1": [
                            2,
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {
                        "op1": 2
                    },
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [
                                0,
                                3
                            ],
                            [
                                5,
                                8
                            ]
                        ],
                        "Tops": [
                            [
                                4,
                                4
                            ],
                            [
                                9,
                                9
                            ]
                        ]
                    },
                    "moduli": {
                        "Sides": 4,
                        "Tops": 0
                    }
                }
            },
            "op3": {
                "op_id": 3,
                "op_name": "QARCH_OT_set_face_tag",
                "properties": {
                    "tag": "TRIM"
                },
                "control_points": {
                    "faces": {
                        "op2": [
                            2,
                            3,
                            4,
                            6,
                            7,
                            9
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "All": [
                            [
                                0,
                                5
                            ]
                        ]
                    },
                    "moduli": {
                        "All": 0
                    }
                }
            },
            "op4": {
                "op_id": 4,
                "op_name": "QARCH_OT_set_face_radial",
                "properties": {
                    "radial": [
                        0.0,
                        0.0,
                        1.0
                    ]
                },
                "control_points": {
                    "faces": {
                        "op0": [
                            0,
                            1,
                            2
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {"ranges": {"All": [[0, 1]]}, "moduli": {"All": 0}}
            },
            "op5": {
                "op_id": 5,
                "op_name": "QARCH_OT_set_face_radial",
                "properties": {
                    "radial": [
                        0.0,
                        0.0,
                        1.0
                    ]
                },
                "control_points": {
                    "faces": {
                        "op2": [
                            2,
                            8
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {"ranges": {"All": [[0, 1]]}, "moduli": {"All": 0}}
            },
            "description": "Extend hip to gable"
        }"""
        return script_text

    def recordset(self, op_id):
        # ops
        # 0 extrude (directed)
        #  1 inset polygon (inset)
        #    2 extrude (soffit)
        #      3 set tag (trim)
        #  4 set radial (y direction for roof)
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()
        # for c in lst_c:
        #     print(self.journal.op_label(c))
        dct_records = {}
        for i, txt in enumerate(['directed', 'inset', 'soffit', 'face tag', "radial"]):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Gable"

        sel_info = self.journal.get_sel_info(op_id)
        mm, lst_orig_poly = _common_start(self.obj, sel_info, break_link=True)
        poly = lst_orig_poly[0]
        mm.free()
        poly.coord_sys.origin = poly.calc_center_median()
        poly.calc_2d()

        z = Vector((0,0,1))
        edir = z.cross(poly.coord_sys.xdir)
        if edir.dot(poly.normal()) < 0:
            edir = -edir
        edir.normalize()

        v = poly.coord_sys.make_3d(poly.bbox_min)
        v0 = poly.coord_sys.origin
        v1 = v - v0
        dist = v1.dot(edir)

        child_rec = dct_records['directed']
        child_rec['properties']['axis']['x'] = edir.x
        child_rec['properties']['axis']['y'] = edir.y
        child_rec['properties']['axis']['z'] = edir.z
        child_rec['properties']['distance'] = dist

        child_rec = dct_records['inset']
        child_rec['properties']['size']['size_x'] = -self.props.soffit_width * 2
        child_rec['properties']['size']['size_y'] = -self.props.soffit_width * 0.8

        child_rec = dct_records['soffit']
        child_rec['properties']['distance'] = self.props.overhang

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        child_rec = dct_records['inset']
        self.props.soffit_width = -child_rec['properties']['size']['size_x'] / 2

        child_rec = dct_records['soffit']
        self.props.overhang = child_rec['properties']['distance']


class QARCH_OT_add_dormer(CompoundOperator):
    bl_idname = "qarch.add_dormer"
    bl_label = "Add Dormer"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Add dormer to roof, single or region required"

    props: PointerProperty(type=DormerProperty)

    @classmethod
    def poll(cls, context):
        # because each gable has a unique direction
        if cls.is_face_selected(context):
            mode = context.preferences.addons['qarch'].preferences.select_mode
            if mode in {'SINGLE', 'REGION'}:
                return True
        return False

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        style = 'default'
        category = 'Roof'
        script_name = "Dormer"
        script_text = self.get_catalog_script(self.context, style, category, script_name)
        return script_text

    def recordset(self, op_id):
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()
        lst = []
        for c in lst_c:  # we extruded 2 faces at once, so all remaining ops show up double in the list
            if c not in lst:
                lst.append(c)
        lst_c = lst
        # for c in lst_c:
        #     print(self.journal.op_label(c))
        dct_records = {}
        ops = ['position', 'base', 'extrude base', 'triangle', 'extrude roof',
               'radial 1', 'inset soffit', 'extrude soffit', 'radial 2',
               'inset window', 'extrude window', 'radial 3', 'siding', 'delete',
               'panes', 'mullions']
        for i, txt in enumerate(ops):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Dormer"

        child_rec = dct_records['position']
        child_rec['properties']['offset']['offset_x'] = self.props.offset_x

        child_rec = dct_records['inset window']
        if self.props.octagon_window:
            child_rec['properties']['poly']['num_sides'] = 8
            child_rec['properties']['poly']['start_angle'] = -math.pi/8
        else:
            child_rec['properties']['poly']['num_sides'] = 4
            child_rec['properties']['poly']['start_angle'] = -math.pi/4

        sel_info = self.journal.get_sel_info(op_id)
        mm, lst_poly = _common_start(self.obj, sel_info, break_link=True)
        poly = lst_poly[0]
        mm.free()
        poly.coord_sys.origin = poly.calc_center_median()
        poly.calc_2d()

        z = Vector((0,0,1))
        edir = z.cross(poly.coord_sys.xdir)
        if edir.dot(poly.normal()) < 0:
            edir = -edir
        edir.normalize()

        child_rec = dct_records['extrude base']
        child_rec['properties']['axis']['x'] = edir.x
        child_rec['properties']['axis']['y'] = edir.y
        child_rec['properties']['axis']['z'] = edir.z

        child_rec = dct_records['extrude roof']
        child_rec['properties']['axis']['x'] = edir.x
        child_rec['properties']['axis']['y'] = edir.y
        child_rec['properties']['axis']['z'] = edir.z

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)

        child_rec = dct_records['position']
        self.props.offset_x = child_rec['properties']['offset']['offset_x']

        child_rec = dct_records['inset window']
        self.props.octagon_window = (child_rec['properties']['poly']['num_sides'] == 8)



