"""Geometry creation routines"""
import copy
import json
import random
import bpy, bmesh
from ..object import TopologyInfo, SelectionInfo, get_bt_collection, get_instance_collection
from .utils import ManagedMesh, managed_bm
from .SmartPoly import SmartPoly
from .coordsys import CoordSys, approx

from mathutils import Vector, Matrix, Euler
import mathutils
import math
import functools, operator
import pathlib
from collections import defaultdict

from ..bpypolyskel import bpypolyskel
import Polygon, Polygon.Shapes, Polygon.Utils


def coincident(pt1, pt2):
    dv = (pt1 - pt2).length
    if dv < 1e-6:
        return True
    return False


def _common_start(obj, sel_info, break_link=False):
    mm = ManagedMesh(obj)
    faces = mm.get_faces(sel_info)

    lst_out = []
    for face in faces:
        control_poly = SmartPoly(CoordSys(face=face, mm=mm), pt_list=face, break_link=break_link)
        lst_out.append(control_poly)

    if (sel_info.get_mode() == 'REGION') and (len(lst_out) > 0):
        # group by plane
        dct_n = defaultdict(list)
        for p in lst_out:
            t = (round(p.normal().x, 3), round(p.normal().y, 3), round(p.normal().z, 3))
            dct_n[t].append(p)

        lst_out = []
        for lst in dct_n.values():
            if len(lst) == 1:
                lst_out.append(lst[0])
            elif len(lst) > 1:  # merge all with first in list
                poly = lst[0]
                p_union = poly.union(lst[1:])
                lst_out.append(p_union)
        # allow-holes could be another mode, for now ignore holes in result polygons (use region boundary)

    return mm, lst_out


def _extract_offset(size_dict, box_size, new_size):
    sx, sy = size_dict['offset_x'], size_dict['offset_y']
    rel_x, rel_y = size_dict['is_relative_x'], size_dict['is_relative_y']
    if rel_x and (box_size.x > 0):
        sx = box_size.x * sx
    if rel_y and (box_size.y > 0):
        sy = box_size.y * sy

    if size_dict.get('center_x', False):
        sx = (box_size.x - new_size.x)/2 + sx
    if size_dict.get('center_y', False):
        sy = (box_size.y - new_size.y)/2 + sy
    return sx, sy


def _extract_size(size_dict, box_size):
    sx, sy = size_dict['size_x'], size_dict['size_y']
    rel_x, rel_y = size_dict['is_relative_x'], size_dict['is_relative_y']
    if rel_x and (box_size.x > 0):
        sx = box_size.x * sx
    if rel_y and (box_size.y > 0):
        sy = box_size.y * sy
    if sx < 0:
        sx = box_size.x + sx
    if sy < 0:
        sy = box_size.y + sy
    return sx, sy


def _extract_vector(direction_dict):
    x = direction_dict['x']
    y = direction_dict['y']
    z = direction_dict['z']
    return x, y, z


def pointing_to_euler(pointing):
    if abs(pointing.dot(Vector((1, 0, 0)))) > abs(pointing.dot(Vector((0, 1, 0)))):
        track = pointing.to_track_quat('Z', 'X')
    else:
        track = pointing.to_track_quat('Z', 'Y')
    eul = track.to_euler()
    rot = Vector(eul)
    return rot


def radial_to_euler(radial, normal):
    mat = Matrix.Identity(3)
    mat[0] = radial.cross(normal)
    mat[1] = radial
    mat[2] = normal
    eul = mat.to_euler()
    rot = Vector(eul)
    return rot


def random_origin(i_edge, size):
    random.seed(i_edge)  # repeatable
    a = 2 * math.pi * random.random()
    r_origin = 2 * size * random.random()
    z_origin = size*random.random()
    origin = Vector((r_origin * math.cos(a), r_origin * math.sin(a), z_origin))
    return origin


def calc_face_uv(face, mm, mode=None, orig=None):
    from ..ops.properties import uv_mode_list
    uv_layer = mm.bm.loops.layers.uv.active
    if mode is None:
        mode = face[mm.key_uv]
    if orig is None:
        orig = face[mm.key_uv_orig]
    rot = face[mm.key_uv_rot]

    mode = uv_mode_list[mode][0]
    if abs(face.normal[2]) < 0.99:
        poly = SmartPoly(CoordSys(face=face, mm=mm, radial=Vector((0,0,1))), pt_list=face, b_no_roll=True)
    else:
        poly = SmartPoly(CoordSys(face=face, mm=mm), pt_list=face, b_no_roll=True)
    r = 1
    if mode in ['GLOBAL_XY', 'GLOBAL_YX']:
        # project origin to plane
        d = poly.normal().dot(poly.points[0].co3)
        v = d * poly.normal()
        poly.coord_sys.origin = v
        poly.calc_2d(b_no_roll=True)
        v = Vector((0,0))

    elif mode in ['FACE_XY', 'FACE_YX']:
        v = Vector((0, 0))
    elif mode in ['FACE_BBOX']:
        v = poly.bbox_min
    elif mode == 'FACE_POLAR':
        #rel = [pc.co3 - orig for pc in poly.points]
        #csys = CoordSys(mm, normal=poly.normal(), radial=Vector((0,0,1)), origin=orig)
        #gxy = [csys.make_2d(p) for p in rel]
        v = poly.coord_sys.make_2d(orig)
        gxy = [(pc.co2 - v) for pc in poly.points]
        r = [a.length for a in gxy]
        r = functools.reduce(max, r, 0)
    elif mode == 'ORIENTED':
        v = orig.to_2d()  # unused
    elif mode == 'ORIENTED_PLAN':
        v = poly.bbox_min
    elif mode == 'ORIENTED_SPIN':
        v = orig
    else:  # none
        return

    for i, loop in enumerate(face.loops):
        if mode in ['ORIENTED', 'ORIENTED_SPIN']:
            xyw = poly.points[i].co3 - orig
            loop[mm.key_uv_w] = xyw.z
            xy = xyw.to_2d()
        elif mode == 'ORIENTED_PLAN':
            xy = poly.points[i].co2 - v
            if poly.box_size.x != 0:
                xy.x /= poly.box_size.x
            if poly.box_size.y != 0:
                xy.y /= poly.box_size.y
            loop[mm.key_uv_w] = 0
            # these next lines make sure that the flipped coordinates are in 0 to 1 range
            if rot[0] != 0:  # flipping y
                xy.y -= 1
            if rot[1] != 0:  # flipping x
                xy.x -= 1
        elif mode == 'FACE_POLAR':
            xy = gxy[i]
        else:
            xy = poly.points[i].co2 - v

        if mode in ['GLOBAL_YX', 'FACE_YX']:  # swap x and y
            xy = Vector((xy.y, xy.x))
        elif mode == 'FACE_POLAR':
            loop[mm.key_uv_w] = r  # scale factor for angle to dimension
        elif mode in ['FACE_BBOX']:
            if poly.box_size.x != 0:
                xy.x /= poly.box_size.x
            if poly.box_size.y != 0:
                xy.y /= poly.box_size.y

        loop[uv_layer].uv = xy


def _shift_and_size(control_poly, new_poly, prop_dict):
    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    start_2d = control_poly.bbox_min + Vector(_extract_offset(prop_dict['position'], control_poly.box_size, Vector((sx,sy))))
    corner = control_poly.coord_sys.make_3d(start_2d)

    new_poly.fit_box(corner, (sx, sy))
    new_poly.update_bmvert()

    return new_poly


def _move_verts(lst_poly, v3):
    for poly in lst_poly:
        poly.make_verts()  # does nothing if they exist

    mm = lst_poly[0].coord_sys.mm
    mm.bm.verts.ensure_lookup_table()
    mm.bm.verts.index_update()  # without this, sometimes still have -1 indices?
    # for v in mm.bm.verts:
    #    print(v.index, v.is_valid, v.co)
    #    if v.is_valid:
    #        assert v.index > -1

    done = {}  # shared verts, don't shift more than once
    for poly in lst_poly:
        for sv in poly.points:
            if sv.bm_vert.index not in done:
                sv.co3 += v3
                sv.bm_vert.co = sv.co3
                done[sv.bm_vert.index] = True
        poly.face_attr["uv_origin"] += v3
        poly.calc_2d()
    return lst_poly


def _make_ngon(control_poly, prop_dict, mm, b_make=True):
    poly = prop_dict['poly']
    n, start_ang = poly['num_sides'], poly['start_angle']
    thickness = prop_dict['frame']

    new_poly = control_poly.generate_ngon(n, start_ang)
    _shift_and_size(control_poly, new_poly, prop_dict)

    if b_make:
        new_poly.make_verts()

    lst = [new_poly]
    if thickness > 0:
        inner_poly = new_poly.generate_inset(thickness)
        if b_make:
            inner_poly.make_verts()

        lst_b = inner_poly.bridge(new_poly)

        material_index = mm.get_material_index(prop_dict['frame_material'])
        for i_edge, p in enumerate(lst_b):  # make frames orient around the polygon
            v_edge = new_poly.points[(i_edge + 1) % len(new_poly.points)].co3 - new_poly.points[i_edge].co3
            v_radial = new_poly.normal().cross(v_edge.normalized())
            # ctr = p.calc_center_median()

            p.face_attr['material'] = material_index
            p.face_attr['radial'] = v_radial

        lst = lst_b  # don't keep the full size poly
        lst.append(inner_poly)

    return lst, new_poly


def _make_self_poly(control_poly, prop_dict, mm, b_make=True):
    if prop_dict['by_inset']:
        new_poly = control_poly.generate_inset(prop_dict['thickness'])
    else:
        new_poly = SmartPoly(control_poly.coord_sys, pt_list=control_poly.points, break_link=True)
        _shift_and_size(control_poly, new_poly, prop_dict)

    if b_make:
        new_poly.make_verts()

    return [new_poly], new_poly


def _make_arch(control_poly, prop_dict, mm, b_make=True):
    from .coordsys import approx_vector
    arch_type = prop_dict['arch']['arch_type']
    n = prop_dict['arch']['num_sides']
    thickness = prop_dict['frame']
    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    drop_sides = prop_dict['arch'].get('drop_length', 0)

    lst_arch, boundary = control_poly.generate_arch(sx, sy, n, arch_type, thickness, drop_sides)
    bpoly = SmartPoly(control_poly.coord_sys, pt_list=boundary, break_link=False)

    # arch is built to size, but may need shifting
    align_2d = Vector(_extract_offset(prop_dict['position'], control_poly.box_size, Vector((sx, sy))))
    v0 = control_poly.coord_sys.make_3d(control_poly.bbox_min + align_2d)

    v1 = control_poly.coord_sys.make_3d(bpoly.bbox_min)
    v2 = v0 - v1
    _move_verts(lst_arch + [bpoly], v2)

    return lst_arch, bpoly


def _make_super(control_poly, prop_dict, mm, b_make=True):
    resolution = prop_dict['resolution']
    super_dict = prop_dict['super_curve']
    start_angle = super_dict['start_angle']
    x, sx, px = super_dict['x'], super_dict['sx'], super_dict['px']
    y, sy, py = super_dict['y'], super_dict['sy'], super_dict['py']
    pn = super_dict['pn']
    new_poly = control_poly.generate_super(x, sx, px, y, sy, py, pn, resolution, start_angle)
    _shift_and_size(control_poly, new_poly, prop_dict)

    if b_make:
        new_poly.make_verts()
    lst = [new_poly]

    return lst, new_poly


def _make_curve_poly(control_poly, prop_dict, mm, b_make=True):
    resolution = prop_dict['resolution']
    ob_dict = prop_dict['local_object']
    ob_name = ob_dict['object_name']

    eul = Euler(ob_dict['rotate'])
    mat_rot = eul.to_matrix()

    curve_obj = bpy.data.objects[ob_name]
    spline = curve_obj.data.splines[0]

    if len(spline.bezier_points) >= 2:
        r = resolution + 1
        segments = len(spline.bezier_points)
        if not spline.use_cyclic_u:
            segments -= 1

        points = []
        for i in range(segments):
            inext = (i + 1) % len(spline.bezier_points)

            knot1 = spline.bezier_points[i].co
            handle1 = spline.bezier_points[i].handle_right
            handle2 = spline.bezier_points[inext].handle_left
            knot2 = spline.bezier_points[inext].co

            _points = mathutils.geometry.interpolate_bezier(knot1, handle1, handle2, knot2, r)
            if i < segments - 1:
                points = points + _points[:-1]
            else:
                points = points + _points

        # strip out straight lines
        lst_points = [points[0]]
        for i in range(1, len(points) - 1):
            e = (points[i] - points[i - 1]).normalized()
            e1 = (points[i + 1] - points[i]).normalized()
            if e.dot(e1) < 0.999:
                lst_points.append(points[i])
        lst_points.append(points[-1])

        # rotation
        lst_points = [mat_rot @ p for p in lst_points]
        new_poly = SmartPoly(coord_sys=control_poly.coord_sys, pt_list=lst_points)
        _shift_and_size(control_poly, new_poly, prop_dict)

        if b_make:
            new_poly.make_verts()
    else:
        return [], None

    return [new_poly], new_poly


def text_to_curve(text, name):
    from ..ops.dynamic_enums import BT_IMG_DESC
    dct_curve = json.loads(text)
    curve_obj = bpy.data.curves.new(name, type='CURVE')
    obj = bpy.data.objects.new(name, object_data=curve_obj)

    sp = curve_obj.splines.new(type="BEZIER")
    sp.bezier_points.add(len(dct_curve['bezier_points']))
    for i, dat in enumerate(dct_curve['bezier_points']):
        bp = sp.bezier_points[i]
        bp.co = dat['co']
        bp.handle_left = dat['handle_left']
        bp.handle_left_type = dat['handle_left_type']
        bp.handle_right = dat['handle_right']
        bp.handle_right_type = dat['handle_right_type']

    col = get_bt_collection()
    col.objects.link(obj)
    obj[BT_IMG_DESC] = dct_curve['description']

    try:
        bpy.ops.ed.undo_push(message="Created curve {}".format(name))
    except Exception:  # wrong context?
        pass

    return obj


def curve_to_text(obj, description):
    lst = []
    for bp in obj.data.splines[0].bezier_points:
        dat = {'co': tuple(bp.co),
               'handle_left': tuple(bp.handle_left),
               'handle_left_type': bp.handle_left_type,
               'handle_right': tuple(bp.handle_right),
               'handle_right_type': bp.handle_right_type,
               }
        lst.append(dat)
    dct_curve = {'description': description, 'bezier_points': lst}
    return json.dumps(dct_curve)


def _make_catalog_poly(control_poly, prop_dict, mm, context, b_make=True):
    from ..ops.dynamic_enums import file_type, from_path, BT_CATALOG_SRC

    cat_dict = prop_dict['catalog_object']
    obj_path = pathlib.Path(cat_dict['category_item'])
    ftype, obj_name = file_type(obj_path.stem)

    try:  # see if loaded already
        obj = bpy.data.objects[obj_name]
    except Exception:
        if ftype in ['curve']:
            text = obj_path.read_text()
        else:
            assert False, "Wrong file type, expected curve"

        obj = text_to_curve(text, obj_name)

        # metadata so we can check for refresh if we swap style order
        style, category, name = from_path(obj_path)
        obj[BT_CATALOG_SRC] = style

    spoof = copy.deepcopy(prop_dict)
    spoof['local_object']['object_name'] = obj_name
    spoof['local_object']['rotate'] = cat_dict['rotate']

    return _make_curve_poly(control_poly, spoof, mm, b_make)


def inset_polygon(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    if len(lst_orig_poly) == 0:  # ok to add to none
        print("no original poly for inset operation")
        lst_orig_poly.append(SmartPoly(CoordSys(mm=mm)))
        prop_dict['join'] = 'FREE'
        prop_dict['size']['is_relative_x'] = False
        prop_dict['size']['is_relative_y'] = False

    shape_type = prop_dict['shape_type']
    join_type = prop_dict['join']
    frame_mat = prop_dict['frame_material']
    center_mat = prop_dict['center_material']
    add_perimeter = prop_dict['add_perimeter']
    # avoid errors with missing objects
    if (shape_type == 'CATALOG') and (prop_dict['catalog_object']['category_item'] in ['', 'N/A', '0']):
        shape_type = 'SELF'
    if (shape_type == 'CURVE') and (prop_dict['local_object']['object_name'] in ['', 'N/A', '0']):
        shape_type = 'SELF'
    arch_info = None  # special for arch
    frame_idx = mm.get_material_index(frame_mat)
    center_idx = mm.get_material_index(center_mat)

    topo = TopologyInfo(from_keys=['Bridge', 'Center', 'Frame'])

    for control_poly in lst_orig_poly:  # note, if a region, the first face provides the info
        b_close = True
        if shape_type == 'NGON':
            lst_new, outer = _make_ngon(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new) - 1)
            topo.add('Center')
        elif shape_type == 'SELF':
            lst_new, outer = _make_self_poly(control_poly, prop_dict, mm)
            topo.add('Center')
        elif shape_type == 'ARCH':
            arch_info = prop_dict['arch']['arch_type'], (prop_dict['arch']['drop_length'] != 0)
            b_close = False
            lst_new, outer = _make_arch(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new) - 1)
            topo.add('Center')
        elif shape_type == 'SUPER':
            lst_new, outer = _make_super(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new) - 1)
            topo.add('Center')
        elif shape_type == 'CURVE':
            lst_new, outer = _make_curve_poly(control_poly, prop_dict, mm)
            topo.add('Center')
        elif shape_type == 'CATALOG':
            lst_new, outer = _make_catalog_poly(control_poly, prop_dict, mm, self.context)
            topo.add('Center')
        else:
            assert False, "Unhandled shape type {}".format(shape_type)

        # catalog curves could be any orientation
        b_extruding = False
        for i_new, p in enumerate(lst_new):
            if p.normal().dot(control_poly.normal()) < .999:  # flipped normal
                p.flip_normal()

        # single poly can be clipped
        if (len(lst_new) == 1) and (len(control_poly.points) >= 3):
            if join_type in ['INSIDE', 'OUTSIDE']:
                lst_new = lst_new[0].clip_with(control_poly, join_type)
                if len(lst_new):
                    outer = lst_new[0]
        if len(lst_new) == 0:
            continue

        # shift all together, don't double shift shared verts
        v_extruding = None
        if prop_dict['extrude_distance'] != 0:
            v_extruding = lst_new[0].normal() * prop_dict['extrude_distance']
            if outer not in lst_new:
                lst_tmp = lst_new + [outer]  # in case boundary is not one of the polys (arch, for example)
                _move_verts(lst_tmp, v_extruding)
            else:
                _move_verts(lst_new, v_extruding)

        for i_new, p in enumerate(lst_new):
            if i_new == len(lst_new) - 1:
                p.face_attr['material'] = center_idx
                if 'uv_mode' in p.face_attr:
                    del p.face_attr['uv_mode']  # don't inherit from control, let material decide
            else:
                p.face_attr['material'] = frame_idx
                # uv mode set by arch, etc
            face = p.make_face()

        if join_type == 'BRIDGE':  # and (shape_type != 'SUPER'):
            # make bmesh verts so bridge faces share them
            control_poly.make_verts()
            # ARCH has fake outer, but it used the same bm verts so was updated in position
            lst_result = outer.bridge(control_poly, add_perimeter, v_extruding, b_close=b_close,
                                      b_allow_square=add_perimeter, arch_type=arch_info)
            topo.add('Bridge', len(lst_result))
            for p in lst_result:
                if control_poly.coord_sys.reference_face:
                    p.face_attr['material'] = control_poly.coord_sys.reference_face.material_index
                    if 'uv_mode' in p.face_attr:
                        del p.face_attr['uv_mode']  # let material decide
                face = p.make_face()

            if len(lst_result) and (control_poly.coord_sys.reference_face is not None):
                mm.delete_face(control_poly.coord_sys.reference_face)

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def grid_divide(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=["All"])
    topo.set_modulus("All", prop_dict['count_y'])
    # lsize = None

    for control_poly in lst_orig_poly:
        count_x = prop_dict['count_x']
        count_y = prop_dict['count_y']

        if prop_dict['define_size']:
            sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
            vsize = Vector((sx, sy))
        else:
            sx, sy = 0, 0
            vsize = Vector((control_poly.box_size.x/(count_x+1), control_poly.box_size.y/(count_y+1)))

        ox, oy = _extract_offset(prop_dict['offset'], control_poly.box_size, vsize)

        lst_poly = control_poly.grid_divide(count_x, count_y, ox, oy, sx, sy)
        topo.add("All", len(lst_poly))
        # if lsize is None:
        #     lsize = len(lst_poly)
        # else:
        #     if len(lst_poly) != lsize:
        #         lsize = None

        # the cells don't share vertices unless we make it so
        dct_new = {}
        for poly in lst_poly:
            for c in poly.points:
                r = round(c.co3.x, 6), round(c.co3.y, 6), round(c.co3.z, 6)
                if r in dct_new:
                    c.bm_vert = dct_new[r]
                else:
                    c.bm_vert = mm.new_vert(c.co3)
                    dct_new[r] = c.bm_vert

            face = poly.make_face()

        if len(lst_poly) and control_poly.coord_sys.reference_face:
            mm.delete_face(control_poly.coord_sys.reference_face)

    # don't have a working warp for "every middle" type selections
    # if (lsize is None) or (lsize < 0):
    #     topo.set_modulus("All", prop_dict['count_y'])
    # else:
    #     topo.set_modulus("All", lsize)

    mm.to_mesh()
    mm.free()
    return topo


def split_face(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    # we assume that all faces are split in 2
    # but some properties might result in just 1
    topo = TopologyInfo(from_keys=["All"])
    topo.set_modulus("All", 2)

    for control_poly in lst_orig_poly:
        control_poly.make_verts()  # so they can be shared

        lst_poly = []
        if prop_dict['cut_type'] == 'POINT':
            i = prop_dict['from_point']
            j = prop_dict['to_point']
            lst_poly = control_poly.split_points(i, j)

        else:
            cut_x = prop_dict['cut_type'] == 'X'
            i = prop_dict['from_point']
            pt = control_poly.points[i].co2
            lst_poly = control_poly.split_xy(pt, cut_x)

        for poly in lst_poly:
            face = poly.make_face()
            topo.add("All")

        if len(lst_poly) != 2:  # bad assumption before, have to just use one long list
            topo.set_modulus("All", 0)

        if len(lst_poly) and control_poly.coord_sys.reference_face:
            mm.delete_face(control_poly.coord_sys.reference_face)

    mm.to_mesh()
    mm.free()
    return topo


def extrude_fancy(self, obj, sel_info, op_id, prop_dict):
    from ..ops.properties import uv_mode_to_int, int_to_uv_mode
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Sides', 'Tops'])
    ncoord = len(lst_orig_poly[0].points)

    side_mat = prop_dict['side_material']
    center_mat = prop_dict['center_material']
    side_idx = mm.get_material_index(side_mat)
    center_idx = mm.get_material_index(center_mat)
    keep_y = prop_dict.get('keep_y', False)

    for control_poly in lst_orig_poly:
        if len(control_poly.points) != len(lst_orig_poly[0].points):
            ncoord = None  # no modulus possible

        sx0, sy0 = _extract_size(prop_dict['size'], control_poly.box_size)
        if control_poly.box_size.x != 0:
            sx0 = sx0 / control_poly.box_size.x
        if control_poly.box_size.y != 0:
            sy0 = sy0 / control_poly.box_size.y

        dz0 = prop_dict['distance']
        da0 = prop_dict['twist']
        steps = prop_dict['steps']

        sx = sx0 ** (1 / steps)
        sy = sy0 ** (1 / steps)
        dz = dz0 / steps
        da = da0 / steps

        control_poly.make_verts()
        bottom_poly = control_poly
        lst_layers = []
        for i in range(steps):
            csys = bottom_poly.coord_sys.copy()  # if not on axis, don't want to overwrite bottom origin during shift
            top_poly = SmartPoly(csys, pt_list=bottom_poly.points, break_link=True, b_no_roll=True)
            if (i == 0) and prop_dict['on_axis']:
                # project not rotate
                v = Vector((prop_dict['axis']['x'], prop_dict['axis']['y'], prop_dict['axis']['z']))
                if prop_dict['align_end']:
                    top_poly.project_to(v)
                    top_poly.calc_coord_sys(b_no_roll=True)
            else:
                v = top_poly.normal()

            # scale to size
            ctr = top_poly.calc_center_box()
            top_poly.scale_around(ctr, sx, sy)

            # move center
            v_extruding = v * dz
            top_poly.shift_3d(v * dz)

            ctr = top_poly.calc_center_box()
            top_poly.rotate_2d(da, ctr)

            # op_poly.calculate()  # called by rotate
            if prop_dict['flip_normals']:
                top_poly.flip_normal()

            top_poly.calc_2d(True)

            top_poly.make_verts()  # to share
            lst_poly = top_poly.bridge_by_number(bottom_poly, b_reversed=prop_dict['flip_normals'])
            lst_layers.append(lst_poly)
            topo.add('Sides', len(lst_poly))

            bottom_poly = top_poly

        lst_layers.append([bottom_poly])  # add the cap face
        topo.add('Tops')

        face = None
        for ilayer, lst_poly in enumerate(lst_layers):
            for i, r_poly in enumerate(lst_poly):
                if ilayer == len(lst_layers) - 1:
                    r_poly.face_attr['material'] = center_idx
                    if 'uv_mode' in r_poly.face_attr:
                        del r_poly.face_attr['uv_mode']  # let material decide
                else:
                    r_poly.face_attr['material'] = side_idx
                    if 'uv_mode' in r_poly.face_attr:
                        del r_poly.face_attr['uv_mode']  # let material decide
                if keep_y and control_poly.coord_sys.reference_face:
                    r_poly.face_attr['radial'] = control_poly.coord_sys.reference_face[mm.key_radial]
                    mode = int_to_uv_mode(control_poly.coord_sys.reference_face[mm.key_uv])
                    if (mode=="FACE_POLAR") and (ilayer == len(lst_layers)-1):  # keep arch mode
                        r_poly.face_attr['uv_mode'] = control_poly.coord_sys.reference_face[mm.key_uv]
                # make new face
                face = r_poly.make_face()

        if prop_dict.get('del_source', False):
            if control_poly.coord_sys.reference_face:
                mm.delete_face(control_poly.coord_sys.reference_face)

    if ncoord is not None:
        topo.set_modulus('Sides', ncoord)

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def extrude_sweep(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Sides', 'Tops'])
    ncoord = len(lst_orig_poly[0].points)

    side_mat = prop_dict['side_material']
    center_mat = prop_dict['center_material']
    side_idx = mm.get_material_index(side_mat)
    center_idx = mm.get_material_index(center_mat)

    for control_poly in lst_orig_poly:
        if len(control_poly.points) != len(lst_orig_poly[0].points):
            ncoord = None  # no modulus possible

        ox, oy, oz = _extract_vector(prop_dict['origin'])
        ax, ay, az = _extract_vector(prop_dict['axis'])
        v_origin = control_poly.coord_sys.inverse @ Vector((ox, oy, oz)) + control_poly.coord_sys.make_3d(control_poly.bbox_min)
        v_axis = control_poly.coord_sys.inverse @ Vector((ax, ay, az))

        ang = prop_dict['angle']
        sx0, sy0 = _extract_size(prop_dict['size'], control_poly.box_size)
        if control_poly.box_size.x != 0:
            sx0 = sx0 / control_poly.box_size.x
        if control_poly.box_size.y != 0:
            sy0 = sy0 / control_poly.box_size.y

        steps = prop_dict['steps']

        sx = sx0 ** (1 / steps)
        sy = sy0 ** (1 / steps)
        da = ang / steps

        control_poly.make_verts()
        bottom_poly = control_poly
        lst_layers = []
        for i in range(steps):
            # sweep uses b_no_roll because rotation that flips the normal from + to - z can change the default roll
            # order, and we want to ensure we match by number
            top_poly = SmartPoly(bottom_poly.coord_sys, pt_list=bottom_poly.points, break_link=True, b_no_roll=True)

            # scale to size
            ctr = top_poly.calc_center_box()
            top_poly.scale_around(ctr, sx, sy)

            # sweep around v_origin
            mat = Matrix.Rotation(da, 3, v_axis)
            top_poly.coord_sys.origin = v_origin
            top_poly.apply_rotation_matrix(mat)
            top_poly.coord_sys.origin = top_poly.calc_center_median()

            top_poly.make_verts()  # to share
            lst_poly = top_poly.bridge_by_number(bottom_poly)
            for p in lst_poly:
                x = v_axis.cross(p.normal())
                if x.length:
                    x.normalize()
                    p.face_attr['radial'] = p.normal().cross(x)
                    p.calc_coord_sys(v_axis)
                else:
                    x = v_origin - p.calc_center_box()
                    x.normalize()
                    x = x - v_axis.dot(x)*v_axis
                    p.face_attr['radial'] = x
                    p.calc_coord_sys(x)
            lst_layers.append(lst_poly)
            topo.add('Sides', len(lst_poly))

            bottom_poly = top_poly

        lst_layers.append([bottom_poly])  # add the cap face
        topo.add('Tops')

        for lst_poly in lst_layers:
            for i, r_poly in enumerate(lst_poly):
                if i == len(lst_poly) - 1:
                    r_poly.face_attr['material'] = center_idx
                else:
                    r_poly.face_attr['material'] = side_idx
                # make new face
                face = r_poly.make_face()

    if ncoord is not None:
        topo.set_modulus('Sides', ncoord)
    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def _combined_bbox(lst_poly):
    minv = lst_poly[0].bbox_min
    maxv = lst_poly[0].bbox_min + lst_poly[0].box_size
    for p in lst_poly:
        v = lst_poly[0].coord_sys.make_2d(p.coord_sys.make_3d(p.bbox_min))
        minv.x = min(minv.x, v.x)
        minv.y = min(minv.y, v.y)
        v = lst_poly[0].coord_sys.make_2d(p.coord_sys.make_3d(p.bbox_min + p.box_size))
        maxv.x = max(maxv.x, v.x)
        maxv.y = max(maxv.y, v.y)
    minv = lst_poly[0].coord_sys.make_3d(minv)
    maxv = lst_poly[0].coord_sys.make_3d(maxv)
    return minv, maxv


def solidify_by_bridge(control_poly, side_list, i_edge, edge_dir, vz, inset, mm, frame_idx, topo, lst_new):
    # extracted from solidify to allow swap between revolution and extrude modes
    ncp = len(control_poly.points)
    b_make = i_edge in side_list
    b_bevel_start = ((i_edge + ncp - 1) % ncp) in side_list
    b_bevel_end = ((i_edge + 1) % ncp) in side_list
    if not b_make:
        return

    lst_start = []

    minv, maxv = _combined_bbox(lst_new)
    group_center = (minv+maxv)/2
    group_csys = CoordSys(mm, None, radial=lst_new[0].coord_sys.ydir, normal=lst_new[0].normal(), origin=group_center)

    if b_bevel_start:
        pt_out, ray_out = control_poly.outward_ray_idx(i_edge)
        mat = Matrix.Rotation(math.pi/2, 3, control_poly.normal())
        normal = mat @ ray_out
        e = edge_dir.normalized()
        scale = abs(ray_out.cross(e).length)
        scale = 1 / max(scale, 0.01)
    else:
        normal = edge_dir.normalized()
        scale = 1
    csys = CoordSys(mm, None, radial=control_poly.normal(), normal=normal, origin=control_poly.points[i_edge].co3)
    for i_new in range(len(lst_new)):
        p_example = lst_new[i_new]

        pt2 = [group_csys.make_2d(p.co3) for p in p_example.points]
        pt3 = [csys.make_3d(p) for p in pt2]
        start_poly = SmartPoly(coord_sys=csys, pt_list=pt3, b_no_roll=True)
        start_poly.scale_around(start_poly.coord_sys.origin, scale, 1)

        align = vz + inset * start_poly.coord_sys.xdir * scale
        start_poly.shift_3d(align)
        lst_start.append(start_poly)

    lst_end = []
    j = (i_edge + 1) % len(control_poly.points)
    if b_bevel_end:
        pt_out, ray_out = control_poly.outward_ray_idx(j)
        mat = Matrix.Rotation(math.pi / 2, 3, control_poly.normal())
        normal = mat @ ray_out
        e = (control_poly.points[j].co3 - control_poly.points[i_edge].co3).normalized()
        scale = abs(ray_out.cross(e).length)
        scale = 1 / max(scale, 0.01)
    else:
        normal = edge_dir.normalized()
        scale = 1
    csys = CoordSys(mm, None, radial=control_poly.normal(), normal=normal, origin=control_poly.points[j].co3)
    for i_end in range(len(lst_new)):
        p_example = lst_new[i_end]

        pt2 = [group_csys.make_2d(p.co3) for p in p_example.points]
        pt3 = [csys.make_3d(p) for p in pt2]
        end_poly = SmartPoly(coord_sys=csys, pt_list=pt3, b_no_roll=True)
        end_poly.scale_around(end_poly.coord_sys.origin, scale, 1)

        align = vz + inset * end_poly.coord_sys.xdir * scale
        end_poly.shift_3d(align)
        lst_end.append(end_poly)

    if b_make:
        if not b_bevel_start:  # close off end
            for p in lst_start:
                p.face_attr['material'] = frame_idx
                face = p.make_face()

            topo.add('Starts', len(lst_start))

        if not b_bevel_end:  # close off end
            for p in lst_end:
                p.face_attr['material'] = frame_idx
                face = p.make_face()

            topo.add('Ends', len(lst_end))

        # bridge
        for p1, p2 in zip(lst_start, lst_end):
            p1.make_verts()
            p2.make_verts()
            if p1.normal().dot(p2.normal()) < -0.001:
                b_reversed = True
                idx_offset = len(p1.points)-2
            else:
                b_reversed = False
                idx_offset = 0
            lst_sides = p1.bridge_by_number(p2, idx_offset=idx_offset, b_reversed=b_reversed)
            origin = random_origin(i_edge, p1.box_size.x)
            for p in lst_sides:
                p.face_attr['material'] = frame_idx
                if 'uv_mode' in p.face_attr:
                    del p.face_attr['uv_mode']  # let material decide (didn't do this for ends because might be arch)
                p.face_attr['radial'] = edge_dir.normalized()  # p.normal().cross(edge_dir.normalized()).normalized()
                p.face_attr['uv_rot'] = pointing_to_euler(edge_dir.normalized())
                p.face_attr['uv_origin'] = origin
                p.calc_coord_sys(radial=p.face_attr['radial'])
                check = p1.calc_center_box() - p.calc_center_box()
                if p.normal().dot(check) > 0:
                    p.flip_normal()
                face = p.make_face()

            topo.add('Sides', len(lst_sides))


def solidify_by_revolution(control_poly, side_list, i_edge, edge_dir, vz, n_steps, inset, mm, frame_idx, topo, lst_new):
    # extracted from solidify to allow swap between revolution and extrude modes
    rot_origin = control_poly.points[i_edge].co3

    b_make = i_edge in side_list
    if not b_make:
        return

    minv, maxv = _combined_bbox(lst_new)
    group_center = (minv + maxv) / 2
    group_csys = CoordSys(mm, None, radial=lst_new[0].coord_sys.ydir, normal=lst_new[0].normal(), origin=group_center)

    csys = CoordSys(mm, None, radial=edge_dir.normalized(), normal=control_poly.normal(), origin=rot_origin)
    lst_poly = []
    for i_new in range(len(lst_new)):
        p_example = lst_new[i_new]

        pt2 = [group_csys.make_2d(p.co3) for p in p_example.points]
        pt3 = [csys.make_3d(p) for p in pt2]
        start_poly = SmartPoly(coord_sys=csys, pt_list=pt3, b_no_roll=True)

        corner = start_poly.coord_sys.make_3d(start_poly.bbox_min)
        align = control_poly.points[i_edge] - corner
        align = align - inset * start_poly.coord_sys.xdir

        start_poly.shift_3d(align)

        start_poly.face_attr['material'] = frame_idx
        lst_rev = start_poly.generate_revolve(rot_origin, csys.ydir, n_steps, vz)
        lst_poly = lst_poly + lst_rev
        for p in lst_poly:
            p.face_attr['material'] = frame_idx
            if 'uv_mode' in p.face_attr:
                del p.face_attr['uv_mode']  # let material decide (didn't do this for ends because might be arch)
            p.face_attr['radial'] = -csys.ydir
            p.calc_coord_sys(radial=p.face_attr['radial'])
            face = p.make_face()
        topo.add('Sides', len(lst_poly))
    topo.set_modulus('Sides', len(lst_poly))


def solidify_edges(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=False)
    mm.set_op(op_id)

    shape_type = prop_dict['shape_type']
    frame_mat = prop_dict['frame_material']
    revolutions = prop_dict['revolutions']
    dash_offset = prop_dict['dash_info']['dash_offset']
    dash_length = prop_dict['dash_info']['dash_length']
    dash_spacing = prop_dict['dash_info']['dash_spacing']

    # avoid errors with missing objects
    if (shape_type == 'CATALOG') and (prop_dict['catalog_object']['category_item'] in ['', 'N/A', '0']):
        shape_type = 'SELF'
    if (shape_type == 'CURVE') and (prop_dict['local_object']['object_name'] in ['', 'N/A', '0']):
        shape_type = 'SELF'

    tag = prop_dict['face_tag']
    side_list = []
    if prop_dict['side_list'] != "":
        side_list = prop_dict['side_list'].split(",")
        side_list = [int(s.strip()) for s in side_list]
    b_all_sides = len(side_list) == 0

    inset = prop_dict['inset']
    z_offset = prop_dict['z_offset']

    frame_idx = mm.get_material_index(frame_mat)

    topo = TopologyInfo(from_keys=['Sides', 'Starts', 'Ends'])

    for orig_poly in lst_orig_poly:  # note, if a region, the first face provides the info
        if len(orig_poly.points) < 3:
            continue

        sx, sy = _extract_size(prop_dict['size'], orig_poly.box_size)
        # fake in position to center the shape
        prop_dict['position'] = {'offset_x': -sx / 2, 'is_relative_x': False,
                                 'offset_y': -sy / 2, 'is_relative_y': False}

        ncp = len(orig_poly.points)
        control_poly = SmartPoly(orig_poly.coord_sys)
        if prop_dict['dashed'] and (revolutions < 3) and (dash_spacing > 0) and (dash_length > 0):
            pts_new = [orig_poly.points[0].co3]
            cur_side_list = []
            for i in range(ncp):
                j = (i + 1) % ncp
                d0 = dash_offset
                v0 = orig_poly.points[i].co3
                e = orig_poly.points[j].co3 - v0
                edir = e.normalized()
                b_exact = False  # did we end at corner?
                if d0 > e.length:  # ensure we get something
                    d0 = 0
                while d0 < e.length:
                    v = v0 + d0 * edir
                    pts_new.append(v)
                    d0 = d0 + dash_length
                    if d0 >= e.length:
                        d0 = e.length
                        b_exact = True
                    v = v0 + d0 * edir
                    pts_new.append(v)
                    if b_all_sides or (i in side_list):
                        cur_side_list.append(len(pts_new) - 2)
                    d0 = d0 + dash_spacing
                if b_exact and (dash_offset == 0):  # don't duplicate vertex at corner
                    pts_new = pts_new[:-1]
            control_poly.add(pts_new)

        else:
            control_poly.add(orig_poly.points, break_link=True)
            if b_all_sides:
                side_list = list(range(ncp))
            cur_side_list = side_list.copy()
        control_poly.calc_2d()

        vz = control_poly.normal() * prop_dict['z_offset']

        if shape_type == 'NGON':
            lst_new, outer = _make_ngon(control_poly, prop_dict, mm, False)
            if len(lst_new) > 1:
                lst_new = lst_new[:-1]  # remove center
        elif shape_type == 'SELF':
            lst_new, outer = _make_self_poly(control_poly, prop_dict, mm, False)
        elif shape_type == 'ARCH':
            lst_new, outer = _make_arch(control_poly, prop_dict, mm, False)
            if len(lst_new) > 1:
                lst_new = lst_new[:-1]  # remove center
        elif shape_type == 'SUPER':
            lst_new, outer = _make_super(control_poly, prop_dict, mm, False)
            if len(lst_new) > 1:
                lst_new = lst_new[-1:]  # only keep center
        elif shape_type == 'CURVE':
            lst_new, outer = _make_curve_poly(control_poly, prop_dict, mm, False)
        elif shape_type == 'CATALOG':
            lst_new, outer = _make_catalog_poly(control_poly, prop_dict, mm, self.context, False)
        else:
            assert False, "Unhandled shape type {}".format(shape_type)

        # consolidate lst new to avoid internal walls
        # this is for frames and arches
        if (shape_type == 'ARCH') and (len(lst_new) > 1):  # not closed, so ok to union all
            poly_a = lst_new[0].union(lst_new[1:])
            lst_new = [poly_a]

        elif len(lst_new) > 1:
            if len(lst_new) > 2:
                poly_a = lst_new[0].union(lst_new[1:-1])
            else:
                poly_a = lst_new[0]
            poly_b = lst_new[-1]
            # ensure we only stitch one edge together
            matches = []
            for poly_test in [lst_new[-2], lst_new[0]]:  # for arch, don't know which side might match
                for i_test, sv in enumerate(poly_test.points):
                    for j, sv1 in enumerate(poly_b.points):
                        if coincident(sv.co3, sv1.co3):
                            for k, sv2 in enumerate(poly_a.points):
                                if coincident(sv.co3, sv2.co3):
                                    matches.append((j, k))
                                    break
                            break
                if len(matches):
                    break

            if len(matches) > 1:  # assuming 2 adjacent points, need points in between on poly_b - j index
                if matches[0][1] < matches[1][1]:
                    j1 = matches[0][0]
                    j2 = matches[1][0]
                    ipos = matches[0][1]
                else:
                    j1 = matches[1][0]
                    j2 = matches[0][0]
                    ipos = matches[1][1]
                jidx = list(range(len(poly_b.points)))
                if j1 < j2:
                    jidx = jidx[j2 + 1:] + jidx[:j1]
                else:
                    jidx = jidx[j1 + 1:] + jidx[:j2]

                for j in jidx:
                    poly_a.points.insert(ipos + 1, poly_b.points[j])
                    ipos = ipos + 1
            poly_a.calc_2d()
            lst_new = [poly_a]

        ncp = len(control_poly.points)
        for i_edge in range(ncp):
            e = control_poly.points[(i_edge + 1) % ncp].co3 - control_poly.points[i_edge].co3
            if e.length > 0:
                e.normalize()
                if revolutions < 3:
                    solidify_by_bridge(control_poly, cur_side_list, i_edge, e, vz, inset, mm, frame_idx, topo, lst_new)
                else:
                    solidify_by_revolution(control_poly, cur_side_list, i_edge, e, z_offset, revolutions,
                                           inset, mm, frame_idx, topo, lst_new)

    mm.to_mesh()
    mm.free()
    return topo


def make_louvers(self, obj, sel_info, op_id, prop_dict):
    from ..object import material_best_mode
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Blades', 'Risers'])  # implement risers
    topo.set_modulus('Blades', 6)

    count_x = prop_dict['count_x']  # sets of louvers
    count_y = prop_dict['count_y']  # blades per louver
    margin_x = prop_dict['margin_x']  # space on either side of a louver
    margin_y = prop_dict['margin_y']  # space above and below a louver
    connect = prop_dict['connect_louvers']  # like stairs
    blade_angle = prop_dict['blade_angle']
    blade_thickness = prop_dict['blade_thickness']
    depth_thickness = prop_dict['depth_thickness']
    depth_offset = prop_dict['depth_offset']
    flip_xy = prop_dict['flip_xy']
    material_index = mm.get_material_index(prop_dict['material'])

    for control_poly in lst_orig_poly:
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
        v_depth = Vector((0, 0, depth_offset))

        x_start = 0
        for i_x in range(count_x):
            marg_0, marg_1 = margin_x / 2, margin_x / 2  # interior louvers are centered
            if i_x == 0:
                marg_0 = margin_x
            if i_x == count_x - 1:
                marg_1 = margin_x
            # louver extents
            if flip_xy:
                p_min = control_poly.bbox_min + Vector((margin_y, x_start + marg_0))
                p_max = control_poly.bbox_min + Vector((h - margin_y, x_start + marg_0 + blade_w))
                v_origin = p_min.x, (p_min.y + p_max.y) / 2
                v_step = (p_max.x - p_min.x) / (count_y - 1), 0
                rot = Matrix.Rotation(blade_angle, 4, 'Y') @ Matrix.Rotation(math.pi / 2, 4, 'Z')

            else:
                p_min = control_poly.bbox_min + Vector((x_start, margin_y))
                p_max = control_poly.bbox_min + Vector((x_start + marg_0 + blade_w, h - margin_y))
                v_origin = (p_min.x + p_max.x) / 2, p_min.y
                v_step = 0, (p_max.y - p_min.y) / (count_y - 1)
                rot = Matrix.Rotation(blade_angle, 4, 'X')
            x_start = x_start + marg_0 + blade_w + marg_1

            v_origin = Vector(v_origin).to_3d()
            v_step = Vector(v_step).to_3d()
            vert_last = None
            for i_y in range(count_y):
                blade_verts, blade_faces = mm.cube(blade_w, depth_thickness, blade_thickness)
                # rotate and translate blade_faces
                ctr = control_poly.calc_center_box()
                for vert in blade_verts:
                    v1 = rot @ vert.co + i_y * v_step + v_origin + v_depth
                    v1 = control_poly.coord_sys.inverse @ v1 + ctr
                    vert.co = v1
                for j in range(6):
                    topo.add('Blades')

                # materials and attributes
                v_edge = blade_verts[3].co - blade_verts[0].co
                v_up = blade_verts[4].co - blade_verts[1].co
                org = random_origin(i_y, depth_thickness) + ctr
                attrs = {
                        mm.key_uv_orig: org,
                        mm.key_uv: material_best_mode(mm.obj.data.materials[material_index].name),
                        mm.key_uv_rot: radial_to_euler(v_edge, v_up),
                        mm.key_radial: v_edge,
                    }
                for face in blade_faces:
                    face.material_index = material_index
                    mm.set_face_attrs(face, attrs)
                    calc_face_uv(face, mm)

                attrs[mm.key_uv_orig] = random_origin(i_y, depth_thickness) + blade_verts[0].co
                if connect and vert_last:
                    vlist = [vert_last[0], vert_last[3], blade_verts[6], blade_verts[7]]
                    face = mm.new_face(vlist)
                    face.material_index = material_index
                    mm.set_face_attrs(face, attrs)
                    calc_face_uv(face, mm)
                    topo.add('Risers')

                vert_last = blade_verts

    mm.to_mesh()
    mm.free()
    return topo


def set_face_property(self, obj, sel_info, op_id, prop_dict):
    mm = ManagedMesh(obj)
    if "tag" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_tag, prop_dict['tag'])
    elif "elevation" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_elev, prop_dict['elevation'])
    elif "uv_mode" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv, prop_dict['uv_mode'])
    elif "uv_orig" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv_orig, prop_dict['uv_origin'])
    elif "uv_rotate" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv_rot, prop_dict['uv_rotate'])
    elif "material" in self.bl_idname:
        idx = mm.get_material_index(prop_dict['material'])
        for face in mm.get_faces(sel_info):
            face.material_index = idx
    elif "radial" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_radial, prop_dict['radial'])
        # reset uv coordinates
        for face in mm.get_faces(sel_info):
            face.normal_update()
            vrot = radial_to_euler(Vector(prop_dict['radial']), face.normal)
            face[mm.key_uv_rot] = vrot
    mm.to_mesh()
    mm.free()

    if ("uv" in self.bl_idname) or ("material" in self.bl_idname) or ('radial' in self.bl_idname):
        pd = {'override_origin': False, 'origin': Vector((0, 0, 0)),
              'override_mode': False, 'mode': 'GLOBAL_XY'}
        calc_uvs(self, obj, sel_info, op_id, pd)

    n_face = sel_info.count_faces()
    topo = TopologyInfo(from_keys=['All'])
    for i in range(n_face):
        topo.add('All')
    return topo


def calc_uvs(self, obj, sel_info, op_id, prop_dict):
    """Recalculate uv with option to override mode and origin"""
    from ..ops.properties import uv_mode_list
    # 'GLOBAL_XY', project 0,0,0 to face, measure from there
    #    good to make fragments of a wall have seamless texture
    # 'FACE_XY', start from face origin
    #    good to keep adjacent polys not seamless (like planks)
    # 'FACE_BBOX', map box 0-1
    #    good for signs and images that should overlay an odd shape without distortion
    # 'FACE_POLAR', uses radius and circumfrential distance (not angle)
    #    allows for arches to have brickwork
    from ..ops.properties import face_tag_to_int, uv_mode_to_int

    b_origin = prop_dict['override_origin']
    v_override = prop_dict['origin']
    b_mode = prop_dict['override_mode']
    s_mode = prop_dict['mode']

    origin = None
    mode = None
    if b_origin:
        origin = v_override
    if b_mode:
        mode = uv_mode_to_int(s_mode)

    mm = ManagedMesh(obj)
    uv_layer = mm.bm.loops.layers.uv.active
    # ignore selection mode, set for each face
    flist = mm.get_faces(sel_info)
    if len(flist) == 0:
        flist = mm.bm.faces

    for face in flist:
        if face.is_valid:
            calc_face_uv(face, mm, mode, origin)

    mm.to_mesh()
    mm.free()

    n_face = len(flist)
    topo = TopologyInfo(from_keys=['All'])
    for i in range(n_face):
        topo.add('All')
    return topo


def set_oriented_material(self, obj, sel_info, op_id, prop_dict):
    from ..object import material_best_mode
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=False)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['All'])

    mat_name = prop_dict['material']
    midx = mm.get_material_index(mat_name)

    lst_orig_poly.sort(key=lambda p: p.coord_sys.reference_face.calc_area())
    poly = lst_orig_poly[-1]  # largest
    if poly.box_size.x > poly.box_size.y:
        axis = poly.coord_sys.xdir
    else:
        axis = poly.coord_sys.ydir

    vorg = random_origin(0, 0.06) + poly.calc_center_box() + poly.normal()*math.sqrt(poly.box_size.length)
    mm.set_facesel_attr(sel_info, mm.key_uv_orig, vorg)
    mm.set_facesel_attr(sel_info, mm.key_uv_rot, pointing_to_euler(axis))
    mm.set_facesel_attr(sel_info, mm.key_uv, material_best_mode(mm.obj.data.materials[midx].name))

    for p in lst_orig_poly:
        p.coord_sys.reference_face.material_index = midx
        calc_face_uv(p.coord_sys.reference_face, mm, mode=None, orig=None)

    topo.add('All', len(lst_orig_poly))
    return topo


def _instance_name(obj, op_id):
    col = get_instance_collection(obj)
    name = "bt{:03d}.{:03d}.{}".format(len(col.objects), op_id, obj.name)
    return name


def _instance_index(obj):
    parts = obj.name.split(".")
    return int(parts[0][2:])  # bt000


def _find_instance_object(obj, op_id):
    search = "{:03d}".format(op_id)
    col = get_instance_collection(obj)
    for obj in col.objects:
        parts = obj.name.split(".")
        if parts[1] == search:
            return obj
    return None


def import_mesh(self, obj, sel_info, op_id, prop_dict):
    from .assets import import_mesh
    from ..ops.dynamic_enums import file_type, from_path, BT_CATALOG_SRC

    topo = TopologyInfo(from_keys=['All'])
    if prop_dict['use_catalog']:
        cat_dict = prop_dict['catalog_object']
        obj_path = pathlib.Path(cat_dict['category_item'])  # actually points to text file
        if str(obj_path) in ['', '0', 'N/A']:
            return topo
        ftype, obj_name = file_type(obj_path.stem)
        print("importing ", cat_dict['style_name'], cat_dict['category_name'], obj_name)
        obj_original = import_mesh(cat_dict['style_name'], cat_dict['category_name'], obj_name)
        # we could load the text journal if it exists
        if obj_original is None:
            self.report({"ERROR_INVALID_INPUT"}, "Mesh not retrieved from library")
            return topo
    else:
        obj_name = prop_dict['local_object']['object_name']
        if obj_name in ['', '0', 'N/A']:
            return topo

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    obj_add = _find_instance_object(obj, op_id)
    head = ""
    if obj_add is not None:  # check if we are changing instance example and unlink old one
        head = obj_add.name[:10]  # "bt000.000.name"
        tail = obj_add.name[10:]
        if (tail != obj_name) and (obj_add.name != obj.name):
            bpy.data.objects.remove(obj_add, do_unlink=True)
            obj_add = None

    if obj_add is None:
        obj_example = bpy.data.objects[obj_name]

        obj_add = obj_example.copy()  # keep mesh reference so we can edit the original
        if head != "":  # keep instancing order and op id
            obj_add.name = head + obj_add.name
        else:
            obj_add.name = _instance_name(obj, op_id)
        inst_col = get_instance_collection(obj)
        inst_col.objects.link(obj_add)

    bpy.ops.ed.undo_push(message="Linked {}".format(obj_add.name))
    pick = _instance_index(obj_add)

    # clear old
    topo = TopologyInfo(from_keys=['All'])
    mm.delete_current_verts()

    dz = prop_dict['z_offset']
    sz = prop_dict['scale']
    e_rot = Euler(prop_dict['rotation'])
    a_count = prop_dict['array']['count']
    a_dir = Vector(_extract_vector(prop_dict['array']['direction']))
    a_dir.normalize()
    a_spacing = prop_dict['array']['spacing']
    a_do_orbit = prop_dict['array']['do_orbit']
    a_origin = Vector(_extract_vector(prop_dict['array']['origin']))

    bb = obj_add.bound_box
    bb_min = Vector(bb[0])
    bb_max = Vector(bb[-2])
    bb_size = bb_max - bb_min

    for control_poly in lst_orig_poly:
        face_sel = SmartPoly(control_poly.coord_sys, control_poly.points, break_link=True)

        face_selector = face_sel.make_face()  # else we can't select this operation for redo or erase
        calc_face_uv(face_selector, mm)
        topo.add('All')

        mm.set_face_attrs(control_poly.coord_sys.reference_face, {mm.key_tag: 'DELETE'})

        inst_dir = control_poly.coord_sys.inverse @ a_dir

        # sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
        sx, sy = sz, sz  # not currently allowing non-uniform scaling
        ox, oy = _extract_offset(prop_dict['position'], control_poly.box_size, Vector((0, 0)))

        v_start = control_poly.coord_sys.make_3d(control_poly.bbox_min)
        v_start += ox * control_poly.coord_sys.xdir + oy * control_poly.coord_sys.ydir + dz * control_poly.coord_sys.normal

        r_mat = control_poly.coord_sys.inverse @ e_rot.to_matrix()
        r_euler = r_mat.to_euler()

        v_scale = Vector((sx, sy, sz))

        dtheta = 0
        v_origin = Vector((0, 0, 0))
        if a_do_orbit:
            v_origin = (control_poly.coord_sys.make_3d(control_poly.bbox_min)
                        + a_origin.x * control_poly.coord_sys.xdir + a_origin.y * control_poly.coord_sys.ydir)
            s1 = control_poly.make_2d(v_origin)
            s2 = control_poly.make_2d(v_start)
            radius = s2 - s1
            if radius.length == 0:
                a_do_orbit = False
            else:
                dtheta = a_spacing / radius.length

        if prop_dict['as_instance']:  # put in vertices
            for i in range(a_count):
                if a_do_orbit:
                    local_rot = Matrix.Rotation(i * dtheta, 3, control_poly.normal())
                    v_inst = v_origin + local_rot @ (v_start - v_origin)
                    r_euler = (local_rot @ r_mat).to_euler()
                else:
                    v_inst = v_start + i * a_spacing * inst_dir

                bmv = mm.new_vert(v_inst)
                mm.instance_on_vert(bmv, pick, r_euler, v_scale)

        else:  # copy mesh to position
            dct_map_verts = {}
            dct_map_matl = {}
            for i_add, mat in enumerate(obj_add.data.materials):
                cur_idx = mm.get_material_index(mat.name)
                dct_map_matl[i_add] = cur_idx

            with managed_bm(obj_add) as bm_add:
                bm_add.verts.ensure_lookup_table()
                for v_add in bm_add.verts:
                    v1 = Vector((v_add.x * v_scale.x, v_add.y * v_scale.y, v_add.z * v_scale.z))
                    v = v_start + r_mat @ v1
                    bmv = mm.new_vert(v)
                    dct_map_verts[v.index] = bmv
                for face_add in bm_add.faces:
                    vlist = [v.index for v in face_add.verts]
                    f = mm.new_face(vlist)
                    f.material_index = dct_map_matl[face_add.material_index]
                    topo.add('All')
                # loop uvs?

    mm.to_mesh()
    mm.free()

    return topo


def flip_normals(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['All'])

    for control_poly in lst_orig_poly:
        new_poly = SmartPoly(control_poly.coord_sys, pt_list=control_poly.points, break_link=True)
        if prop_dict['toggle']:  # if false, this can be used to insert a "null" operation to root a script
            new_poly.flip_normal()

        face = new_poly.make_face()
        face.normal_update()

        if control_poly.coord_sys.reference_face:
            attrs = mm.get_face_attrs(control_poly.coord_sys.reference_face)
            attrs[mm.key_radial] = new_poly.coord_sys.ydir
            mm.set_face_attrs(face, attrs)
            mm.delete_face(control_poly.coord_sys.reference_face)
        else:
            mm.set_face_attrs(face, {mm.key_radial: new_poly.coord_sys.ydir})
        calc_face_uv(face, mm)

        mm.to_mesh()
        mm.free()
        topo.add('All', len(lst_orig_poly))

    return topo


def project_face(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=['All'])

    material_index = mm.get_material_index(prop_dict['material'])
    hip = prop_dict.get('hip', False)
    target = prop_dict['target'] % len(lst_orig_poly)
    poly_b = lst_orig_poly[target]

    for i_y, poly_a in enumerate(lst_orig_poly):
        if poly_b is poly_a:
            continue

        if hip:
            p0 = poly_a.calc_center_box()
            p1 = p0 + poly_a.normal()
            p2 = poly_b.calc_center_box()
            p3 = p0 + poly_b.normal()
            res = mathutils.geometry.intersect_line_line(p0, p1, p2, p3)
            ipt = (res[0]+res[1])/2  # assume an intersection!
            ivec = Vector((0, 0, 1))  # force z, keep point
            # working in xy plane
            a_norm = Vector((poly_a.normal().x, poly_a.normal().y, 0)).normalized()
            b_norm = Vector((poly_b.normal().x, poly_b.normal().y, 0)).normalized()
            if a_norm.dot(b_norm) > 0:
                b_norm = -b_norm
            avg = (a_norm + b_norm) / 2
            avg.normalize()
            midplane_norm = ivec.cross(avg)
            lst_a = []
            for p in poly_a.points:
                v = mathutils.geometry.intersect_line_plane(p.co3, p.co3 + a_norm, ipt, midplane_norm)
                lst_a.append(v)
            lst_b = []
            for p in poly_b.points:
                v = mathutils.geometry.intersect_line_plane(p.co3, p.co3 + b_norm, ipt, midplane_norm)
                lst_b.append(v)
            if a_norm.dot(midplane_norm) > 0:
                n = midplane_norm
            else:  # face same direction for bridge
                n = -midplane_norm
            poly_a1 = SmartPoly(CoordSys(mm, radial=Vector((0,0,1)), normal=n), pt_list=lst_a, b_no_roll=True)
            lst_bridge_a = poly_a1.bridge_by_number(poly_a)
            if b_norm.dot(midplane_norm) > 0:
                n = midplane_norm
            else:
                n = -midplane_norm
            poly_b1 = SmartPoly(CoordSys(mm, radial=Vector((0,0,1)), normal=n), pt_list=lst_b, b_no_roll=True)
            lst_bridge_b = poly_b1.bridge_by_number(poly_b)
            lst_poly = lst_bridge_a + lst_bridge_b

        else:
            v_dir = poly_b.calc_center_box() - poly_a.calc_center_box()

            poly_c = SmartPoly(poly_a.coord_sys, pt_list=poly_a.points, break_link=True)
            poly_c.project_to(poly_b.normal())  # shape of a when projected
            poly_c.calc_coord_sys(b_no_roll=True)

            line_a = poly_a.calc_center_box()
            line_b = line_a + poly_a.normal()
            v = mathutils.geometry.intersect_line_plane(line_a, line_b, poly_b.calc_center_box(), poly_b.normal())
            if v is not None:
                poly_c.shift_3d(v - poly_c.calc_center_box())

            lst_poly = []
            if not prop_dict['bridge']:
                v_dir = poly_a.normal()
                # use c as target
                poly_a.make_verts()
                poly_c.make_verts()
                lst_poly = poly_c.bridge(poly_a, v_extruding=v_dir)
            else:
                # use c for bridge calculation
                poly_c.make_verts()
                poly_b.make_verts()
                lst_poly = poly_b.bridge(poly_c, False, v_extruding=v_dir)

                # transfer positions of a to c, ie, unproject c
                for i in range(len(poly_a.points)):
                    poly_c.points[i].co3 = poly_a.points[i].co3
                    poly_c.points[i].bm_vert.co = poly_a.points[i].co3

        # materials and attributes
        for p in lst_poly:
            p.face_attr['material'] = material_index
            if hip:
                p.face_attr['radial'] = Vector((0,0,1))
            else:
                p.face_attr['radial'] = v_dir
            p.calc_coord_sys(p.face_attr['radial'])
            face = p.make_face()

        topo.add('All', len(lst_poly))
    return topo


def copy_faces(self, obj, sel_info, op_id, prop_dict):
    """Used by compound operator to make points the children can build from"""
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    mm.deselect_all()

    topo = TopologyInfo(from_keys=['All'])
    topo.add('All', len(lst_orig_poly))

    for control_poly in lst_orig_poly:
        face = control_poly.make_face()
        face.hide = False
        face.select_set(True)
        mm.delete_face(control_poly.coord_sys.reference_face)

    mm.to_mesh()
    mm.free()

    print("copied", topo.to_dict())
    return topo


def build_face(self, obj, sel_info, op_id, prop_dict):
    mm = ManagedMesh(obj)
    verts = mm.vert_list(sel_info)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=['All'])
    poly = SmartPoly(CoordSys(mm=mm))
    for v in verts:
        poly.add(v, break_link=True)
    poly.calc_coord_sys()

    if prop_dict['flip_normal']:
        poly.flip_normal()

    poly.face_attr['material'] = mm.get_material_index(prop_dict['material'])
    face = poly.make_face()

    mm.to_mesh()
    mm.free()
    topo.add('All')

    return topo


def build_roof(self, obj, sel_info, op_id, prop_dict):
    from ..object.materials import material_best_mode
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=['All', 'Attic'])
    tan = prop_dict['slope']
    height = 0
    # use a tangent of the roof pitch angle of 0.6 instead of the roof's height
    # height = 0.0
    # tan = 0.6
    material_index = mm.get_material_index('BT_Roof')

    control_poly = lst_orig_poly[0]
    pts = [sv.co2 for sv in control_poly.points]
    first_poly = Polygon.Polygon(pts)
    first_poly.simplify()

    if len(lst_orig_poly) > 1:
        Polygon.setTolerance(1e-4)
        for other in lst_orig_poly[1:]:
            other_pts = [control_poly.coord_sys.make_2d(sv) for sv in other.points]
            first_poly.addContour(other_pts)
        first_poly.simplify()

        # we need a single master polygon with holes
        n_total = len(first_poly)
        if n_total > 1:
            n_outer = 0
            for c in range(n_total):
                if not first_poly.isHole(c):
                    n_outer += 1

            if n_outer > 1:  # this might not work, might have to have connected roof to start
                boundary = Polygon.Utils.convexHull(first_poly)
                first_poly = boundary & first_poly

    num_verts = 0
    verts = []
    holes = []
    n_contour = len(first_poly)
    for i in range(n_contour):
        c = first_poly.contour(i)
        if i == 0:
            num_verts = len(c)
            lst = [control_poly.coord_sys.make_3d(Vector(p)) for p in c]
            if first_poly.orientation(i) == -1:
                lst.reverse()
            verts.extend(lst)
            print("c0", lst)
        else:
            lst = [control_poly.coord_sys.make_3d(Vector(p)) for p in c]
            if first_poly.orientation(i) == 1:
                lst.reverse()
            hole_info = (len(verts), len(lst))
            holes.append(hole_info)
            verts.extend(lst)
            print(i, lst)

    faces = []

    # now extend 'faces' by faces of straight polygon
    faces = bpypolyskel.polygonize(verts, 0, num_verts, holes, height, tan, faces, None)

    dct_verts = {}
    for i, v in enumerate(verts):
        dct_verts[i] = mm.new_vert(v)
    for idx_list in faces:
        vlist = [dct_verts[i] for i in idx_list]
        new_face = mm.new_face(vlist)
        new_face.material_index = material_index
        new_face.normal_update()
        xdir = Vector((0,0,1)).cross(new_face.normal).normalized()
        ydir = new_face.normal.cross(xdir)
        mode = material_best_mode('BT_Roof')
        mm.set_face_attrs(new_face, {mm.key_radial: ydir.normalized(), mm.key_uv: mode})
        calc_face_uv(new_face, mm)

    topo.add('All', len(faces))
    mm.to_mesh()
    mm.free()

    return topo


def plan_inset_walls(self, obj, sel_info, op_id, prop_dict):
    side_list = prop_dict['side_list'].split(",")
    side_list = [s.strip() for s in side_list]
    side_list = [int(s) for s in side_list if s != '']
    thickness = prop_dict['thickness']
    mat_name = prop_dict['material']
    topo = TopologyInfo(from_keys=['Walls', 'Floors'])
    if mat_name in ['0', '', 'N/A']:
        return topo

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    material_index = mm.get_material_index(mat_name)

    for control_poly in lst_orig_poly:
        if len(side_list) == 0:
            pd = {'by_inset': True, 'thickness': thickness}
            lst, poly = _make_self_poly(control_poly, pd, mm, b_make=False)
        else:
            ncp = len(control_poly.points)
            lst_new_pts = []
            test = [i in side_list for i in range(ncp)]
            for i_edge in range(ncp):
                do_prev = test[(i_edge - 1 + ncp) % ncp]
                do_cur = test[i_edge]

                prev0 = control_poly.points[(i_edge - 1 + ncp) % ncp].co3
                prev1 = control_poly.points[i_edge].co3
                prev_in = control_poly.normal().cross((prev1 - prev0).normalized())
                cur0 = control_poly.points[i_edge].co3
                cur1 = control_poly.points[(i_edge + 1) % ncp].co3
                cur_in = control_poly.normal().cross((cur1 - cur0).normalized())

                if do_prev and do_cur:  # intersect inset
                    prev0 = prev0 + prev_in * thickness
                    prev1 = prev1 + prev_in * thickness
                    cur0 = cur0 + cur_in * thickness
                    cur1 = cur1 + cur_in * thickness
                elif do_prev:  # intersect inset with original
                    prev0 = prev0 + prev_in * thickness
                    prev1 = prev1 + prev_in * thickness
                elif do_cur:  # intersect original with inset
                    cur0 = cur0 + cur_in * thickness
                    cur1 = cur1 + cur_in * thickness
                else:  # use original
                    lst_new_pts.append(cur0)
                    continue
                tup = mathutils.geometry.intersect_line_line(prev0, prev1, cur0, cur1)
                pt0 = tup[0]
                lst_new_pts.append(pt0)

            poly = SmartPoly(control_poly.coord_sys, pt_list=lst_new_pts)

        face = poly.make_face()
        topo.add('Floors')

        control_poly.make_verts()
        lst_wall = poly.bridge(control_poly)

        for p in lst_wall:
            edge_0 = p.points[1].co3 - p.points[0].co3
            radial = p.normal().cross(edge_0).normalized()
            p.calc_coord_sys(radial=radial)
            p.face_attr['uv_mode'] = 'ORIENTED_PLAN'
            p.face_attr['material'] = material_index
            p.face_attr['radial'] = radial
            face = p.make_face()

        topo.add('Walls', len(lst_wall))

        if control_poly.coord_sys.reference_face:
            mm.delete_face(control_poly.coord_sys.reference_face)
    mm.to_mesh()
    mm.free()
    return topo


def set_plan_floor(self, obj, sel_info, op_id, prop_dict):
    rotation = prop_dict['rotation']
    mat_name = prop_dict['material']
    elevation = prop_dict['elevation']
    topo = TopologyInfo(from_keys=['All'])
    if mat_name in ['0', '', 'N/A']:
        return topo

    pd = {'override_origin': False, 'origin': Vector((0, 0, 0)),
          'override_mode': False, 'mode': 'GLOBAL_XY'}

    mm = ManagedMesh(obj)
    material_index = mm.get_material_index(mat_name)
    mm.set_facesel_attr(sel_info, mm.key_elev, elevation)
    mm.set_facesel_attr(sel_info, mm.key_uv_rot, Vector((0, 0, rotation)))
    mm.set_facesel_attr(sel_info, mm.key_uv, 'ORIENTED_SPIN')
    for face in mm.get_faces(sel_info):
        face.material_index = material_index
        calc_uvs(self, obj, sel_info, op_id, pd)
    mm.to_mesh()
    mm.free()

    n_face = sel_info.count_faces()
    for i in range(n_face):
        topo.add('All')
    return topo


def plan_feature(self, obj, sel_info, op_id, prop_dict):
    mat_name = prop_dict['material']
    offset = prop_dict['offset']
    size = prop_dict['size']
    flip_x = prop_dict['flip_x']
    flip_y = prop_dict['flip_y']
    topo = TopologyInfo(from_keys=['Walls', 'Features'])
    if mat_name in ['0', '', 'N/A']:
        return topo

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    material_index = mm.get_material_index(mat_name)

    for control_poly in lst_orig_poly:
        # 2 x cut separated by size and starting at offset
        lst_new = control_poly.grid_divide(2, 0, offset, 0, size, 0)
        if offset == 0:
            poly = lst_new[0]
            topo.add('Features')
            topo.add('Walls', len(lst_new)-1)
        else:
            poly = lst_new[1]
            topo.add('Walls')
            topo.add('Features')
            if len(lst_new) > 2:
                topo.add('Walls', len(lst_new) - 2)
        poly.face_attr['material'] = material_index
        if flip_x:
            poly.face_attr['uv_rot'][1] = math.pi
        if flip_y:
            poly.face_attr['uv_rot'][0] = math.pi

        for p in lst_new:
            face = p.make_face()

        if control_poly.coord_sys.reference_face:
            mm.delete_face(control_poly.coord_sys.reference_face)
    mm.to_mesh()
    mm.free()

    return topo


def perpendicular_face(self, obj, sel_info, op_id, prop_dict):
    """Simple rectangle but out of plane. Often useful"""
    mat_name = prop_dict['material']
    topo = TopologyInfo(from_keys=['All'])
    if mat_name in ['0', '', 'N/A']:
        return topo

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    material_index = mm.get_material_index(mat_name)

    rotation = prop_dict['rotation']

    for control_poly in lst_orig_poly:

        pd = {
            'size': prop_dict['size'],
            'position': prop_dict['position'],
            'poly': {'num_sides': 4, 'start_angle': -math.pi / 4},
            'frame': 0,
        }

        lst, poly = _make_ngon(control_poly, pd, mm, b_make=False)
        p_rot = poly.coord_sys.make_3d(poly.bbox_min)
        v_rot = poly.coord_sys.xdir
        v_z = prop_dict['offset_z'] * control_poly.normal()

        R = Matrix.Rotation(math.pi / 2, 3, v_rot)
        R1 = Matrix.Rotation(rotation, 3, Vector((0, 0, 1)))
        mat = R1 @ R

        poly.coord_sys.origin = p_rot  # rotation is relative to origin
        poly.apply_rotation_matrix(mat)
        poly.shift_3d(v_z)

        poly.update_bmvert()

        poly.face_attr['radial'] = mat @ poly.face_attr['radial']
        poly.face_attr['material'] = material_index
        face = poly.make_face()

        topo.add('All')
    mm.to_mesh()
    mm.free()
    return topo


def straight_rail(mm, pt_o, radial, norm, shape, v_end, material_index, topo):
    csys = CoordSys(mm, radial=radial, normal=norm, origin=pt_o)
    start = SmartPoly(csys.copy())
    for pt in shape.points:
        start.add(csys.make_3d(pt.co2))
    start.calc_2d()

    end = SmartPoly(csys.copy())
    end.coord_sys.shift_origin3d(v_end)
    for pt in shape.points:
        end.add(end.coord_sys.make_3d(pt.co2))
    end.calc_2d()

    start.make_verts()
    end.make_verts()

    lst_br = end.bridge_by_number(start)
    lst_br = [start, end] + lst_br

    for poly in lst_br:
        poly.face_attr['material'] = material_index
        poly.face_attr['uv_rot'] = pointing_to_euler(v_end.normalized())
        face = poly.make_face()

    topo.add('Starts')
    topo.add('Ends')
    topo.add('Sides', len(lst_br) - 2)


def curved_rail(mm, rail_pts, rail_inset, rail_ht, shape, material_index, topo):
    rail_control_poly = SmartPoly(CoordSys(mm))
    for p in rail_pts:
        rail_control_poly.add(p)
    rail_control_poly.shift_3d(Vector((0, 0, rail_ht)))
    side_list = list(range(len(rail_control_poly.points)-1))
    for i_edge in range(len(rail_control_poly.points)-1):
        edge_dir = rail_control_poly.points[i_edge + 1].co3 - rail_control_poly.points[i_edge].co3
        edge_dir.normalize()
        if i_edge > 0:
            elast = rail_control_poly.points[i_edge].co3 - rail_control_poly.points[i_edge - 1].co3
            elast.normalize()
            rail_control_poly.coord_sys.normal = elast.cross(edge_dir).normalized()
            # x and y dir not used by solidify
        else:
            enext = rail_control_poly.points[i_edge+2].co3 - rail_control_poly.points[i_edge + 1].co3
            enext.normalize()
            rail_control_poly.coord_sys.normal = edge_dir.cross(enext).normalized()

        vz = Vector((0, 0, 0))
        solidify_by_bridge(rail_control_poly, side_list, i_edge,
                           edge_dir, vz, rail_inset, mm, material_index, topo,[shape])


def straight_balusters(mm, n_step, rail_in, rail_out, h_tread, b_rail_ht, rail_ht, bottom_rail):
    for i in range(n_step):
        r = rail_in[2 * i]
        s = rail_in[2 * i + 1]
        zz = Vector((0, 0, h_tread))
        zzb = Vector((0, 0, b_rail_ht))
        zzt = Vector((0, 0, rail_ht))
        norm = (rail_in[i] - rail_out[i]).normalized()
        if bottom_rail:
            plist = [r, r + zzb, s + zz + zzb, s]
            plist1 = [r + zzb, r + zzt, s + zz + zzt, s + zz + zzb]
            sidepanel = SmartPoly(CoordSys(mm, radial=zz.normalized(), normal=norm), pt_list=plist)
            sidepanel.make_face()
        else:
            plist1 = [r, r + zzt, s + zz + zzt, s]
        sidepanel = SmartPoly(CoordSys(mm, radial=zz.normalized(), normal=norm), pt_list=plist1)
        sidepanel.make_face()


def curved_balusters(mm, n_step, rail_in, rail_out, h_tread, b_rail_ht, rail_ht, bottom_rail):
    for i in range(n_step):
        r = rail_in[i]
        s = rail_in[i + 1]
        zz = Vector((0, 0, h_tread))
        zzb = Vector((0, 0, b_rail_ht))
        zzt = Vector((0, 0, rail_ht))
        norm = (rail_in[i] - rail_out[i]).normalized()
        if bottom_rail:
            plist = [r, r + zzb, s + zzb, s - zz]
            plist1 = [r + zzb, r + zzt, s + zzt, s + zzb]
            sidepanel = SmartPoly(CoordSys(mm, radial=zz.normalized(), normal=norm), pt_list=plist)
            sidepanel.make_face()
        else:
            plist1 = [r, r + zzt, s + zzt, s - zz]
        sidepanel = SmartPoly(CoordSys(mm, radial=zz.normalized(), normal=norm), pt_list=plist1)
        sidepanel.make_face()


def build_stairs(self, obj, sel_info, op_id, prop_dict):
    curved = prop_dict['curved']
    curve_left = prop_dict['curve_left']
    open_riser = prop_dict['open_riser']
    radius = prop_dict['radius']
    w_tread = prop_dict['w_tread']
    d_tread = prop_dict['d_tread']
    thickness = prop_dict['thickness']
    overhang = prop_dict['overhang']
    height = prop_dict['height']
    h_tread = prop_dict['h_tread']
    rotation = prop_dict['rotation']
    min_support = prop_dict['min_support']
    tread_mat = prop_dict['tread_material']
    riser_mat = prop_dict['riser_material']
    support_mat = prop_dict['support_material']
    rails = prop_dict['rails']
    balusters = prop_dict['balusters']
    b_rail_ht = prop_dict['bot_rail_ht']
    b_rail_w = prop_dict['bot_rail_w']
    b_rail_d = prop_dict['bot_rail_d']

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    tread_index = mm.get_material_index(tread_mat)
    riser_index = mm.get_material_index(riser_mat)
    support_index = mm.get_material_index(support_mat)

    n_step = int(math.ceil(height / h_tread))
    h_tread = height / n_step

    rotation_matrix = Matrix.Rotation(rotation, 3, Vector((0,0,1)))

    topo = TopologyInfo(from_keys=['Risers', 'Treads', 'Supports', 'Balusters', 'Starts', 'Ends', 'Sides'])
    pts_in = []
    pts_out = []
    if not curved:
        for i in range(n_step):
            x = 0
            y = i * d_tread
            z = i * h_tread
            pt = Vector((x,y,z))
            pts_in.append(pt)
            y = y + d_tread
            pt = Vector((x, y, z))
            pts_in.append(pt)

            x = w_tread
            y = i * d_tread
            pt = Vector((x,y,z))
            pts_out.append(pt)
            y = y + d_tread
            pt = Vector((x, y, z))
            pts_out.append(pt)
    else:
        if curve_left:
            ox = -radius
        else:
            ox = radius

        for i in range(n_step):
            circ = i*d_tread
            theta = circ/radius
            theta_1 = (circ + d_tread)/radius
            if not curve_left:
                theta = math.pi - theta
                theta_1 = math.pi - theta_1

            x = ox + radius * math.cos(theta)
            y = radius * math.sin(theta)
            z = i * h_tread
            pt = Vector((x, y, z))
            pts_in.append(pt)
            x = ox + radius * math.cos(theta_1)
            y = radius * math.sin(theta_1)
            pt = Vector((x, y, z))
            pts_in.append(pt)

            x = ox + (w_tread + radius) * math.cos(theta)
            y = (w_tread + radius) * math.sin(theta)
            pt = Vector((x, y, z))
            pts_out.append(pt)
            x = ox + (w_tread + radius) * math.cos(theta_1)
            y = (w_tread + radius) * math.sin(theta_1)
            pt = Vector((x, y, z))
            pts_out.append(pt)

    vz_step = Vector((0,0,1)) * h_tread
    vz_tread = Vector((0,0,1)) * thickness
    vz_support_min = Vector((0,0,-1)) * min_support
    vz_support_max = Vector((0, 0, -1)) * (min_support + h_tread)

    for i_cont, control_poly in enumerate(lst_orig_poly):
        support_origin = (pts_in[0] + pts_out[0] + vz_step) / 2 + random_origin(i_cont, 0.1)
        reference = control_poly.coord_sys.make_3d(control_poly.bbox_min)
        ox, oy = _extract_offset(prop_dict['position'], control_poly.box_size, Vector((w_tread, d_tread * n_step)))
        oz = prop_dict['z_offset']
        v_offset = ox * control_poly.coord_sys.xdir + oy * control_poly.coord_sys.ydir + oz * control_poly.coord_sys.normal
        reference = reference + v_offset

        for i in range(n_step):
            # make tread, riser, and support sides
            i0 = pts_in[i*2]
            i1 = pts_in[i*2 + 1]
            o0 = pts_out[i*2]
            o1 = pts_out[i*2 + 1]

            vi_over = (i0 - i1).normalized() * overhang
            vo_over = (o0 - o1).normalized() * overhang
            inside = [i0+vi_over, i0+vi_over+vz_tread, i1 + vz_tread, i1]
            outside = [o0+vo_over, o0+vo_over+vz_tread, o1 + vz_tread, o1]

            vr = (o0 - i0).normalized() * thickness
            vr1 = (o1 - i1).normalized() * thickness
            if i==0:
                in_sup = [i0, i1, i1 + vz_support_min, i0 + vz_support_min]
                out_sup = [o0, o1, o1 + vz_support_min, o0 + vz_support_min]
                in_sup_1 = [i0 + vr, i1 + vr1, i1 + vz_support_min + vr1, i0 + vz_support_min + vr]
                out_sup_1 = [o0 - vr, o1 - vr1, o1 + vz_support_min - vr1, o0 + vz_support_min - vr1]
            else:
                in_sup = [i0, i1, i1 + vz_support_min, i0 + vz_support_max]
                out_sup = [o0, o1, o1 + vz_support_min, o0 + vz_support_max]
                in_sup_1 = [i0 + vr, i1 + vr1, i1+vz_support_min+vr1, i0 + vz_support_max + vr]
                out_sup_1 = [o0 - vr, o1 - vr1, o1 + vz_support_min - vr1, o0 + vz_support_max - vr1]

            riser = [i1+vr1, o1-vr1, o1-vr1+vz_step, i1+vr1+vz_step]
            vxi = (i1 - i0).normalized() * thickness
            vxo = (o1 - o0).normalized() * thickness
            riser_1 = [i1+vr1+vxi, o1-vr1+vxo, o1-vr1+vxo+vz_step, i1+vr1+vxi+vz_step]

            if not curve_left:  # we will want to flip normals on these
                for lst in [inside, outside, in_sup, out_sup, in_sup_1, out_sup_1, riser, riser_1]:
                    lst.reverse()

            # apply transformation
            for lst in [inside, outside, in_sup, out_sup, in_sup_1, out_sup_1, riser, riser_1]:
                for j in range(4):
                    lst[j] = rotation_matrix @ lst[j] + reference
            # update vectors needed for orientation of polys
            vr = (outside[0] - inside[0]).normalized() * thickness
            vr1 = (outside[3] - inside[3]).normalized() * thickness
            vr_avg = (vr+vr1).normalized()
            vxi = (inside[3] - inside[0]).normalized() * thickness
            vxo = (outside[3] - outside[0]).normalized() * thickness
            vx_avg = (vxi+vxo).normalized()

            # make step
            inside = SmartPoly(CoordSys(mm, radial=Vector((0,0,1)), normal=vr_avg), pt_list=inside)
            outside = SmartPoly(CoordSys(mm, radial=Vector((0, 0, 1)), normal=vr_avg), pt_list=outside)
            # make supports
            in_sup = SmartPoly(CoordSys(mm, radial=(in_sup[2] - in_sup[3]).normalized(), normal=vr_avg), pt_list=in_sup)
            out_sup = SmartPoly(CoordSys(mm, radial=(out_sup[2] - out_sup[3]).normalized(), normal=vr_avg), pt_list=out_sup)
            in_sup_1 = SmartPoly(CoordSys(mm, radial=(in_sup_1[2] - in_sup_1[3]).normalized(), normal=vr_avg), pt_list=in_sup_1)
            out_sup_1 = SmartPoly(CoordSys(mm, radial=(out_sup_1[2] - out_sup_1[3]).normalized(), normal=vr_avg), pt_list=out_sup_1)
            riser = SmartPoly(CoordSys(mm, radial=Vector((0, 0, 1)), normal=vx_avg), pt_list=riser)
            riser_1 = SmartPoly(CoordSys(mm, radial=Vector((0, 0, 1)), normal=vx_avg), pt_list=riser_1)

            for info in [(inside, outside, tread_index), (in_sup, in_sup_1, support_index),
                         (out_sup_1, out_sup, support_index), (riser, riser_1, riser_index)]:
                poly_a, poly_b, mat = info
                if poly_a is riser:  # do riser check
                    if open_riser or (i == (n_step - 1)):
                        continue

                lst_br = poly_b.bridge_by_number(poly_a)
                lst = [poly_a, poly_b] + lst_br
                for poly in lst:
                    poly.face_attr['material'] = mat
                    if poly_a in [in_sup, out_sup_1]:  # align wood grain with axis of stairs
                        v_diag = (poly_a.points[2].co3 - poly_a.points[3].co3).normalized()
                        poly.face_attr['uv_rot'] = pointing_to_euler(v_diag)
                        if not curved:  # common origin
                            poly.face_attr['origin'] = support_origin

                    poly.make_face()

                if poly_a is inside:
                    topo.add('Treads', len(lst))
                elif poly_a is riser:
                    topo.add('Risers', len(lst))
                elif poly_a in [in_sup, out_sup_1]:
                    topo.add('Supports', len(lst))

        if rails:
            rail_index = mm.get_material_index(prop_dict['rail_material'])
            shape_type = prop_dict['rail_type']
            rail_ht = prop_dict['rail_ht']
            rail_inset = prop_dict['rail_inset']
            rail_in = [rotation_matrix @ p + reference for p in pts_in]
            rail_out = [rotation_matrix @ p + reference for p in pts_out]

            # recommend absolute sizing for rails and balusters
            pos = {
                "offset_x": 0.0,
                "is_relative_x": False,
                "offset_y": 0.0,
                "is_relative_y": False
            }
            if shape_type == 'NGON':
                pd = {'poly': prop_dict['rail_poly'], 'frame':0, 'size':prop_dict['rail_size'], 'position':pos}
                lst_new, outer = _make_ngon(control_poly, pd, mm, False)
            elif shape_type == 'CURVE':
                pd = {'local_object': prop_dict['rail_local_object'], 'size':prop_dict['rail_size'], 'position':pos}
                lst_new, outer = _make_curve_poly(control_poly, pd, mm, False)
            elif shape_type == 'CATALOG':
                pd = {'catalog_object': prop_dict['rail_catalog_object'], 'size':prop_dict['rail_size'], 'position':pos}
                lst_new, outer = _make_catalog_poly(control_poly, pd, mm, self.context, False)
            outer.coord_sys.origin = outer.calc_center_box()
            outer.calc_2d()

            if not curved:  # one long rail
                norm = (rail_in[2]-rail_in[0]).normalized()
                radial = Vector((0,0,1))
                if prop_dict['left_rail']:
                    v_inset = rail_inset * (rail_out[0] - rail_in[0]).normalized()
                    pt_o = rail_in[0] + Vector((0, 0, rail_ht)) + v_inset
                    v_end = rail_in[-1] + Vector((0,0,h_tread)) - rail_in[0]
                    straight_rail(mm, pt_o, radial, norm, outer, v_end, rail_index, topo)
                    if balusters:
                        if prop_dict['bottom_rail']:
                            pt_o = rail_in[0] + Vector((0, 0, b_rail_ht)) + v_inset
                            shape = SmartPoly(CoordSys(mm, radial=radial, normal=norm, origin=pt_o))
                            for pt in [[0,0], [b_rail_w,0], [b_rail_w,b_rail_d], [0,b_rail_d]]:
                                p = Vector(pt)
                                shape.add(shape.coord_sys.make_3d(p))
                            shape.calc_2d(b_no_roll=True)
                            straight_rail(mm, pt_o, radial, norm, shape, v_end, rail_index, topo)

                        # make faces for balusters  # TODO would be nicer if we shared bm_verts for selection
                        straight_balusters(mm, n_step, rail_in, rail_out, h_tread, b_rail_ht, rail_ht, prop_dict['bottom_rail'])

                if prop_dict['right_rail']:
                    v_inset = rail_inset * (rail_in[0] - rail_out[0]).normalized()
                    pt_o = rail_out[0] + Vector((0, 0, rail_ht)) + v_inset
                    v_end = rail_out[-1] + Vector((0,0,h_tread)) - rail_out[0]
                    straight_rail(mm, pt_o, radial, norm, outer, v_end, rail_index, topo)
                    if balusters:
                        if prop_dict['bottom_rail']:
                            pt_o = rail_out[0] + Vector((0, 0, b_rail_ht)) + v_inset
                            shape = SmartPoly(CoordSys(mm, radial=radial, normal=norm, origin=pt_o))
                            for pt in [[0,0], [b_rail_w,0], [b_rail_w,b_rail_d], [0,b_rail_d]]:
                                p = Vector(pt)
                                shape.add(shape.coord_sys.make_3d(p))
                            shape.calc_2d(b_no_roll=True)
                            straight_rail(mm, pt_o, radial, norm, shape, v_end, rail_index, topo)

                        straight_balusters(mm, n_step, rail_out, rail_in, h_tread, b_rail_ht, rail_ht, prop_dict['bottom_rail'])
            else:
                # Use solidify, even though we don't have a flat polygon
                # just update normal at each step
                p_last = rail_in[-1] + Vector((0,0,h_tread))
                rail_in = rail_in[::2]
                rail_in.append(p_last)
                p_last = rail_out[-1] + Vector((0, 0, h_tread))
                rail_out = rail_out[::2]
                rail_out.append(p_last)
                if prop_dict['left_rail']:
                    curved_rail(mm, rail_in, -rail_inset, rail_ht, outer, rail_index, topo)
                    if balusters:
                        if prop_dict['bottom_rail']:
                            shape = SmartPoly(CoordSys(mm))
                            for pt in [[0,0], [b_rail_w,0], [b_rail_w,b_rail_d], [0,b_rail_d]]:
                                p = Vector(pt)
                                shape.add(shape.coord_sys.make_3d(p))
                            shape.calc_2d(b_no_roll=True)
                            curved_rail(mm, rail_in, -rail_inset, b_rail_ht, shape, rail_index, topo)

                        # make faces for balusters
                        curved_balusters(mm, n_step, rail_in, rail_out, h_tread, b_rail_ht, rail_ht, prop_dict['bottom_rail'])

                if prop_dict['right_rail']:
                    curved_rail(mm, rail_out, rail_inset, rail_ht, outer, rail_index, topo)
                    if balusters:
                        if prop_dict['bottom_rail']:
                            shape = SmartPoly(CoordSys(mm))
                            for pt in [[0,0], [b_rail_w,0], [b_rail_w,b_rail_d], [0,b_rail_d]]:
                                p = Vector(pt)
                                shape.add(shape.coord_sys.make_3d(p))
                            shape.calc_2d(b_no_roll=True)
                            curved_rail(mm, rail_out, rail_inset, b_rail_ht, shape, rail_index, topo)

                            # make faces for balusters
                            curved_balusters(mm, n_step, rail_out, rail_in, h_tread, b_rail_ht, rail_ht, prop_dict['bottom_rail'])

    return topo


def extrude_walls(self, obj, sel_info, op_id, prop_dict):
    """Convert plan polygons to walls, windows, etc"""
    assert False, "Should be implemented as a compound operation, not a geometery operation"
    # break into sequential ops: (12)
    #  extrude full height walls
    #  extrude half walls
    #  create arches
    #  create columns
    #  extrude up to window bases
    #  create windows
    #  extrude over windows
    #  extrude up to door bases
    #  create doors
    #  extrude over doors
    #  create fireplaces
    #  extrude over fireplaces


def niche(self, obj, sel_info, op_id, prop_dict):
    """Sized for bricks"""
    brick_w = 0.17
    brick_h = 0.05
    gap = 0.01

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Frame', 'Bridge', 'Center'])

    frame_idx = mm.get_material_index("BT_Brick")
    add_perimeter =  prop_dict['add_perimeter']

    for control_poly in lst_orig_poly:  # note, if a region, the first face provides the info
        sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)

        # if diam of arch is sx, then circumference is pi sx/2, which needs to be a multiple of brick rows
        n_brick = math.floor(math.pi/2 * sx / brick_h+gap) # approx
        c = n_brick * brick_h + (n_brick-1) * gap
        w = c / (math.pi/2)

        # subtract radius for drop ht
        dh = sy - w/2

        # size prop dict
        spd = {'size_x': w, 'size_y': w/2, 'is_relative_x': False, 'is_relative_y': False}

        # arch prop dict
        apd = {'arch_type': 'ROMAN', 'num_sides': n_brick, 'drop_length': dh}

        # frame
        n_fb = prop_dict['frame_bricks']
        frame = n_fb * brick_w + (n_fb-1) * gap

        pd = {'frame': frame, 'size': spd, 'arch': apd, 'position': prop_dict['position']}

        lst_new, outer = _make_arch(control_poly, pd, mm)
        if dh != 0:
            poly_front = lst_new[-2]
            poly_legs = [lst_new[-3], lst_new[-1]]
        else:
            poly_front = lst_new[-1]
            poly_legs = []

        for i_new, p in enumerate(lst_new): # not the center
            if p is poly_front:
                continue
            p.face_attr['material'] = frame_idx
            if p in poly_legs:  # uv mode set by arch for others
                p.face_attr['uv_mode'] = 'GLOBAL_XY'
            face = p.make_face()

        topo.add('Frame', len(lst_new) - 1)

        # make bmesh verts so bridge faces share them
        control_poly.make_verts()
        # ARCH has fake outer, but it used the same bm verts so was updated in position
        lst_result = outer.bridge(control_poly, add_perimeter, v_extruding=Vector((0, 0, 1)), arch_type=('ROMAN', True))
        topo.add('Bridge', len(lst_result))
        for p in lst_result:
            if control_poly.coord_sys.reference_face:
                p.face_attr['material'] = control_poly.coord_sys.reference_face.material_index
                if 'uv_mode' in p.face_attr:
                    del p.face_attr['uv_mode']  # let material decide
            face = p.make_face()

        poly_back = SmartPoly(poly_front.coord_sys, poly_front.points, break_link=True)
        v_back = -prop_dict['recess'] * poly_back.normal()
        poly_back.shift_3d(v_back)
        poly_back.face_attr['material'] = frame_idx
        face = poly_back.make_face()
        topo.add('Center')
        lst_result2 = poly_front.bridge_by_number(poly_back, v_extruding=Vector((0, 0, 1)))
        topo.add('Center', len(lst_result2))
        for p in lst_result2:
            if control_poly.coord_sys.reference_face:
                p.face_attr['material'] = frame_idx
                if 'uv_mode' in p.face_attr:
                    del p.face_attr['uv_mode']  # let material decide
            face = p.make_face()

        if len(lst_result) and (control_poly.coord_sys.reference_face is not None):
            mm.delete_face(control_poly.coord_sys.reference_face)

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo
