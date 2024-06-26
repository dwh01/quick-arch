import bpy
from bpy.props import PointerProperty, BoolProperty

from ..generic import SizeOffsetProperty, CountProperty, FrameProperty
from ..arch import ArchProperty
from .window_props import WindowProperty
from ...utils import get_limits, infer_values

class AddWindowProperty(bpy.types.PropertyGroup):

    count: CountProperty
    only_hole: BoolProperty(name="Only hole", default=False, description="Only hole. No window/frame")
    arch: PointerProperty(type=ArchProperty)
    size_offset: PointerProperty(type=SizeOffsetProperty)
    frame: PointerProperty(type=FrameProperty)
    window: PointerProperty(type=WindowProperty)
    add_arch: BoolProperty(name="Add Arch", default=False, description="Add arch over door/window")
    infer_values_switch: BoolProperty(name="Inferred Values", default=False, description="Inferred values")

    def init(self, wall_dimensions, opposite_wall_dimensions, relative_offset):
        self["limits"] = get_limits(wall_dimensions, opposite_wall_dimensions, relative_offset)
        self.size_offset.init(
            self["limits"],
            default_size=(1.0, 1.2),
            default_offset=((wall_dimensions[0]-1.0)/2, 0.8),
        )
        # call set_offset and set_size to restrict values
        self.size_offset.offset = self.size_offset.offset
        self.size_offset.size = self.size_offset.size

    def draw(self, context, layout):

        self.size_offset.draw(context, layout)

        col = layout.column(align=True)
        col.prop(self, "only_hole")

        if not self.only_hole:

            layout.separator()
            col = layout.column()
            col.label(text="Frame")
            self.frame.draw(context, col)

            layout.separator()
            col = layout.column()
            col.label(text="Window")
            self.window.draw(context, col)

        layout.separator()
        col = layout.column(align=True)
        col.prop(self, "add_arch")
        if self.add_arch:
            self.arch.draw(context, col)

        layout.separator()
        col = layout.column(align=True)
        if not self.infer_values_switch:
            col.prop(self, "infer_values_switch", icon="RIGHTARROW", emboss=False)
        else:
            col.prop(self, "infer_values_switch", icon="DOWNARROW_HLT", emboss=False)
            values = infer_values(self, "w")
            filtered_values = {k:v for k,v in values.items() if k.startswith("Window")}
            for key,value in filtered_values.items():
                row = col.row(align=True)
                row.label(text=str(key))
                row.label(text=str(value))
