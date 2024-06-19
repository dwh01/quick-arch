import bpy
from .custom import CompoundOperator
from .properties import SimpleWindowProperty, PointerProperty, SimpleDoorProperty, SimpleRailProperty
from .properties import ExtendGableProperty, DormerProperty
from ..object import Journal, get_obj_data, ACTIVE_OP_ID, SelectionInfo, wrap_id
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
        dct_c, lst_c = self.journal.child_ops(op_id)
        for c in lst_c:
            print(self.journal.op_label(c))
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
        # ops
        # 0 grid divide (bottom height)
        #  1 solidify edges (top-bot rails)
        #  2 grid divide (x cuts)
        #    3 solidify edges (bars)
        #    4 set face tag (delete)
        #  4 set face tag (delete)
        dct_c, lst_c = self.journal.child_ops(op_id)
        for c in lst_c:
            print(self.journal.op_label(c))
        dct_records = {}
        for i, txt in enumerate(['bottom ht', 'tob-bot rails', 'x cuts', 'bars', 'face tag']):
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
        self.journal[op_id]['description'] = "Simple Railing"

        mm = ManagedMesh(self.obj)
        sel_info = self.journal.get_sel_info(op_id)
        faces = mm.get_faces(sel_info)
        poly = SmartPoly()
        poly.add(list(faces[0].verts))
        poly.calculate()
        width = poly.box_size.x
        mm.free()

        spacing = self.props.rail_spacing
        n = int(math.ceil(width / spacing)) - 1

        child_rec = dct_records['x cuts']
        child_rec['properties']['count_x'] = n

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])



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
            mode = context.preferences.addons['qarch'].preferences.select_mode
            if mode in {'SINGLE', 'REGION'}:
                return True
        return False

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # this script is not generally applicable because it has a globally set direction vector
        # so we remove it from the catalog and only have it here
        script_text = """{
            "max_id": 3,
            "controlled": {
                "op-1": [
                    0
                ],
                "op0": [
                    1
                ],
                "op1": [
                    2
                ],
                "op2": [
                    3
                ],
                "op3": []
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
                    "align_end": false,
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
                        "offset_x": 0.10000000149011612,
                        "is_relative_x": false,
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
            "description": "Extend hip to gable"
        }"""
        return script_text

    def recordset(self, op_id):
        # ops
        # 0 extrude (directed)
        #  1 inset polygon (inset)
        #    2 extrude (soffit)
        #      3 set tag (trim)
        dct_c, lst_c = self.journal.child_ops(op_id)
        for c in lst_c:
            print(self.journal.op_label(c))
        dct_records = {}
        for i, txt in enumerate(['directed', 'inset', 'soffit', 'face tag']):
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

        mm = ManagedMesh(self.obj)
        sel_info = self.journal.get_sel_info(op_id)
        faces = mm.get_faces(sel_info)
        poly = SmartPoly()
        poly.add(list(faces[0].verts))
        poly.calculate()
        mm.free()

        z = Vector((0,0,1))
        edir = z.cross(poly.xdir)
        if edir.dot(poly.normal) < 0:
            edir = -edir

        v = poly.make_3d(poly.bbox[0])
        v1 = v - poly.center
        dist = v1.dot(edir)

        print(edir, v1, dist)
        child_rec = dct_records['directed']
        child_rec['properties']['axis']['x'] = edir.x
        child_rec['properties']['axis']['y'] = edir.y
        child_rec['properties']['axis']['z'] = edir.z
        child_rec['properties']['distance'] = dist

        child_rec = dct_records['inset']
        child_rec['properties']['size']['size_x'] = -self.props.soffit_width
        child_rec['properties']['size']['size_y'] = -self.props.soffit_width/2
        child_rec['properties']['position']['offset_x'] = self.props.soffit_width/2

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
        self.props.soffit_width = -child_rec['properties']['size']['size_x']

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
        # this script is not generally applicable because it has a globally set direction vector
        # so we remove it from the catalog and only have it here
        script_text = """{
            "max_id": 7,
            "controlled": {
                "op-1": [0],
                "op0": [1,2],
                "op1": [2],
                "op2": [3],
                "op3": [4],
                "op4": [5,6],
                "op5": [],
                "op6": [7],
                "op7": []
            },
            "adjusting": [],
            "face_tags": [],
            "version": "0.1",
            "op0": {
                "op_id": 0,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 1.4499999284744263,
                        "is_relative_x": false,
                        "offset_y": 0.10000000149011612,
                        "is_relative_y": true
                    },
                    "size": {
                        "size_x": 0.75,
                        "is_relative_x": false,
                        "size_y": 0.25,
                        "is_relative_y": true
                    },
                    "join": "FREE",
                    "add_perimeter": false,
                    "shape_type": "NGON",
                    "poly": {
                        "num_sides": 4,
                        "start_angle": -0.7853981852531433
                    },
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN"
                    },
                    "frame": 0.0,
                    "frame_material": "BT_Roof",
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
                        "rotate": [0.0,0.0,0.0]
                    },
                    "catalog_object": {
                        "style_name": "default",
                        "category_name": "Decks",
                        "search_text": "",
                        "category_item": "0",
                        "rotate": [0.0,0.0,0.0]
                    },
                    "resolution": 4,
                    "center_material": "BT_Roof",
                    "extrude_distance": 0.0
                },
                "control_points": {
                    "faces": {
                        "op-1": [
                            4
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Bridge": [],
                        "Center": [
                            [0,0]
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
            "op1": {
                "op_id": 1,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0.0,
                        "is_relative_x": false,
                        "offset_y": 0.5,
                        "is_relative_y": true
                    },
                    "size": {
                        "size_x": 1.0,
                        "is_relative_x": true,
                        "size_y": 1.0,
                        "is_relative_y": true
                    },
                    "join": "OUTSIDE",
                    "add_perimeter": false,
                    "shape_type": "NGON",
                    "poly": {
                        "num_sides": 4,
                        "start_angle": 0.0
                    },
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN"
                    },
                    "frame": 0.0,
                    "frame_material": "BT_Roof",
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
                        "rotate": [0.0,0.0,0.0]
                    },
                    "catalog_object": {
                        "style_name": "default",
                        "category_name": "Decks",
                        "search_text": "",
                        "category_item": "0",
                        "rotate": [0.0,0.0,0.0]
                    },
                    "resolution": 4,
                    "center_material": "BT_Roof",
                    "extrude_distance": 0.0
                },
                "control_points": {
                    "faces": {
                        "op0": [0]
                    },
                    "verts": {},
                    "flags": {
                        "op0": 3
                    },
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Bridge": [],
                        "Center": [
                            [0,0]
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
                    "distance": 0.009999999776482582,
                    "steps": 1,
                    "on_axis": false,
                    "axis": {
                        "x": 0.0,
                        "y": -1.0,
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
                        "op0": [0],
                        "op1": [0]
                    },
                    "verts": {},
                    "flags": {
                        "op0": 3,
                        "op1": 1
                    },
                    "mode": "REGION"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [0,4]
                        ],
                        "Tops": [
                            [5,5]
                        ]
                    },
                    "moduli": {
                        "Sides": 5,
                        "Tops": 0
                    }
                }
            },
            "op3": {
                "op_id": 3,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.3499999940395355,
                    "steps": 1,
                    "on_axis": true,
                    "axis": {
                        "x": 0.0,
                        "y": -1.0,
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
                        "op2": [5]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "REGION"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [0,4]
                        ],
                        "Tops": [
                            [5,5]
                        ]
                    },
                    "moduli": {
                        "Sides": 5,
                        "Tops": 0
                    }
                }
            },
            "op4": {
                "op_id": 4,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0.02500000037252903,
                        "is_relative_x": false,
                        "offset_y": 0.009999999776482582,
                        "is_relative_y": false
                    },
                    "size": {
                        "size_x": -0.05000000074505806,
                        "is_relative_x": false,
                        "size_y": -0.05000000074505806,
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
                        "rotate": [0.0,0.0,0.0]
                    },
                    "catalog_object": {
                        "style_name": "default",
                        "category_name": "Decks",
                        "search_text": "",
                        "category_item": "0",
                        "rotate": [0.0,0.0,0.0]
                    },
                    "resolution": 4,
                    "center_material": "BT_Trim",
                    "extrude_distance": 0.0
                },
                "control_points": {
                    "faces": {
                        "op3": [5]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "REGION"
                },
                "gen_info": {
                    "ranges": {
                        "Bridge": [
                            [1,5]
                        ],
                        "Center": [
                            [0,0]
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
            "op5": {
                "op_id": 5,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.10000000149011612,
                    "steps": 1,
                    "on_axis": false,
                    "axis": {
                        "x": 0.0,
                        "y": -1.0,
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
                        "op4": [5,1]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [0,5]
                        ],
                        "Tops": [
                            [6,6]
                        ]
                    },
                    "moduli": {
                        "Sides": 6,
                        "Tops": 0
                    }
                }
            },
            "op6": {
                "op_id": 6,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0.25,
                        "is_relative_x": true,
                        "offset_y": 0.15000000596046448,
                        "is_relative_y": true
                    },
                    "size": {
                        "size_x": 0.5,
                        "is_relative_x": true,
                        "size_y": 0.5,
                        "is_relative_y": true
                    },
                    "join": "BRIDGE",
                    "add_perimeter": true,
                    "shape_type": "NGON",
                    "poly": {
                        "num_sides": 8,
                        "start_angle": -0.7853981852531433
                    },
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN"
                    },
                    "frame": 0.05000000074505806,
                    "frame_material": "BT_Trim",
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
                        "rotate": [0.0,0.0,0.0]
                    },
                    "catalog_object": {
                        "style_name": "default",
                        "category_name": "Decks",
                        "search_text": "",
                        "category_item": "0",
                        "rotate": [0.0,0.0,0.0]
                    },
                    "resolution": 4,
                    "center_material": "BT_Glass",
                    "extrude_distance": 0.0
                },
                "control_points": {
                    "faces": {
                        "op4": [0]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "REGION"
                },
                "gen_info": {
                    "ranges": {
                        "Bridge": [
                            [9,16]
                        ],
                        "Center": [
                            [8,8]
                        ],
                        "Frame": [
                            [0,7]
                        ]
                    },
                    "moduli": {
                        "Bridge": 0,
                        "Center": 0,
                        "Frame": 0
                    }
                }
            },
            "op7": {
                "op_id": 7,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.02500000037252903,
                    "steps": 1,
                    "on_axis": false,
                    "axis": {
                        "x": 0.0,
                        "y": -1.0,
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
                    "side_material": "BT_Trim",
                    "center_material": "BT_Trim"
                },
                "control_points": {
                    "faces": {
                        "op6": [
                            0,
                            1,
                            2,
                            3,
                            4,
                            5,
                            6,
                            7
                        ]
                    },
                    "verts": {},
                    "flags": {},
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "Sides": [
                            [ 0,3],
                            [5,8],
                            [10,13],
                            [15,18],
                            [20,23],
                            [25,28],
                            [30,33],
                            [35,38]
                        ],
                        "Tops": [
                            [4,4],
                            [9,9],
                            [14,14],
                            [19,19],
                            [24,24],
                            [29,29],
                            [34,34],
                            [39,39]
                        ]
                    },
                    "moduli": {
                        "Sides": 4,
                        "Tops": 0
                    }
                }
            },
            "description": "Dormer with window"
        }"""
        return script_text

    def recordset(self, op_id):
        # ops
        # 0 inset (square)
        #  1 inset (triangle)
        #    2 extrude (merge)
        #      3 extrude (flat)
        #        4 inset (soffit width)
        #          5 extrude (soffit)
        #          6 inset (window)
        #            7 extrude (frame)
        dct_c, lst_c = self.journal.child_ops(op_id)
        for c in lst_c:
            print(self.journal.op_label(c))
        dct_records = {}
        for i, txt in enumerate(['square', 'triangle', 'merge', 'flat',
                                 'soffit width', 'soffit', 'window', 'frame']):
            j = lst_c[i]
            dct_records[txt] = self.journal[j]
            dct_records[txt]['description'] = txt
        return dct_records

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        from ..mesh import geom

        dct_records = self.recordset(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()
        self.journal[op_id]['description'] = "Simple Dormer"

        child_rec = dct_records['square']
        child_rec['properties']['position'] = self.props.position.to_dict()

        # changing number of sides, must keep some things consistent since we didn't use "all" bridge faces and
        # the automatic system will get the new extrude faces wrong
        child_rec = dct_records['triangle']
        if self.props.rounded:
            n_sides = 8
            faces = [1,2,6,7]
            ranges = [1,7]
        else:
            n_sides = 4
            faces = [1,5]
            ranges = [1,5]
        child_rec['properties']['poly']['num_sides'] = n_sides

        child_rec = dct_records['soffit width']
        opkey = wrap_id(child_rec['op_id'])
        child_rec["gen_info"]["ranges"]["Bridge"] = [ranges]

        child_rec = dct_records['soffit']
        child_rec['control_points']['faces'][opkey]=faces
        print("---set control points",child_rec)

        sel_info = self.journal.get_sel_info(op_id)
        mm, lst_poly = geom._common_start(self.obj, sel_info, break_link=True)
        poly = lst_poly[0]
        mm.free()

        z = Vector((0,0,1))
        edir = z.cross(poly.xdir)
        if edir.dot(poly.normal) < 0:
            edir = -edir

        # estimate center y position so we can get extrude distance. Actual polys may not exist yet
        sz_sq = poly.box_size.y/4
        sz_tri = sz_sq
        if self.props.rounded:
            sz_oct = sz_sq + sz_tri*math.sin(math.pi/8)
            ctr = (0*2 + sz_sq*2 + sz_oct*2 + sz_tri+sz_sq) / (2+2+2+1)
        else:
            ctr = (0*2 + sz_sq*2 + sz_tri+sz_sq) / (2+2+1)

        v1 = -poly.ydir * ctr
        dist = v1.dot(edir)

        child_rec = dct_records['flat']
        child_rec['properties']['axis']['x'] = edir.x
        child_rec['properties']['axis']['y'] = edir.y
        child_rec['properties']['axis']['z'] = edir.z
        child_rec['properties']['distance'] = dist

        child_rec = dct_records['soffit width']
        child_rec['properties']['size']['size_x'] = -self.props.soffit_width
        child_rec['properties']['size']['size_y'] = -self.props.soffit_width/2
        child_rec['properties']['position']['offset_x'] = self.props.soffit_width/2

        child_rec = dct_records['soffit']
        child_rec['properties']['distance'] = self.props.overhang

        child_rec = dct_records['window']
        if self.props.octagon_window:
            n_sides = 8
        else:
            n_sides = 4
        start = -math.pi/n_sides
        child_rec['properties']['poly']['num_sides'] = n_sides
        child_rec['properties']['poly']['start_angle'] = start

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        dct_records = self.recordset(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        child_rec = dct_records['square']
        self.props.position.from_dict(child_rec['properties']['position'])

        child_rec = dct_records['triangle']
        n_sides = child_rec['properties']['poly']['num_sides']
        self.props.rounded = (n_sides == 8)

        child_rec = dct_records['inset']
        self.props.soffit_width = -child_rec['properties']['size']['size_x']

        child_rec = dct_records['soffit']
        self.props.overhang = child_rec['properties']['distance']

        child_rec = dct_records['window']
        n_sides = child_rec['properties']['poly']['num_sides']
        self.props.octagon_window = (n_sides == 8)
