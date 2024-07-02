import bpy
from bpy.app.handlers import persistent

debug_undo_state = False

lst_cls = []
# use push so we don't have to update pull functions all the time

for mod_name in ['dynamic_enums', 'properties', 'custom', 'compound', 'assets', 'geom', 'state']:
    pathname = f'qarch.ops.{mod_name}'
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

def register_ops():
    for cls in lst_cls:
        bpy.utils.register_class(cls)

    if debug_undo_state:
        bpy.app.handlers.undo_pre.append(pre_undo_handler)
        bpy.app.handlers.undo_post.append(post_undo_handler)
        bpy.app.handlers.depsgraph_update_post.append(post_redo_handler)


def unregister_ops():
    for cls in lst_cls:
        bpy.utils.unregister_class(cls)
