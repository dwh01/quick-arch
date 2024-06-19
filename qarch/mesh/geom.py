"""Geometry creation routines"""
import copy
import json

import bpy, bmesh
from ..object import TopologyInfo, SelectionInfo, get_bt_collection, get_instance_collection
from .utils import ManagedMesh, managed_bm
from .SmartPoly import SmartPoly, coincident

from mathutils import Vector, Matrix, Euler
import mathutils
import math
import functools, operator
import pathlib
from collections import defaultdict

from ..bpypolyskel import bpypolyskel
import Polygon, Polygon.Shapes, Polygon.Utils

def _common_start(obj, sel_info, break_link=False):
    mm = ManagedMesh(obj)
    vlist_nested = mm.get_face_verts(sel_info)
    lst_out = []
    for vlist in vlist_nested:
        control_poly = SmartPoly(name="control")
        for v in vlist:
            control_poly.add(v, break_link)
        if len(control_poly.coord):
            control_poly.calculate()
            lst_out.append(control_poly)

    if (sel_info.get_mode() == 'REGION') and (len(lst_out) > 0):
        # group by plane
        dct_n = defaultdict(list)
        for p in lst_out:
            t = (round(p.normal.x, 3), round(p.normal.y,3), round(p.normal.z, 3))
            dct_n[t].append(p)

        lst_out = []
        for lst in dct_n.values():
            if len(lst)==1:
                lst_out.append(lst[0])
            elif len(lst) > 1:
                poly = lst[0]
                p_union = poly.union(lst[1:])
                lst_out.append(p_union)
        # allow-holes could be another mode, for now ignore holes in result polygons (use region boundary)

    return mm, lst_out


def _extract_offset(size_dict, box_size):
    sx, sy = size_dict['offset_x'], size_dict['offset_y']
    rel_x, rel_y = size_dict['is_relative_x'], size_dict['is_relative_y']
    if rel_x and (box_size.x > 0):
        sx = box_size.x * sx
    if rel_y and (box_size.y > 0):
        sy = box_size.y * sy
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


def union_polygon(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info)
    mm.set_op(op_id)
    if len(lst_orig_poly) == 0:  # ok to add to none
        lst_orig_poly.append(SmartPoly())

    topo = TopologyInfo(from_keys=['All'])  # flat list
    face_attr = None
    for control_poly in lst_orig_poly:
        face = mm.find_face_by_smart_vec(control_poly.coord)
        if face:
            face_attr = mm.get_face_attrs(face)

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
            if face_attr:
                mm.set_face_attrs(face, face_attr)
            topo.add('All')

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def _make_ngon(control_poly, prop_dict, mm, b_make=True):
    poly = prop_dict['poly']
    n, start_ang = poly['num_sides'], poly['start_angle']
    thickness = prop_dict['frame']

    # initialize with control coordinate system
    new_poly = SmartPoly(matrix=control_poly.matrix, name="new")
    new_poly.center = control_poly.center
    new_poly.generate_ngon(n, start_ang)

    # shift center off origin such that scaling to relative size 1 exactly fits control bounding box
    box_center = (new_poly.bbox[1] + new_poly.bbox[0]) / 2
    new_poly.shift_2d(-box_center)
    # global alignment with control
    new_poly.center = control_poly.center

    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    if new_poly.box_size.x != 0:
        sx = sx / new_poly.box_size.x
    if new_poly.box_size.y != 0:
        sy = sy / new_poly.box_size.y
    new_poly.scale(sx, sy)
    new_poly.update_3d()
    new_poly.calculate()  # update bbox

    voffset = control_poly.bbox[0] + Vector(_extract_offset(prop_dict['position'], control_poly.box_size))
    align_corner = control_poly.make_3d(voffset) - new_poly.make_3d(new_poly.bbox[0])
    new_poly.shift_3d(align_corner)
    new_poly.calculate()

    if b_make:
        new_poly.make_verts(mm)

    lst = [new_poly]
    if thickness > 0:
        new_poly.update_3d()
        inner_poly = new_poly.generate_inset(thickness)
        if b_make:
            inner_poly.make_verts(mm)
        lst.append(inner_poly)

        lst = inner_poly.bridge_by_number(new_poly)
        lst.append(inner_poly)

    return lst, new_poly


def _make_self_poly(control_poly, prop_dict, mm, b_make=True):
    new_poly = SmartPoly()
    new_poly.add(control_poly.coord, break_link=True)
    new_poly.calculate()

    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    if new_poly.box_size.x != 0:
        sx = sx / new_poly.box_size.x
    if new_poly.box_size.y != 0:
        sy = sy / new_poly.box_size.y
    new_poly.scale(sx, sy)
    new_poly.update_3d()
    new_poly.calculate()  # update center

    voffset = control_poly.bbox[0] + Vector(_extract_offset(prop_dict['position'], control_poly.box_size))
    align_corner = control_poly.make_3d(voffset) - new_poly.make_3d(new_poly.bbox[0])
    new_poly.shift_3d(align_corner)
    if b_make:
        new_poly.make_verts(mm)

    return [new_poly], new_poly


def _make_arch(control_poly, prop_dict, mm, b_make=True):
    arch_type = prop_dict['arch']['arch_type']
    n = prop_dict['arch']['num_sides']
    thickness = prop_dict['frame']
    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    new_poly = SmartPoly(matrix = control_poly.matrix)
    new_poly.center = control_poly.center

    lst_arch = new_poly.generate_arch(sx, sy, n, arch_type, thickness, mm)
    lst_arch.append(new_poly)

    bbmin = new_poly.bbox[0].x  # frame extends past this
    for ap in lst_arch[:-1]:
        bb_test = ap.bbox[0].x + new_poly.make_2d(ap.center).x
        bbmin = min(bbmin, bb_test)

    voffset = control_poly.bbox[0] + Vector(_extract_offset(prop_dict['position'], control_poly.box_size))
    align_corner = control_poly.make_3d(voffset) - new_poly.make_3d(Vector((bbmin, new_poly.bbox[0].y)))

    for p in lst_arch:
        p.shift_3d(align_corner)
        p.update_bmverts()

    if (prop_dict.get('join', 'FREE') == 'BRIDGE') and (len(lst_arch) > 1):
        # need a fake poly to hide inside edges during bridging
        # outside perimeter
        lst_co = [p.coord[0] for p in lst_arch[:-1]]
        lst_co.append(lst_arch[-1].coord[1])
        if arch_type == "JACK":
            lst_co.insert(0, new_poly.coord[0])
            lst_co.insert(1, new_poly.coord[1])
            lst_co.append(new_poly.coord[2])
            lst_co.append(new_poly.coord[3])
        tmp_poly = SmartPoly(matrix = lst_arch[-1].matrix)
        tmp_poly.add(lst_co, break_link=False)
        tmp_poly.calculate()
    else:
        tmp_poly = lst_arch[-1]
    return lst_arch, tmp_poly


def _make_super(control_poly, prop_dict, mm, b_make=True):
    resolution = prop_dict['resolution']

    new_poly = SmartPoly(matrix=control_poly.matrix, name="new")
    new_poly.center = control_poly.center

    super_dict = prop_dict['super_curve']
    start_angle = super_dict['start_angle']
    x, sx, px = super_dict['x'], super_dict['sx'], super_dict['px']
    y, sy, py = super_dict['y'], super_dict['sy'], super_dict['py']
    pn = super_dict['pn']
    new_poly.generate_super(x, sx, px, y, sy, py, pn, resolution, start_angle)
    npc = new_poly.center - control_poly.center  # can be asymmetric so off center

    sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
    if new_poly.box_size.x != 0:
        sx = sx / new_poly.box_size.x
    if new_poly.box_size.y != 0:
        sy = sy / new_poly.box_size.y

    new_poly.shift_3d(-npc)  # scale around geometric origin
    new_poly.scale(sx, sy)
    new_poly.update_3d()
    npc.x *= sx
    npc.y *= sy
    new_poly.shift_3d(npc)
    new_poly.update_3d()  # update bbox
    new_poly.calculate()  # update center

    voffset = control_poly.bbox[0] + Vector(_extract_offset(prop_dict['position'], control_poly.box_size))
    align_corner = control_poly.make_3d(voffset) - new_poly.make_3d(new_poly.bbox[0])
    new_poly.shift_3d(align_corner)
    new_poly.calculate()

    if b_make:
        new_poly.make_verts(mm)
    lst = [new_poly]

    if prop_dict['join'] == 'BRIDGE':  # project to outside along radial, not outward ray
        outer = SmartPoly(matrix=new_poly.matrix, name="outer")
        outer.center = new_poly.center - npc
        outer.generate_ngon(resolution, start_angle)
        for sv in outer.coord:
            far = outer.center + (sv.co3 - outer.center)*100
            pt2, idx = control_poly.intersect_projection(outer.center, far)
            sv.co3 = outer.make_3d(pt2)
        outer.calculate()

        lst = new_poly.bridge_by_number(outer)
        lst.append(new_poly)
    else:
        outer = new_poly

    return lst, outer


def _make_curve_poly(control_poly, prop_dict, mm, b_make=True):
    resolution = prop_dict['resolution']
    ob_dict = prop_dict['local_object']
    ob_name = ob_dict['object_name']

    eul = Euler(ob_dict['rotate'])
    mat_rot = eul.to_matrix()

    new_poly = SmartPoly(matrix=control_poly.matrix, name="default")  # default in case no points
    new_poly.center = control_poly.center

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
            if i < segments-1:
                points = points + _points[:-1]
            else:
                points = points + _points

        # strip out straight lines
        lst_points = [points[0]]
        for i in range(1, len(points)-1):
            e = (points[i] - points[i-1]).normalized()
            e1 = (points[i+1] - points[i]).normalized()
            if e.dot(e1) < 0.999:
                lst_points.append(points[i])
        lst_points.append(points[-1])

        # rotation
        lst_points = [mat_rot @ p for p in lst_points]
        new_poly = SmartPoly(name="new")
        for p in lst_points:
            new_poly.add(p)
        new_poly.calculate()
        print(new_poly.debug_str())
        print(", ".join(["<{0[0]:.3f},{0[1]:.3f},{0[2]:.3f}>".format(sv.co3) for sv in new_poly.coord]))

        sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
        if new_poly.box_size.x != 0:
            sx = sx / new_poly.box_size.x
        if new_poly.box_size.y != 0:
            sy = sy / new_poly.box_size.y

        new_poly.scale(sx, sy)
        new_poly.update_3d()

        voffset = control_poly.bbox[0] + Vector(_extract_offset(prop_dict['position'], control_poly.box_size))
        align_corner = control_poly.make_3d(voffset) - new_poly.make_3d(new_poly.bbox[0])
        new_poly.shift_3d(align_corner)

        if b_make:
            new_poly.make_verts(mm)

    return [new_poly], new_poly


def text_to_curve(text, name):
    from ..ops import BT_IMG_DESC
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
    dct_curve = {'description':description, 'bezier_points':lst}
    return json.dumps(dct_curve)


def _make_catalog_poly(control_poly, prop_dict, mm, context, b_make=True):
    from ..ops import file_type, from_path, BT_CATALOG_SRC

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


def get_material_index(mat_name, obj):
    mat_idx = None
    for i, mat in enumerate(obj.data.materials):
        if mat.name == mat_name:
            mat_idx = i

    if mat_idx is None:
        obj.data.materials.append(bpy.data.materials[mat_name])
        mat_idx = len(obj.data.materials) - 1
    return mat_idx

def inset_polygon(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=False)
    mm.set_op(op_id)

    if len(lst_orig_poly) == 0:  # ok to add to none
        print("no original poly")
        lst_orig_poly.append(SmartPoly())
        prop_dict['join'] = 'FREE'
        prop_dict['size']['is_relative_x'] = False
        prop_dict['size']['is_relative_y'] = False

    shape_type = prop_dict['shape_type']
    join_type = prop_dict['join']
    frame_mat = prop_dict['frame_material']
    center_mat = prop_dict['center_material']
    add_perimeter = prop_dict['add_perimeter']
    # avoid errors with missing objects
    if (shape_type == 'CATALOG') and (prop_dict['catalog_object']['category_item'] in ['','N/A','0']):
        shape_type = 'SELF'
    if (shape_type == 'CURVE') and (prop_dict['local_object']['object_name'] in ['','N/A','0']):
        shape_type = 'SELF'

    frame_idx = get_material_index(frame_mat, self.obj)
    center_idx = get_material_index(center_mat, self.obj)

    topo = TopologyInfo(from_keys=['Bridge', 'Center', 'Frame'])

    faces = mm.get_faces(sel_info)
    if len(faces)==0:
        faces = [None] * len(lst_orig_poly)  # adding to nothing
    face_attr = None

    for orig_poly, orig_face in zip(lst_orig_poly, faces):  # note, if a region, the first face provides the info
        if orig_face:
            face_attr = mm.get_face_attrs(orig_face)

        control_poly = SmartPoly()
        control_poly.add(orig_poly.coord, break_link=True)
        control_poly.calculate()
        b_close = True
        if shape_type == 'NGON':
            lst_new, outer = _make_ngon(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new)-1)
            topo.add('Center')
        elif shape_type == 'SELF':
            lst_new, outer = _make_self_poly(control_poly, prop_dict, mm)
            topo.add('Center')
        elif shape_type == 'ARCH':
            b_close = False
            lst_new, outer = _make_arch(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new)-1)
            topo.add('Center')
        elif shape_type == 'SUPER':
            lst_new, outer = _make_super(control_poly, prop_dict, mm)
            if len(lst_new) > 1:
                topo.add('Frame', len(lst_new)-1)
            topo.add('Center')
        elif shape_type == 'CURVE':
            lst_new, outer = _make_curve_poly(control_poly, prop_dict, mm)
            topo.add('Center')
        elif shape_type == 'CATALOG':
            lst_new, outer = _make_catalog_poly(control_poly, prop_dict, mm, self.context)
            topo.add('Center')
        else:
            assert False, "Unhandled shape type {}".format(shape_type)

        # shift center z
        b_extruding = False
        for i_new, p in enumerate(lst_new):
            if p.normal.dot(control_poly.normal) < .999:  # flipped normal
                p.flip_z()

            if prop_dict['extrude_distance'] != 0:
                p.shift_3d( p.normal * prop_dict['extrude_distance'] )
                b_extruding = True
            #p.calculate()  # refresh winding angles, center, etc
        if (len(lst_new) == 1) and (len(control_poly.coord) >= 3):
            if join_type in ['INSIDE', 'OUTSIDE']:
                lst_new = lst_new[0].clip_with(control_poly, join_type)
                if len(lst_new):
                    outer = lst_new[0]

        for i_new, p in enumerate(lst_new):
            face = p.make_face(mm)
            if i_new == len(lst_new)-1:
                face.material_index = center_idx
            else:
                face.material_index = frame_idx

        if (join_type == 'BRIDGE') and (shape_type != 'SUPER'):
            # make bmesh verts so bridge faces share them
            control_poly.make_verts(mm)
            # ARCH has fake outer, but it used the same bm verts so was updated in position
            n_outer = 0
            lst_result = outer.bridge(control_poly, mm, add_perimeter, b_extruding, b_close=b_close)
            topo.add('Bridge', len(lst_result))
            for p in lst_result:
                face = p.make_face(mm)
                if face_attr is not None:
                    mm.set_face_attrs(face, face_attr)  # keep tags, uv mode, etc
                    face.material_index = orig_face.material_index

            if len(lst_result) and (orig_face is not None):
                mm.delete_face(orig_face)

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def grid_divide(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=["All"])
    topo.set_modulus("All", prop_dict['count_y'])
    face_attr = None
    faces = mm.get_faces(sel_info)
    mat_idx =0
    for control_poly, orig_face in zip(lst_orig_poly, faces):
        face = orig_face  # mm.find_face_by_smart_vec(control_poly.coord)
        if face:
            face_attr = mm.get_face_attrs(face)
            mat_idx = face.material_index
        sx, sy = _extract_offset(prop_dict['offset'], control_poly)

        count_x = prop_dict['count_x']
        count_y = prop_dict['count_y']
        for i in range((count_x+1)*(count_y+1)):
            topo.add("All")

        lst_poly = control_poly.grid_divide(count_x, count_y, sx, sy)

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
            if face_attr is not None:
                mm.set_face_attrs(face, face_attr)
                face.material_index = mat_idx

        if len(lst_poly):
            # remove old face
            face = mm.find_face_by_smart_vec(control_poly.coord)
            if face is not None:
                mm.delete_face(face)
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
    face_attr = None
    mat_idx = 0
    orig_faces = mm.get_faces(sel_info)
    for control_poly, orig_face in zip(lst_orig_poly, orig_faces):
        face = orig_face # mm.find_face_by_smart_vec(control_poly.coord)
        if face:
            face_attr = mm.get_face_attrs(face)
            mat_idx = face.material_index
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
            topo.add("All")
            if face_attr is not None:
                mm.set_face_attrs(face, face_attr)
                face.material_index = mat_idx

        if len(lst_poly) != 2: # bad assumption before, have to just use one long list
            topo.set_modulus("All", 0)

        if len(lst_poly):
            # remove old face
            face = mm.find_face_by_smart_vec(control_poly.coord)
            if face is not None:
                mm.delete_face(face)
            mm.to_mesh()
        # else discard new points and leave old face in place

    mm.free()
    return topo

def extrude_fancy(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Sides','Tops'])
    ncoord = len(lst_orig_poly[0].coord)

    side_mat = prop_dict['side_material']
    center_mat = prop_dict['center_material']
    side_idx = get_material_index(side_mat, self.obj)
    center_idx = get_material_index(center_mat, self.obj)

    lst_faces = mm.get_faces(sel_info)
    for control_poly, control_face in zip(lst_orig_poly, lst_faces):
        if len(control_poly.coord) != len(lst_orig_poly[0].coord):
            ncoord = None  # no modulus possible
        attrs = mm.get_face_attrs(control_face)

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
            top_poly.calculate()
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
            if prop_dict['flip_normals']:
                top_poly.flip_z()

            top_poly.make_verts(mm)  # to share
            lst_poly = top_poly.bridge_by_number(bottom_poly, reversed=prop_dict['flip_normals'])
            lst_layers.append(lst_poly)
            for j in range(len(lst_poly)):
                topo.add('Sides')

            bottom_poly = top_poly

        lst_layers.append([bottom_poly]) # add the cap face
        topo.add('Tops')

        face = None
        for lst_poly in lst_layers:
            for r_poly in lst_poly:
                # make new face
                face = r_poly.make_face(mm)
                mm.set_face_attrs(face, attrs)
                face.material_index = side_idx
                calc_face_uv(face, mm)
        # last one is the center
        if face is not None:
            face.material_index = center_idx

    if ncoord is not None:
        topo.set_modulus('Sides', ncoord)

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def extrude_sweep(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Sides','Tops'])
    ncoord = len(lst_orig_poly[0].coord)

    side_mat = prop_dict['side_material']
    center_mat = prop_dict['center_material']
    side_idx = get_material_index(side_mat, self.obj)
    center_idx = get_material_index(center_mat, self.obj)

    lst_faces = mm.get_faces(sel_info)
    for control_poly, control_face in zip(lst_orig_poly, lst_faces):
        if len(control_poly.coord) != len(lst_orig_poly[0].coord):
            ncoord = None  # no modulus possible
        attrs = mm.get_face_attrs(control_face)

        ox, oy, oz = _extract_vector(prop_dict['origin'])
        ax, ay, az = _extract_vector(prop_dict['axis'])
        v_origin = control_poly.inverse @ Vector((ox, oy, oz)) + control_poly.make_3d(control_poly.bbox[0])
        v_axis = control_poly.inverse @ Vector((ax, ay, az))

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
            for j in range(len(lst_poly)):
                topo.add('Sides')

            bottom_poly = top_poly

        lst_layers.append([bottom_poly])  # add the cap face
        topo.add('Tops')

        for lst_poly in lst_layers:
            for r_poly in lst_poly:
                # make new face
                face = r_poly.make_face(mm)
                mm.set_face_attrs(face, attrs)
                face.material_index = side_idx
                calc_face_uv(face, mm)
        # last one is the center
        if face is not None:
            face.material_index = center_idx

    if ncoord is not None:
        topo.set_modulus('Sides', ncoord)
    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def _combined_bbox(lst_poly):
    minv = lst_poly[0].bbox[0]
    maxv = lst_poly[0].bbox[1]
    for p in lst_poly:
        v = lst_poly[0].make_2d(p.make_3d(p.bbox[0]))
        minv.x = min(minv.x, v.x)
        minv.y = min(minv.y, v.y)
        v = lst_poly[0].make_2d(p.make_3d(p.bbox[1]))
        maxv.x = max(maxv.x, v.x)
        maxv.y = max(maxv.y, v.y)
    minv = lst_poly[0].make_3d(minv)
    maxv = lst_poly[0].make_3d(maxv)
    return minv, maxv


def _dir_check(cross_section, control_poly):
    if math.fabs(cross_section.ydir.dot(control_poly.normal)) >= math.fabs(cross_section.xdir.dot(control_poly.normal)):
        inset_dir = cross_section.xdir
    else:
        inset_dir = cross_section.ydir
    proj_center = mathutils.geometry.intersect_line_plane(cross_section.center, cross_section.center + control_poly.normal, control_poly.center, control_poly.normal)
    if inset_dir.dot(control_poly.center - proj_center) < 0:
        inset_dir = -inset_dir
    return inset_dir


def solidify_by_bridge(control_poly, side_list, i_edge, e, vz, inset, mm, frame_idx, topo, tag, lst_new):
    # extracted from solidify to allow swap between revolution and extrude modes
    mat_inline = Matrix.Identity(3)
    local_z = e
    local_y = control_poly.normal
    local_x = local_y.cross(local_z)
    for i in range(3):
        mat_inline[0][i] = local_x[i]
        mat_inline[1][i] = local_y[i]
        mat_inline[2][i] = local_z[i]

    ncp = len(control_poly.coord)
    b_make = i_edge in side_list
    b_bevel_start = ((i_edge + ncp - 1) % ncp) in side_list
    b_bevel_end = ((i_edge + 1) % ncp) in side_list
    if b_make:
        print("bevels", (i_edge + ncp - 1) % ncp, i_edge, (i_edge + 1) % ncp, b_bevel_start, b_bevel_end)
    else:
        return
    lst_start = []
    if b_bevel_start:
        pt_out, ray_out = control_poly.outward_ray_idx(i_edge)
        if ray_out.length == 0:
            ax = Vector((0, 0, 0))
        else:
            theta = local_z.angle(ray_out) - math.pi / 2
            ax = local_z.cross(ray_out)
        if ax.length == 0:
            mat = Matrix.Identity(3)
        else:
            ax.normalize()
            ax = mat_inline @ ax
            mat = Matrix.Rotation(-theta, 3, ax.normalized())
        edge_mat = mat @ mat_inline
        scale = math.fabs(math.cos(theta))
        scale = 1 / max(scale, 0.01)
    else:
        edge_mat = mat_inline
        scale = 1

    for i_new in range(len(lst_new)):
        start_poly = SmartPoly(matrix=edge_mat, name="start")
        start_poly.center = control_poly.coord[i_edge].co3
        for sv in lst_new[i_new].coord:
            v = Vector((sv.co2.x * scale, sv.co2.y))
            start_poly.add(start_poly.make_3d(v))
        start_poly.calculate()
        inset_dir = _dir_check(start_poly, control_poly)
        start_poly.shift_3d(vz + inset * inset_dir * scale)
        # start_poly.calculate()
        lst_start.append(start_poly)

    for i in range(3):  # this is redundant but every once in a while mat_inline is flipped. Blender bug?
        mat_inline[0][i] = local_x[i]
        mat_inline[1][i] = local_y[i]
        mat_inline[2][i] = local_z[i]
    lst_end = []
    if b_bevel_end:
        pt_out, ray_out = control_poly.outward_ray_idx((i_edge + 1) % ncp)
        if ray_out.length == 0:
            ax = Vector((0, 0, 0))
        else:
            theta = local_z.angle(ray_out) - math.pi / 2
            ax = local_z.cross(ray_out)
        if ax.length == 0:
            mat = Matrix.Identity(3)
        else:
            ax.normalize()
            ax = mat_inline @ ax
            mat = Matrix.Rotation(-theta, 3, ax)
        edge_mat = mat @ mat_inline
        scale = math.fabs(math.cos(theta))
        scale = 1 / max(scale, 0.01)

    else:
        edge_mat = mat_inline
        scale = 1

    for i_end in range(len(lst_new)):
        end_poly = SmartPoly(matrix=edge_mat, name="end")
        end_poly.center = control_poly.coord[(i_edge + 1) % ncp].co3
        for sv in lst_new[i_end].coord:
            v = Vector((sv.co2.x * scale, sv.co2.y))
            end_poly.add(end_poly.make_3d(v))
        end_poly.calculate()
        inset_dir = _dir_check(end_poly, control_poly)
        end_poly.shift_3d(vz + inset * inset_dir * scale)
        lst_end.append(end_poly)

    if b_make:
        reversed = False
        i_off = 0
        if not b_bevel_start:  # close off end
            for p in lst_start:
                if p.normal.dot(lst_end[0].normal) < 0:
                    reversed = True
                    i_off = 2
                face = p.make_face(mm)
                mm.set_face_attrs(face, {mm.key_tag: tag})
                face.material_index = frame_idx
            topo.add('Starts', len(lst_start))

        if not b_bevel_end:  # close off end
            for p in lst_end:
                face = p.make_face(mm)
                mm.set_face_attrs(face, {mm.key_tag: tag})
                face.material_index = frame_idx
            topo.add('Ends', len(lst_end))

        # bridge
        for p1, p2 in zip(lst_start, lst_end):
            lst_sides = p1.bridge_by_number(p2, idx_offset=i_off, reversed=reversed)
            for p in lst_sides:
                face = p.make_face(mm)
                mm.set_face_attrs(face, {mm.key_tag: tag})
                face.material_index = frame_idx
            topo.add('Sides', len(lst_sides))

def solidify_by_revolution(control_poly, side_list, i_edge, e, vz, n_steps, inset, mm, frame_idx, topo, tag, lst_new):
    # extracted from solidify to allow swap between revolution and extrude modes
    mat_inline = Matrix.Identity(3)
    local_y = e
    local_z = control_poly.normal
    local_x = local_y.cross(local_z)
    for i in range(3):
        mat_inline[0][i] = local_x[i]
        mat_inline[1][i] = local_y[i]
        mat_inline[2][i] = local_z[i]

    rot_origin = control_poly.coord[i_edge].co3

    b_make = i_edge in side_list

    lst_poly = []
    for i_new in range(len(lst_new)):
        start_poly = SmartPoly(matrix=mat_inline, name="start")
        start_poly.center = control_poly.coord[i_edge].co3
        for sv in lst_new[i_new].coord:
            v = Vector((sv.co2.x, sv.co2.y))
            start_poly.add(start_poly.make_3d(v))
        start_poly.calculate()
        inset_dir = _dir_check(start_poly, control_poly)
        edge_dist = inset - start_poly.bbox[0].x  # shift to put bbox edge on axis of rotation
        start_poly.shift_3d(edge_dist * inset_dir)
        # start_poly.calculate()
        lst_rev = start_poly.generate_revolve(rot_origin, e.normalized(), n_steps, vz, mm, b_make)
        lst_poly = lst_poly + lst_rev

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
    b_all_sides = len(side_list)==0

    inset = prop_dict['inset']
    z_offset = prop_dict['z_offset']

    frame_idx = None
    for i, mat in enumerate(self.obj.data.materials):
        if mat.name == frame_mat:
            frame_idx = i
    if frame_idx is None:
        self.obj.data.materials.append(bpy.data.materials[frame_mat])
        frame_idx = len(self.obj.data.materials) - 1

    topo = TopologyInfo(from_keys=['Sides', 'Starts', 'Ends'])

    faces = mm.get_faces(sel_info)

    face_attr = None
    for orig_poly, orig_face in zip(lst_orig_poly, faces):  # note, if a region, the first face provides the info
        if len(orig_poly.coord) < 3:
            continue
        face_attr = mm.get_face_attrs(orig_face)
        sx, sy = _extract_size(prop_dict['size'], orig_poly.box_size)
        # fake in position to center the shape
        prop_dict['position'] = {'offset_x': -sx/2, 'is_relative_x': False,
                                 'offset_y': -sy/2, 'is_relative_y': False}

        ncp = len(orig_poly.coord)
        control_poly = SmartPoly()
        if prop_dict['dashed'] and (revolutions < 3) and (dash_spacing > 0) and (dash_length > 0):
            pts_new = []

            cur_side_list = []
            for i in range(ncp):
                j = (i+1) % ncp
                d0 = dash_offset
                v0 = orig_poly.coord[i].co3
                e = orig_poly.coord[j].co3 - v0
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
                        cur_side_list.append(len(pts_new)-2)
                    d0 = d0 + dash_spacing
                if b_exact and (dash_offset==0):  # don't duplicate vertex at corner
                    pts_new = pts_new[:-1]
            control_poly.add(pts_new)

        else:
            control_poly.add(orig_poly.coord, break_link=True)
            if b_all_sides:
                side_list = list(range(ncp))
            cur_side_list = side_list.copy()
        control_poly.calculate()

        vz = control_poly.normal * prop_dict['z_offset']

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
            poly_test = lst_new[-2]
            matches = []
            for poly_test in [lst_new[-2], lst_new[0]]:  # for arch, don't know which side might match
                for i_test, sv in enumerate(poly_test.coord):
                    for j, sv1 in enumerate(poly_b.coord):
                        if coincident(sv.co3, sv1.co3):
                            for k, sv2 in enumerate(poly_a.coord):
                                if coincident(sv.co3, sv2.co3):
                                    matches.append((j, k))
                                    break
                            break
                if len(matches):
                    break

            if len(matches) > 1: # assuming 2 adjacent points, need points in between on poly_b - j index
                if matches[0][1] < matches[1][1]:
                    j1 = matches[0][0]
                    j2 = matches[1][0]
                    ipos = matches[0][1]
                else:
                    j1 = matches[1][0]
                    j2 = matches[0][0]
                    ipos = matches[1][1]
                jidx = list(range(len(poly_b.coord)))
                if j1 < j2:
                    jidx = jidx[j2+1:] + jidx[:j1]
                else:
                    jidx = jidx[j1+1:] + jidx[:j2]

                for j in jidx:
                    poly_a.coord.insert(ipos+1, poly_b.coord[j])
                    ipos = ipos + 1
            poly_a.calculate()
            lst_new = [poly_a]

        ncp = len(control_poly.coord)
        for i_edge in range(ncp):
            e = control_poly.coord[(i_edge + 1) % ncp].co3 - control_poly.coord[i_edge].co3
            if e.length > 0:
                e.normalize()
                if revolutions < 3:
                    solidify_by_bridge(control_poly, cur_side_list, i_edge, e, vz, inset, mm, frame_idx, topo, tag, lst_new)
                else:
                    solidify_by_revolution(control_poly, cur_side_list, i_edge, e, z_offset, revolutions, inset, mm, frame_idx, topo, tag, lst_new)


    mm.to_mesh()
    mm.free()
    return topo


def make_louvers(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Blades','Risers'])  # implement risers
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
    tag = prop_dict['face_tag']

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
            vert_last = None
            for i_y in range(count_y):
                blade_verts, blade_faces = mm.cube(blade_w, depth_thickness, blade_thickness, tag)
                # rotate and translate blade_faces
                for vert in blade_verts:
                    v1 = rot @ vert.co + i_y * v_step + v_origin + v_depth
                    v1 = control_poly.inverse @ v1 + control_poly.center
                    vert.co = v1
                for j in range(6):
                    topo.add('Blades')
                if connect and vert_last:
                    vlist = [vert_last[0], vert_last[3], blade_verts[6], blade_verts[7]]
                    mm.new_face(vlist)
                    topo.add('Risers')
                vert_last = blade_verts
    # could add an option to remove the face, but usually we are making window shades and want to keep the glass
    # face = mm.find_face_by_smart_vec(control_poly.coord)
    # if face is not None:
    #     mm.delete_face(face)
    #     mm.to_mesh()
    mm.to_mesh()
    mm.free()
    return topo


def set_face_property(self, obj, sel_info, op_id, prop_dict):
    mm = ManagedMesh(obj)
    if "tag" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_tag, prop_dict['tag'])
    elif "thickness" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_thick, prop_dict['thickness'])
    elif "uv_mode" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv, prop_dict['uv_mode'])
    elif "uv_orig" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv_orig, prop_dict['uv_origin'])
    elif "uv_rotate" in self.bl_idname:
        mm.set_facesel_attr(sel_info, mm.key_uv_rot, prop_dict['uv_rotate'])
    mm.to_mesh()
    mm.free()

    if "uv" in self.bl_idname:
        pd = {'override_origin': False, 'origin': Vector((0, 0, 0)),
              'override_mode': False, 'mode': 'GLOBAL_XY'}
        calc_uvs(self, obj, sel_info, op_id, pd)

    n_face = sel_info.count_faces()
    topo = TopologyInfo(from_keys=['All'])
    for i in range(n_face):
        topo.add('All')
    return topo


def calc_face_uv(face, mm, mode=None, orig=None):
    from ..ops.properties import uv_mode_list
    uv_layer = mm.bm.loops.layers.uv.active
    if mode is None:
        mode = face[mm.key_uv]
    if orig is None:
        orig = face[mm.key_uv_orig]

    poly = SmartPoly()
    for v in face.verts:
        poly.add(v)
    poly.calculate()
    r = 1
    mode = uv_mode_list[mode][0]
    if mode in ['GLOBAL_XY', 'GLOBAL_YX']:
        v = Vector((0, 0, 0))
        v = poly.make_2d(v)
    elif mode in ['FACE_XY', 'FACE_YX']:
        v = Vector((0, 0))
    elif mode == 'FACE_BBOX':
        v = poly.bbox[0]
    elif mode == 'FACE_POLAR':
        v = poly.make_2d(orig)
        xy= [(pc.co2-v) for pc in poly.coord]
        r = [a.length for a in xy]
        r = functools.reduce(max, r, 0)
    elif mode == 'ORIENTED':
        v = orig.to_2d()
    else:  # none
        return

    for i, loop in enumerate(face.loops):
        if mode == 'ORIENTED':
            xyw = poly.coord[i].co3 - orig
            loop[mm.key_uv_w] = xyw.z
            xy = xyw.to_2d()
        else:
            xy = poly.coord[i].co2 - v

        if mode in ['GLOBAL_YX', 'FACE_YX']:
            xy = Vector((xy.y, xy.x))
        elif mode == 'FACE_POLAR':
            loop[mm.key_uv_w] = r  # scale factor for angle to dimension

        loop[uv_layer].uv = xy


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
    mat_name = prop_dict['material']
    midx = 0
    for midx in range(len(obj.data.materials)):
        if obj.data.materials[midx].name == mat_name:
            break

    mm = ManagedMesh(obj)
    flist = mm.get_faces(sel_info)
    sortable = [(f, f.calc_area()) for f in flist]
    sortable.sort(key=lambda t: t[1])
    face = sortable[-1][0]
    poly = SmartPoly(name="control")
    for v in face.verts:
        poly.add(v)
    poly.calculate()
    if poly.box_size.x > poly.box_size.y:
        axis = poly.xdir
    else:
        axis = poly.ydir

    rot = axis.to_track_quat('Z','Y').to_euler()
    rand = math.fmod(face.verts[0].co.length, 7)/100  # make neighbors not the same
    org = poly.center - 0.06 * poly.normal + rand  # reproducible, not really random

    mm.set_facesel_attr(sel_info, mm.key_uv_orig, org)
    mm.set_facesel_attr(sel_info, mm.key_uv_rot, rot)
    mm.set_facesel_attr(sel_info, mm.key_uv, 'ORIENTED')

    topo = TopologyInfo(from_keys=['All'])
    for f in flist:
        f.material_index = midx
        topo.add('All')
        calc_face_uv(f, mm, mode=None, orig=None)
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
    from .assets import find_or_load
    from ..ops import file_type, from_path, BT_CATALOG_SRC

    if prop_dict['use_catalog']:
        cat_dict = prop_dict['catalog_object']
        obj_path = pathlib.Path(cat_dict['category_item'])
        if str(obj_path) in ['', '0', 'N/A']:
            topo = TopologyInfo(from_keys=['All'])
            return topo
        ftype, obj_name = file_type(obj_path.stem)
        obj_original = find_or_load(obj_name, obj_path)

    else:
        obj_name = prop_dict['local_object']['object_name']
        if obj_name in ['', '0', 'N/A']:
            topo = TopologyInfo(from_keys=['All'])
            return topo

    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)
    obj_add = _find_instance_object(obj, op_id)
    head = ""
    if obj_add is not None:  # check if we are changing instance example and unlink old one
        head = obj_add.name[:10] # "bt000.000.name"
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
    bb_size = bb_max-bb_min

    facelist = mm.get_faces(sel_info)
    for control_poly, control_face in zip(lst_orig_poly, facelist):
        face_selector = control_poly.make_face(mm)  # else we can't select this operation for redo or erase
        attrs = mm.get_face_attrs(control_face)
        mm.set_face_attrs(face_selector, attrs)
        face_selector.material_index = control_face.material_index
        calc_face_uv(face_selector, mm)
        mm.set_face_attrs(control_face, {mm.key_tag: 'DELETE'})

        topo.add('All')

        inst_dir = control_poly.inverse @ a_dir

        #sx, sy = _extract_size(prop_dict['size'], control_poly.box_size)
        sx, sy = sz, sz
        ox, oy = _extract_offset(prop_dict['position'], control_poly.box_size)

        v_start = control_poly.make_3d(control_poly.bbox[0])
        v_start += ox*control_poly.xdir + oy*control_poly.ydir + dz*control_poly.normal

        r_mat = control_poly.inverse @ e_rot.to_matrix()
        r_euler = r_mat.to_euler()

        v_scale = Vector((sx, sy, sz))

        dtheta = 0
        v_origin = Vector((0,0,0))
        if a_do_orbit:
            v_origin = (control_poly.make_3d(control_poly.bbox[0])
                        + a_origin.x*control_poly.xdir + a_origin.y*control_poly.ydir)  # in face coordinates
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
                    local_rot = Matrix.Rotation(i*dtheta, 3, control_poly.normal)
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
                b_found = False
                for idx in range(len(obj.data.materials)):
                    if obj.data.materials.name == mat.name:
                        dct_map_matl[i_add] = idx
                        b_found = True
                        break
                if not b_found:
                    idx = len(obj.data.materials)
                    obj.data.materials.append(mat)
                    dct_map_matl[i_add] = idx

            with managed_bm(obj_add) as bm_add:
                bm_add.verts.ensure_lookup_table()
                for v_add in bm_add.verts:
                    v1 = Vector((v_add.x*v_scale.x, v_add.y*v_scale.y, v_add.z*v_scale.z))
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

    faces = mm.get_faces(sel_info)
    if len(faces) == 0:
        faces = [None] * len(lst_orig_poly)  # adding to nothing
    face_attr = None

    for control_poly, orig_face in zip(lst_orig_poly, faces):
        new_poly = SmartPoly()
        new_poly.add(control_poly.coord, break_link=True)
        new_poly.flip_z()

        face_attr =  mm.get_face_attrs(orig_face)
        face = new_poly.make_face(mm)
        mm.set_face_attrs(face, face_attr)

    topo = TopologyInfo(from_keys=['All'])
    topo.add('All', len(lst_orig_poly))
    return topo


def project_face(self, obj, sel_info, op_id, prop_dict):
    mm, lst_orig_poly = _common_start(obj, sel_info, break_link=True)
    mm.set_op(op_id)

    topo= TopologyInfo(from_keys=['All'])

    target = prop_dict['target'] % len(lst_orig_poly)
    poly_b = lst_orig_poly[target]

    faces = mm.get_faces(sel_info)
    for poly_a, org_face in zip(lst_orig_poly, faces):
        if poly_b is poly_a:
            continue

        poly_c = SmartPoly()
        poly_c.add(poly_a.coord)
        poly_c.project_to(poly_b.normal)  # shape of a when projected

        line_a = poly_a.center
        line_b = line_a + poly_a.normal
        v = mathutils.geometry.intersect_line_plane(line_a, line_b, poly_b.center, poly_b.normal)
        if v is not None:
            poly_c.shift_3d(v - poly_c.center)

        lst_poly = []
        if not prop_dict['bridge']:
            # use c as target
            poly_a.make_verts(mm)
            poly_c.make_verts(mm)
            lst_poly = poly_a.bridge_by_number(poly_c)
        else:
            # use c for bridge calculation
            if poly_c.normal.dot(poly_b.normal) < 0:
                poly_c.flip_z()  # should be facing same direction
            poly_c.make_verts(mm)
            if poly_b.coord[0].bm_vert is None:
                poly_b.make_verts(mm)
            lst_poly = poly_c.bridge(poly_b, mm, False, b_extruding=True)

            # transfer positions of a to c, ie, unproject c
            # since we premade and shared verts, this fixes all the bridging polys
            poly_c.flip_z()  # should be facing original direction
            for i in range(len(poly_a.coord)):
                poly_c.coord[i].co3 = poly_a.coord[i].co3
                poly_c.coord[i].bm_vert.co = poly_a.coord[i].co3
            poly_c.calculate()

        tag = prop_dict['tag']
        for p in lst_poly:
            face = p.make_face(mm)
            face.material_index = org_face.material_index
            mm.set_face_attrs(face, {mm.key_tag: tag})

        topo.add('All', len(lst_poly))
    return topo


def extrude_walls(self, obj, sel_info, op_id, prop_dict):
    # need to extrude individually
    # remember to do -normal direction, so flip_z on results to get proper normals
    # make sure to copy materials, set oriented if face was already, keep common origin and orientation
    #  but calculate new uv_w locations (see make_oriented)
    # then clear thickness so it doesn't happen twice (unless in rebuild which starts over)
    mm = ManagedMesh(obj)
    lst_thick_faces = mm.thick_faces(sel_info)

    mm.set_op(op_id)
    topo = TopologyInfo(from_keys=['Sides', 'Tops'])

    for orig_face in lst_thick_faces:
        face_attr = mm.get_face_attrs(orig_face)
        control_poly = SmartPoly()
        control_poly.add(list(orig_face.verts), break_link=False)
        control_poly.calculate()
        offset = -control_poly.normal * orig_face[mm.key_thick]

        top_poly = SmartPoly()
        top_poly.add(control_poly.coord, break_link=True)
        top_poly.shift_3d(offset)
        top_poly.calculate()

        top_poly.make_verts(mm)  # to share
        lst_poly = top_poly.bridge_by_number(control_poly)
        topo.add('Sides', len(lst_poly))
        lst_poly.append(top_poly)
        topo.add('Tops')
        for p in lst_poly:
            p.flip_z()
            face = p.make_face(mm)
            mm.set_face_attrs(face, face_attr)
            face.material_index = orig_face.material_index
            calc_face_uv(face, mm, face[mm.key_uv], face[mm.key_uv_orig])

            mm.set_face_attrs(face, {mm.key_thick:0})
        mm.set_face_attrs(orig_face, {mm.key_thick:0})

    # finalize and save
    mm.to_mesh()
    mm.free()
    return topo


def build_face(self, obj, sel_info, op_id, prop_dict):
    mm = ManagedMesh(obj)
    verts = mm.vert_list(sel_info)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=['All'])
    poly = SmartPoly()
    for v in verts:
        poly.add(v, break_link=True)
    poly.calculate()

    poly.coord.sort(key=lambda sv: sv.winding)
    poly.calculate()

    if prop_dict['flip_normal']:
        poly.flip_z()

    face = poly.make_face(mm)
    if prop_dict['tag'] != '':
        mm.set_face_attrs(face, {mm.key_tag: prop_dict['tag']})

    mm.to_mesh()
    mm.free()
    topo.add('All')

    return topo


def build_roof(self, obj, sel_info, op_id, prop_dict):
    # use cases: 1 face, multiple faces
    # for multiface, use see smartpoly union (but we can allow holes for courtyards, etc)
    # strip out duplicate verts (same position) and straight line verts (same direction)

    mm = ManagedMesh(obj)
    flist = mm.get_faces(sel_info)
    mm.set_op(op_id)

    topo = TopologyInfo(from_keys=['All', 'Attic'])
    height = prop_dict['height']
    tan = 0
    # use a tangent of the roof pitch angle of 0.6 instead of the roof's height
    # height = 0.0
    # tan = 0.6


    spoly = SmartPoly()
    spoly.add(list(flist[0].verts))
    spoly.calculate()
    pts = [sv.co2 for sv in spoly.coord]

    if len(flist) > 1:
        first_poly = Polygon.Polygon(pts)
        Polygon.setTolerance(1e-4)
        for other in flist[1:]:
            opoly = SmartPoly()
            opoly.add(list(other.verts))
            opoly.calculate()
            offset = spoly.make_2d(opoly.center)
            other_pts = [sv.co2 + offset for sv in opoly.coord]

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
    else:
        first_poly = Polygon.Polygon(pts)
        first_poly.simplify()

    firstVertIndex = 0
    numVerts = 0
    verts = []
    holes = []
    n_contour = len(first_poly)
    for i in range(n_contour):
        c = first_poly.contour(i)
        if i==0:
            numVerts = len(c)
            lst = [Vector(p).to_3d() for p in c]
            if first_poly.orientation(i) == -1:
                lst.reverse()
            verts.extend(lst)
        else:
            lst = [Vector(p).to_3d() for p in c]
            if first_poly.orientation(i) == 1:
                lst.reverse()
            hole_info = (len(verts), len(lst))
            holes.append(hole_info)
            verts.extend(lst)

    unitVectors = None  # we have no unit vectors, let them compute by polygonize()

    faces = []

    # now extend 'faces' by faces of straight polygon
    faces = bpypolyskel.polygonize(verts, firstVertIndex, numVerts, holes, height, tan, faces, unitVectors)

    pt3d = [spoly.make_3d(v) for v in verts]
    dct_verts = {}
    for i, v in enumerate(pt3d):
        dct_verts[i] = mm.new_vert(v)
    for idx_list in faces:
        vlist = [dct_verts[i] for i in idx_list]
        new_face = mm.new_face(vlist)
        mm.set_face_attrs(new_face, {mm.key_tag: 'ROOF'})
        calc_face_uv(new_face, mm)

    topo.add('All', len(faces))
    mm.to_mesh()
    mm.free()

    return topo