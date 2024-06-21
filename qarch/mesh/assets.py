"""Importing mesh from other blend files"""
import bpy
import gpu
import sys
import os
import subprocess
import pathlib
import json

PY_VERSION = "python3.10"
# use property update function
#  load file-> grab collection list and place into global enum generator
#              and put object names into dict[collection]=[names] for another enum generator
#  select collection enum -> push filter onto name picker enum function

# a smarter thing would be to register as an asset drop target and let user just dump assets from the asset library

# import mesh -> set layers and op id -> merge with active mesh

WIDTH = 256
HEIGHT = 256


def draw(image_name):
    context = bpy.context
    scene = context.scene

    view_matrix = scene.camera.matrix_world.inverted()

    projection_matrix = scene.camera.calc_matrix_camera(
        context.evaluated_depsgraph_get(), x=WIDTH, y=HEIGHT)

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for s in area.spaces:
                if s.type == "VIEW_3D":
                    break
            for r in area.regions:
                if r.type == "WINDOW":
                    break

    offscreen = gpu.types.GPUOffScreen(WIDTH, HEIGHT)
    with offscreen.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        offscreen.draw_view3d(
            scene,
            context.view_layer,
            s,  # context.space_data,
            r,  # context.region,
            view_matrix,
            projection_matrix,
            do_color_management=True)
        gpu.state.depth_mask_set(False)

        fb = gpu.state.active_framebuffer_get()
        buffer = fb.read_color(0, 0, WIDTH, HEIGHT, 4, 0, 'UBYTE')

    offscreen.free()

    if image_name not in bpy.data.images:
        bpy.data.images.new(image_name, WIDTH, HEIGHT)
    image = bpy.data.images[image_name]
    image.scale(WIDTH, HEIGHT)

    buffer.dimensions = WIDTH * HEIGHT * 4
    image.pixels = [v / 255 for v in buffer]
    return image


def gen_import_script(obj_name, filepath, b_delete):
    from ..ops import qarch_asset_dir
    text = """import bpy
    obj_name = "{}"
    filepath = "{}"
    b_delete = {}
    if b_delete:
        try:
            obj = bpy.data.objects[obj_name]
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        data_to.objects.append(obj_name)
    bpy.data.collections["Collection"].objects.link(bpy.data.objects[obj_name])
    bpy.ops.wm.save_mainfile()
    """.format(obj_name, filepath, b_delete)

    txt_file = qarch_asset_dir / "import_asset.py"
    txt_file.write_text(text)


def export_mesh(obj, style_name, category_name, category_item, description):
    from ..ops import qarch_asset_dir, mesh_name, to_path, BT_CATALOG_SRC
    from ..object import is_bt_object, Journal

    qual_name = mesh_name(category_item)  # prefix with mesh_

    txt_file = to_path(style_name, category_name, qual_name)
    img_file = txt_file.with_suffix(".png")
    img_file.parent.mkdir(parents=True, exist_ok=True)

    img = draw(category_item)
    img.save(filepath=str(img_file))

    obj.name = qual_name
    # create a custom property that will survive naming conflicts (obj.001)
    obj[BT_CATALOG_SRC] = "{}/{}/{}".format(style_name, category_name, qual_name)

    # crate a description file; we could also dump a journal here
    if is_bt_object(obj):
        j = Journal(obj)
        j.set_description(description)
        j.flush()
        txt = json.dumps(j.jj, indent=4)
    else:
        txt = json.dumps({'description': description})
    txt_file.write_text(txt)

    python_exe = os.path.join(sys.prefix, 'bin', PY_VERSION)
    p = pathlib.Path(python_exe)
    blender_exe = str(p.parents[3] / "blender")

    gen_import_script(obj.name, bpy.data.filepath, True)

    libpath = qarch_asset_dir / "{}.blend".format(style_name)
    scriptpath = qarch_asset_dir / "import_asset.py"
    subprocess.call([blender_exe, "--background", str(libpath), "--python", str(scriptpath)])


def find_object(style_name, category_name, category_item):
    from ..ops import BT_CATALOG_SRC
    qual_name = category_item  # because this is called from operators with enums that have the qualified stem

    first_cut = [ob for ob in bpy.data.objects if ob.name.startswith(qual_name)]
    test = "{}/{}/{}".format(style_name, category_name, category_item)
    for ob in first_cut:
        if hasattr(ob, BT_CATALOG_SRC):
            if ob[BT_CATALOG_SRC] == test:
                return ob

    return None


def import_mesh(style_name, category_name, category_item):
    from ..ops import qarch_asset_dir, mesh_name, to_path
    from ..object import get_bt_collection, get_obj_data, JOURNAL_PROP_NAME, get_block

    ob = find_object(style_name, category_name, category_item)
    if ob is not None:
        print("found")
        return ob

    # we want to restore this at the end
    active = bpy.context.active_object

    # probably loads as the last item in objects, but just in case
    cur_objs = set(obj.name for obj in bpy.data.objects)

    libpath = qarch_asset_dir / "{}.blend".format(style_name)
    with bpy.data.libraries.load(str(libpath), link=False) as (data_from, data_to):
        if category_item not in data_from.objects:
            print("item not in library")
            for name in data_from.objects:
                print(name)
        data_to.objects.append(category_item)

    bpy.ops.ed.undo_push(message="loaded {} from {}".format(category_item, style_name))

    for obj in bpy.data.objects:
        if obj.name in cur_objs:
            continue
        obj.name = category_item
        col = get_bt_collection()
        col.objects.link(obj)

        txt_file = to_path(style_name, category_name, category_item)
        txt = txt_file.read_text()
        as_dict = json.loads(txt)  # as a minimum, we have a dict with description in it
        if 'controlled' in as_dict:
            text_block = get_block(obj)  # create the block
            text_block.write(txt)
            bpy.ops.ed.undo_push(message="loaded text block")

        # restore status
        obj.select_set(False)
        active.select_set(True)
        bpy.context.view_layer.objects.active = active
        bpy.ops.object.mode_set(mode='EDIT')

        return obj
    print("No new object")
