import bpy
from .custom import CompoundOperator
from .properties import InsetPolyProperty, PointerProperty
from ..object import Journal, get_obj_data, ACTIVE_OP_ID

class QARCH_OT_add_window(CompoundOperator):
    bl_idname = "qarch.add_window"
    bl_label = "Add Window"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=InsetPolyProperty)

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        return r"""{
            "max_id": 0,
            "controlled": {
                "op0": []
            },
            "adjusting": [],
            "face_tags": [],
            "op0": {
                "op_id": 0,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0.25,
                        "is_relative_x": true,
                        "offset_y": 0.25,
                        "is_relative_y": true
                    },
                    "size": {
                        "size_x": 0.5,
                        "is_relative_x": true,
                        "size_y": 0.5,
                        "is_relative_y": true
                    },
                    "inset_type": "NGON",
                    "use_ngon": true,
                    "poly": {
                        "num_sides": 5,
                        "start_angle": -0.7853981852531433
                    },
                    "use_arch": false,
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN",
                        "thickness": 0.10000000149011612
                    },
                    "extrude_distance": 0.0,
                    "add_perimeter": true
                },
                "control_points": [
                    [
                        0,
                        [
                            0,
                            1,
                            2,
                            3
                        ]
                    ]
                ],
                "control_op": -1,
                "compound_count": 0
            }}"""

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        child_list = self.journal.controlled_list(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()

        # in this case, we have one child
        child_rec = self.journal[child_list[0]]
        child_rec['properties']['poly']['num_sides'] = self.props.num_sides
        child_rec['properties']['arch']['num_sides'] = self.props.num_sides

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        child_list = self.journal.controlled_list(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        # in this case, we have one child
        child_rec = self.journal[child_list[0]]
        # the polygon sides take precedence
        self.props.num_sides = child_rec['properties']['poly']['num_sides']
