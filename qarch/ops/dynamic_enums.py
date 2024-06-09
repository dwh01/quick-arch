"""Dynamic enum management with icons"""
import os
import pathlib
import bpy
import bpy.utils.previews

BT_CATALOG_SRC = 'BT_Catalog_Src'
BT_IMG_CAT = 'BT_Category'
BT_IMG_DESC = 'BT_Description'
BT_IMG_SCRIPT = 'script_'
BT_IMG_CURVE = 'curve_'

# storage for icons
preview_collections = {}
# storage for enum tuples
dynamic_enum_sets = {}
# style catalogs
catalogs = {}

# built in location
qarch_asset_dir = pathlib.Path(__file__).parent.parent / pathlib.Path("assets")


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


def scan_catalog_images(filepath):
    lst_new = []
    with bpy.data.libraries.load(str(filepath)) as (data_from, data_to):
        for img_name in data_from.images:
            if img_name not in data_to.images:
                data_to.images.append(img_name)
                lst_new.append(img_name)

    cat_name = filepath.stem
    lst_remove = []
    lst_keep = []
    for img_name in lst_new:
        img = bpy.data.images[img_name]
        try:
            valid = img[BT_IMG_CAT]
            lst_keep.append(img)
        except Exception as exc:
            lst_remove.append(img)

    for img in lst_remove:
        bpy.data.images.remove(img)

    return lst_keep


def icon_image(img, pcoll, cat_name):
    # slow method
    #     icon_new = pcoll.new("{}_{}".format(cat_name, img.name))
    #     icon_new.image_size = img.size
    #     print("loading icon {}".format(img.name))
    #     icon_new.image_pixels_float = img.pixels
    img_name = "{}_{}.png".format(cat_name, img.name)
    pth = qarch_asset_dir / pathlib.Path("temp") / pathlib.Path(img_name)
    img.save(filepath = str(pth))
    icon_new = pcoll.load(img_name[:-4], str(pth), 'IMAGE')
    # os.remove(pth)  must remain, clean up at unregister
    return icon_new


def remove_temp_images():
    pth = qarch_asset_dir / pathlib.Path("temp")
    files = pth.glob("*.*")
    for file in files:
        os.remove(str(file))


def scan_catalog_file(bfile):
    style_name = bfile.stem

    lst_images = scan_catalog_images(bfile)
    if len(lst_images) == 0:
        return

    previews = preview_collections.get(style_name, {})
    dyn_set = dynamic_enum_sets.get(style_name, {})

    for img in lst_images:
        cat_name = img[BT_IMG_CAT]
        pcoll = previews.get(cat_name)
        if pcoll is None:
            pcoll = bpy.utils.previews.new()

        enum_items = dyn_set.get(cat_name)
        if enum_items is None:
            enum_items = []

        icon = pcoll.get(img.name)
        if not icon:
            icon = icon_image(img, pcoll, cat_name)
            enum_text = img.name
            enum_items.append((enum_text, img.name, img[BT_IMG_DESC], icon.icon_id, len(enum_items)+1))

        previews[cat_name] = pcoll
        dyn_set[cat_name] = enum_items

        bpy.data.images.remove(img)

    preview_collections[style_name] = previews
    dynamic_enum_sets[style_name] = dyn_set
    catalogs[style_name] = bfile


def scan_builtin_styles():
    lst_blend = qarch_asset_dir.glob("*.blend")
    for bfile in lst_blend:
        if bfile == pathlib.Path(bpy.data.filepath):
            continue
        if bfile.stem == "BT_Materials":  # shared material library
            continue
        scan_catalog_file(bfile)
    bpy.ops.ed.undo_push(message="Scan Catalog")


def enum_catalogs(self, context):
    """Callback to list catalogs (styles) available"""
    if len(catalogs) == 0:
        scan_builtin_styles()

    key = "_catalogs_"
    lst = dynamic_enum_sets.get(key)
    if lst is None:
        lst = []
        for k, v in catalogs.items():
            lst.append(
                (k, k, str(v))
            )

        dynamic_enum_sets[key] = lst
    return lst


def get_calatalog_file(context):
    preferences = context.preferences.addons['qarch'].preferences  # note: self is passed to functions
    style_name = preferences.build_style
    return catalogs[style_name]


empty_enums = [('0','N/A','No selection',0)]
empty_icon_enums = [('0','N/A','No selection',0,0)]
def enum_categories(self, context):
    """Callback requires self.show_scripts, gives list of categories
    """
    if len(catalogs) == 0:
        scan_builtin_styles()

    preferences = context.preferences.addons['qarch'].preferences  # note: self is passed to functions
    style_name = preferences.build_style

    if style_name == "":
        return empty_enums

    key = style_name + "_categories"

    search, show_curves, show_scripts = find_search_props(self, context)

    lst = dynamic_enum_sets.get(key)
    if lst is None:
        lst = []
        for k, v in dynamic_enum_sets[style_name].items():
            # make user friendly label
            if k.startswith(BT_IMG_SCRIPT):
                label = k[len(BT_IMG_SCRIPT):]
            elif k.startswith(BT_IMG_CURVE):
                label = k[len(BT_IMG_CURVE):]
            else:
                label = k
            lst.append(
                (k, label, "{} [{} items]".format(k, len(v)), len(lst)+1)
            )
        dynamic_enum_sets[key] = lst

    # the catalog changes rarely for normal users, so we load all the enums once and then filter the list
    if show_scripts:
        lst = [e for e in lst if e[0].startswith(BT_IMG_SCRIPT)]  # names should be script_door, etc. when in catalog
    elif show_curves:
        lst = [e for e in lst if e[0].startswith(BT_IMG_CURVE)]  # names should be script_door, etc. when in catalog
    else:
        lst = [e for e in lst if not e[0].startswith(BT_IMG_SCRIPT)]

    if len(lst)==0:
        return empty_enums
    return empty_enums + lst


def enum_category_items(self, context):
    """Callback uses self.category_name, self.search_text"""
    if len(catalogs) == 0:
        scan_builtin_styles()

    preferences = context.preferences.addons['qarch'].preferences  # note: self is passed to functions
    style_name = preferences.build_style
    category_name = self.category_name
    if (style_name == "") or (category_name == "0"):
        return empty_icon_enums

    lst = dynamic_enum_sets[style_name][category_name]

    search, show_curves, show_scripts = find_search_props(self, context)
    if len(search) > 2:
        lst = [e for e in lst if (search in e[1].lower()) or (search in e[2].lower())]

    if len(lst)==0:
        return empty_icon_enums
    return empty_icon_enums + lst


# basic face tags, user can add more
lst_FaceEnums = [
    ("DELETE", "Delete", "Delete face at end"),
    ("NOTHING", "Nothing", "No special tag"),
    ("WALL", "Wall", "Wall face"),
    ("GLASS", "Glass", "Glass face"),
    ("TRIM", "Trim", "Framing around door or window"),
    ("DOOR", "Door", "Face of door, may become vertex group"),
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
