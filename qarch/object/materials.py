import bpy
import pathlib
from collections import OrderedDict

BT_Material_File = "BT_Materials.blend"

lst_bt_materials = []


def import_bt_materials():
    from ..ops import qarch_asset_dir
    global lst_bt_materials

    path = qarch_asset_dir / pathlib.Path(BT_Material_File)

    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        for mat in data_from.materials:
            if mat[:2] == "BT":
                if mat not in bpy.data.materials:
                    data_to.materials.append(mat)
                if mat not in lst_bt_materials:
                    lst_bt_materials.append(mat)

    try:
        bpy.ops.ed.undo_push(message="Loaded materials")
    except Exception as e:
        print("Warning, could not push undo after material load")
        pass


def material_best_mode(mat_name):
    """Get best uv mode from material name"""
    if len(lst_bt_materials)==0:
        import_bt_materials()
    if mat_name in lst_bt_materials:
        mat = bpy.data.materials[mat_name]
        return mat['BT_MODE']
    else:
        return 'FACE_XY'


dct_tag_to_mat = {
        'DELETE': 'BT_Transparent',
        'NOTHING': 'BT_Nothing',
        'PLAN_ARCH': 'BT_Plan_Arch',
        'PLAN_COLUMNS': 'BT_Plan_Columns',
        'PLAN_DOOR': 'BT_Plan_Door',
        'PLAN_EXT_EXT_WALL': 'BT_Plan_Ext_Ext_Wall',
        'PLAN_EXT_INT_WALL': 'BT_Plan_Ext_Int_Wall',
        'PLAN_FIREPLACE': 'BT_Plan_Fireplace',
        'PLAN_FIREPLACE_2': 'BT_Plan_Fireplace_2',
        'PLAN_FIXED_WINDOW': 'BT_Plan_FixedWindow',
        'PLAN_FLOOR': 'BT_Plan_Floor',     # plan_stairs, plan_deck, plan_balcony, plan_roof
        'PLAN_HALF_WALL': 'BT_Plan_Half_Wall',
        'PLAN_INT_INT_wALL': 'BT_Plan_Int_Int_Wall',
        'PLAN_SASH_WINDOW': 'BT_Plan_SashWindow',
    }

floorset = {'BT_Plan_Floor'}     # plan_stairs, plan_deck, plan_balcony, plan_roof


def tag_to_material(tag):
    """Convert face tag to material name"""
    from ..ops import int_to_face_tag
    global dct_tag_to_mat

    if isinstance(tag, int):
        tag = int_to_face_tag(tag)

    return dct_tag_to_mat.get(tag, 'BT_Nothing')


dct_hold_ordered_mat = OrderedDict()
empty_enum = [('BT_Nothing', 'BT_Nothing', 'Nothing', 0)]


def enum_all_material(self, context):
    global dct_hold_ordered_mat
    global lst_bt_materials
    if len(lst_bt_materials) == 0:
        import_bt_materials()

    lst_enum = []
    for mat in bpy.data.materials:
        if mat.name not in dct_hold_ordered_mat:
            e = (mat.name, mat.name, "Best uv mode is " + material_best_mode(mat.name), 1+len(dct_hold_ordered_mat))
            dct_hold_ordered_mat[mat.name] = e
        lst_enum.append(dct_hold_ordered_mat[mat.name])

    return empty_enum + lst_enum


def enum_oriented_material(self, context):
    lst_e = enum_all_material(self, context)
    lst = []
    for e in lst_e:
        if e[2] == "Best uv mode is " + "ORIENTED":
            lst.append(e)
    return empty_enum + lst


def enum_plan_material(self, context):
    lst_e = enum_all_material(self, context)
    lst = []
    for e in lst_e:
        if e[1].startswith("BT_Plan_"):
            lst.append(e)
    return empty_enum + lst


def enum_plan_wall_material(self, context):
    lst_e = enum_plan_material(self, context)
    lst_e = [e for e in lst_e if "Wall" in e[1]]
    return empty_enum + lst_e


def enum_plan_floor_material(self, context):
    global floorset
    lst_e = enum_plan_material(self, context)
    lst_e = [e for e in lst_e if e[0] in floorset]
    return empty_enum + lst_e


def enum_nonplan_material(self, context):
    lst_e = enum_all_material(self, context)
    lst = []
    for e in lst_e:
        if not e[1].startswith("BT_Plan_"):
            lst.append(e)
    return lst



