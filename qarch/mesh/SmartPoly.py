import mathutils
from mathutils import Matrix, Vector
import bpy, bmesh
import functools
import operator
from .geom_2d import (bridge_points_by_circumfrence,
                      generate_arch, generate_inset, generate_ngon, generate_revolve, generate_super)

from .coordsys import CoordSys, SmartPoint, approx, approx_vector
import math

def polygon3_to_smart(coord_sys, poly3):
    """returns polygons, ignores holes

    :param CoordSys coord_sys: the coordinate system to apply
    :param shapely.Polygon poly3: the polygon to convert
    :return list(SmartPoly):
    """
    import shapely
    lst_out = []

    p = shapely.get_exterior_ring(poly3)
    if p is None:
        return []
    if len(p.coords)==0:
        return []
    s_pt = []
    for pt in p.coords:
        s_pt.append(Vector(pt))
    if (s_pt[0]-s_pt[-1]).length < 0.001:
        s_pt = s_pt[:-1]
    s_pt.reverse()  # shapely uses clockwise winding

    s_pts = [coord_sys.make_3d(v) for v in s_pt]

    m_poly = SmartPoly(coord_sys=coord_sys.copy(), pt_list=s_pts)
    m_poly.calc_coord_sys(coord_sys.ydir, b_no_roll=True)
    if m_poly.normal().dot(coord_sys.normal) < 0:
        m_poly.flip_normal()

    lst_out.append(m_poly)

    return lst_out


class SmartPoly:
    def __init__(self, coord_sys, pt_list=None, break_link=False, b_no_roll=False):
        """Polygon will be built in coord_sys, use pt_list if provided
        :param CoordSys coord_sys: orient and locate the polygon
        :param pt_list: source of points [optional]
        :type pt_list: SmartPoly, BMFace, list of BMVert, or list of Vector
        :param bool break_link: if true, do not save BMVert connection
        :param bool b_no_roll: if true, do not sort points
        :return: None """
        self.coord_sys = coord_sys
        self.points = []
        self.bbox_min = Vector((0, 0))
        self.bbox_max = Vector((0, 0))
        self.box_size = Vector((0, 0))

        self.face_attr = {'uv_origin': Vector((0, 0, 0))}
        if coord_sys.reference_face:
            self.face_attr['uv_origin'] = coord_sys.reference_face[coord_sys.mm.key_uv_orig]
            self.face_attr['material'] = coord_sys.reference_face.material_index
            self.face_attr['uv_mode'] = coord_sys.reference_face[coord_sys.mm.key_uv]
            self.face_attr['uv_rot'] = coord_sys.reference_face[coord_sys.mm.key_uv_rot]
            self.face_attr['material'] = coord_sys.reference_face.material_index
            self.face_attr['radial'] = coord_sys.reference_face[coord_sys.mm.key_radial]

        if pt_list:
            self.add(pt_list, break_link)
            self.calc_2d(b_no_roll)

    def add(self, ptlist, break_link=False):
        """Add points to polygon
        :param ptlist: list of points or a single point
        :type ptlist: BMFace or a list of Vector(2) or Vector(3) or BMVert or SmartPoint
        :param break_link: True if we don't want to keep the bm vert connections
        :type break_link: None or bool
        :return: None
        """
        if isinstance(ptlist, bmesh.types.BMFace):
            for v in ptlist.verts:
                self.add(v, break_link)
            return
        elif isinstance(ptlist, SmartPoly):
            for v in ptlist.points:
                self.add(v, break_link)
            return
        elif isinstance(ptlist, list):
            for v in ptlist:
                self.add(v, break_link)
            return

        if type(ptlist) in [bmesh.types.BMVert, Vector, SmartPoint, tuple]:
            sv = SmartPoint(ptlist, break_link)
            if sv.co3 is None:
                sv.co3 = self.coord_sys.make_3d(sv.co2)
        else:
            raise TypeError("Unexpected point type {}".format(type(ptlist)))

        self.points.append(sv)

    def apply_rotation_matrix(self, mat):
        """Apply matrix to points, updates coord_sys
        :param Matrix mat: rotation matrix(3x3)
        """
        for pt in self.points:
            v = pt.co3 - self.coord_sys.origin
            pt.co3 = (mat @ v) + self.coord_sys.origin
            pt.co2 = None
        # bring uv origin along
        v = self.face_attr['uv_origin'] - self.coord_sys.origin
        self.face_attr['uv_origin'] = (mat @ v) + self.coord_sys.origin

        # update coord_sys
        self.coord_sys.apply_rotation_matrix(mat)

        self.calc_2d(b_no_roll=True)  # fix 2d coordinates

    def bridge(self, other, insert_perimeter=False, v_extruding=None, b_close=True, b_allow_square=False, arch_type=None):
        lst1 = [p.co3 for p in self.points]
        lst2 = [p.co3 for p in other.points]

        if other.normal().dot(self.normal()) < 0:  # make winding go same way by flipping order
            lst2.reverse()
            b_reverse = True
            print("reverse")
        else:
            b_reverse = False

        if arch_type and len(lst1) != len(lst2):  # pick only nice points on arch to use
            arch_name, dropped = arch_type
            mid = len(self.points)//2
            reindex = []
            bl, br, tc = 0, 0, 0
            for i in range(1, len(self.points)):
                if (self.points[i].co2.x < self.points[bl].co2.x) and (self.points[i].co2.y <= self.points[bl].co2.y):
                    bl = i
                if (self.points[i].co2.x > self.points[br].co2.x) and (self.points[i].co2.y <= self.points[br].co2.y):
                    br = i
                if (self.points[i].co2.y > self.points[tc].co2.y):
                    tc = i

            reindex = [bl, br, tc]
            print("arch reindex", reindex)
            tmp = [lst1[i] for i in reindex]
            lst_links = bridge_points_by_circumfrence(tmp, lst2, self.coord_sys)
            for lnk in lst_links:
                lnk[0] = reindex[lnk[0]]
        else:
            lst_links = bridge_points_by_circumfrence(lst1, lst2, self.coord_sys)

        if b_reverse:  # fix indexing
            ll2 = len(lst2)
            for lnk in lst_links:
                lnk[1] = ll2 - lnk[1] - 1

        # by circumfrence is pretty robust, although concave polygons can always cause self intersection,
        # but sometimes we want to project lines to make new points on other so the line angles are pretty
        # b_extruding could be used to permit crossing lines if we tried to remove them
        if insert_perimeter:
            for i_link, link in enumerate(lst_links):
                i = link[0]
                j = link[1]

                a = self.points[i-1]
                b = self.points[i]
                c = self.points[(i+1) % len(self.points)]
                out_ray = self.outward_ray(a, b, c, b_allow_square=b_allow_square)
                pt, e = other.ray_intersection(b.co3, out_ray, True)  # check outward ray only
                if pt is None:
                    continue

                if approx_vector(pt, other.points[j].co3):  # already best spot
                    continue

                # check that we don't jump indices on other (cross rays)
                prev = lst_links[i_link-1][1]
                nxt = lst_links[(i_link+1) % len(lst_links)][1]
                # if b_reverse:  # swap edge order
                #     prev, nxt = nxt, prev
                # if nxt == 0:
                #     nxt = len(other.points)-1
                # if prev == len(other.points)-1:
                #     prev = 0
                # print(prev, e[0], e[1], nxt, "check crossing")
                # if (e[0] >= prev) and (e[1] <= nxt):

                if True:
                    if e[0] > e[1]:  # wrap around
                        e = e[0], len(other.points)  # splice at end
                    other.splice(e[1], pt)
                    for lnk in lst_links:  # fix numbering
                        if lnk[1] >= e[1]:
                            lnk[1] += 1
                    link[1] = e[1]

        # make bridge share points
        lst_poly = []
        ctr = self.calc_center_median()
        self.make_verts()
        other.make_verts()
        n = len(lst_links)
        for i_link, link in enumerate(lst_links):
            if (not b_close) and (i_link == len(lst_links)):  # don't wrap
                break

            link_next = lst_links[(i_link + 1) % n]
            if b_reverse:
                if link_next[1] <= link[1]:  # expected case
                    pts_out = list(range(link_next[1], link[1]+1))
                else:  # wrap around
                    pts_out = list(range(link_next[1], len(other.points))) + list(range(link[1]+1))
            else:
                if link_next[1] >= link[1]:  # expected case
                    pts_out = list(range(link[1], link_next[1]+1))
                else:  # wrap around
                    pts_out = list(range(link[1], len(other.points))) + list(range(link_next[1]+1))
            pts_out = [other.points[k] for k in pts_out]
            if b_reverse:
                pts_out.reverse()

            if link_next[0] >= link[0]:
                pts_in = list(range(link[0], link_next[0] + 1))
            else:
                pts_in = list(range(link[0], len(self.points))) + list(range(link_next[0] + 1))
            pts_in.reverse()
            pts_in = [self.points[k] for k in pts_in]

            points = pts_out + pts_in
            poly = SmartPoly(coord_sys=self.coord_sys, pt_list=points, break_link=False)
            poly.calc_coord_sys()

            if approx(1, abs(poly.normal().z)):  # on flat, point towards center
                v_edge = pts_out[-1] - pts_out[0]
                if v_edge.length:
                    v_radial = poly.normal().cross(v_edge.normalized()).normalized()
                    poly.face_attr['radial'] = v_radial
                    poly.calc_coord_sys(radial=v_radial)
            elif v_extruding:  # y in extrude direction
                poly.face_attr['radial'] = v_extruding.normalized()
                poly.calc_coord_sys(radial=poly.face_attr['radial'])
            # else use control coord sys

            lst_poly.append(poly)

        return lst_poly

    def bridge_by_number(self, other, idx_offset=0, b_reversed=False, v_extruding=None):
        """Simple bridging for when we know the polys match (extrude, for instance)
        :param SmartPoly other: target to bridge to
        :param int idx_offset: used to handle twisting
        :param bool b_reversed: True if the other order is reversed (flipped normal)"""
        from .coordsys import ppstr
        ncp = len(self.points)
        assert ncp == len(other.points)
        new_faces = []
        radial = self.calc_center_box() - other.calc_center_box()
        for i in range(ncp):
            ii = (i+1) % ncp
            if b_reversed:
                j = ncp - i -1
                jj = (2*ncp - i - 2) % ncp
                vlist = [self.points[ii], self.points[i], other.points[(j + idx_offset) % ncp], other.points[(jj+idx_offset) % ncp]]
            else:
                vlist = [self.points[ii], self.points[i], other.points[(i+idx_offset) % ncp], other.points[(ii+idx_offset) % ncp]]

            p_new = SmartPoly(self.coord_sys, pt_list=vlist, break_link=False)
            p_new.calc_coord_sys(radial)
            if v_extruding:  # y in extrude direction
                p_new.face_attr['radial'] = v_extruding.normalized()
                p_new.calc_coord_sys(radial=p_new.face_attr['radial'])
            elif approx(1, abs(p_new.normal().z)):  # on flat, point towards center
                v_edge = vlist[-1].co3 - vlist[-2].co3
                if v_edge.length:
                    v_radial = p_new.normal().cross(v_edge.normalized()).normalized()
                    p_new.face_attr['radial'] = v_radial
                    p_new.calc_coord_sys(radial=v_radial)
            else:  # y in extrude direction
                p_new.face_attr['radial'] = radial.normalized()
                p_new.calc_coord_sys(radial=p_new.face_attr['radial'])
            # else use control coord sys

            p_new.face_attr['uv_origin'] = Vector(self.calc_center_box())  # for xy, doesn't really matter, but allows polar frame if desired
            new_faces.append(p_new)
        return new_faces

    def calc_2d(self, b_no_roll=False):
        """Convert 3d positions to 2d"""
        for pt in self.points:
            assert pt.co3, "Can't calc 2d because 3d is invalid"
            pt.co2 = self.coord_sys.make_2d(pt.co3)

        xx = [pt.co2.x for pt in self.points]
        yy = [pt.co2.y for pt in self.points]
        self.bbox_min = Vector((min(xx), min(yy)))
        self.bbox_max = Vector((max(xx), max(yy)))
        self.box_size = self.bbox_max - self.bbox_min
        if not b_no_roll:
            self.roll_point_start()

        return self.box_size

    def calc_center_box(self):
        """return center of bounding box, in 3d"""
        ctr = self.bbox_min + self.box_size/2
        return self.coord_sys.make_3d(ctr)

    def calc_center_median(self):
        """Median point, in 3d"""
        n = len(self.points)
        lst = [pt.co3 for pt in self.points]
        ctr = functools.reduce(operator.add, lst) / n
        return ctr

    def calc_coord_sys(self, radial=None, b_no_roll=False):
        """Used when adding free points with no face reference: calculate a plane matrix
        :param radial: if known, the inward direction for y
        :type radial: None or Vector(3)
        :return CoordSys: coordinate system
        """
        normal = self.coord_sys.normal
        # try to find a normal based on points
        v0 = self.points[0].co3
        for i in range(1, len(self.points)):
            v1 = (self.points[i].co3 - v0)
            if v1.length > 0:
                v1.normalize()
                for j in range(i+1, len(self.points)):
                    v2 = (self.points[j].co3 - v0)
                    if v2.length > 0:
                        v2.normalize()
                        if approx(1, abs(v1.dot(v2))):
                            continue
                        else:
                            normal = v1.cross(v2).normalized()
                            break
                break

        origin = self.calc_center_median()
        self.coord_sys = CoordSys(self.coord_sys.mm, None, radial=radial, normal=normal, origin=origin)
        self.calc_2d(b_no_roll)

        return self.coord_sys

    def clip_with(self, other, join_type):
        """Return 0 or more pieces of this polygon after clipping with other"""
        import shapely
        prec = 1/10000.0
        #roundit = lambda v: (int(v[0] * prec), int(v[1] * prec))
        #unround = lambda v: Vector((v[0] / prec, v[1] / prec))

        if len(self.points) < 3:
            return []
        if len(other.points) < 3:
            return [self]

        self_pts = [c.co2 for c in self.points]
        other_pts = [self.coord_sys.make_2d(c.co3) for c in other.points]
        self_poly = shapely.Polygon(self_pts)
        other_poly = shapely.Polygon(other_pts)

        res_poly = self
        if join_type == 'OUTSIDE':
            res_poly = self_poly.difference(other_poly, grid_size=prec)
        elif join_type == 'INSIDE':
            res_poly = self_poly.intersection(other_poly, grid_size=prec)
        elif join_type == 'UNION':
            res_poly = self_poly.union(other_poly, grid_size=prec)
        elif join_type == 'DIFFERENCE':
            a = self_poly.difference(other_poly, grid_size=prec)
            lst = polygon3_to_smart(self.coord_sys, a)
            return lst
        elif join_type == 'PARTITION':
            a = self_poly.difference(other_poly, grid_size=prec)
            c = self_poly.intersection(other_poly, grid_size=prec)
            lst = polygon3_to_smart(self.coord_sys, a)
            lst = lst + polygon3_to_smart(self.coord_sys, c)
            return lst

        return polygon3_to_smart(self.coord_sys, res_poly)

    def debug_str(self):
        from .coordsys import ppstr
        s = "SmartPoly\n"
        s = s + str(self.coord_sys) + "\n"
        for p in self.points:
            s = s + "  " + str(p) + "\n"
        s = s + "box min {} size {}\n".format(ppstr(self.bbox_min), ppstr(self.box_size))
        return s

    def fit_box(self, min_corner3, size2):
        """Align bbox min to min_corner (in global space) and resize to fit size2 in 2d space
        :param Vector min_corner3: align bbox min here (in world space)
        :param size2: width and height
        :type size2: Vector(2) or tuple"""
        min_cur = self.coord_sys.make_3d(self.bbox_min)
        shift_3d = min_corner3 - min_cur

        # avoid division errors
        if self.box_size.x == 0:
            self.box_size.x = 1
        if self.box_size.y == 0:
            self.box_size.y = 1

        sx = size2[0] / self.box_size.x
        sy = size2[1] / self.box_size.y

        for pt in self.points:
            pt.co2 = self.scale_2d(pt.co2, (sx,sy))
            pt.co3 = self.coord_sys.make_3d(pt)
            pt.co3 += shift_3d  # shift to new box corner
            pt.co2 = None  # invalid now

        # bring uv origin along; if it was out of plane, we lose that knowledge
        o2 = self.face_attr['uv_origin'].to_2d()
        o2 = self.scale_2d(o2, (sx,sy))
        o3 = self.coord_sys.make_3d(o2) + shift_3d
        self.face_attr['uv_origin'] = o3

        self.calc_2d()  # updates bbox and size as well as co2 values

    def flip_normal(self):
        """Reverse winding and normal"""
        self.points.reverse()
        self.coord_sys.flip_normal()
        self.calc_2d()

    def generate_arch(self, w, h, brick_size, arch_type, thickness, drop_sides=0):
        """Return list of SmartPoly, with last being center of arch
        :param float w: width of bounding box
        :param float h: height of bounding box
        :param int brick_size: size of steps
        :param str arch_type: name of arch method [JACK, ROMAN, GOTHIC, OVAL, TUDOR]
        :param float thickness: width of arch frame, or 0 for no frame
        :param bool bridge_result: add bridging polygons to self
        :returns lst_poly, boundary_points: list of smart poly with center last, list of boundary points for bridging
        """
        from ..mesh.coordsys import ppstr
        kpoly = None
        lst_pts1, lst_pts2, lst_ctr, lst_pts3 = generate_arch(w, h, brick_size, arch_type, thickness, drop_sides)
        if thickness:
            lst_facepoints, newverts = self.zip_quads(lst_pts1, lst_pts2, False)
            lst_poly = [SmartPoly(self.coord_sys, pt_list=ptlist, break_link=False) for ptlist in lst_facepoints]

            for p, ctr in zip(lst_poly, lst_ctr):
                if ctr is None:
                    continue
                c = p.calc_center_box()
                ctr = self.coord_sys.make_3d(ctr)
                r = ctr - c
                p.face_attr['radial'] = r
                p.face_attr['uv_origin'] = ctr
                p.face_attr['uv_mode'] = 'FACE_POLAR'
                p.calc_coord_sys(radial=r)

            boundary_pts = [lst_pts2[0]] + lst_pts1 + [lst_pts2[-1]]

            pre_0 = None
            post_0 = None
            peak = 0
            for j, pt in enumerate(lst_pts2):  # find center
                if abs(pt.x) < 0.001:
                    if lst_pts1[j].y > peak:
                        peak = lst_pts1[j].y
                elif pt.x > 0:
                    pre_0 = j
                elif pt.x < 0:
                    post_0 = j
                    break
            if arch_type in ['GOTHIC', 'TUDOR', 'ARABIC', 'TRIANGLE']:  # diamond keystone
                keypts = [lst_pts2[pre_0 + 1], lst_pts1[pre_0+1], Vector((0,peak)), lst_pts1[post_0-1]]
                if abs(keypts[1].x) < 0.001:  # special case pentagon
                    keypts = [lst_pts2[pre_0], lst_pts1[pre_0], Vector((0,peak)), lst_pts1[post_0], lst_pts2[post_0]]
                # remove degenerate spike from center poly, pre_0+1 in range stops at pre_0, but we want center point
                lst_pts1 = lst_pts1[:pre_0 + 2] + lst_pts1[post_0:]
                lst_pts2 = lst_pts2[:pre_0 + 2] + lst_pts2[post_0:]
                kpoly = SmartPoly(self.coord_sys, pt_list=keypts, break_link=False)
            else:
                if (lst_pts1[pre_0] - lst_pts1[post_0]).length < brick_size:
                    pre_0 -= 1
                    post_0 += 1
                keypts = [lst_pts2[pre_0], lst_pts1[pre_0], lst_pts1[post_0], lst_pts2[post_0]]
                kpoly = SmartPoly(self.coord_sys, pt_list=keypts, break_link=False)
                kpoly.face_attr['radial'] = kpoly.coord_sys.ydir
                kpoly.face_attr['uv_origin'] = kpoly.coord_sys.make_3d(Vector((0,0)))
                kpoly.face_attr['uv_mode'] = 'FACE_POLAR'
                kpoly.calc_coord_sys(radial=kpoly.face_attr['radial'])

            if len(lst_pts3):
                n = len(lst_pts3) // 4
                for i in range(n):
                    ptlist = lst_pts3[i * 4: (i + 1) * 4]
                    if i == 1:  # center or center + drop
                        if ptlist[1].y != ptlist[0].y:
                            if arch_type in ['SQUARE']:  # full lst_pts2 extends beyond drop center
                                pt_add = [v for v in lst_pts2 if ptlist[0].x < v.x < ptlist[2].x]
                                ptlist = ptlist + pt_add
                            else: # only add bottom points
                                ptlist = ptlist[1:3] + lst_pts2

                        else:
                            ptlist = lst_pts2

                    poly = SmartPoly(self.coord_sys, pt_list=ptlist, break_link=True)
                    lst_poly.append(poly)

                if n == 3:
                    boundary_pts = lst_pts1 + [lst_pts3[0], lst_pts3[1], lst_pts3[-2], lst_pts3[-1]]
                else:
                    boundary_pts = lst_pts1 + lst_pts3[1:3]
                # poly = SmartPoly(self.coord_sys, pt_list=lst_pts3)  # the space below the jack arch
            else:
                poly = SmartPoly(self.coord_sys, pt_list=lst_pts2)  # the inside
                lst_poly.append(poly)
                print("generate arch shouldn't get here")

        else:
            ptlist = lst_pts1
            if len(lst_pts3):  # add drop if present
                if lst_pts3[1].y != ptlist[-1].y:
                    ptlist = lst_pts1 + lst_pts3

            poly = SmartPoly(self.coord_sys, pt_list=ptlist)
            lst_poly = [poly]

            boundary_pts = ptlist

        return lst_poly, boundary_pts, kpoly

    def generate_inset(self, thickness):
        """Create an inset of self at distance thickness
        :param float thickness: distance to inset
        :return SmartPoly: inset polygon"""
        lst_pts = generate_inset(self.points, self.coord_sys.normal, thickness)
        poly = SmartPoly(self.coord_sys, pt_list=lst_pts)
        poly.make_verts()
        return poly

    def generate_ngon(self, n_sides, start_angle, total_angle=2*math.pi):
        """Create a regular polygon
        :param int n_sides: number of sides on shape
        :param float start_angle: clocking to first point
        :param float total_angle: 2 pi for full circle
        :return SmartPoly: n-gon"""
        lst_pts = generate_ngon(n_sides, start_angle, total_angle)
        poly = SmartPoly(self.coord_sys, pt_list=lst_pts)
        poly.make_verts()
        return poly

    def generate_revolve(self, r_origin, r_axis, n_steps, vz):
        """Revolve this polygon around an axis
        :param Vector r_origin: world point to rotate around
        :param Vector r_axis: rotation axis
        :param int n_steps: number of steps around
        :param float vz: shift polygon away from axis by this much
        :return list(poly): first and last polys are the end caps, the rest are in column major order
        """

        bottom_pt = self.coord_sys.make_3d(self.bbox_min)
        lst_pts = generate_revolve(bottom_pt, self.points, r_origin, r_axis, n_steps, vz)

        # replace points with BMVerts for sharing
        lst_start = []
        lst_end = []
        for lst in lst_pts:
            for i in range(len(lst)):
                lst[i] = self.coord_sys.mm.new_vert(lst[i])
            lst_start.append(lst[0])
            lst_end.append(lst[-1])

        lst_poly = []
        poly = SmartPoly(self.coord_sys, pt_list=lst_start, break_link=False)
        poly.flip_normal()
        lst_poly.append(poly)

        ncp = len(lst_pts[0])
        for i in range(n_steps):
            ii = (i + 1) % n_steps
            for j in range(ncp):
                jj = (j + 1) % ncp
                pts = [lst_pts[i][j], lst_pts[ii][j], lst_pts[ii][jj], lst_pts[i][jj]]
                poly = SmartPoly(self.coord_sys, pt_list=pts, break_link=False)
                poly.calc_coord_sys(r_axis)  # use r_axis as "in"
                lst_poly.append(poly)

        poly = SmartPoly(self.coord_sys, pt_list=lst_end, break_link=False)
        lst_poly.append(poly)

        return lst_poly

    def generate_super(self, x, sx, px, y, sy, py, n, resolution, start_angle):
        """Create super-ellipse points
        :param float x: x frequency factor
        :param float sx: x scale factor
        :param float px: x power factor
        :param float y: y frequency factor
        :param float sy: y scale factor
        :param float py: y power factor
        :param float n: power normalizer
        :param int resolution: number of points to generate
        :param float start_angle: rotational offset
        :return SmartPoly: result polygon
        """
        lst_pts = generate_super(x, sx, px, y, sy, py, n, resolution, start_angle)
        poly = SmartPoly(self.coord_sys, pt_list=lst_pts)
        poly.make_verts()
        return poly

    def grid_divide(self, count_x, count_y, offset_x=0, offset_y=0, size_x=0, size_y=0):
        import shapely
        if count_x == 0 and count_y == 0:
            return [SmartPoly(self.coord_sys, pt_list=self.points, break_link=True)]
        lst_poly = []
        dx = self.box_size.x / (count_x + 1)
        if size_x:
            dx = size_x
        dy = self.box_size.y / (count_y + 1)
        if size_y:
            dy = size_y

        master = shapely.Polygon([c.co2 for c in self.points])
        x0 = self.bbox_min.x
        if offset_x:
            x1 = x0 + offset_x
        else:
            x1 = x0 + dx
        for i in range(count_x + 1):
            if i==count_x:
                x1 = self.bbox_min.x + self.box_size.x
            y0 = self.bbox_min.y
            if offset_y:
                y1 = y0 + offset_y
            else:
                y1 = y0 + dy
            for j in range(count_y + 1):
                if j == count_y:
                    y1 = self.bbox_min.y + self.box_size.y
                cutter = shapely.box(x0, y0, x1, y1)
                # cutter = shapely.Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
                res_poly = master.intersection(cutter, grid_size=1e-4)
                if res_poly:
                    lst = polygon3_to_smart(self.coord_sys, res_poly)
                    lst_poly += lst
                y0 = y1
                y1 = y1 + dy
            x0 = x1
            x1 = x1 + dx

        if len(lst_poly) == 0:  # fallback for things shapely doesn't like
            if count_x == 1 and count_y == 0:
                pt = self.bbox_min + Vector((self.box_size.x/2, 0))
                return self.split_xy(pt, False)
            elif count_y == 1 and count_x == 0:
                pt = self.bbox_min + Vector((0, self.box_size.y / 2))
                return self.split_xy(pt, True)

        return lst_poly

    def make_face(self):
        """calculate attributes and make face"""
        from .geom import calc_face_uv, radial_to_euler, random_origin
        from ..object import material_best_mode

        ref = self.coord_sys.reference_face
        mm = self.coord_sys.mm
        if ref:
            attrs = mm.get_face_attrs(ref)
            del attrs[mm.key_tag]
        else:
            attrs = {}

        if 'material' in self.face_attr:
            mat_idx = self.face_attr['material']
        elif ref:
            mat_idx = ref.material_index
        else:
            mat_idx = 0
        best_mode = material_best_mode(mm.obj.data.materials[mat_idx].name)
        attrs[mm.key_uv] = best_mode
        if 'uv_mode' in self.face_attr:
            attrs[mm.key_uv] = self.face_attr['uv_mode']

        if ref:
            pointing = self.face_attr.get('radial', ref[mm.key_radial])
        else:
            pointing = self.face_attr.get('radial', self.coord_sys.ydir)
        attrs[mm.key_radial] = pointing
        self.calc_coord_sys(pointing, b_no_roll=True)

        if attrs[mm.key_uv] in ['ORIENTED', 'ORIENTED_SPIN', 'FACE_BBOX', 'FACE_POLAR']:
            if 'uv_rot' in self.face_attr:
                attrs[mm.key_uv_rot] = self.face_attr['uv_rot']
            else:
                vrot = radial_to_euler(pointing, self.coord_sys.normal)
                attrs[mm.key_uv_rot] = vrot
            if 'uv_origin' in self.face_attr:
                attrs[mm.key_uv_orig] = self.face_attr['uv_origin']
            else:
                attrs[mm.key_uv_orig] = self.coord_sys.make_3d(self.bbox_min)

        vlist = []
        for pt in self.points:
            if pt.bm_vert is not None:
                if pt.bm_vert not in vlist:
                    vlist.append(pt.bm_vert)
                else:
                    pass  # print("Dup vert {} skipped".format(pt))
            else:
                pt.bm_vert = self.coord_sys.mm.new_vert(pt.co3)
                vlist.append(pt.bm_vert)
        if len(vlist) > 2:
            face = self.coord_sys.mm.new_face(vlist)
            if 'material' in self.face_attr:
                face.material_index = self.face_attr['material']
            elif ref:
                face.material_index = ref.material_index

            mm.set_face_attrs(face, attrs)
            calc_face_uv(face, mm)  # these depend on the things we just set
            return face
        else:
            print("< 3 verts")
        return None

    def make_verts(self):
        """Create BMVerts for points that don't have them"""
        for pt in self.points:
            if (pt.bm_vert is not None) and pt.bm_vert.is_valid:
                pass
            else:
                pt.bm_vert = self.coord_sys.mm.new_vert(pt.co3)

    def normal(self):
        """Shorthand to get coordsys normal"""
        return self.coord_sys.normal

    def outward_ray(self, sv1, sv2, sv3, b_allow_square=False):
        """Given 3 points, find the outward ray from the corner
        :param SmartPoint sv1: previous vertex
        :param SmartPoint sv2: ray shooting vertex
        :param SmartPoint sv3: next vertex
        :param bool b_allow_square: if true, rectangle rays are perpendicular instead of 45 degrees
        :return Vector: direction of ray
        """
        # work in 3d for the cross product testing
        v1 = (sv2.co3 - sv1.co3).normalized()
        v2 = (sv3.co3 - sv2.co3).normalized()
        vz = v1.cross(v2)
        if vz.length <= 0.001:  # straight line
            v_out = -self.normal().cross(v1.normalized())
        elif vz.dot(self.normal()) < 0:  # concave
            v_out = v2.normalized() - v1.normalized()
        else:
            v_out = v1.normalized() - v2.normalized()
        v_out.normalize()

        if b_allow_square:
            # special corner case to make squares inside nicer
            hor1 = approx(abs(v1.dot(self.coord_sys.xdir)), 1)
            hor2 = approx(abs(v2.dot(self.coord_sys.xdir)), 1)
            ver1 = approx(abs(v1.dot(self.coord_sys.ydir)), 1)
            ver2 = approx(abs(v2.dot(self.coord_sys.ydir)), 1)

            if (hor1 and ver2) or (ver1 and hor2):
                if v_out.dot(self.coord_sys.ydir) >= 0:
                    v_out = self.coord_sys.ydir
                else:
                    v_out = -self.coord_sys.ydir

        return v_out

    def outward_ray_idx(self, idx):
        """Get outward start and ray from index number
        :param int idx: the point to launch the ray from
        :return Vector, Vector: the point and direction for the ray"""
        n = len(self.points)
        sv1 = self.points[(idx + n - 1) % n]
        sv2 = self.points[idx]
        sv3 = self.points[(idx + 1) % n]
        ray_out = self.outward_ray(sv1, sv2, sv3)
        return sv2.co3, ray_out

    def project_to(self, v):
        """Change normal and project shape
        :param Vector v: the new normal directions
        """
        norm = v.normalized()
        for c in self.points:
            dp = norm.dot((c.co3 - self.coord_sys.origin))
            c.co3 = c.co3 - dp * norm

    def ray_intersection(self, start, direction, b_out_only):
        """Test for ray intersection, return closest point and edge indices
        :param Vector start: ray start
        :param Vector direction: ray direction
        :param bool b_out_only: only check outward direction
        :return Vector, list(int): the point and edge indices, or None, []
        """
        direction = direction.normalized()
        a = start
        b = a + direction

        n = len(self.points)
        lst_hit = []
        for idx in range(n):
            e0 = self.points[idx].co3
            e1 = self.points[(idx + 1) % n].co3

            res = mathutils.geometry.intersect_line_line(a, b, e0, e1)
            if res is not None:
                sep = (res[0] - res[1]).length
                if approx(sep, 0):
                    v0 = res[0]
                    # on segment?
                    ve = e1-e0
                    elen = ve.length
                    ve = ve.normalized()
                    vi = v0-e0
                    ilen = vi.dot(ve)
                    if ilen > elen:
                        continue
                    if ilen < 0:
                        continue

                    v1 = v0-a
                    d0 = v1.dot(direction)

                    if approx(d0, 0): # cant' get any closer
                        return v0, (idx, idx+1)

                    if (d0 < 0) and b_out_only:
                        continue

                    lst_hit.append([d0, v0, (idx, (idx+1) % n)])

        if len(lst_hit):
            lst_hit.sort(key=lambda t: t[0])
            return lst_hit[0][1], lst_hit[0][2]

        return None, []

    def remove_duplicates(self, b_inline=False):
        """Remove duplicate coordinates
        :param b_inline: if True, remove straight line points that aren't needed
        :type b_inline: None or bool
        :return int: Length of remaining points
        """
        clean = [self.points[0]]
        for pt in self.points[1:]:
            if clean[-1] == pt:
                pass
            else:
                clean.append(pt)

        if b_inline and len(clean) > 3:
            clean_2 = [clean[0]]
            for i in range(1, len(clean)-1):
                v1 = clean[i] - clean[i-1]
                v2 = clean[i+1] - clean[i]
                if approx(1, v1.dot(v2)):
                    pass
                else:
                    clean_2.append(clean[i])
            clean_2.append(clean[-1])  # technically, this could be in a line and not needed
            clean = clean_2

        self.points = clean
        return len(self.points)

    def roll_point_start(self):
        """Make sure first point is closest to bbox min"""
        first_idx = self.coord_sys.first_corner_index([p.co3 for p in self.points])
        self.points = self.points[first_idx:] + self.points[:first_idx]

    def rotate_2d(self, angle, ctr3):
        """2d rotation of points and coordinate system
        :param float angle: angle to ratate around normal
        :param Vector ctr3: point in 3d to rotate around
        """
        mat = Matrix.Rotation(angle, 3, self.coord_sys.normal)
        self.shift_3d(-ctr3)
        self.apply_rotation_matrix(mat)
        self.shift_3d(ctr3)

    def scale_2d(self, v2, scale_xy):
        """Scales relative to bbox min
        :param Vector v2: 2D point to scale
        :param scale_xy: tuple or Vector scale
        :returns Vector: result position"""
        v2 = v2 - self.bbox_min  # scale relative to corner
        v2.x *= scale_xy[0]
        v2.y *= scale_xy[1]
        return v2 + self.bbox_min

    def scale_around(self, ctr, sx, sy):
        """2D scaling in polygon coordinates
        :param Vector ctr: 3D center of scaling
        :param float sx: scale x size
        :param float sy: scale y size"""
        for pt in self.points:
            v = pt - ctr
            vx = v.dot(self.coord_sys.xdir) * sx
            vy = v.dot(self.coord_sys.ydir) * sy
            vz = v.dot(self.coord_sys.normal)
            v = (vx * self.coord_sys.xdir +
                 vy * self.coord_sys.ydir +
                 vz * self.coord_sys.normal)
            pt.co3 = v + ctr
        v = self.face_attr['uv_origin']
        vx = v.dot(self.coord_sys.xdir) * sx
        vy = v.dot(self.coord_sys.ydir) * sy
        vz = v.dot(self.coord_sys.normal)
        v = (vx * self.coord_sys.xdir +
             vy * self.coord_sys.ydir +
             vz * self.coord_sys.normal)
        self.face_attr['uv_origin'] = v + ctr
        self.calc_2d(b_no_roll=True)

    def shift_3d(self, v):
        """Add offset to points and coordinate system
        :param Vector v: the amount to shift"""
        for pt in self.points:
            pt.co3 += v
            if pt.bm_vert:
                pt.bm_vert.co += v
        self.face_attr['uv_origin'] += v
        self.coord_sys.origin += v

    def splice(self, idx, pt):
        """Insert a point at idx
        :param int idx: point to insert in front of
        :param vector pt: new point"""

        sv = SmartPoint(pt)
        if sv.co3 is None:
            sv.co3 = self.coord_sys.make_3d(sv.co2)
        else:
            sv.co2 = self.coord_sys.make_2d(sv.co3)
        self.points.insert(idx, sv)

    def split_points(self, i, j):
        """Split poly on the line joining i and j
        :param int i: index of first point
        :param int j: index of second point
        :return list(SmartPoly): list of polygons generated"""
        if abs(i-j) < 2:
            return []
        if i > j:
            j, i = i, j
        if (i == 0) and (j == len(self.points)-1):
            return []

        new_poly = []
        n = len(self.points)

        vlist1 = [self.points[k % n] for k in range(i, j + 1)]
        if len(vlist1):
            poly = SmartPoly(self.coord_sys, pt_list=vlist1)
            new_poly.append(poly)

        vlist2 = [self.points[k % n] for k in range(j, i+n + 1)]
        if len(vlist2):
            poly2 = SmartPoly(self.coord_sys, pt_list=vlist2)
            new_poly.append(poly2)

        return new_poly

    def split_xy(self, pt, cut_x):
        """Split horizontal or vertical - doing both x and y at once was complicated, so do one at a time
        :param vector pt: anchor position for cut
        :param bool cut_x: False to use a y line
        :return list[Poly]: generated polygons
        """
        cut = []
        cut_y = not cut_x
        n = len(self.points)
        for i in range(n):
            a, b = self.points[i].co2, self.points[(i+1) % n].co2
            if cut_x:
                if (a.y < pt.y < b.y) or (b.y < pt.y < a.y):
                    dxdy = (b.x - a.x) / (b.y - a.y)
                    dy = pt.y - a.y
                    dx = dxdy * dy
                    pos = Vector((dx + a.x, dy + a.y))
                    dist = (a-pos).length  # distance sort needed if x and y, but we don't because made things hard
                    cut.append((i, dist, pos))
            if cut_y:
                if (a.x < pt.x < b.x) or (b.x < pt.x < a.x):
                    dydx = (b.y - a.y) / (b.x - a.x)
                    dx = pt.x - a.x
                    dy = dydx * dx
                    pos = Vector((dx + a.x, dy + a.y))
                    dist = (a - pos).length
                    cut.append((i, dist, pos))

        # sort by index and distance along edge
        cut.sort(key=lambda t: t[1])
        cut.sort(key=lambda t: t[0])

        # reverse because we don't want to change indices
        self.make_verts()
        new_coord = [sv for sv in self.points]
        cut.reverse()
        for i, dist, pos in cut:
            sv = SmartPoint(pos)
            sv.co3 = self.coord_sys.make_3d(pos)
            sv.bm_vert = self.coord_sys.mm.new_vert(sv.co3)
            new_coord.insert(i + 1, sv)

        # now link up the points
        indices = []
        n = len(new_coord)
        for i in range(len(new_coord)):
            if cut_x:
                if new_coord[i].co2.y == pt.y:
                    indices.append(i)
            if cut_y:
                if new_coord[i].co2.x == pt.x:
                    indices.append(i)

        if len(indices) < 2:
            return []

        # need last edge direction to prevent cut along edge
        b = new_coord[indices[0]]
        a = new_coord[(indices[0]+n-1) % n]
        e_last = (b.co2 - a.co2).normalized().to_3d()

        master_poly = SmartPoly(self.coord_sys, pt_list=new_coord, break_link=False)

        n = len(indices)
        new_poly = []
        remainder = None
        set_used = set()
        for i in range(n):
            idx = indices[i]
            next_idx = indices[(i+1) % n]

            b = new_coord[idx]
            a = new_coord[next_idx]
            e_next = (b.co2 - a.co2).normalized().to_3d()
            if next_idx-idx < 2:  # adjacent points, so on a horizontal edge
                pass
            elif (idx==0) and (next_idx==n-1):  # adjacent points
                pass
            else:
                if e_next.dot(e_last) < -0.999:  # don't double back over edge
                    pass
                elif (idx, next_idx) not in set_used:  # don't do reverse of existing cut
                    set_used.add((next_idx, idx))
                    lst_p = master_poly.split_points(idx, next_idx)
                    if len(lst_p) > 1:
                        if next_idx > idx:
                            new_poly.append(lst_p[0])  # we continue to split the remainder
                            remainder = lst_p[1]
                        else:
                            new_poly.append(lst_p[1])  # we continue to split the remainder
                            remainder = lst_p[0]
                    else:
                        remainder = lst_p[0]
            e_last = e_next

        if len(new_poly):
            if remainder:
                new_poly.append(remainder)
        return new_poly

    def union(self, lst_poly, b_coverage=False):
        """Create a merged polygon"""
        import shapely
        prec = 1/10000.0

        self_pts = [c.co2 for c in self.points]
        self_poly = shapely.Polygon(self_pts)

        if b_coverage:
            for other in lst_poly:
                other_pts = [self.coord_sys.make_2d(c.co3) for c in other.points]
                other_poly = shapely.Polygon(other_pts)
                self_poly = shapely.coverage_union(self_poly, other)
            res = self_poly
        else:
            lst_all = [self_poly]
            for other in lst_poly:
                other_pts = [self.coord_sys.make_2d(c.co3) for c in other.points]
                other_poly = shapely.Polygon(other_pts)
                other_poly = other_poly
                lst_all.append(other_poly)

            # for i in range(len(lst_all)):
            #     lst_all[i] = lst_all[i].buffer(0.1)
            # res = shapely.union_all(lst_all, grid_size=prec).buffer(-0.1)
            res = shapely.union_all(lst_all, grid_size=prec)


        s_pts = []
        for pt in res.exterior.coords:
            s_pts.append(pt)
        s_pts.reverse()

        verts = [self.coord_sys.make_3d(v) for v in s_pts]
        if (verts[0] - verts[-1]).length < 0.001:
            verts = verts[:-1]

        # test for bad verts that sometimes appear at seams
        n = len(verts)
        lst = []
        for j in range(n):
            k = (j+1) % n
            i = (j-1+n) % n
            e1 = verts[j] - verts[i]
            if approx(e1.length, 0):
                print("skip duplicate",i,j, e1.length)
                continue
            e2 = verts[k] - verts[j]
            if approx(e2.length, 0):
                print("skip duplicate", j, k, e2.length)
                continue
            e1.normalize()
            e2.normalize()
            if -0.99 < e1.dot(e2) < 0.99:
                lst.append(verts[j])
            else:
                print(j, "skip inline", verts[j])

        verts = lst

        u_poly = SmartPoly(self.coord_sys.copy(), pt_list=verts)
        u_poly.calc_coord_sys(self.coord_sys.ydir, b_no_roll=True)
        if u_poly.normal().dot(self.normal()) < 0:
            u_poly.flip_normal()

        return u_poly


    def update_3d(self):
        """Update 3d position from 2d"""
        for pt in self.points:
            pt.co3 = self.coord_sys.make_3d(pt)

    def update_bmvert(self):
        """Transfer 3d position to bm_verts"""
        for pt in self.points:
            if pt.bm_vert:
                pt.bm_vert.co = pt.co3

    def zip_quads(self, lst1, lst2, b_join_ends):
        """Make quads of BMVert from parallel points (2d), optionally join as a loop
        Makes the BMVerts so they can be shared

        :param list(Vector) lst1: outside ring in ccw order
        :param list(Vector) lst2: inside ring in ccw order
        :param bool b_join_ends: flag to connect first and last pairs or not
        returns list, list: [[face verts]] and [new verts]
        """
        rval = []
        if b_join_ends:
            n = len(lst1)
        else:
            n = len(lst1) - 1

        if len(lst1[0]) == 2:
            lst1 = [self.coord_sys.make_3d(v) for v in lst1]
            lst2 = [self.coord_sys.make_3d(v) for v in lst2]

        verts1 = [self.coord_sys.mm.new_vert(v) for v in lst1]
        verts2 = [self.coord_sys.mm.new_vert(v) for v in lst2]

        ncp = len(lst1)
        for i in range(n):
            j = (i + 1) % ncp
            lst = [verts1[i], verts1[j], verts2[j], verts2[i]]
            rval.append(lst)
        return rval, verts1 + verts2
