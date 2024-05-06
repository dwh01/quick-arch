import bpy
import bmesh
import pickle

from .add_window_props import AddWindowProperty
from .window_types import build_window, edit_window
from ...utils import get_object_data, get_children, managed_bmesh, get_parent_type, calc_face_dimensions, get_relative_offset

class QARCH_OT_add_window(bpy.types.Operator):
    """Create window from selected faces"""

    bl_idname = "qarch.add_window"
    bl_label = "Add Window"
    bl_options = {"REGISTER", "UNDO"}

    props: bpy.props.PointerProperty(type=AddWindowProperty)

    @classmethod
    def poll(cls, context):
        if context.object is None:
            return False
        if context.mode == "OBJECT":
            obj = get_parent_type(context.object, "window")
            return obj is not None

        return context.mode == "EDIT_MESH"


    def execute(self, context):
        if context.mode == "OBJECT":
            self.prepare_for_edit(context)
            # this is goofy but calling build window here creates the same window as before
            # and leaves the property panel visible, but locked: maybe because it keeps
            # rolling back all the way each time it tries to update?
            # Stop here so the blank face is put back, and we enter edit mode.
            # User must click button a second time to create the window with a live property panel
            return {"FINISHED"}

        return build_window(context, self.props)

    def prepare_for_edit(self, context):
        obj = get_parent_type(context.object, "window")

        window_opts = get_object_data(obj, "create")

        lst_del = get_children(obj)
        lst_del.reverse()
        lst_del.append(obj)

        parent = obj.parent
        dw_faces = window_opts['dw_faces']
        # fill in hole for window creation
        with managed_bmesh(parent) as bm:
            bm.verts.ensure_lookup_table()
            for f in bm.faces:
                f.select_set(False)

            # assuming 1, multiple windows will break don't know which is which
            for a_verts in dw_faces:
                vlist = []
                for coord in a_verts:
                    vlist.append(bm.verts.new(coord))
                a = bm.faces.new(vlist)
                a.normal_update()
                shift = window_opts['depth']
                for v in a.verts:
                    v.co = v.co + shift * a.normal
                a.select_set(True)

                vlist = []
                a_verts.reverse()
                for coord in a_verts:
                    vlist.append(bm.verts.new(coord))
                b = bm.faces.new(vlist)

                self.props.init(
                    calc_face_dimensions(a),
                    calc_face_dimensions(b),
                    get_relative_offset(a, b),
                )

                self.props.from_dict(window_opts['prop'])
                self.props.count = 1  # because only one window selected for editing
                self.props.size_offset.offset.x = 0  # because perfectly fits the restored face
                self.props.size_offset.offset.y = 0

        parent.select_set(True)
        bpy.context.view_layer.objects.active = parent
        bpy.context.view_layer.update()
        # print(bpy.context.object, parent)

        for obj in lst_del:
            obj.select_set(False)
            bpy.data.objects.remove(obj, do_unlink=True)

        #if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='EDIT')


    def draw(self, context):
        self.props.draw(context, self.layout)
