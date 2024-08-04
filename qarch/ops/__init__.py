import bpy
from bpy.app.handlers import persistent
from .. import __package__ as base_package
from .dynamic_enums import load_styles, load_previews, qarch_asset_dir, user_asset_dir
from .properties import StyleNameProperty

debug_undo_state = False

lst_cls = []
# use push so we don't have to update pull functions all the time

for mod_name in ['dynamic_enums', 'properties', 'custom', 'compound', 'assets', 'geom', 'state']:
    pathname = f'{base_package}.ops.{mod_name}'
    _temp = __import__(pathname, globals(), locals(), ['lst_classes', 'lst_funcs'], 0)
    lst_classes = _temp.lst_classes
    lst_funcs = _temp.lst_funcs

    _temp2 = __import__(pathname, globals(), locals(), lst_classes, 0)
    for cls_name in lst_classes:
        globals()[cls_name] = getattr(_temp2, cls_name)
        lst_cls.append(globals()[cls_name])

    # not just functions, anything not registered with bpy but imported at module level
    _temp2 = __import__(pathname, globals(), locals(), lst_funcs, 0)
    for cls_name in lst_funcs:
        globals()[cls_name] = getattr(_temp2, cls_name)


@persistent
def pre_undo_handler(*args):
    print("pre undo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def post_undo_handler(*args):
    print("post undo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def pre_redo_handler(*args):
    print("pre redo", args)
    bpy.context.window_manager.print_undo_steps()
@persistent
def post_redo_handler(*args):
    print("post deps", args)
    bpy.context.window_manager.print_undo_steps()

# --- progress bar
# https://blog.michelanders.nl/2021/05/progress-indicator-updated.html
# update function to tag all info areas for redraw
def update(self, context):
    areas = context.window.screen.areas
    for area in areas:
        if area.type == 'VIEW3d':
            area.tag_redraw()


# a variable where we can store the original draw funtion
info_header_draw = lambda s, c: None


def register_progress():
    # a value between [0,100] will show the slider
    bpy.types.Scene.progress_indicator = bpy.props.FloatProperty(
        default=-1,
        subtype='PERCENTAGE',
        precision=1,
        min=-1,
        soft_min=0,
        soft_max=100,
        max=101,
        update=update)

    # the label in front of the slider can be configured
    bpy.types.Scene.progress_indicator_text = bpy.props.StringProperty(
        default="Progress",
        update=update)

    # save the original draw method of the Info header
    global info_header_draw
    info_header_draw = bpy.types.VIEW3D_HT_tool_header.draw

    # create a new draw function
    def newdraw(self, context):
        global info_header_draw
        # first call the original stuff
        info_header_draw(self, context)
        # then add the prop that acts as a progress indicator
        if (context.scene.progress_indicator >= 0) and (context.scene.progress_indicator <= 100):
            self.layout.separator()
            text = context.scene.progress_indicator_text
            self.layout.prop(context.scene,
                             "progress_indicator",
                             text=text,
                             slider=True)

            # replace it

    bpy.types.VIEW3D_HT_tool_header.draw = newdraw


def unregister_progress():
    bpy.types.VIEW3D_HT_tool_header.draw = info_header_draw


def register_ops():
    load_styles()
    bpy.app.timers.register(load_previews, first_interval=2)  # delay because long, let interface get up and running

    for cls in lst_cls:
        bpy.utils.register_class(cls)

    bpy.types.Scene.style_list = bpy.props.CollectionProperty(type=StyleNameProperty)

    if debug_undo_state:
        bpy.app.handlers.undo_pre.append(pre_undo_handler)
        bpy.app.handlers.undo_post.append(post_undo_handler)
        bpy.app.handlers.depsgraph_update_post.append(post_redo_handler)

    register_progress()

def unregister_ops():
    for cls in lst_cls:
        bpy.utils.unregister_class(cls)

    unregister_progress()
