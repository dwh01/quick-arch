"""Importing mesh from other blend files"""
import bpy
import gpu

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

def find_or_load(obj_name, txt_file):
    try:
        obj = bpy.data.objects[obj_name]
        return obj
    except Exception:
        pass

    active = bpy.context.active_object
    # probably the last item in objects, but just in case
    cur_objs = set(obj.name for obj in bpy.data.objects)
    bpy.ops.import_mesh.stl(filepath=str(txt_file))
    bpy.ops.ed.undo_push(message="loaded {}".format(obj_name))

    for obj in bpy.data.objects:
        if obj.name in cur_objs:
            continue
        obj.name = obj_name

        obj.select_set(False)
        active.select_set(True)
        bpy.context.view_layer.objects.active = active
        bpy.ops.object.mode_set(mode='EDIT')  # load seems to kick us into object mode

        return obj
