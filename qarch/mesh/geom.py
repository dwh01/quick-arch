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
    mm, orig_poly = _common_start(obj, sel_info, break_link=False)
    mm.set_op(op_id)
    if len(orig_poly.coord) < 3:
        return

    control_poly = SmartPoly()
    control_poly.add(orig_poly.coord, break_link = True)
    control_poly.calculate()

    new_poly = SmartPoly(matrix=control_poly.matrix, name="new")
    new_poly.center = control_poly.center

    thickness = prop_dict['thickness']
    inner_arch = None
    if prop_dict['use_ngon']:
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

        if thickness > 0:
            new_poly.update_3d()
            inner_arch = SmartPoly()
            inner_arch.add(new_poly.coord, break_link=True)
            lst_ray = []  # collect first otherwise we affect the next one in line
            # TODO = calculate cosine correction for uniform frame
            for i in range(len(inner_arch.coord)):
                pt, ray = inner_arch.outward_ray_idx(i)
                lst_ray.append(ray)
            for i in range(len(inner_arch.coord)):
                inner_arch.coord[i].co3 -= lst_ray[i]*thickness
            inner_arch.calculate()

    elif prop_dict['use_arch']:
        arch_type = prop_dict['arch']['arch_type']
        n = prop_dict['arch']['num_sides']
        sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)

        inner_arch = new_poly.generate_arch(sx, sy, n, arch_type, thickness)
        new_poly.center = control_poly.center

    else:  # self similar
        new_poly = SmartPoly()
        new_poly.add(control_poly.coord, break_link=True)
        new_poly.calculate()

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

    # shift center z
    b_extruding = False
    if prop_dict['extrude_distance'] != 0:
        new_poly.center = new_poly.center + new_poly.normal * prop_dict['extrude_distance']
        b_extruding = True

    new_poly.update_3d()  # 3d offset of polygons used when clipping
    new_poly.calculate()  # refresh winding angles, center, etc
    if new_poly.normal.dot(control_poly.normal) < .999:  # flipped normal
        new_poly.flip_z()
        if inner_arch:
            inner_arch.flip_z()

    # make bmesh verts so bridge faces share them
    control_poly.make_verts(mm)
    new_poly.make_verts(mm)

    add_perimeter = prop_dict['add_perimeter']
    lst_result = new_poly.bridge(control_poly, mm, add_perimeter, b_extruding)
    if inner_arch:
        dc = new_poly.center - inner_arch.center
        inner_arch.shift_3d(dc)
        if prop_dict['use_arch']:
            offset = new_poly.coord[0].co3 - inner_arch.coord[0].co3
            vy = new_poly.ydir.dot(offset) * new_poly.ydir
            inner_arch.shift_3d(vy)

            inner_arch.make_verts(mm)
            tmp = inner_arch.coord
            tmp.reverse()
            new_poly.coord += tmp

        else:
            inner_arch.make_verts(mm)
            tmp = inner_arch.coord.copy()
            tmp.reverse()
            # without this, the bottom is not connected (which was good for the arch)
            close_0 = mm.new_vert(new_poly.coord[0].co3)
            close_1 = mm.new_vert(inner_arch.coord[0].co3)
            new_poly.add(close_0, break_link=False)
            new_poly.add(close_1, break_link=False)
            new_poly.coord += tmp

        lst_result.insert(0, inner_arch)
        lst_result.insert(0, new_poly)
    else:
        lst_result.insert(0, new_poly)

    for r_poly in lst_result:
        # make new face
        face = r_poly.make_face(mm)

    if len(lst_result):
        face = mm.find_face_by_smart_vec(orig_poly.coord)
        if face is not None:
            mm.delete_face(face)

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
        lst_poly = top_poly.bridge_by_number(bottom_poly)
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
        lst_poly = top_poly.bridge_by_number(bottom_poly)
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
    mm, control_poly = _common_start(obj, sel_info, break_link=False)
    mm.set_op(op_id)

    # cross section, this poly should have z in the control plane
    mat_inline = Matrix.Identity(3)
    for i in range(3):
        mat_inline[0][i] = control_poly.normal[i]
        mat_inline[1][i] = control_poly.xdir[i]
        mat_inline[2][i] = control_poly.ydir[i]

    poly = prop_dict['poly']
    n, start_ang = poly['num_sides'], poly['start_angle']
    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    do_horizontal = prop_dict['do_horizontal']
    do_vertical = prop_dict['do_vertical']

    z_offset = prop_dict['z_offset']
    vz = z_offset * control_poly.normal

    lst_poly = []
    lst_connect = []  # needed so we know to square off the ends
    ncp = len(control_poly.coord)
    for i in range(ncp):
        e = control_poly.coord[(i+1) % ncp].co3 - control_poly.coord[i].co3
        if e.length > 0:
            e.normalize()
            conn = True
            if abs(e.x) >= abs(e.y):
                is_horiz = True
                if not do_horizontal:
                    conn = False
            else:
                is_horiz = False
                if not do_vertical:
                    conn = False
            lst_connect.append(conn)

    for i in range(ncp):
        e = control_poly.coord[(i + 1) % ncp].co3 - control_poly.coord[i].co3
        if e.length > 0:
            e.normalize()
            b_bevel = lst_connect[(i + ncp -1) % ncp] and lst_connect[i]
            b_make = lst_connect[(i + ncp -1) % ncp] or lst_connect[i]

            if not b_bevel:
                if not lst_connect[i]: # align with last edge instead of this edge
                    e = control_poly.coord[i].co3 - control_poly.coord[(i + ncp - 1) % ncp].co3
                    e.normalize()

                crs = control_poly.xdir.cross(e)
                dx = control_poly.xdir.dot(e)
                dy = math.asin(crs.length)
                if crs.dot(control_poly.normal) < 0:
                    dy = -dy
                ang = math.atan2(dy, dx)
                r90 = -math.pi / 2
                ang = ang + r90  # not normal but edge points outward

                rmat = Matrix.Rotation(ang, 3, 'X')  # local x is control normal
                edge_mat = rmat @ mat_inline

                # test sometimes the polygon is flipped TODO, not working yet
                vtest = edge_mat @ e
                test = Vector((0,0,1)).dot(vtest)
                if test < 0:
                    rmat = Matrix.Rotation(math.pi, 3, 'X')  # local x is control normal
                    edge_mat = rmat @ edge_mat

            else:
                pt_out, ray_out = control_poly.outward_ray_idx(i)
                crs = control_poly.xdir.cross(ray_out)
                dx = control_poly.xdir.dot(ray_out)
                dy = math.asin(crs.length)
                if crs.dot(control_poly.normal) < 0:
                    dy = -dy
                ang = math.atan2(dy, dx)

                r90 = -math.pi / 2
                ang = ang + r90  # not normal but edge points outward
                rmat = Matrix.Rotation(ang, 3, 'X')   # local x is control normal
                edge_mat = rmat @ mat_inline

                # test sometimes the polygon is flipped
                vtest = edge_mat @ e
                test = Vector((0,0,1)).dot(vtest)
                if test < 0:
                    rmat = Matrix.Rotation(math.pi, 3, 'X')  # local x is control normal
                    edge_mat = rmat @ edge_mat

            new_poly = SmartPoly(matrix=edge_mat, name="new")
            new_poly.center = control_poly.coord[i].co3
            new_poly.generate_ngon(n, start_ang)
            if new_poly.box_size.x != 0:
                sx0 = sx / new_poly.box_size.x
            else:
                sx0 = sx
            if new_poly.box_size.y != 0:
                sy0 = sy / new_poly.box_size.y
            else:
                sy0 = sy
            new_poly.scale(sx0, sy0)

            new_poly.update_3d()  # 3d offset of polygons used when clipping
            new_poly.shift_3d(vz)
            new_poly.calculate()
            if b_make:
                new_poly.make_verts(mm)
            lst_poly.append(new_poly)

    lst_ext = []
    for i in range(ncp):
        ii = (i + 1) % ncp
        if lst_connect[i]:
            lst_f = lst_poly[ii].bridge_by_number(lst_poly[i], 0)
            lst_ext = lst_ext + lst_f
        elif lst_connect[(i+ncp-1) % ncp]:  # dlose end of tube
            lst_ext.append(lst_poly[i])
        if not lst_connect[(i+ncp-1) % ncp]:  # close start of tube
            lst_ext.append(lst_poly[i])


    if len(lst_ext):
        for poly in lst_ext:
            face = poly.make_face(mm)
        mm.to_mesh()
    mm.free()


def make_louvers(self, obj, sel_info, op_id, prop_dict):
    mm, control_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    count_x = prop_dict['count_x']  # sets of louvers
    count_y = prop_dict['count_y']  # blades per louver
    margin_x = prop_dict['margin_x']  # space on either side of a louver
    margin_y = prop_dict['margin_y']  # space above and below a louver
    connect = prop_dict['connect_louvers']  # TODO like stairs
    blade_angle = prop_dict['blade_angle']
    blade_thickness = prop_dict['blade_thickness']
    depth_thickness = prop_dict['depth_thickness']
    depth_offset = prop_dict['depth_offset']
    flip_xy = prop_dict['flip_xy']

    # array of cubes really
    if flip_xy:
        w = control_poly.box_size.y
        h = control_poly.box_size.x
    else:
        w = control_poly.box_size.x
        h = control_poly.box_size.y

    n_gaps = 1 + count_x
    w_gaps = n_gaps * margin_x
    w_louvers = w - w_gaps
    blade_w = w_louvers / count_x
    v_depth = Vector((0,0,depth_offset))

    x_start = 0
    for i_x in range(count_x):
        marg_0, marg_1 = margin_x/2, margin_x/2  # interior louvers are centered
        if i_x == 0:
            marg_0 = margin_x
        if i_x == count_x-1:
            marg_1 = margin_x
        # louver extents
        if flip_xy:
            p_min = control_poly.bbox[0] + Vector((margin_y, x_start + marg_0))
            p_max = control_poly.bbox[0] + Vector((h-margin_y, x_start + marg_0 + blade_w))
            v_origin = p_min.x, (p_min.y + p_max.y) / 2
            v_step = (p_max.x - p_min.x) / (count_y - 1), 0
            rot = Matrix.Rotation(blade_angle, 4, 'Y') @ Matrix.Rotation(math.pi/2, 4, 'Z')

        else:
            p_min = control_poly.bbox[0] + Vector((x_start, margin_y))
            p_max = control_poly.bbox[0] + Vector((x_start + marg_0 + blade_w, h-margin_y))
            v_origin = (p_min.x + p_max.x)/2, p_min.y
            v_step = 0, (p_max.y - p_min.y)/(count_y-1)
            rot = Matrix.Rotation(blade_angle, 4, 'X')
        x_start = x_start + marg_0 + blade_w + marg_1

        v_origin = Vector(v_origin).to_3d()
        v_step = Vector(v_step).to_3d()
        for i_y in range(count_y):
            blade_verts = mm.cube(blade_w, depth_thickness, blade_thickness)
            # rotate and translate blade_faces
            for vert in blade_verts:
                v1 = rot @ vert.co + i_y * v_step + v_origin + v_depth
                v1 = control_poly.inverse @ v1 + control_poly.center
                vert.co = v1

    # could add an option to remove the face, but usually we are making window shades and want to keep the glass
    # face = mm.find_face_by_smart_vec(control_poly.coord)
    # if face is not None:
    #     mm.delete_face(face)
    #     mm.to_mesh()
    mm.to_mesh()
    mm.free()
