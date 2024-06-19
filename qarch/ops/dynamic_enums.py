"""Dynamic enum management with icons"""
import os
import pathlib
import bpy
import bpy.utils.previews
import json

BT_CATALOG_SRC = 'BT_Catalog_Src'
BT_IMG_CAT = 'BT_Category'
BT_IMG_DESC = 'BT_Description'
BT_IMG_SCRIPT = 'script_'
BT_IMG_CURVE = 'curve_'
BT_IMG_MESH = "mesh_"

# storage for icons
preview_collections = {}
# storage for enum tuples
dynamic_enum_sets = {}
# style catalogs
catalogs = {}

# note:
# 1) a design feature of blender makes it impossible to safely store "loose" images
# even marked fake user and with automatically-pack-data turned on for the file
# the images eventually get garbage collected and disappear
# 2) you can't append to another blend file, you have to overwrite it, so it is
# hard to push assets into a library. we can push into a directory
qarch_asset_dir = pathlib.Path(__file__).parent.parent / pathlib.Path("assets")

# file structure is style/category/text+image
# with the text files using script_name.txt or curve_name.txt, and the images as xxx_name.png for previews


def to_path(style, category='', name=''):
    p = qarch_asset_dir / pathlib.Path(style)
    if category != '':
        p = p / pathlib.Path(category)
        if name != '':
            p = p / pathlib.Path(name)
    return p


def from_path(p):
    """Convert path to style, category, name"""
    name = p.name

    p1 = p.relative_to(qarch_asset_dir)
    parts = p1.parts
    style = parts[0]
    if len(parts) > 1:
        category = parts[1]
    else:
        category = ''
    return style, category, name


def file_type(name):
    if name.startswith(BT_IMG_SCRIPT):
        return "script", name[len(BT_IMG_SCRIPT):]
    if name.startswith(BT_IMG_CURVE):
        return "curve", name[len(BT_IMG_CURVE):]
    return "mesh", name


def script_name(stem):
    return BT_IMG_SCRIPT + stem + ".txt"


def curve_name(stem):
    return BT_IMG_CURVE + stem + ".txt"


def mesh_name(stem):
    return BT_IMG_MESH + stem + ".stl"


def text_name(stem):
    return stem + ".txt"


def load_catalog(reload=False):
    """Fill global dictionary"""
    global catalogs

    if not (reload or len(catalogs)==0):
        styles = list(catalogs.keys())
        categories = set()
        for s in styles:
            sset = set(catalogs[s].keys())
            categories = categories + sset
        return catalogs, styles, categories

    catalogs.clear()
    styles = []
    categories = set()
    for p in qarch_asset_dir.iterdir():
        if p.is_dir():
            styles.append(p.stem)
            subcat = {}
            catalogs[p.stem] = subcat

            for q in p.iterdir():
                if q.is_dir():
                    categories.add(q.stem)
                    subcat[q.stem] = [r.stem for r in q.iterdir() if r.suffix == ".png"]

    return catalogs, styles, categories


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

    catalog, styles, categories = load_catalog(reload)

    for style_name in styles:
        previews = preview_collections.get(style_name, {})
        dyn_set = dynamic_enum_sets.get(style_name, {})

        for cat_name in categories:
            if cat_name not in catalog[style_name]:
                continue

            pcoll = previews.get(cat_name)
            if pcoll is None:
                pcoll = bpy.utils.previews.new()

            enum_items = dyn_set.get(cat_name)
            if enum_items is None:
                enum_items = []

            for stem in catalog[style_name][cat_name]:
                if stem.startswith(BT_IMG_MESH):
                    p_test = to_path(style_name, cat_name, stem).with_suffix(".stl")
                else:
                    p_test = to_path(style_name, cat_name, stem).with_suffix(".txt")
                if p_test.exists():
                    icon = pcoll.get(stem)
                    if not icon:
                        icon = pcoll.load(stem, str(p_test.with_suffix(".png")), 'IMAGE')
                        print("loaded preview", p_test.with_suffix(".png"))

                    ftype, user_name = file_type(stem)
                    description = ftype
                    if ftype in ['script', 'curve']:
                        as_dict = json.loads(p_test.read_text())
                        description = as_dict.get('description', '')
                    enum_val = (str(p_test), user_name, description, icon.icon_id, len(enum_items)+1)
                    enum_items.append(enum_val)

            previews[cat_name] = pcoll
            dyn_set[cat_name] = enum_items

        preview_collections[style_name] = previews
        dynamic_enum_sets[style_name] = dyn_set


def enum_catalogs(self, context):
    """Callback to list catalogs (styles) available, in order"""
    if len(catalogs) == 0:
        load_previews()

    key = "_catalogs_"
    lst = []
    for k, v in catalogs.items():
        lst.append(
            (k, k, 'style')
        )

    lst.sort(key=lambda e: e[0])

    # numbered
    lst_n = [e[:3] + (i,) for i, e in enumerate(lst)]
    dynamic_enum_sets[key] = lst_n

    return lst_n


empty_enums = [('0','N/A','No selection',0)]
empty_icon_enums = [('0','N/A','No selection',0,0)]


def enum_categories(self, context):
    """Callback gives list of categories
    """
    global catalogs
    lst_return = []
    # search, show_curves, show_scripts = find_search_props(self, context)

    set_done = set()  # no duplicate names

    lst_style_enum = enum_catalogs(self, context)
    if hasattr(self, "style_name") and (self.style_name != ""):
        lst_style_enum = [[self.style_name]]

    for es in lst_style_enum:
        style_name = es[0]
        for k in catalogs[style_name]:
            if k in set_done:
                continue
            set_done.add(k)
            lst_return.append((k, k, ''))

    lst_return.sort(key=lambda e: e[0])  # alphabetic
    lst_return = [e + (i+1,) for i, e in enumerate(lst_return)]

    return empty_enums + lst_return


def enum_category_items(self, context):
    """Callback uses self.category_name, self.search_text"""
    global catalogs

    lst_style_enum = enum_catalogs(self, context)
    if hasattr(self, "style_name") and (self.style_name != ""):
        lst_style_enum = [self.style_name]

    category_name = self.category_name
    if category_name == "0":
        return empty_icon_enums
    lst_return = []
    search, show_curves, show_scripts = find_search_props(self, context)
    lst_style_enum = enum_catalogs(self, context)
    for es in lst_style_enum:
        style_name = es[0]

        lst_categories = catalogs[style_name].keys()
        if hasattr(self, "category_name") and (self.category_name != ""):
            if self.category_name in catalogs[style_name]:
                lst_categories = [self.category_name]

        for category_name in lst_categories:
            lst = dynamic_enum_sets[style_name][category_name]
            for e in lst:
                p = pathlib.Path(e[0])
                ftype, name = file_type(p.stem)
                if show_curves and (ftype != "curve"):
                    continue
                elif show_scripts and (ftype != "script"):
                    continue
                elif (not (show_curves or show_scripts)) and (ftype != 'mesh'):
                    continue
                if len(search) > 2:
                    if search in e[1].lower():
                        lst_return.append(e)
                else:
                    lst_return.append(e)

    lst_return.sort(key=lambda e: e[1])  # alphabetic by friendly name
    lst_return = [e[:4] + (i+1,) for i, e in enumerate(lst_return)]  # number
    return empty_icon_enums + lst_return


# basic face tags, user can add more
lst_FaceEnums = [
    ("DELETE", "Delete", "Delete face at end"),
    ("NOTHING", "Nothing", "No special tag"),
    ("WALL", "Wall", "Wall face"),
    ("GLASS", "Glass", "Glass face"),
    ("TRIM", "Trim", "Framing around door or window"),
    ("DOOR", "Door", "Face of door, may become vertex group"),
    ("ROOF", "Roof", "Face of roof"),
    ("BRASS", "Brass", "Metal highlights"),
    ("IRON", "Iron", "Wrought iron")
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
    addon_prefs = preferences.addons['qarch'].preferences
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
    if len(lst_enum)==0:
        return empty_enums
    return empty_enums + lst_enum
