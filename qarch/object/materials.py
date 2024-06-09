import bpy
import pathlib
from collections import OrderedDict

BT_Material_File = "BT_Materials.blend"

lst_bt_materials = []

# minimal set of material to uv mode
dct_mat_mode = {
        'BT_Brick': 'FACE_POLAR',
        'BT_Glass': 'GLOBAL_XY',
        'BT_Trim': 'FACE_XY',
        'BT_Wood': 'ORIENTED',
    }


def import_bt_materials():
    global lst_bt_materials
    if len(lst_bt_materials):
        return

    path = pathlib.Path(__file__)  # qarch/object/materials.py
    path = path.parent.parent / pathlib.Path("assets") / pathlib.Path(BT_Material_File)

    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        for mat in data_from.materials:
            if (mat[:2] == "BT") and (mat not in data_to.materials):
                data_to.materials.append(mat)
                lst_bt_materials.append(mat)

    print(lst_bt_materials)
    # for each material, if we specify the best coordinate mode, record that (so we don't have to manually keep updated)
    for m in lst_bt_materials:
        mat = bpy.data.materials[m]
        try:
            s = mat['BT_MODE']  # from scripting tab, do "bpy.data.materials[xxx]['BT_MODE']='yyy'"
        except Exception:
            continue
        dct_mat_mode[mat.name] = s


def material_best_mode(mat):
    """Get best uv mode from material name"""
    global dct_mat_mode
    return dct_mat_mode.get(mat, 'GLOBAL_XY')


def tag_to_material(tag):
    """Convert face tag to default material name"""
    from ..ops import int_to_face_tag
    if isinstance(tag, int):
        tag = int_to_face_tag(tag)

    dct_mat = {
        'NOTHING': 'BT_Trim',
        'WALL': 'BT_Brick',
        'GLASS': 'BT_Glass',
        'TRIM': 'BT_Trim',
        'DOOR': 'BT_Wood',
    }

    return dct_mat.get(tag, 'BT_Brick')


dct_hold_ordered_mat = OrderedDict()


def enum_oriented_material(self, context):
    global dct_hold_ordered_mat
    lst_enum = []
    for mat in bpy.data.materials:
        mode = material_best_mode(mat.name)
        if mode == 'ORIENTED':
            if mat.name not in dct_hold_ordered_mat:
                e = (mat.name, mat.name, "Best uv mode is ORIENTED", len(dct_hold_ordered_mat))
                dct_hold_ordered_mat[mat.name] = e
            lst_enum.append(dct_hold_ordered_mat[mat.name])

    return lst_enum


def enum_all_material(self, context):
    global dct_hold_ordered_mat
    lst_enum = []
    for mat in bpy.data.materials:
        if mat.name not in dct_hold_ordered_mat:
            e = (mat.name, mat.name, "Best uv mode is "+material_best_mode(mat.name), len(dct_hold_ordered_mat))
            dct_hold_ordered_mat[mat.name] = e
        lst_enum.append(dct_hold_ordered_mat[mat.name])

    return lst_enum
