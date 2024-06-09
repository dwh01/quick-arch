import bpy
from .custom import CompoundOperator
from .properties import SimpleWindowProperty, PointerProperty
from ..object import Journal, get_obj_data, ACTIVE_OP_ID

class QARCH_OT_add_window(CompoundOperator):
    bl_idname = "qarch.add_window"
    bl_label = "Add Window"
    bl_options = {"REGISTER", "UNDO"}

    props: PointerProperty(type=SimpleWindowProperty)

    def get_script(self):
        """Returns the same kind of script you get by exporting something"""
        # make something, export it, and copy the script into your class
        return r"""{
            "max_id": 6,
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
                    3,
                    4
                ],
                "op3": [],
                "op4": [
                    5,
                    6
                ],
                "op5": [],
                "op6": []
            },
            "adjusting": [],
            "face_tags": [],
            "op0": {
                "op_id": 0,
                "op_name": "QARCH_OT_grid_divide",
                "properties": {
                    "count_x": 2,
                    "count_y": 0
                },
                "control_points": {
                    "faces": {
                        "op-1": [
                            0
                        ]
                    },
                    "verts": {
                        "op-1": [
                            0
                        ]
                    },
                    "flags": {
                        "op-1": 3
                    },
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "All": [
                            [
                                0,
                                2
                            ]
                        ]
                    },
                    "moduli": {
                        "All": 0
                    }
                }
            },
            "op1": {
                "op_id": 1,
                "op_name": "QARCH_OT_grid_divide",
                "properties": {
                    "count_x": 0,
                    "count_y": 2
                },
                "control_points": {
                    "faces": {
                        "op0": [
                            1
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
                                2
                            ]
                        ]
                    },
                    "moduli": {
                        "All": 2
                    }
                }
            },
            "op2": {
                "op_id": 2,
                "op_name": "QARCH_OT_inset_polygon",
                "properties": {
                    "position": {
                        "offset_x": 0.05000000074505806,
                        "is_relative_x": true,
                        "offset_y": 0.05000000074505806,
                        "is_relative_y": true
                    },
                    "size": {
                        "size_x": 0.8999999761581421,
                        "is_relative_x": true,
                        "size_y": 0.8999999761581421,
                        "is_relative_y": true
                    },
                    "inset_type": "SELF",
                    "use_ngon": false,
                    "poly": {
                        "num_sides": 4,
                        "start_angle": -0.7853981852531433
                    },
                    "use_arch": false,
                    "arch": {
                        "num_sides": 12,
                        "arch_type": "ROMAN"
                    },
                    "extrude_distance": 0.0,
                    "add_perimeter": false,
                    "thickness": 0.10000000149011612
                },
                "control_points": {
                    "faces": {
                        "op1": [
                            1
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
                                0,
                                3
                            ]
                        ],
                        "Center": [
                            [
                                4,
                                4
                            ]
                        ]
                    },
                    "moduli": {
                        "Bridge": 0,
                        "Center": 0
                    }
                }
            },
            "op3": {
                "op_id": 3,
                "op_name": "QARCH_OT_extrude_fancy",
                "properties": {
                    "distance": 0.019999999552965164,
                    "steps": 1,
                    "on_axis": false,
                    "axis": {
                        "x": 0.0,
                        "y": 0.0,
                        "z": 1.0
                    },
                    "twist": 0.0,
                    "align_end": false,
                    "size": {
                        "size_x": 1.0,
                        "is_relative_x": true,
                        "size_y": 1.0,
                        "is_relative_y": true
                    }
                },
                "control_points": {
                    "faces": {
                        "op2": [
                            0,
                            1,
                            2,
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {
                        "op2": 2
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
                            ],
                            [
                                10,
                                13
                            ],
                            [
                                15,
                                18
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
                            ],
                            [
                                14,
                                14
                            ],
                            [
                                19,
                                19
                            ]
                        ]
                    },
                    "moduli": {
                        "Sides": 4,
                        "Tops": 0
                    }
                }
            },
            "op4": {
                "op_id": 4,
                "op_name": "QARCH_OT_grid_divide",
                "properties": {
                    "count_x": 1,
                    "count_y": 1
                },
                "control_points": {
                    "faces": {
                        "op2": [
                            4
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
                                3
                            ]
                        ]
                    },
                    "moduli": {
                        "All": 1
                    }
                }
            },
            "op5": {
                "op_id": 5,
                "op_name": "QARCH_OT_solidify_edges",
                "properties": {
                    "poly": {
                        "num_sides": 4,
                        "start_angle": -0.7853981852531433
                    },
                    "size": {
                        "size_x": 0.009999999776482582,
                        "is_relative_x": false,
                        "size_y": 0.009999999776482582,
                        "is_relative_y": false
                    },
                    "do_horizontal": true,
                    "do_vertical": true,
                    "z_offset": 0.0,
                    "inset": 0.004999999888241291,
                    "face_tag": "TRIM",
                },
                "control_points": {
                    "faces": {
                        "op4": [
                            0,
                            1,
                            2,
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {
                        "op4": 3
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
                            ],
                            [
                                10,
                                13
                            ],
                            [
                                15,
                                18
                            ],
                            [
                                20,
                                23
                            ],
                            [
                                25,
                                28
                            ],
                            [
                                30,
                                33
                            ],
                            [
                                35,
                                38
                            ],
                            [
                                40,
                                43
                            ],
                            [
                                45,
                                48
                            ],
                            [
                                50,
                                53
                            ],
                            [
                                55,
                                58
                            ],
                            [
                                60,
                                63
                            ],
                            [
                                65,
                                68
                            ],
                            [
                                70,
                                73
                            ],
                            [
                                75,
                                78
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
                            ],
                            [
                                14,
                                14
                            ],
                            [
                                19,
                                19
                            ],
                            [
                                24,
                                24
                            ],
                            [
                                29,
                                29
                            ],
                            [
                                34,
                                34
                            ],
                            [
                                39,
                                39
                            ],
                            [
                                44,
                                44
                            ],
                            [
                                49,
                                49
                            ],
                            [
                                54,
                                54
                            ],
                            [
                                59,
                                59
                            ],
                            [
                                64,
                                64
                            ],
                            [
                                69,
                                69
                            ],
                            [
                                74,
                                74
                            ],
                            [
                                79,
                                79
                            ]
                        ]
                    },
                    "moduli": {
                        "Sides": 0,
                        "Tops": 0
                    }
                }
            },
            "op6": {
                "op_id": 6,
                "op_name": "QARCH_OT_set_face_tag",
                "properties": {
                    "face_tag": "GLASS",
                    "face_thickness": 0.0,
                    "face_uv_mode": "GLOBAL_XY"
                },
                "control_points": {
                    "faces": {
                        "op4": [
                            0,
                            1,
                            2,
                            3
                        ]
                    },
                    "verts": {},
                    "flags": {
                        "op4": 3
                    },
                    "mode": "GROUP"
                },
                "gen_info": {
                    "ranges": {
                        "All": [
                            [
                                0,
                                3
                            ]
                        ]
                    },
                    "moduli": {
                        "All": 0
                    }
                }
            }
            }"""


    def _grid_id(self, op_id):
        op3 = self.get_descent_id(op_id, 3)
        clist = self.journal.controlled_list(op3)
        return clist[1]

    def write_props_to_journal(self, op_id):
        """After this operator properties are updated, push them down to the script operators
        by updating the journal text
        """
        grid_id = self._grid_id(op_id)

        # normal operator properties
        self.journal[op_id]['properties'] = self.props.to_dict()

        # grid divide for panes is op4
        child_rec = self.journal[grid_id]
        child_rec['properties']['count_x'] = self.props.x_panes - 1
        child_rec['properties']['count_y'] = self.props.y_panes - 1

        self.journal.flush()

    def read_props_from_journal(self, op_id):
        """Get the properties from the script and put them into this operator's properties
        """
        grid_id = self._grid_id(op_id)

        # normal operator properties
        record = self.journal[op_id]
        self.props.from_dict(record['properties'])

        # in this case, we have one child
        child_rec = self.journal[grid_id]

        self.props.x_panes = child_rec['properties']['count_x'] + 1
        self.props.y_panes = child_rec['properties']['count_y'] + 1
