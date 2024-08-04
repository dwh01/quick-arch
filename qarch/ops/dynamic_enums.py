"""Dynamic enum management with icons"""
import os
import pathlib
import bpy
import bpy.utils.previews
import json
import traceback
from .. import __package__ as base_package


# registration and module init info
lst_classes = []
lst_funcs = [
    'qarch_asset_dir',
    'int_to_face_tag',
    'face_tag_to_int',
    'file_type',
    'BT_IMG_DESC',
    'mesh_name',
    'curve_name',
    'script_name',
    'to_path',
]

BT_IMG_CAT = 'BT_Category'
BT_IMG_DESC = 'BT_Description'
BT_IMG_SCRIPT = 'script_'
BT_IMG_CURVE = 'curve_'
BT_IMG_MESH = "mesh_"
BT_THUMBS = "QARCH_thumbnails"

# storage for icons (images)
preview_collections = {}
# storage for enum tuples
dynamic_enum_sets = {}
# style catalogs, map category name to list of files
catalogs = {}
# map style group name to list of architectural styles
style_dict = {}

# note:
# 1) a design feature of blender makes it hard to safely store "loose" images
# even marked fake user and with automatically-pack-data turned on for the file
# the images eventually tend to get garbage collected and disappear
qarch_asset_dir = pathlib.Path(__file__).parent.parent / pathlib.Path("assets")
ver = bpy.app.version
if ver[0] == 4 and ver[1] >= 2:
    user_asset_dir = pathlib.Path(bpy.utils.extension_path_user(base_package, path="assets", create=True))
    print("user dir", user_asset_dir)
else:
    user_asset_dir = qarch_asset_dir


# file structure is default/category/text+image or user/category/...
# with the text files using script_name.txt or curve_name.txt, and the images as xxx_name.png for previews
def to_path(is_user, category='', name=''):
    if not is_user:
        p = qarch_asset_dir / "default"
    else:
        p = user_asset_dir / "user"

    if category != '':
        p = p / category
        if name != '':
            p = p / name
    return p


def file_type(name):
    if isinstance(name, pathlib.Path):
        return file_type(name.stem)
    if (len(name) > 4) and (name[-4] == "."):
        name = name[:-4]

    if name.startswith(BT_IMG_SCRIPT):
        return "script", name[len(BT_IMG_SCRIPT):]
    if name.startswith(BT_IMG_CURVE):
        return "curve", name[len(BT_IMG_CURVE):]
    return "mesh", name


def script_name(stem):
    if isinstance(stem, pathlib.Path):
        return file_type(stem.stem)

    if stem[-4] == ".":
        stem = stem[:-4]
    if stem[:len(BT_IMG_SCRIPT)] != BT_IMG_SCRIPT:
        stem = BT_IMG_SCRIPT + stem
    return stem + ".txt"


def curve_name(stem):
    if stem[-4] == ".":
        stem = stem[:-4]
    if stem[:len(BT_IMG_CURVE)] != BT_IMG_CURVE:
        stem = BT_IMG_CURVE + stem
    return stem + ".txt"


def mesh_name(stem):
    if stem[-4] == ".":
        stem = stem[:-4]
    if stem[:len(BT_IMG_MESH)] != BT_IMG_MESH:
        stem = BT_IMG_MESH + stem
    return stem + ".txt"


def load_styles():
    """Called in ops __init__ register function"""
    p = qarch_asset_dir / "default/styles.txt"
    txt = p.read_text()
    as_dict = json.loads(txt)
    style_dict.update(as_dict)

    p = user_asset_dir / "user/styles.txt"
    if p.exists():
        print(p)
        txt = p.read_text()
        as_dict = json.loads(txt)
        for c in as_dict:
            if c not in style_dict:
                style_dict[c]={}
            style_dict[c].update(as_dict[c])


def load_catalog(reload=False):
    """Fill global dictionary"""
    global catalogs

    if not (reload or (len(catalogs) == 0)):
        return catalogs

    catalogs.clear()
    for topdir in [qarch_asset_dir / "default", user_asset_dir / "user"]:
        if not topdir.exists():
            print("make",topdir)
            os.makedirs(str(topdir))
        for p in topdir.iterdir():
            if p.is_dir():
                category = p.stem
                if category not in catalogs:
                    catalogs[category] = {}
                for r in p.iterdir():
                    if str(r) in catalogs[category]:
                        continue

                    if r.suffix == ".txt":
                        try:
                            as_dict = json.loads(r.read_text())
                        except Exception as exc:
                            print("Could not parse json for {}".format(r))
                            traceback.print_exc()
                            continue
                        s_list = as_dict.get('style', [])
                        s_desc = as_dict.get('description', '')
                        catalogs[category][str(r)] = {'styles': set(s_list), 'description': s_desc}

    print("loaded catalogs")
    return catalogs


def find_search_props(self, context):
    """Extract things used to filter enum lists"""
    search = ""
    show_curves = False
    show_scripts = False
    if hasattr(self, 'local_object'):
        search = self.local_object.search_text
        show_curves = self.local_object.show_curves
    elif hasattr(self, 'catalog_object'):
        search = self.catalog_object.search_text
        show_curves = self.catalog_object.show_curves
        show_scripts = self.catalog_object.show_scripts
    else:
        if hasattr(self, 'search_text'):
            search = self.search_text
        if hasattr(self, 'show_curves'):
            show_curves = self.show_curves
        if hasattr(self, 'show_scripts'):
            show_scripts = self.show_scripts

    return search.lower(), show_curves, show_scripts


def load_previews(reload=False):
    """Load images and build enum lists"""
    global catalogs
    if (not reload) and len(catalogs):
        return

    catalog = load_catalog(reload)

    thumb_col = preview_collections.get(BT_THUMBS)
    if thumb_col is None:
        thumb_col = bpy.utils.previews.new()
        preview_collections[BT_THUMBS] = thumb_col

    for category, filedict in catalog.items():
        enum_items = {'mesh': [], 'script': [], 'curve': []}
        for filepath, info in filedict.items():
            filepath = pathlib.Path(filepath)
            img_path = filepath.with_suffix(".png")
            if img_path.exists:
                icon = thumb_col.load(filepath.stem, str(img_path), 'IMAGE', True)
                icon_id = icon.icon_id
            else:
                icon_id = "QUESTION"

            ftype, stem = file_type(filepath)
            description = info['description']
            enum_val = (str(filepath), stem, description, icon_id, len(enum_items[ftype])+1)
            enum_items[ftype].append(enum_val)

        dynamic_enum_sets[category] = enum_items
    print("loaded previews")


def enum_styles(self, context):
    """Callback to list styles available"""
    lst = []
    for group, styles in style_dict.items():
        for s in styles:
            lst.append((s, s, group))

    lst.sort(key=lambda e: e[0])
    any = ('Any', 'Any', 'all styles')
    lst.insert(0, any)

    # numbered
    lst_n = [e[:3] + (i,) for i, e in enumerate(lst)]
    # storage
    dynamic_enum_sets['styles'] = lst_n

    return lst_n


empty_enums = [('0','N/A','No selection',0)]
empty_icon_enums = [('0','N/A','No selection',0,0)]


def enum_categories(self, context):
    """Callback gives list of categories
    """
    global catalogs
    lst_return = []
    if len(catalogs)==0:
        load_previews(True)

    for category in catalogs.keys():
        lst_return.append((category, category, ''))

    lst_return.sort(key=lambda e: e[0])  # alphabetic
    lst_return = [e + (i+1,) for i, e in enumerate(lst_return)]

    return empty_enums + lst_return


def enum_category_items(self, context):
    """Callback uses self.category_name, self.search_text"""
    global catalogs
    if len(catalogs)==0:
        load_previews()

    style_filter = ""
    if hasattr(self, "style_name") and (self.style_name != ""):
        style_filter = self.style_name
        if style_filter == "Any":
            style_filter = ""

    category_name = self.category_name
    if category_name == "0":
        return empty_icon_enums

    lst_return = []
    search, show_curves, show_scripts = find_search_props(self, context)
    if show_curves:
        ftype = "curve"
    elif show_scripts:
        ftype = "script"
    else:
        ftype = "mesh"

    lst_items = dynamic_enum_sets[category_name][ftype]
    for e in lst_items:
        info = catalogs[category_name][e[0]]
        if len(info['styles']) and len(style_filter):
            if style_filter not in info['styles']:
                continue

        if len(search) > 2:
            if search not in e[1].lower():
                continue

        lst_return.append(e)

    lst_return.sort(key=lambda e: e[1])  # alphabetic by friendly name
    lst_return = [e[:4] + (i+1,) for i, e in enumerate(lst_return)]  # number
    return empty_icon_enums + lst_return


# basic face tags, user can add more
lst_FaceEnums = [
    ("DELETE", "Delete", "Delete face at end"),
    ("NOTHING", "Nothing", "No special tag"),
    # floor plan tags
    ('PLAN_ARCH', 'Plan Arch', "Open arch in wall"),
    ('PLAN_COLUMNS', 'Plan Columns', "Columns instead of solid wall"),
    ('PLAN_DOOR', 'Plan Door', 'Door'),
    ('PLAN_EXT_EXT_WALL', 'Plan Ext Wall', 'Exterior wall (both sides)'),
    ('PLAN_EXT_INT_WALL', 'Plan Ext-Int Wall', 'Exterior-Interior wall'),
    ('PLAN_INT_INT_wALL', 'Plan Int Wall', "Interior wall (both sides)"),
    ('PLAN_HALF_WALL', 'Plan Half Wall', "Half height wall (interior)"),
    ('PLAN_SASH_WINDOW', 'Plan Sash Window', "Window that opens"),
    ('PLAN_FIXED_WINDOW', 'Plan Fixed Window', "Window that doesn't open"),
    ('PLAN_FIREPLACE', 'Plan Fireplace', 'Fireplace'),
    ('PLAN_FIREPLACE_2', 'Plan Fireplace-2', 'Double sided fireplace for interior wall'),
    ('PLAN_FLOOR', 'Plan Floor', "Floor area"),
]


# hold enums for face tags
dct_hold_face_enums = {}


def face_tag_to_int(s):
    global dct_hold_face_enums
    if len(dct_hold_face_enums)==0:
        for e in lst_FaceEnums:
            if e[0] not in dct_hold_face_enums:
                dct_hold_face_enums[e[0]] = e

    for i, e in enumerate(dct_hold_face_enums.keys()):
        if e == s:
            return i-1
    return 0


def int_to_face_tag(i):
    lst = list(dct_hold_face_enums.keys())
    if i < len(lst)-1:
        return lst[i+1]
    return "NOTHING"


def get_face_tag_enum(self, context):
    from ..object import Journal
    global lst_FaceEnums
    global dct_hold_face_enums

    lst_enum = []

    set_used = set()
    for e in lst_FaceEnums:
        if e[0] not in dct_hold_face_enums:
            dct_hold_face_enums[e[0]] = e
        set_used.add(e[0])
        lst_enum.append(e + (len(lst_enum)-1,))

    preferences = context.preferences
    addon_prefs = preferences.addons[base_package].preferences
    user_tags = [s.strip() for s in addon_prefs.user_tags.split(",")]
    for s in user_tags:
        if s not in set_used:
            e = (s, s, "tag from user preferences")
            if s not in dct_hold_face_enums:
                dct_hold_face_enums[s] = e
            lst_enum.append(dct_hold_face_enums[s]+ (len(lst_enum)-1,))
            set_used.add(s)

    journal = Journal(context.object)
    obj_tags = [s.strip() for s in journal['face_tags']]
    for s in obj_tags:
        if s not in set_used:
            e = (s, s, "tag from user preferences")
            if s not in dct_hold_face_enums:
                dct_hold_face_enums[s] = e
            lst_enum.append(dct_hold_face_enums[s]+ (len(lst_enum)-1,))
            set_used.add(s)

    return lst_enum


# hold enums for objects
dct_obj_enum = {}


def enum_objects_or_curves(self, context):
    search, show_curves, show_scripts = find_search_props(self, context)
    lst_enum = []
    if show_curves:
        col = bpy.data.curves
    else:
        col = bpy.data.objects

    for obj in col:  # must search every time because new things could be added
        if len(search) > 1:
            name = obj.name.lower()
            if search not in name:
                continue

        e_tuple = (obj.name, obj.name, "", len(lst_enum)+1)
        lst_enum.append(e_tuple)

        # only used for string permanence
        dct_obj_enum[obj.name] = e_tuple
    if len(lst_enum) == 0:
        return empty_enums

    lst_enum.sort(key=lambda e: e[1])  # alphabetic by friendly name
    lst_enum = [e[:3] + (i + 1,) for i, e in enumerate(lst_enum)]  # number

    return empty_enums + lst_enum


def exists_in_catalog(unused, category, stem):
    for ftype, lst_items in dynamic_enum_sets[category].items():
        for e in lst_items:
            if e[1] == stem:
                return True
    return False