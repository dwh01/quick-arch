import bpy
from bpy.props import IntProperty, FloatProperty, EnumProperty, PointerProperty


class FillPanel(bpy.types.PropertyGroup):

    count_x: IntProperty(
        name="Horizontal Count",
        min=1,
        max=10,
        default=2,
        description="Number of panels in horizontal direction",
    )

    count_y: IntProperty(
        name="Vertical Count",
        min=1,
        max=10,
        default=2,
        description="Number of panels in vertical direction",
    )

    panel_border: FloatProperty(
        name="Panel Border",
        min=0.01,
        max=1.0,
        default=0.03,
        unit="LENGTH",
        description="Borders of each panel",
    )

    margin: FloatProperty(
        name="Margin",
        min=0.01,
        max=1.0,
        default=0.15,
        unit="LENGTH",
        description="Margin",
    )

    panel_gap: FloatProperty(
        name="Gap",
        step=1,
        min=0.01,
        max=1.0,
        default=0.1,
        unit="LENGTH",
        description="Gap between panels",
    )

    panel_depth: FloatProperty(
        name="Panel Depth",
        step=1,
        min=0.01,
        max=0.1,
        default=0.01,
        unit="LENGTH",
        description="Depth of panels",
    )

    def draw(self, layout):

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "count_x")
        row.prop(self, "count_y")
        row = col.row(align=True)
        row.prop(self, "margin")
        row.prop(self, "panel_gap")
        row = col.row(align=True)
        row.prop(self, "panel_border")
        row.prop(self, "panel_depth")

    def to_dict(self):
        d = {'count_x': self.count_x, 'count_y': self.count_y, 'panel_border': self.panel_border,
             'margin': self.margin, 'panel_gap':self.panel_gap, 'panel_depth': self.panel_depth}
        return d

    def from_dict(self, d):
        self.count_x = d['count_x']
        self.count_y = d['count_y']
        self.panel_border = d['panel_border']
        self.margin = d['margin']
        self.panel_gap = d['panel_gap']
        self.panel_depth = d['panel_depth']

class FillGlassPanes(bpy.types.PropertyGroup):

    count_x: IntProperty(
        name="Horizontal Count",
        min=1,
        max=10,
        default=2,
        description="Number of panes in horizontal direction",
    )

    count_y: IntProperty(
        name="Vertical Count",
        min=1,
        max=10,
        default=2,
        description="Number of panes in vertical direction",
    )

    pane_border: FloatProperty(
        name="Pane Border",
        min=0.01,
        max=1.0,
        default=0.01,
        unit="LENGTH",
        description="Borders of each pane",
    )

    margin: FloatProperty(
        name="Margin",
        min=0.01,
        max=1.0,
        default=0.1,
        unit="LENGTH",
        description="Margin",
    )

    pane_gap: FloatProperty(
        name="Gap",
        step=1,
        min=0.01,
        max=1.0,
        default=0.01,
        unit="LENGTH",
        description="Gap between panes",
    )

    glass_thickness: FloatProperty(
        name="Glass Thickness",
        step=1,
        min=0.01,
        max=0.1,
        default=0.002,
        unit="LENGTH",
        description="Thickness of glass",
    )

    def draw(self, layout):

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "count_x")
        row.prop(self, "count_y")
        row = col.row(align=True)
        row.prop(self, "margin")
        row.prop(self, "pane_gap")
        row = col.row(align=True)
        row.prop(self, "pane_border")
        row.prop(self, "glass_thickness")

    def to_dict(self):
        d = {'count_x': self.count_x, 'count_y': self.count_y, 'pane_border': self.pane_border,
             'margin': self.margin, 'pane_gap':self.pane_gap, 'glass_thickness': self.glass_thickness}
        return d

    def from_dict(self, d):
        self.count_x = d['count_x']
        self.count_y = d['count_y']
        self.pane_border = d['pane_border']
        self.margin = d['margin']
        self.pane_gap = d['pane_gap']
        self.glass_thickness = d['glass_thickness']


class FillLouver(bpy.types.PropertyGroup):
    louver_width: FloatProperty(
        name="Louver Width",
        step=1,
        min=0.01,
        max=1.0,
        default=0.04,
        description="Width of louvers",
    )

    margin: FloatProperty(
        name="Margin",
        step=1,
        min=0.01,
        max=1.0,
        default=0.15,
        unit="LENGTH",
        description="Margin of louvers from face border",
    )

    def draw(self, layout):
        row = layout.row(align=True)
        row.prop(self, "margin")
        row.prop(self, "louver_width")

    def to_dict(self):
        d = {'louver_width': self.louver_width, 'margin': self.margin}
        return d

    def from_dict(self, d):
        self.louver_width = d['louver_width']
        self.margin = d['margin']


class FillBars(bpy.types.PropertyGroup):
    bar_count_x: IntProperty(
        name="Horizontal Bars",
        min=0,
        max=100,
        default=5,
        description="Number of horizontal bars",
    )

    bar_count_y: IntProperty(
        name="Vertical Bars",
        min=0,
        max=100,
        default=1,
        description="Number of vertical bars",
    )

    bar_radius: FloatProperty(
        name="Bar Radius",
        min=0.01,
        max=1.0,
        default=0.01,
        unit="LENGTH",
        description="Radius of bars"
    )

    bar_depth: FloatProperty(
        name="Bar Depth",
        min=0.0,
        max=1.0,
        default=0.04,
        unit="LENGTH",
        description="Depth of bars",
    )

    def draw(self, layout):

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "bar_count_x")
        row.prop(self, "bar_count_y")
        row = col.row(align=True)
        row.prop(self, "bar_radius")
        row.prop(self, "bar_depth")

    def to_dict(self):
        d = {'bar_count_x': self.bar_count_x, 'bar_count_y': self.bar_count_y, 'bar_radius': self.bar_radius,
             'bar_depth': self.bar_depth}
        return d

    def from_dict(self, d):
        self.bar_count_x = d['bar_count_x']
        self.bar_count_y = d['bar_count_y']
        self.bar_radius = d['bar_radius']
        self.bar_depth = d['bar_depth']



class FillProperty(bpy.types.PropertyGroup):

    fill_types = [
        ("NONE", "None", "", 0),
        ("PANELS", "Panels", "", 1),
        ("GLASS_PANES", "Glass Panes", "", 2),
        ("LOUVER", "Louver", "", 3),
        # ("BAR", "Bars", "", 4),
    ]

    fill_type: EnumProperty(
        name="Fill Type",
        items=fill_types,
        default="NONE",
        description="Type of fill for door",
    )

    panel_fill: PointerProperty(type=FillPanel)
    glass_fill: PointerProperty(type=FillGlassPanes)
    louver_fill: PointerProperty(type=FillLouver)
    # bar_fill: PointerProperty(type=FillBars)

    def draw(self, context, layout):

        prop_name = (
            "Fill Type"
            if self.fill_type == "NONE"
            else self.fill_type.title().replace("_", " ")
        )
        # col = layout.column(align=True)
        layout.prop_menu_enum(self, "fill_type", text=prop_name)

        # -- draw fill types
        fill_map = {
            "PANELS": self.panel_fill,
            "LOUVER": self.louver_fill,
            "GLASS_PANES": self.glass_fill,
            # "BAR": self.bar_fill,
        }
        fill = fill_map.get(self.fill_type)
        if fill:
            fill.draw(layout)

    def to_dict(self):
        d = {'fill_type': self.fill_type, 'panel_fill': self.panel_fill.to_dict(),
             'glass_fill': self.glass_fill.to_dict(), 'louver_fill': self.louver_fill.to_dict()}
        return d

    def from_dict(self, d):
        self.fill_type = d['fill_type']
        self.panel_fill.from_dict(d['panel_fill'])
        self.glass_fill.from_dict(d['glass_fill'])
        self.louver_fill.from_dict(d['louver_fill'])