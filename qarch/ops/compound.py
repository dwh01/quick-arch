import bpy
from .custom import CompoundOperator
from .properties import SimpleWindowProperty, PointerProperty, SimpleDoorProperty
from ..object import Journal, get_obj_data, ACTIVE_OP_ID, SelectionInfo
from ..mesh import ManagedMesh, SmartPoly
from mathutils import Vector
import math

class QARCH_OT_add_window(CompoundOperator):
    bl_idname = "qarch.add_window"
    bl_label = "Add Window"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleWindowProperty)

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        # or load one from the catalog
        style = "default"
        category = "Windows"
        if self.props.arch_height == 0:
            script_name = "Simple_Window"
        else:
            script_name = "Arched_Window"
        script_text = self.get_catalog_script(self.context, style, category, script_name)

        return script_text

    def recordset(self, op_id):
        dct_records = {}
        dct_c, lst_c = self.journal.child_ops(op_id)
        for c in lst_c:
            print(self.journal.op_label(c))
        # lst_c is depth first
        if self.props.arch_height == 0:
            # ops
            # 0 inset polygon (position) [1]
            #   1 inset polygon (frame size) [2,3]
            #     2 solidify edges (window frame)
            #     3 grid divide (panes) [4]
            #       4 solidify edges (mullions)
            #       5 set face tag (glass)
            for i, txt in enumerate(['position', 'frame size', 'window frame', 'panes', 'mullion', 'glass']):
                j = lst_c[i]
                dct_records[txt] = self.journal[j]
                dct_records[txt]['description'] = txt
        else:
            # ops
            # 0 inset polygon (position) [1,2]
            #   1 inset polygon (frame size) [3, 4]
            #     3 solidify edges (window frame)
            #     4 grid divide (panes) [1]
            #       7 solidify edges (mullions) [4]
            #       8 set face tag (glass) [4]
            #   2 inset polygon (arch)
            #     5 extrude fancy (arch frame) [2]
            #     6 split face (arch panes) [9]
            #       9 solidify edges (arch mullion)

            for i, txt in enumerate(['position', 'frame size', 'window frame', 'panes', 'mullion', 'glass',
                                     'arch', 'arch frame', 'arch panes', 'arch mullion']):
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
        self.journal[op_id]['description'] = "Simple/Arched Window"

        # grid divide for panes
        child_rec = dct_records['panes']
        child_rec['properties']['count_x'] = self.props.x_panes - 1
        child_rec['properties']['count_y'] = self.props.y_panes - 1

        child_rec = dct_records['position']
        child_rec['properties']['position']['offset_x'] = self.props.rel_x
        child_rec['properties']['size']['size_x'] = self.props.width

        if self.props.arch_height > 0:
            child_rec = dct_records['arch']
            child_rec['properties']['size']['size_y'] = self.props.arch_height
            if self.props.arch_height > 0.5:
                child_rec['properties']['arch']['arch_type'] = 'GOTHIC'
            elif self.props.arch_height == 0.5:
                child_rec['properties']['arch']['arch_type'] = 'ROMAN'
            elif self.props.arch_height > 0.25:
                child_rec['properties']['arch']['arch_type'] = 'OVAL'
            else:
                child_rec['properties']['arch']['arch_type'] = 'TUDOR'

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])


        child_rec = dct_records['panes']
        self.props.x_panes = child_rec['properties']['count_x'] + 1
        self.props.y_panes = child_rec['properties']['count_y'] + 1

        child_rec = dct_records['position']
        self.props.rel_x = child_rec['properties']['position']['offset_x']
        self.props.width = child_rec['properties']['size']['size_x']

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
        changed = (old_ht==0) != (self.props.arch_height==0)
        if changed:
            if old_ht == 0:  # no arch
                if num_children != 6:
                    return True
            else:
                if num_children != 10:
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

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        # or load one from the catalog
        style = 'default'
        category = 'Doors'
        script_name = "Simple_Door_one_sided"
        script_text = self.get_catalog_script(self.context, style, category, script_name)
        return script_text

    def recordset(self, op_id):
        # ops
        # 0 inset polygon (split wall)
        #  1 inset polygon (make inner frame)
        #    3 extrude fancy (recess center)
        #      5 inset polygon (with raise to make bevel)
        #        6 inset polygon (base for knob)
        #          7 extrude fancy (knob)
        #    4 tag face (delete center from 1)
        #  2 solidify edges (door frame)
        dct_records = {}
        for i, txt in enumerate(['split wall', 'inset frame', 'door trim', 'recess', 'delete face', 'bevel', 'knob base', 'knob']):
            dct_records[txt] = self.journal[op_id + 1 + i]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Door"

        child_rec = dct_records['split wall']
        child_rec['properties']['position']['offset_x'] = self.props.rel_x

        child_rec = dct_records['recess']
        child_rec['properties']['distance'] = -self.props.panel_depth
        child_rec = dct_records['bevel']
        child_rec['properties']['extrude_distance'] = self.props.panel_depth

        child_rec = dct_records['knob base']
        if self.props.handle_side == 'LEFT':
            child_rec['properties']['position']['offset_x'] = -.12  # from central panel parent
        else:
            child_rec['properties']['position']['offset_x'] = 0.6  # from central panel parent

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        child_rec = dct_records['split wall']
        self.props.rel_x = child_rec['properties']['position']['offset_x']
        child_rec = dct_records['recess']
        self.props.panel_depth = -child_rec['properties']['distance']
        child_rec = dct_records['bevel']
        self.props.panel_depth = child_rec['properties']['extrude_distance']
        child_rec = dct_records['knob base']
        if child_rec['properties']['position']['offset_x'] < 0:
            self.props.handle_side = 'LEFT'
        else:
            self.props.handle_side = 'RIGHT'
