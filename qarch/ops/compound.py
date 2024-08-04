import bpy
from .. import __package__ as base_package
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

    def get_script(self):
        """Script to position and create frame and window"""
        shutter = ""
        if self.props.window_count == 1:
            if self.props.shutters not in ['0','N/A','']:
                shutter = pathlib.Path(self.props.shutters)

        outer_text = self.get_catalog_script(self.context, 'default', 'Windows', "Outer_Window")
        inner_text = self.get_catalog_script(self.context, 'default', 'Windows', "Inner_Window")

        dct_master = json.loads(outer_text)
        dct_master['op11']['properties']['count_x'] = self.props.window_count - 1
        dct_master['op11']['gen_info']['ranges']['All'] = [[0, self.props.window_count-1]]
        if not self.props.outer_key:  # drop last operation to extrude the keystone
            del dct_master['op15']
            dct_master['max_id'] = 14
            del dct_master['controlled']['op15']
            dct_master['controlled']['op4'] = dct_master['controlled']['op4'][:-1]

        if shutter != "":
            sel_info = SelectionInfo()
            sel_info.add_face(14, 4)  # left frame extrude
            sel_info.set_mode('GROUP')
            dct_shutter = json.loads(shutter.read_text())
            for op_id in dct_shutter['controlled'].keys():
                if op_id =="op-1":
                    continue
                dct_shutter[op_id]['description'] = "Left " + dct_shutter[op_id]['description']
            left_op_id = merge_record_dct(dct_master, dct_shutter, sel_info)
            sel_info = SelectionInfo()
            sel_info.add_face(14, 9)  # right frame extrude
            sel_info.set_mode('GROUP')
            dct_shutter = json.loads(shutter.read_text())
            for op_id in dct_shutter['controlled'].keys():
                if op_id =="op-1":
                    continue
                dct_shutter[op_id]['description'] = "Right " + dct_shutter[op_id]['description']
            right_op_id = merge_record_dct(dct_master, dct_shutter, sel_info)

        for i in range(self.props.window_count):
            sel_info = SelectionInfo()
            sel_info.add_face(11, i)
            sel_info.set_mode('GROUP')
            dct_inner = json.loads(inner_text)
            if self.props.sash == "Picture":  # use for single pane
                for op in range(10,13):
                    del dct_inner[wrap_id(op)]
                    del dct_inner['controlled'][wrap_id(op)]
                dct_inner['max_id'] = 9
                dct_inner['controlled']['op6'] = dct_inner['controlled']['op6'][:1]

            for op_id in dct_inner['controlled'].keys():
                if op_id == "op-1":
                    continue
                dct_inner[op_id]['description'] = f"W{i} " + dct_inner[op_id]['description']

            win_op_id = merge_record_dct(dct_master, dct_inner, sel_info)

        script_text = json.dumps(dct_master, cls=MyEncoder, indent=4)
        return script_text

    def recordset(self, op_id):
        dct_records = {}
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()

        for op in lst_c:
            rec = self.journal[op]
            txt = rec['description']
            if txt in dct_records:
                txt = txt + " " + str(op)
            dct_records[txt] = rec

        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
                by updating the journal text
                """
        from ..mesh.geom import _extract_size, _extract_offset
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
        self.journal[op_id]['description'] = "Simple Window"

        # we use wall size to position window
        mm = ManagedMesh(self.obj)
        sel_info = self.journal.get_sel_info(op_id)
        faces = mm.get_faces(sel_info)
        # using first selection, so don't apply to multiple different sizes
        poly = SmartPoly(CoordSys(mm, faces[0]), pt_list=faces[0], break_link=True)
        orig_material = self.obj.data.materials[faces[0].material_index].name

        mm.free()

        size = _extract_size(self.journal[op_id]['properties']['size'], poly.box_size)
        offset = _extract_offset(self.journal[op_id]['properties']['position'], poly.box_size, Vector(size))

        if self.props.shutters not in ['0', 'N/A', ''] and (self.props.window_count==1):
            dct_records['Right Shutter Base']['properties']['position']['offset_x'] = 1
            for rec in dct_records.values():
                if 'Shutter' in rec['description']:
                    for s in ['side_material', 'center_material', 'frame_material', 'material']:
                        if s in rec['properties']:
                            rec['properties'][s] = self.props.shutter_material
            rec_left_shutter = dct_records['Left Shutter Base']['properties']
            rec_right_shutter = dct_records['Right Shutter Base']['properties']
        else:
            rec_left_shutter = None

        # convert outer divides to non-proportional so we can apply to next wall
        # of different size and get matching window
        rec = dct_records['Set Width']['properties']  # grid divide
        rec_off = rec["offset"]
        rec_siz = rec["size"]
        for k in ['size_x', 'is_relative_x']:
            rec_siz[k] = self.journal[op_id]['properties']['size'][k]
        for k in ['offset_x', 'is_relative_x', 'center_x']:
            rec_off[k] = self.journal[op_id]['properties']['position'][k]

        if offset[0] == 0:  # change pointing of next
            op_dict = dct_records['Set Height']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 0
        else:
            op_dict = dct_records['Set Height']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 1

        rec = dct_records['Set Height']['properties']  # grid divide
        rec_off = rec["offset"]
        rec_siz = rec["size"]
        for k in ['size_y', 'is_relative_y', 'is_ratio_yx']:
            rec_siz[k] = self.journal[op_id]['properties']['size'][k]
        for k in ['offset_y', 'is_relative_y', 'center_y']:
            rec_off[k] = self.journal[op_id]['properties']['position'][k]

        if offset[1] == 0:  # change pointing of next
            op_dict = dct_records['Center in Wall']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 0
        else:
            op_dict = dct_records['Center in Wall']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 1

        rec = dct_records['Outer Apron']['properties']
        rec['offset']['offset_y'] = self.props.outer_width

        rec = dct_records['Center in Wall']['properties']
        rec['extrude_distance'] = -self.props.wall_thickness / 2

        rec = dct_records['Outer Arch']['properties']
        rec['frame'] = self.props.outer_width
        remainder = size[1] - self.props.outer_width  # subtract apron
        if self.props.outer_arch_type in ['ROMAN', 'TRIANGLE']:
            arch_ht = 0.5
        elif self.props.outer_arch_type == 'DUTCH':
            arch_ht = 0.4
        elif self.props.outer_arch_type in ['SQUARE', 'JACK']:
            arch_ht = 1
        elif self.props.outer_arch_type == 'ARABIC':
            arch_ht = 0.7
        elif self.props.outer_arch_type == 'GOTHIC':
            arch_ht = 0.866  # equilateral
        else:  # OVAL, TUDOR
            arch_ht = 0.3
        arch_ht = min(arch_ht, self.props.max_outer_arch)
        outer_calc_ht = arch_ht * size[0]
        drop_len = remainder - outer_calc_ht  #- 0.002  # leave sliver at top for surround ops
        if drop_len < self.props.trim_width:  # oops, too tall, need room for apron
            arch_ht = (remainder - self.props.trim_width)/size[0]
            drop_len = self.props.trim_width
            outer_calc_ht = arch_ht * size[0]
            print("adjusted outer arch ht to fit", arch_ht)
        # check for angled base
        adjust = False
        if (self.props.outer_arch_type == 'ROMAN') and (arch_ht < 0.5):
            adjust = True
        if adjust:
            drop_len = max(0, drop_len - self.props.outer_width/2)


        rec['size']['size_y'] = arch_ht
        rec['arch']['drop_length'] = drop_len
        rec['arch']['arch_type'] = self.props.outer_arch_type
        rec['arch']['keystone'] = self.props.outer_key
        rec['center_material'] = self.props.frieze_material
        rec['frame_material'] = self.props.outer_material
        if self.props.outer_material == 'BT_Brick':
            rec['arch']['key_material'] = 'BT_Brick_Color'
        else:
            rec['arch']['key_material'] = 'BT_Trim'

        rec = dct_records['Extrude Outer Apron']['properties']
        rec['distance'] = self.props.wall_thickness/2 + self.props.frame_protrude
        rec['center_material'] = self.props.outer_material
        rec['side_material'] = self.props.outer_material

        rec = dct_records['Intrude Outer Apron']['properties']
        rec['distance'] = -self.props.wall_thickness / 2 - self.props.frame_protrude
        rec['center_material'] = self.props.outer_material
        rec['side_material'] = self.props.outer_material

        rec = dct_records['Extrude Outer Frame']['properties']
        rec['distance'] = self.props.wall_thickness / 2 + self.props.lintel_protrude
        rec['center_material'] = self.props.outer_material
        rec['side_material'] = self.props.outer_material

        rec = dct_records['Intrude Outer Frame']['properties']
        rec['distance'] = -self.props.wall_thickness / 2 - self.props.lintel_protrude
        rec['center_material'] = self.props.outer_material
        rec['side_material'] = self.props.outer_material

        rec = dct_records['Extrude Outer Surround']['properties']
        rec['distance'] = self.props.wall_thickness / 2
        rec['center_material'] = orig_material

        rec = dct_records['Intrude Outer Surround']['properties']
        rec['distance'] = -self.props.wall_thickness / 2

        rec = dct_records['Divide Inner N']['properties']
        if self.props.outer_arch_type == 'ARABIC':   # grid divide fails on this shape
            self.props.window_count = 1
        rec['count_x'] = self.props.window_count - 1

        rec = dct_records['Outer Sill Cut']['properties']
        rec2 = dct_records['Outer Sill Extrude']['properties']
        if self.props.outer_material == 'BT_Brick':
            rec['offset']['offset_y'] = 0.002  # big brick sill
            rec2['center_material'] = self.props.outer_material
            rec2['side_material'] = self.props.outer_material
            rec2['distance'] = self.props.sill_protrude
        else:
            rec['offset']['offset_y'] = self.props.outer_width - 0.025  # one inch sill
            rec2['center_material'] = 'BT_Trim'
            rec2['side_material'] = 'BT_Trim'
            rec2['distance'] = self.props.sill_protrude

        rec = dct_records['Extrude Outer Sides']['properties']
        if self.props.hide_outer_sides:
            rec['distance'] = self.props.wall_thickness/2
            rec['center_material'] = orig_material
        else:
            rec['distance'] = self.props.wall_thickness / 2 + self.props.frame_protrude
            rec['center_material'] = self.props.outer_material
            rec['side_material'] = self.props.outer_material

        if rec_left_shutter is not None:
            rec_left_shutter['size']['size_x'] = (size[0] - 2*self.props.outer_width)/2
            rec_left_shutter['size']['size_y'] = -self.props.outer_width
            rec_left_shutter['size']['is_relative_x'] = False
            rec_left_shutter['size']['is_relative_y'] = False
            rec_left_shutter['position']['offset_x'] = self.props.outer_width * 0.75 - rec_left_shutter['size']['size_x']
            rec_left_shutter['position']['offset_y'] = 0.01
            rec_left_shutter['position']['is_relative_x'] = False
            rec_right_shutter['size']['size_x'] = (size[0] - 2*self.props.outer_width)/2
            rec_right_shutter['size']['size_y'] = -self.props.outer_width
            rec_right_shutter['size']['is_relative_x'] = False
            rec_right_shutter['size']['is_relative_y'] = False
            rec_right_shutter['position']['offset_x'] = self.props.outer_width * 0.25
            rec_right_shutter['position']['offset_y'] = 0.01
            rec_right_shutter['position']['is_relative_x'] = False

        if self.props.outer_key:
            rec = dct_records['Extrude Keystone']['properties']
            rec['distance'] =  self.props.wall_thickness/2 + self.props.lintel_protrude + 0.01
            rec['center_material'] = self.props.key_material
            rec['side_material'] = self.props.key_material

        if self.props.outer_arch_type == 'JACK':
            top_arch_ht = outer_calc_ht - self.props.outer_width  # inset by frame thickness at top, a bit small for angled
        elif self.props.outer_arch_type == 'SQUARE':
            top_arch_ht = outer_calc_ht - self.props.outer_width/2  # not sure why different than jack
        else:
            top_arch_ht = outer_calc_ht
        fit_arch_ht = top_arch_ht
        full_outer = fit_arch_ht + drop_len

        if self.props.inner_arch_type in ['ROMAN', 'TRIANGLE']:
            arch_ht = 0.5
        elif self.props.inner_arch_type == 'DUTCH':
            arch_ht = 0.4
        elif self.props.inner_arch_type in ['SQUARE', 'JACK']:
            arch_ht = 1
        elif self.props.inner_arch_type == 'ARABIC':
            arch_ht = 0.7
        elif self.props.inner_arch_type == 'GOTHIC':
            arch_ht = 0.866  # equilateral
        else: # OVAL, TUDOR
            arch_ht = 0.3
        arch_ht = min(arch_ht, self.props.max_inner_arch)
        top_gap = self.props.top_gap
        fit_arch_ht = fit_arch_ht - top_gap
        old_drop = drop_len
        if self.props.outer_arch_type not in ['SQUARE', 'JACK']:  # decrease for arch at sides being lower
            if self.props.window_count == 2:
                fit_arch_ht = fit_arch_ht * 0.75
            else:
                fit_arch_ht = fit_arch_ht * 0.5
        else: # fake drop len higher
            drop_len = drop_len + fit_arch_ht

        if self.props.inner_arch_type in ['SQUARE', 'JACK']:
            fit_arch_ht = drop_len - top_gap  # only come up to arch start

        wwidth = (size[0]-2*self.props.outer_width) / self.props.window_count
        if self.props.outer_arch_type == 'JACK':  # narrower trim, rise over run = arch_ht
            theta = math.atan2(arch_ht,1)
            wwidth = (size[0]-2*self.props.outer_width*math.cos(theta)) / self.props.window_count

        # get inner arch height from divisions and stack on drop len to align
        inner_arch_ht = wwidth * arch_ht
        print("fit", fit_arch_ht, "drop", drop_len, "wwidth", wwidth, "ratio", arch_ht, "inner", inner_arch_ht)
        if fit_arch_ht < inner_arch_ht:
            if old_drop/2 > (inner_arch_ht - fit_arch_ht):  # fix by changing drop height
                old_drop = old_drop - (inner_arch_ht - fit_arch_ht)
            else:
                arch_ht = fit_arch_ht/wwidth
                if arch_ht < 0.3:
                    arch_ht = 0.3
                    inner_arch_ht = wwidth * arch_ht
                print("adjusted arch_ht", arch_ht)

        drop_len = old_drop
        if self.props.outer_arch_type in ['SQUARE', 'JACK']:  # reset drop height after faking for size calc
            if self.props.inner_arch_type in ['SQUARE', 'JACK']:
                if top_gap == 0:
                    # found that if there is no surround, it can extrude in z direction
                    dct_records['Extrude Outer Surround']['properties']['distance'] = 0
                    dct_records['Intrude Outer Surround']['properties']['distance'] = 0
                drop_len = full_outer - top_gap - inner_arch_ht - self.props.outer_width
            else:
                drop_len = full_outer - top_gap - inner_arch_ht - self.props.outer_width
        else:
            if self.props.inner_arch_type in ['SQUARE', 'JACK']:
                drop_len = old_drop - inner_arch_ht - top_gap
                if drop_len < 0:
                    drop_len = self.props.trim_width
                    arch_ht = (old_drop - top_gap - drop_len)/wwidth
                print("old", old_drop, "new", drop_len)
            else:
                drop_len = old_drop

        for i in range(self.props.window_count):
            prefix = f'W{i} '

            rec = dct_records[prefix + 'Inner Apron']['properties']
            rec['offset']['offset_y'] = self.props.trim_width

            rec = dct_records[prefix + 'Extrude Inner Apron']['properties']
            rec['distance'] = self.props.wall_thickness/2 + self.props.inner_protrude

            rec = dct_records[prefix + 'Intrude Inner Apron']['properties']
            rec['distance'] = -(self.props.wall_thickness / 2 + self.props.inner_protrude)

            rec = dct_records[prefix + 'Inner Arch']['properties']
            rec['frame'] = self.props.trim_width
            rec['size']['size_y'] = arch_ht
            rec['size']['size_x'] = 1 # (size[0])/self.props.window_count - 0.004  # avoid roundoff
            rec['size']['is_relative_x'] = True # False
            if (self.props.window_count==3) and (i==1):
                drop_len = drop_len + self.props.center_higher

            rec['arch']['drop_length'] = drop_len
            rec['arch']['arch_type'] = self.props.inner_arch_type
            rec['arch']['keystone'] = self.props.outer_key
            rec['center_material'] = self.props.frieze_material
            rec['frame_material'] = self.props.trim_material
            if self.props.trim_material == 'BT_Brick':
                rec['arch']['key_material'] = 'BT_Brick_Color'
            else:
                rec['arch']['key_material'] = 'BT_Trim'

            rec = dct_records[prefix + 'Intrude Inner Frame']
            rec['distance'] = -(self.props.wall_thickness/2 + self.props.inner_protrude)

            rec = dct_records[prefix + 'Extrude Inner Frame']
            rec['distance'] = self.props.wall_thickness / 2 + self.props.inner_protrude
            rec['center_material'] = self.props.trim_material
            rec['side_material'] = self.props.trim_material

            # now split for sashes
            rec = dct_records[prefix + 'Split Window']['properties']
            rec_in = dct_records[prefix + 'Position Inner Glass']['properties']
            if self.props.sash != "Picture":
                rec_out = dct_records[prefix + 'Position Outer Glass']['properties']
            else:
                rec_out = {'position':{},'size':{}}
            if self.props.sash in ['French', 'Sliding']:
                rec['count_x'] = 1
                rec['count_y'] = 0
                # clear y offset
                rec_in['position']['offset_y'] = 0.025
                rec_in['size']['size_y'] = -0.05
                rec_out['position']['offset_y'] = 0.025
                rec_out['position']['size_y'] = -0.05
                if self.props.sash == 'Sliding':  # add overlap
                    rec_in['size']['size_x'] = -0.0325
                    rec_out['position']['offset_x'] = 0.0125
                    rec_out['position']['size_x'] = -0.0325
            else:
                rec['count_x'] = 0
                rec['count_y'] = 1
                if self.props.sash == "Picture":  # use for single pane
                    rec['count_y'] = 0
                    rec_in['position']['offset_y'] = 0.025
                    rec_in['size']['size_y'] = -0.025
                elif self.props.sash == "Casement":  # 1/3 split
                    rec['offset']['offset_y'] = 0.67
                    rec['offset']['is_relative_y'] = True
                else:
                    if self.props.inner_arch_type in ['JACK', 'SQUARE']:
                        rec['offset']['offset_y'] = (inner_arch_ht + drop_len - self.props.trim_width)/2
                    else:
                        rec['offset']['offset_y'] = drop_len / 2

            if self.props.sash in ['Sliding', 'Hung']:
                rec_out['extrude_distance'] = 0.02
                rec_in['extrude_distance'] = -0.02
            else:
                rec_out['extrude_distance'] = 0
                rec_in['extrude_distance'] = 0

            for s in ['Inner Muntins', 'Outer Muntins']:
                if (self.props.sash == "Picture") and (s == 'Outer Muntins'):
                    continue
                rec = dct_records[prefix + s]['properties']
                rec['spacing'] = self.props.pane_size
                if self.props.muntin_angle == 0:
                    rec['angle_1'] = 0
                    rec['angle_2'] = math.pi / 2
                elif self.props.muntin_angle == math.pi / 2:
                    rec['angle_2'] = 0
                    rec['angle_1'] = math.pi / 2
                else:
                    rec['angle_1'] = self.props.muntin_angle
                    rec['angle_2'] = self.props.muntin_angle


        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        dct_records = self.recordset(op_id)  # after reading props since the records change based on selections


class QARCH_OT_add_door(CompoundOperator):
    bl_idname = "qarch.add_door"
    bl_label = "Add Door"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleDoorProperty)

    def get_script(self):
        """Merges door frame, in or out door, and door finish scripts"""
        script_text = self.get_catalog_script(self.context, 'default', 'Doors', 'Arched_Double_Door')
        finish_faces = [(13,0), (10,9), (18,0), (15,10)]
        dct_master = json.loads(script_text)

        if self.props.door_type in ["Left", "Right"]:  # single door
            # abuse journal
            j = Journal(self.obj)
            j.obj = None  # ensure no writeback
            j.jj = dct_master
            j.controlled = dct_master['controlled']
            if self.props.door_type == "Left":
                remove = 14
                finish_faces = finish_faces[:2]
            else:
                remove = 9
                finish_faces = finish_faces[2:]
            j.delete_record(remove, flush=False)
            # update divide topology
            j.jj["op8"]['properties']['count_x'] = 0
            j.jj["op8"]["gen_info"]["ranges"]["All"] = [[0, 1]]
            j.jj["op8"]["gen_info"]["moduli"]["All"] = 0
            if self.props.door_type == "Left":
                j.jj["op9"]['control_points']['faces']['op8'] = 1
            else:
                j.jj["op14"]['control_points']['faces']['op8'] = 1

        finish_file = self.props.finish.category_item
        if len(finish_file) > 3:
            path = pathlib.Path(finish_file)
            finish_text = path.read_text()
            # add to faces
            for f_op, f_seq in finish_faces:
                sel_info = SelectionInfo()
                sel_info.add_face(f_op, f_seq)
                sel_info.set_mode('SINGLE')
                dct_finish = json.loads(finish_text)
                for update_op in range(0, dct_finish['max_id']+1):
                    wrap = wrap_id(update_op)
                    if wrap in dct_finish:
                        rec = dct_finish[wrap]
                        rec['description'] = rec.get('description', wrap) + ' for-{}-{}'.format(f_op, f_seq)
                finish_op_id = merge_record_dct(dct_master, dct_finish, sel_info)
                print("finish_op_id", finish_op_id)

        script_text = json.dumps(dct_master, cls=MyEncoder, indent=4)
        return script_text

    def invoke(self, context, event):
        """Setup search fields"""
        self.props.knob.category_name = "Handles"
        self.props.hinges.category_name = "Hinges"
        self.props.finish.category_name = "Panels"
        self.props.finish.search_text = "finish"
        return super().invoke(context, event)

    def recordset(self, op_id):
        dct_records = {}
        dct_c, lst_c = self.journal.child_ops(op_id)
        lst_c.sort()

        for op in lst_c:
            rec = self.journal[op]
            if not 'description' in rec:
                rec['description'] = op
            txt = rec['description']
            dct_records[txt] = rec

        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        from ..mesh.geom import _extract_size, _extract_offset
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
        self.journal[op_id]['description'] = "Door Macro"

        # we use wall size to position window
        mm = ManagedMesh(self.obj)
        sel_info = self.journal.get_sel_info(op_id)
        faces = mm.get_faces(sel_info)
        # using first selection, so don't apply to multiple different sizes
        poly = SmartPoly(CoordSys(mm, faces[0]), pt_list=faces[0], break_link=True)
        mm.free()

        size = _extract_size(self.journal[op_id]['properties']['size'], poly.box_size)
        offset = _extract_offset(self.journal[op_id]['properties']['position'], poly.box_size, Vector(size))

        # convert outer divides to non-proportional so we can apply to next wall
        # of different size and get matching door
        rec = dct_records['Set Width']['properties']  # grid divide
        rec_off = rec["offset"]
        rec_siz = rec["size"]
        for k in ['size_x', 'is_relative_x']:
            rec_siz[k] = self.journal[op_id]['properties']['size'][k]
        for k in ['offset_x', 'is_relative_x', 'center_x']:
            rec_off[k] = self.journal[op_id]['properties']['position'][k]

        if offset[0] == 0:  # change pointing of next
            op_dict = dct_records['Set Height']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 0
        else:
            op_dict = dct_records['Set Height']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 1

        rec = dct_records['Set Height']['properties']  # grid divide
        rec_off = rec["offset"]
        rec_siz = rec["size"]
        for k in ['size_y', 'is_relative_y', 'is_ratio_yx']:
            rec_siz[k] = self.journal[op_id]['properties']['size'][k]
        for k in ['offset_y', 'is_relative_y', 'center_y']:
            rec_off[k] = self.journal[op_id]['properties']['position'][k]

        if offset[1] == 0:  # change pointing of next
            op_dict = dct_records['Center in Wall']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 0
        else:
            op_dict = dct_records['Center in Wall']['control_points']['faces']
            k = next(iter(op_dict))
            op_dict[k][0] = 1

        rec = dct_records['Center in Wall']['properties']
        rec['extrude_distance'] = -self.props.wall_thickness/2
        if self.props.arch_type in ['ROMAN', 'TRIANGLE']:
            arch_ht = 0.5
        elif self.props.arch_type == 'DUTCH':
            arch_ht = 0.4
        elif self.props.arch_type in ['SQUARE', 'JACK']:
            arch_ht = 1
        elif self.props.arch_type == 'ARABIC':
            arch_ht = 0.7
        elif self.props.arch_type == 'GOTHIC':
            arch_ht = 0.866  # equilateral
        else:  # OVAL, TUDOR
            arch_ht = 0.3

        if arch_ht * size[0] > size[1] - 0.02:
            arch_ht = (size[1] - 0.02)/size[0]
            print("adjusted arch_ht")

        drop_len = size[1] - arch_ht * size[0]
        drop_len = drop_len - 0.01  # ensure a bridge for the next step
        print(drop_len)
        rec = dct_records['Door Shape']['properties']
        rec['arch']['arch_type'] = self.props.arch_type
        rec['size']['size_y'] = arch_ht
        rec['arch']['drop_length'] = drop_len
        rec['frame'] = self.props.trim_width

        for s in ['Extrude Surround', 'Intrude Surround', 'Extrude Frame']:
            rec = dct_records[s]['properties']
            rec['distance'] = self.props.wall_thickness / 2

        rec = dct_records['Divide Door']['properties']
        if self.props.door_type == 'Left':
            rec['count_x'] = 0
            rec2 = dct_records['Left Door Position']['control_points']['faces']
            rec2[next(iter(rec2))] = [1]
            rec3 = dct_records['Open Bottom']['control_points']['faces']
            rec3[next(iter(rec3))] = [0]

        elif self.props.door_type == 'Right':
            rec['count_x'] = 0
            rec2 = dct_records['Right Door Position']['control_points']['faces']
            rec2[next(iter(rec2))] = [1]  # with double door it is 3
            rec3 = dct_records['Open Bottom']['control_points']['faces']
            rec3[next(iter(rec3))] = [0]

        else:
            rec['count_x'] = 1
            rec2 = dct_records['Right Door Position']['control_points']['faces']
            rec2[next(iter(rec2))] = [3]
            rec3 = dct_records['Open Bottom']['control_points']['faces']
            rec3[next(iter(rec3))] = [0,2]

        for s in ["Left ", "Right "]:
            if self.props.door_type == "Left" and s == "Right ":
                continue
            if self.props.door_type == "Right" and s == "Left ":
                continue

            rec = dct_records[s + 'Door Position']['properties']
            rec2 = dct_records[s + 'Import Hinges']['properties']
            rec2['catalog_object']['category_item'] = self.props.hinges.category_item
            if s=="Right ":
                rec2['position']['offset_x'] = size[0] - 2*self.props.trim_width - 0.01
            # rec3 = dct_records[s + 'Handle Position']

            if self.props.open_in:
                rec['extrude_distance'] = -0.015
                rec2['z_offset'] = -0.03
            else:
                rec['extrude_distance'] = 0.045
                rec2['z_offset'] = 0

            if self.props.door_type == "Sliding":
                rec2['z_offset'] = -0.02  # hide inside

            rec = dct_records[s + 'Import Handle']['properties']
            rec['catalog_object']['category_item'] = self.props.knob.category_item

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
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
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
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
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
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
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
            #mode = context.preferences.addons[base_package].preferences.select_mode
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
                    "mode": "GROUP"
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
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
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
            mode = context.preferences.addons[base_package].preferences.select_mode
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
        self.journal[op_id]['properties'] = self.props.to_dict(compact=True)
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



