"""Object utilities
Create new objects
Get/Set object data
"""

import bpy
import uuid
import json

# custom layer names
FACE_CATEGORY = 'bt_face_cat'
FACE_THICKNESS = 'bt_face_thick'
FACE_UV_MODE = 'bt_uv_mode'
VERT_OP_ID = 'bt_op_id'
VERT_OP_SEQUENCE = 'bt_sequence'

# custom data field for object
BT_OBJ_DATA = 'bt_data'

# things stored in object data
ACTIVE_OP_ID = "op_id"  # used to force re-editing of old operation and replay of sequences
JOURNAL_PROP_NAME = "journal_name"  # object custom property name


def create_object(collection, name):
    """Create object and initialize layers, etc
    Return object
    """
    # hide import here to prevent load sequence conflicts
    from .journal import get_block, update_block, blank_journal

    # empty mesh object
    mesh = bpy.data.meshes.new(name)
    v = mesh.vertices.add(1)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)

    # create custom property on object
    obj[BT_OBJ_DATA] = "{}"

    # protect against name changes and collisions
    unique_str = str(uuid.uuid4())
    journal_name = f"{name}{unique_str}"
    set_obj_data(obj, JOURNAL_PROP_NAME, journal_name)

    # create the block
    update_block(get_block(obj), blank_journal())

    # no operation will match -1
    set_obj_data(obj, ACTIVE_OP_ID, -1)

    # setup layers for mesh based data
    key = obj.data.attributes.new(FACE_CATEGORY, 'INT', 'FACE')
    key = obj.data.attributes.new(FACE_UV_MODE, 'INT', 'FACE')
    key = obj.data.attributes.new(FACE_THICKNESS, 'FLOAT', 'FACE')
    key = obj.data.attributes.new(VERT_OP_ID, 'INT', 'POINT')

    attribute_values = [-1]
    key.data.foreach_set("value", attribute_values)
    key = obj.data.attributes.new(VERT_OP_SEQUENCE, 'INT', 'POINT')

    return obj


def get_obj_data(obj, field):
    """Return object data field, or None"""
    try:
        obj_dict = json.loads(obj[BT_OBJ_DATA])
    except KeyError:
        return None
    return obj_dict.get(field, None)


def set_obj_data(obj, field, data):
    """Store data in object data. Uses json to parse dictionary."""
    obj_dict = json.loads(obj[BT_OBJ_DATA])
    obj_dict[field] = data
    obj[BT_OBJ_DATA] = json.dumps(obj_dict)





