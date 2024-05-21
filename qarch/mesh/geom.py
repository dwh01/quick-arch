"""Geometry creation routines"""
import bpy, bmesh
from .utils import ManagedMesh, managed_bm
from .SmartPoly import SmartPoly
from mathutils import Vector, Matrix
import math


def _common_start(obj, sel_info, break_link=False):
    mm = ManagedMesh(obj)
    vlist_nested = mm.get_sel_verts(sel_info)

    control_poly = SmartPoly(name="control")
    for vlist in vlist_nested:
        for v in vlist:
            control_poly.add(v, break_link)
    if len(control_poly.coord):
        control_poly.calculate()

    return mm, control_poly


def _extract_offset(size_dict, box_size):
    sx, sy = size_dict['offset_x'], size_dict['offset_y']
    rel_x, rel_y = size_dict['is_relative_x'], size_dict['is_relative_y']
    if rel_x:
        sx = box_size.x * sx
    if rel_y:
        sy = box_size.x * sx
    return sx, sy


def _extract_size(size_dict, box_size):
    sx, sy = size_dict['size_x'], size_dict['size_y']
    rel_x, rel_y = size_dict['is_relative_x'], size_dict['is_relative_y']
    if rel_x:
        sx = box_size.x * sx
    if rel_y:
        sy = box_size.x * sy
    return sx, sy

def _extract_vector(direction_dict):
    x = direction_dict['x']
    y = direction_dict['y']
    z = direction_dict['z']
    return x, y, z


def union_polygon(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info)
    mm.set_op(op_id)

    poly = prop_dict['poly']
    n, start_ang = poly['num_sides'], poly['start_angle']

    new_poly = SmartPoly(matrix=control_poly.matrix, name="new")
    new_poly.center = control_poly.center
    new_poly.generate_ngon(n, start_ang)
    if new_poly.normal.dot(control_poly.normal) < .999:  # flipped normal
        new_poly.flip_z()

    # shift center off origin such that scaling to relative size 1 exactly fits control bounding box
    box_center = (new_poly.bbox[1] + new_poly.bbox[0])/2
    new_poly.shift_2d(-box_center)
    # global alignment with control
    new_poly.center = control_poly.center

    # scale to size
    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    if new_poly.box_size.x != 0:
        sx = sx / new_poly.box_size.x
    if new_poly.box_size.y != 0:
        sy = sy / new_poly.box_size.y
    new_poly.scale(sx, sy)

    # offset
    align_corner = control_poly.bbox[0] - new_poly.bbox[0]
    sx, sy = _extract_offset(prop_dict['position'], control_poly.box_size)
    align_corner.x += sx
    align_corner.y += sy
    new_poly.shift_2d(align_corner)

    new_poly.update_3d()  # 3d offset of polygons used when clipping
    new_poly.calculate()  # refresh winding angles, center, etc
    if len(control_poly.coord) >= 3:
        lst_result = new_poly.clip_with(control_poly)
    else:
        lst_result = [new_poly]

    for r_poly in lst_result:
        # make new face
        face = r_poly.make_face(mm)

    # finalize and save
    mm.to_mesh()
    mm.free()


def inset_polygon(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    if len(control_poly.coord) < 3:
        return

    new_poly = SmartPoly(matrix=control_poly.matrix, name="new")
    new_poly.center = control_poly.center

    if prop_dict['use_ngon'] == True:
        poly = prop_dict['poly']
        n, start_ang = poly['num_sides'], poly['start_angle']

        new_poly.generate_ngon(n, start_ang)

        # shift center off origin such that scaling to relative size 1 exactly fits control bounding box
        box_center = (new_poly.bbox[1] + new_poly.bbox[0]) / 2
        new_poly.shift_2d(-box_center)
        # global alignment with control
        new_poly.center = control_poly.center

        sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
        if new_poly.box_size.x != 0:
            sx = sx/new_poly.box_size.x
        if new_poly.box_size.y != 0:
            sy = sy/new_poly.box_size.y
        new_poly.scale(sx, sy)
    else:
        arch_type = prop_dict['arch']['arch_type']
        n = prop_dict['arch']['num_sides']
        sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)

        # nc = len(control_poly.coord)
        # if nc < n/3:
        #     split = 2
        # elif nc < n/2:
        #     split = 1
        # else:
        #     split = 0
        # if split:  # make nicer transition on top and sides
        #     for i in range(len(control_poly.coord)-1, -1, -1):
        #         if (control_poly.coord[i].winding < 5/4*math.pi-0.01) or (control_poly.coord[i].winding > 7/4*math.pi-0.01):
        #             control_poly.split_edge(i, split)
        #     control_poly.calculate()

        new_poly.generate_arch(sx, sy, n, arch_type)
        new_poly.center = control_poly.center

    # offset
    align_corner = control_poly.bbox[0] - new_poly.bbox[0]
    sx, sy = _extract_offset(prop_dict['position'], control_poly.box_size)
    align_corner.x += sx
    align_corner.y += sy
    new_poly.shift_2d(align_corner)

    # shift center z
    if prop_dict['extrude_distance'] != 0:
        new_poly.center = new_poly.center + new_poly.normal * prop_dict['extrude_distance']

    new_poly.update_3d()  # 3d offset of polygons used when clipping
    new_poly.calculate()  # refresh winding angles, center, etc
    if new_poly.normal.dot(control_poly.normal) < .999:  # flipped normal
        new_poly.flip_z()

    # make bmesh verts so bridge faces share them
    control_poly.make_verts(mm)
    new_poly.make_verts(mm)

    add_perimeter = prop_dict['add_perimeter']
    lst_result = new_poly.bridge(control_poly, mm, add_perimeter)
    lst_result.insert(0, new_poly)

    for r_poly in lst_result:
        # make new face
        face = r_poly.make_face(mm)

    # finalize and save
    mm.to_mesh()
    mm.free()


def grid_divide(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info)
    mm.set_op(op_id)

    count_x = prop_dict['count_x']
    count_y = prop_dict['count_y']

    lst_poly = control_poly.grid_divide(count_x, count_y)

    # the cells don't share vertices unless we make it so
    dct_new = {}
    for poly in lst_poly:
        for c in poly.coord:
            r = round(c.co3.x, 6), round(c.co3.y, 6), round(c.co3.z, 6)
            if r in dct_new:
                c.bm_vert = dct_new[r]
            else:
                c.bm_vert = mm.new_vert(c.co3)
                dct_new[r] = c.bm_vert
        face = poly.make_face(mm)

    if len(lst_poly):
        # remove old face
        face = mm.find_face_by_smart_vec(control_poly.coord)
        if face is not None:
            mm.delete_face(face)
        mm.to_mesh()

    mm.free()


def split_face(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    control_poly.make_verts(mm)  # so they can be shared

    lst_poly = []
    if prop_dict['cut_type']=='POINT':
        i = prop_dict['from_point']
        j = prop_dict['to_point']
        lst_poly = control_poly.split_points(i, j)

    else:
        cut_x = prop_dict['cut_type']=='X'
        i = prop_dict['from_point']
        pt = control_poly.coord[i].co2
        lst_poly = control_poly.split_xy(pt, cut_x, mm)

    for poly in lst_poly:
        face = poly.make_face(mm)

    if len(lst_poly):
        # remove old face
        face = mm.find_face_by_smart_vec(control_poly.coord)
        if face is not None:
            mm.delete_face(face)
        mm.to_mesh()
    # else discard new points and leave old face in place

    mm.free()


def extrude_fancy(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    sx0, sy0 = _extract_size(prop_dict['size'], control_poly.box_size)
    if control_poly.box_size.x != 0:
        sx0 = sx0 / control_poly.box_size.x
    if control_poly.box_size.y != 0:
        sy0 = sy0 / control_poly.box_size.y
    dz0 = prop_dict['distance']
    da0 = prop_dict['twist']
    steps = prop_dict['steps']

    sx = sx0**(1/steps)
    sy = sy0**(1/steps)
    dz = dz0/steps
    da = da0/steps

    control_poly.make_verts(mm)
    bottom_poly = control_poly
    lst_layers = []
    for i in range(steps):
        top_poly = SmartPoly()
        top_poly.add(bottom_poly.coord, break_link=True)

        if (i == 0) and (prop_dict['on_axis']==True):
            # project not rotate
            v = Vector((prop_dict['axis']['x'], prop_dict['axis']['y'], prop_dict['axis']['z']))
            top_poly.project_to(v)
        top_poly.calculate()

        # scale to size
        top_poly.scale(sx, sy)

        # move center
        top_poly.center += top_poly.normal * dz

        top_poly.rotate(da)

        top_poly.update_3d()  # 3d offset of polygons used when clipping
        top_poly.calculate()  # refresh winding angles, center, etc

        top_poly.make_verts(mm)  # to share
        lst_poly = top_poly.bridge(bottom_poly, mm)
        lst_layers.append(lst_poly)

        bottom_poly = top_poly

    lst_layers.append([bottom_poly]) # add the cap face

    for lst_poly in lst_layers:
        for r_poly in lst_poly:
            # make new face
            face = r_poly.make_face(mm)

    # finalize and save
    mm.to_mesh()
    mm.free()


def extrude_sweep(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    ox, oy, oz = _extract_vector(prop_dict['origin'])
    ax, ay, az = _extract_vector(prop_dict['axis'])
    v_origin = Vector((ox, oy, oz))
    v_axis = Vector((ax, ay, az))
    ang = prop_dict['angle']
    sx0, sy0 = _extract_size(prop_dict['size'], control_poly.box_size)
    if control_poly.box_size.x != 0:
        sx0 = sx0 / control_poly.box_size.x
    if control_poly.box_size.y != 0:
        sy0 = sy0 / control_poly.box_size.y
    steps = prop_dict['steps']

    sx = sx0 ** (1 / steps)
    sy = sy0 ** (1 / steps)
    da = ang/steps

    control_poly.make_verts(mm)
    bottom_poly = control_poly
    lst_layers = []
    for i in range(steps):
        top_poly = SmartPoly()
        top_poly.add(bottom_poly.coord, break_link=True)
        top_poly.calculate()

        # scale to size
        top_poly.scale(sx, sy)
        top_poly.update_3d()  # 3d offset of polygons used when clipping

        # sweep
        mat = Matrix.Rotation(da, 3, v_axis)
        top_poly.shift_3d(-v_origin)
        top_poly.apply_matrix(mat)
        top_poly.shift_3d(v_origin)

        top_poly.calculate()  # refresh winding angles, center, etc

        top_poly.make_verts(mm)  # to share
        lst_poly = top_poly.bridge(bottom_poly, mm)
        lst_layers.append(lst_poly)

        bottom_poly = top_poly

    lst_layers.append([bottom_poly])  # add the cap face

    for lst_poly in lst_layers:
        for r_poly in lst_poly:
            # make new face
            face = r_poly.make_face(mm)

    # finalize and save
    mm.to_mesh()
    mm.free()


def solidify_edges(self, obj, sel_info, op_id, prop_dict):
    pass


def make_louvers(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    count_x = prop_dict['count_x']  # sets of louvers
    count_y = prop_dict['count_y']  # blades per louver
    margin_x = prop_dict['margin_x']  # space on either side of a louver
    margin_y = prop_dict['margin_y']  # space above and below a louver
    connect = prop_dict['connect_louvers']  # like stairs
    blade_angle = prop_dict['blade_angle']
    blade_thickness = ['blade_thickness']
    depth_thickness = prop_dict['depth_thickness']
    depth_offset = prop_dict['depth_offset']
    flip_xy = prop_dict['flip_xy']

    # array of cubes really
    if flip_xy:
        w = control_poly.box_size.y / count_x
        h = control_poly.box_size.x
    else:
        w = control_poly.box_size.x / count_x
        h = control_poly.box_size.y

    n_gaps = 1 + count_x
    w_gaps = n_gaps * margin_x
    w_louvers = w - w_gaps
    blade_w = w_louvers / count_x
    v_depth = Vector((0,0,depth_offset))

    for i_x in range(count_x):
        marg_0, marg_1 = margin_x/2, margin_x/2  # interior louvers are centered
        if i_x == 0:
            marg_0 = margin_x
        if i_x == count_x-1:
            marg_1 = margin_x
        # louver extents
        if flip_xy:
            p_min = control_poly.bbox[0] + Vector((margin_y, i_x * w + marg_0))
            p_max = control_poly.bbox[0] + Vector((h-margin_y, (i_x + 1) * w - marg_1))
            v_origin = p_min.x, (p_min.y + p_max.y) / 2
            v_step = (p_max.x - p_min.x) / (count_y - 1), 0
            rot = Matrix.Rotation(blade_angle, 4, 'Y') @ Matrix.Rotation(math.pi/2, 4, 'X')

        else:
            p_min = control_poly.bbox[0] + Vector((i_x*w + marg_0, margin_y))
            p_max = control_poly.bbox[0] + Vector(((i_x+1)*w - marg_1, h-margin_y))
            v_origin = (p_min.x + p_max.x)/2, p_min.y
            v_step = 0, (p_max.y - p_min.y)/(count_y-1)
            rot = Matrix.Rotation(blade_angle, 4, 'X')

        for i_y in range(count_y):
            blade_verts = mm.cube(blade_w, depth_thickness, blade_thickness)
            # rotate and translate blade_faces
            for vert in blade_verts:
                vert.co = rot @ vert.co + i_y * v_step + v_origin + v_depth
                vert.co = control_poly.inverse @ vert.co + control_poly.center

    # could add an option to remove the face, but usually we are making window shades and want to keep the glass
    # face = mm.find_face_by_smart_vec(control_poly.coord)
    # if face is not None:
    #     mm.delete_face(face)
    #     mm.to_mesh()
    mm.free()
