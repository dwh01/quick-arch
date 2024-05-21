"""Polygon class that allows work in a virtual 2D space"""
import bpy
import functools
import operator
import bmesh.types
import math
import mathutils
import mathutils.geometry
from mathutils import Vector, Matrix
import Polygon, Polygon.Shapes


def atan(v):
    if isinstance(v, SmartVec):
        return atan(v.co2)
    a = math.atan2(v.y, v.x)
    if a < 0:
        a = 2 * math.pi + a
    return a


def sort_winding(pts):
    """Order vectors by clockwise angle"""
    w = [(atan(p), p) for p in pts]
    w.sort(key=lambda t: t[0])
    pts = [t[1] for t in w]
    return pts


def merge_contour(pts_outer, pts_hole):
    p0 = sort_winding(pts_outer)
    p1 = sort_winding(pts_hole)
    p1.reverse()
    p = p0 + p1
    return p


def parallel(e1, e2):
    """are two edges parallel"""
    v1 = (e1[1]-e1[0]).normalized()
    v2 = (e2[1]-e2[0]).normalized()
    a = v1.to_3d().dot(v2.to_3d())
    if abs(a) > 0.99999:
        return True
    return False


def coincident(pt1, pt2):
    dv = (pt1-pt2).length
    if dv < 1e-6:
        return True
    return False


def parallel_overlap(e1, e2):
    v1 = (e1[1] - e1[0])
    l1 = v1.length()
    v1 = v1/l1
    v2 = (e2[0] - e1[0])
    along2 = v1.to_3d().dot(v2.to_3d())
    v3 = (e2[1] - e1[0])
    along3 = v1.to_3d().dot(v2.to_3d())

    if (along2 < 0 and along3 < 0) or (along2 > l1 and along3 > l1):
        return None

    if (along2 <= 0 and l1 <= along3) or (along3 <= 0 and l1 <= along2):
        return e1

    if (0 <= along2 <= l1) and (0 <= along3 <= l1):
        return e2

    if 0 <= along2 <= 1:
        if along3 < 0:
            return e1[0], e2[0]
        elif along3 > 1:
            return e1[1], e2[0]
    elif 0 <= along3 <= 1:
        if along2 < 0:
            return e1[0], e2[1]
        elif along2 > 1:
            return e1[1], e2[1]

    assert False


def cycle_winding(coord):
    """Start with rightmost coordinate"""
    center_sort = list(coord)
    lst_min = [0]
    w_min = center_sort[0].winding
    for i in range(1, len(center_sort)):
        if center_sort[i].winding == w_min:
            lst_min.append(i)
        elif center_sort[i].winding < w_min:
            w_min = center_sort[i].winding
            lst_min = [i]
    if len(lst_min) > 1:
        lst_min.sort(key=lambda i: center_sort[i].co2.x)
    i_min = lst_min[-1]
    center_sort = center_sort[i_min:] + center_sort[:i_min]
    return center_sort


class SmartVec:
    """Wrapper to track bmesh index and changed state"""
    def __init__(self, pt, vert=None):
        if len(pt)==3:
            self.co3 = Vector(pt)
            self.co2 = None
        else:
            self.co3 = None
            self.co2 = Vector(pt)
        self.winding = 0  # angle counter-clockwise
        self.bm_vert = vert
        self.changed = False

    def __str__(self):
        return "SV({:.2f},{:.2f}|{:.1f})".format(self.co2.x, self.co2.y, self.winding*180/math.pi)

    def __repr__(self):
        return "SV({:.2f},{:.2f}|{:.1f})".format(self.co2.x, self.co2.y, self.winding*180/math.pi)


class SmartPoly:
    def __init__(self, matrix=None, name="poly"):
        self.name = name
        self.coord = []
        self.edges = []

        self.center = Vector((0,0,0))
        self.matrix = Matrix.Identity(3)  # map 3d to 2d
        self.inverse = Matrix.Identity(3)  # map 2d to 3d

        self.xdir = Vector((1,0,0))
        self.ydir = Vector((0,1,0))
        self.normal = Vector((0, 0, 1))

        self.bbox = [Vector((0, 0)), Vector((0, 0))]
        self.box_size = Vector((0,0))
        self.is_oriented_rect = False
        self.area = 0

        # sometimes we want to add 2d points with a known matrix
        if matrix is not None:
            self.matrix = matrix
            self.xdir = Vector(matrix[0])
            self.ydir = Vector(matrix[1])
            self.normal = Vector(matrix[2])
            self.inverse = matrix.transposed()

    def add(self, pt, break_link=False):
        """Handles lots of things that could be points"""
        if isinstance(pt, bmesh.types.BMFace):
            for v in pt.verts:
                self.add(v, break_link)
            return
        elif isinstance(pt, SmartPoly):
            for v in pt.coord:
                self.add(v, break_link)
            return
        elif isinstance(pt, list):
            for v in pt:
                self.add(v, break_link)
            return

        if isinstance(pt, bmesh.types.BMVert):
            sv = SmartVec(pt.co)
            if not break_link:
                sv.bm_vert = pt
        elif isinstance(pt, Vector):
            sv = SmartVec(pt)
        elif isinstance(pt, tuple):
            sv = SmartVec(Vector(pt))
        elif isinstance(pt, SmartVec):
            if pt.co3 is not None:
                sv = SmartVec(pt.co3)
            else:
                sv = SmartVec(pt.co2)
            if not break_link:
                sv.bm_vert = pt.bm_vert
        else:
            raise TypeError("Unexpected point type {}".format(type(pt)))

        self.coord.append(sv)

    def apply_matrix(self, mat):
        for c in self.coord:
            c.co3 = mat @ c.co3
        self.center = mat @ self.center

    def bridge(self, other, mm, insert_perimeter=False):
        """Avoid twist that can happen with bmesh.ops.bridge_loops"""
        # project inner points onto outer edges
        # slide to closest end of the edge, that's the line to make
        # this algorithm fails if one poly is so concave that the point is on the wrong side of center (winding fail)
        v_offset = self.make_2d(other.center)
        b_center_out = other.pt_inside(-v_offset) is None
        other_coord_2d = [self.make_2d(c.co3) for c in other.coord]

        n = len(other.coord)
        connections = []
        alternate = []  # in case we wrap around a corner, can we advance a connection?
        last_con = None
        for p in self.coord:
            dx = math.cos(p.winding)
            dy = math.sin(p.winding)

            # line segment intersection will only work if we start from inside other
            if b_center_out:
                a = v_offset  # use other origin, just matching winding direction really, not closest point
            else:
                e = other.pt_inside(p.co2 - v_offset)
                if e is None:  # start from center of other
                    a = v_offset  # other origin
                else:
                    a = p.co2
            b = a + Vector((dx,dy))*(other.box_size.x+other.box_size.y)

            b_ok = False
            for i in range(n):
                c = other_coord_2d[i]
                d = other_coord_2d[(i+1) % n]
                pt_i = mathutils.geometry.intersect_line_line_2d(a, b, c, d)
                if pt_i is not None:
                    c_dist = (c - pt_i).length
                    d_dist = (d - pt_i).length
                    t_dist = (d-c).length
                    # if not close to existing point, and we allow it, insert a new point
                    if insert_perimeter and (c_dist > t_dist/10) and (d_dist > t_dist/10):
                        # work in other coords to ensure correct placement
                        f = c_dist / t_dist
                        pnew = other.coord[i].co3 * (1-f) + other.coord[(i+1) % n].co3 * f
                        sv = other.splice(i+1, pnew)
                        other_coord_2d.insert(i+1, self.make_2d(sv.co3))
                        n = n+1

                        b_make = other.coord[i].bm_vert is not None  # do we need to make a bm vert for consistency?
                        if b_make:
                            sv.bm_vert = mm.new_vert(sv.co3)
                        connections.append(i+1)
                        alternate.append(i+1)
                    else:
                        if c_dist < d_dist:
                            connections.append(i)
                            if c_dist > 0.001:
                                alternate.append(i+1)
                            else:
                                alternate.append(i)
                        else:
                            connections.append((i+1) % n)
                            if d_dist < 0.001:
                                alternate.append(i+1)
                            else:
                                alternate.append((i + 1) % n)
                    b_ok = True
                    break
            if not b_ok:
                if len(connections):
                    connections.append(connections[-1]+1)
                    alternate.append(connections[-1])
                else:
                    connections.append(0)
                    alternate.append(connections[-1])

        for i in range(1, len(connections)-1):
            if connections[i] == connections[i-1]:  # test alternate needed instead of making triangle
                t = connections[i+1]
                if t == 0:  # wrap around
                    t = n
                if t > connections[i] + 1:  # we skipped ahead on outside
                    connections[i] = alternate[i]  # so try to make a quad
            if connections[i] < connections[i-1]:
                if 0 < i < (len(connections)-1):
                    connections[i] = connections[i-1]  # don't go backwards
        if 0:
            print(self.coord)
            print(other.coord)
            print(other_coord_2d)
            print("conn",connections)
        lst_points = []
        nn = len(self.coord)
        for i in range(nn):
            i1 = (i+1) % nn
            pts = [self.coord[i1], self.coord[i]]

            k = connections[i]
            k1 = connections[i1]
            if k1 < k:  # wrap around
                k1 = k1 + n

            dbg = ["i",i1,i,"o"]
            for j in range(k, k1+1):
                pts.append(other.coord[j % n])
                dbg.append(j % n)
            lst_points.append(pts)
            # print(dbg)

        new_faces = []
        for vlist in lst_points:
            tmp = []
            for v in vlist:
                if v not in tmp:
                    tmp.append(v)
            vlist = tmp
            if len(vlist) < 3:
                continue
            p_new = SmartPoly()
            p_new.add(vlist)
            new_faces.append(p_new)
        return new_faces

    def calc_matrix(self):
        """Use points to make a coordinate system"""
        if len(self.coord) < 3:
            return

        if self.coord[0].co3 is not None:
            v1 = (self.coord[0].co3 - self.center).normalized()
            v2 = (self.coord[1].co3 - self.center).normalized()
            self.normal = v1.cross(v2)
            if self.normal.length == 0:
                # print("replace norm with +z")
                self.normal = Vector((0,0,1))
            else:
                self.normal.normalize()

            if self.normal[2] < -0.99:
                self.ydir = -self.ydir
            elif self.normal[2] < 0.99:
                self.xdir = Vector((0, 0, 1)).cross(self.normal).normalized()
                self.ydir = self.normal.cross(self.xdir).normalized()

            # matrix to rotate flat, transpose brings us back
            self.matrix[0] = self.xdir
            self.matrix[1] = self.ydir
            self.matrix[2] = self.normal
            self.inverse = self.matrix.transposed()

    def calc_center(self):
        """Assumes 3d coords calculated else polygon in canonical position
        if not, set the matrix in the constructor and call update_3d, but that sets center to 0,0 in 2d
        """
        n = len(self.coord)
        for c in self.coord:
            if c.co3 is None:  # special case convert to 3d points
                c.co3 = c.co2.to_3d()
        self.center = functools.reduce(operator.add, [c.co3 for c in self.coord]) / n

    def calc_2d(self):
        """Make 2d points"""
        # note - this may change 2d points that were used for initialization
        # because it will move the center to the origin
        for pt in self.coord:
            pt.co2 = self.make_2d(pt.co3)
            pt.winding = math.atan2(pt.co2.y, pt.co2.x)
            if pt.winding < 0:
                pt.winding = 2 * math.pi + pt.winding

    def calc_bbox(self):
        v_min = self.bbox[0]
        v_max = self.bbox[1]
        for pt in self.coord:
            for i in range(2): # x and y
                v_min[i] = min(v_min[i], pt.co2[i])
                v_max[i] = max(v_max[i], pt.co2[i])

        self.box_size = v_max - v_min

        if len(self.coord) == 4:
            all_passed = True
            for i in range(4):
                e = self.coord[(i+1) % 4].co2 - self.coord[i].co2
                if not((round(e.x, 6) == 0) or (round(e.y, 6) == 0)):
                    all_passed = False
                break
            self.is_oriented_rect = all_passed

    def calc_area(self):
        n = len(self.coord) - 1
        area = 0
        a = self.coord[0].co2
        for i in range(1, n):
            b = self.coord[i].co2
            c = self.coord[i+1].co2
            area = area + mathutils.geometry.area_tri(a, b, c)
        self.area = area

    def calculate(self):
        """Get everything ready once the points are added
        if you have a hole or badly convex poly, don't sort
        """
        self.calc_center()
        self.calc_matrix()
        self.calc_2d()
        self.calc_bbox()
        self.calc_area()

    def clip_with(self, other):
        """Return 0 or more pieces of this polygon after clipping with other"""
        # better to use a good library than try to do it ourselves
        # need Polygon3 from PyPy
        # from blender shell or script do
        # import sys, os, subprocess
        # python_exe = os.path.join(sys.prefix, 'bin', 'python3.10')
        # subprocess.call([python_exe, "-m", "pip", "install", "Polygon3"])
        if len(self.coord) < 3:
            return []
        if len(other.coord) < 3:
            return [self]

        v_offset = self.make_2d(other.center)
        self_pts = [c.co2 for c in self.coord]
        other_pts = [c.co2 + v_offset for c in other.coord]
        self_poly = Polygon.Polygon(self_pts)
        other_poly = Polygon.Polygon(other_pts)
        res_poly = self_poly - other_poly  # we could also do & to get intersection, or + for union, etc
        return self._polygon_to_smart(res_poly)

    def flip_z(self):
        self.normal = -self.normal
        self.ydir = self.normal.cross(self.xdir)
        self.matrix[0] = self.xdir
        self.matrix[1] = self.ydir
        self.matrix[2] = self.normal
        self.inverse = self.matrix.transposed()
        self.calc_2d()
        self.calc_bbox()

    def _polygon_to_smart(self, res_poly):
        """Deal with potential holes and disjoint polygons"""
        # and fix the center point location
        lst_poly = []
        lst_hole = []
        lst_ctr = []
        for i in range(len(res_poly)):
            contour = res_poly.contour(i)
            s_poly = Polygon.Polygon(contour)
            if res_poly.isHole(i):
                lst_hole.append(s_poly)
            else:
                lst_poly.append(s_poly)
                lst_ctr.append(s_poly.center())

        # to add holes, have to find best pair of points to connect
        # will assume only one hole per polygon
        lst_out = []
        for s_poly, ctr in zip(lst_poly, lst_ctr):
            b_merged = False
            for q_poly in lst_hole:
                if s_poly.covers(q_poly):
                    s_pts = [Vector(v) for v in s_poly.contour(0)]
                    if s_poly.orientation(0) == -1:
                        s_pts.reverse()
                    q_pts = [Vector(v) for v in q_poly.contour(0)]
                    if q_poly.orientation(0) == 1:
                        q_pts.reverse()
                    combined = s_pts + q_pts
                    m_poly = SmartPoly(self.matrix)
                    for v2 in combined:
                        m_poly.add(self.make_3d(v2))
                    m_poly.center = self.make_3d(Vector(ctr))
                    m_poly.calculate()
                    lst_out.append(m_poly)
                    b_merged = True
                    break
            if not b_merged:
                m_poly = SmartPoly(self.matrix)
                m_poly.center = self.make_3d(Vector(ctr))
                s_pts = [Vector(v) for v in s_poly.contour(0)]
                if s_poly.orientation(0) == -1:
                    s_pts.reverse()
                for v2 in s_pts:
                    m_poly.add(self.make_3d(v2))
                m_poly.calculate()
                lst_out.append(m_poly)

        return lst_out

    def debug_str(self):
        lines = [
            f"Poly {self.name}",
            "ctr={:.2f},{:.2f},{:.2f}".format(self.center.x, self.center.y, self.center.z),
            "X={:.2f},{:.2f},{:.2f}  Z={:.2f},{:.2f},{:.2f}".format(self.xdir.x, self.xdir.y, self.xdir.z, self.normal.x, self.normal.y, self.normal.z),
            "bbox={:.2f},{:.2f}-{:.2f},{:.2f}, size={:.2f},{:.2f}".format(self.bbox[0].x, self.bbox[0].y, self.bbox[1].x, self.bbox[1].y, self.box_size.x, self.box_size.y)
        ]
        for sv in self.coord:
            lines.append("  {:.2f},{:.2f}  @{:.1f}".format(sv.co2.x, sv.co2.y, sv.winding*180/math.pi))
        return "\n".join(lines)

    def generate_arch(self, w, h, n_sides, arch_type):
        """arch_type_list =
        ("JACK", "Jack", "Flat", 1),
        ("ROMAN", "Roman", "Round/Oval (1 pt)", 2),
        ("GOTHIC", "Gothic", "Gothic pointed (2 pt)", 3),
        ("OVAL", "Oval", "Victorian oval (3 pt)", 4),
        ("TUDOR", "Tudor", "Tudor pointed (4 pt)", 5),
        """
        # thanks to ThisIsCarpentry.com for classic geometric construction algorithms
        lst_pts = []
        if arch_type == 'JACK':
            # points are spaced in angle, not in distance
            theta_0 = math.atan2(h, w/2)
            theta_1 = math.pi - theta_0
            step = (theta_1 - theta_0) / n_sides

            for i in range(n_sides + 1):
                t = step * i + theta_0
                if t == math.pi/2:
                    x = 0
                else:
                    x = h / math.tan(t)
                lst_pts.append(Vector((x, h)))

        elif arch_type == 'ROMAN':
            r = w**2/(8*h) + h/2
            d = h-r
            if round(d,3) == 0:  # full circular arc
                theta = math.pi
            else:
                theta = 2 * math.atan2(w/2, -d)
            theta_0 = math.pi/2 - theta/2
            step = theta / n_sides
            for i in range(n_sides + 1):
                t = step * i + theta_0
                vx = 0 + r * math.cos(t)
                vy = d + r * math.sin(t)
                lst_pts.append(Vector((vx, vy)))

        elif arch_type == 'GOTHIC':
            a = w/4
            b = h/2
            c = a - b**2/a
            if c <= 0:  # normal gothic arch
                d = 0  # center on springline
                r_arc = w/2 - c
                theta_start = 0
            else:  # segmented pointed arch, center dropped
                c1 = c
                p1 = Vector((a,b))
                p2 = Vector((c,0))
                p3 = Vector((-a,0))
                p4 = Vector((-a,-1))
                p_i = mathutils.geometry.intersect_line_line(p1, p2, p3, p4)[0]
                c = p_i.x
                d = p_i.y
                p5 = Vector([0, h]).to_2d()
                r_arc = (p5 - p_i.to_2d()).length
                p6 = Vector([w/2, 0]) - p_i.to_2d()
                theta_start = math.atan2(p6.y, p6.x)

            theta = math.atan2(h-d, -c)  # angle from horizontal to peak
            if n_sides % 2 == 1:
                n_sides = n_sides + 1
            n_arc = n_sides // 2

            step = (theta-theta_start) / n_arc
            for i in range(n_arc + 1):
                t = step * i + theta_start
                vx = c + r_arc * math.cos(t)
                vy = d + r_arc * math.sin(t)
                lst_pts.append(Vector((vx, vy)))

            theta_1 = math.pi - theta  # for downward stroke
            for i in range(1, n_arc + 1):
                t = step * i + theta_1
                vx = -c + r_arc * math.cos(t)
                vy = d + r_arc * math.sin(t)
                lst_pts.append(Vector((vx, vy)))

        elif arch_type == 'OVAL':
            r_corner = 2 * (h / 3)
            c = w / 2 - r_corner
            alpha = math.atan2(h/3, c)
            a = math.sqrt((h/3)**2 + c**2)/2
            b = a/math.sin(alpha)
            d = b - h/3
            r_center = h + d
            theta = math.atan2(c, d)  # angle from center line

            f_center = 2 * theta / math.pi  # fraction taken up by center arc
            n_center = int(f_center * n_sides)
            if (n_sides - n_center) % 2 == 1:  # ensure even side count to divide between ends
                n_center = n_center - 1  # rounding center down because sides have sharper curvature
            n_corner = (n_sides - n_center) // 2
            if n_corner == 0:
                theta_0 = 0
                theta_1 = math.pi
                theta = math.pi/2
            else:
                # we sweep points up from horizontal, not from center
                theta_0 = math.pi / 2 - theta
                theta_1 = math.pi / 2 + theta
            print(n_corner, theta_0, theta_1, n_center, n_corner + n_corner + n_corner)
            if n_corner > 0:
                step = theta_0 / n_corner
                for i in range(n_corner + 1):
                    t = step * i
                    vx = c + r_corner * math.cos(t)
                    vy = 0 + r_corner * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))
            if n_center > 0:
                step = (2 * theta) / n_center
                if n_corner == 0:
                    c_start = 0
                else:
                    c_start = 1
                for i in range(c_start, n_center + 1):  # don't duplicate point at 0
                    t = step * i + theta_0
                    vx = 0 + r_center * math.cos(t)
                    vy = -d + r_center * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))
            if n_corner > 0:
                step = theta_0 / n_corner
                for i in range(1, n_corner + 1):
                    t = step * i + theta_1
                    vx = -c + r_corner * math.cos(t)
                    vy = 0 + r_corner * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))

        elif arch_type == 'TUDOR':
            r_corner = 2 * (h / 3)
            cc = w / 2 - r_corner
            # angle of ray 1, starting from top center, away from centerline
            alpha = math.atan2(h / 3, w / 2)

            p1 = Vector((-r_corner * math.sin(alpha), h-r_corner * math.cos(alpha)))
            p2 = (p1 + Vector((cc, 0))) / 2
            # angle of ray 3, start from midpoint between c and p1
            beta = math.atan2(p2.y, cc-p2.x)
            dir_beta = Vector((-math.sin(beta), -math.cos(beta)))

            a = Vector((0,h,0))
            b = p1.to_3d()
            c = p2.to_3d()
            d = (p2 + dir_beta).to_3d()
            res = mathutils.geometry.intersect_line_line(a, b, c, d)[0]
            v_peak = Vector((0, h, 0)) - res
            r_center = v_peak.length
            theta_peak = math.atan2(v_peak.y, v_peak.x)  # angle from springline
            v_corner = Vector((cc, 0, 0)) - res
            theta_corner = math.atan2(v_corner.y, v_corner.x)

            f_center = (math.pi - 2 * theta_corner) / math.pi  # fraction taken up by center arc
            n_center = int(f_center * n_sides)
            if (n_sides - n_center) % 2 == 1:  # ensure even side count to divide between ends
                n_center = n_center - 1  # rounding center down because sides have sharper curvature
            n_corner = (n_sides - n_center) // 2

            if n_center % 2 == 1:
                n_center = n_center + 1  # ensure two halves even if we have extra side
            n_center = n_center // 2
            print(theta_peak, theta_corner, n_center, n_corner, f_center)
            # we sweep points up from horizontal, not from center
            theta_0 = theta_corner
            theta_1 = math.pi - theta_corner

            if n_corner>0:
                step = theta_0 / n_corner
                for i in range(n_corner + 1):
                    t = step * i
                    vx = cc + r_corner * math.cos(t)
                    vy = 0 + r_corner * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))
            if n_center > 0:
                if n_corner == 0:
                    c_start = 0
                else:
                    c_start = 1
                step = (theta_peak - theta_0) / n_center
                for i in range(c_start, n_center + 1):  # don't duplicate point at 0
                    t = step * i + theta_0
                    vx = res.x + r_center * math.cos(t)
                    vy = res.y + r_center * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))
                for i in range(1, n_center + 1):  # don't duplicate point at 0
                    t = step * i + math.pi - theta_peak
                    vx = -res.x + r_center * math.cos(t)  # mirror image
                    vy = res.y + r_center * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))
            if n_corner > 0:
                step = theta_0 / n_corner
                for i in range(1, n_corner + 1):
                    t = step * i + theta_1
                    vx = -cc + r_corner * math.cos(t)  # mirror
                    vy = 0 + r_corner * math.sin(t)
                    lst_pts.append(Vector((vx, vy)))

        for pt in lst_pts:
            co = self.make_3d(pt)
            self.add(co, True)

        self.calculate()

    def generate_ngon(self, n_sides, start_angle):
        angle_delta = (2 * math.pi) / n_sides
        for i in range(n_sides):
            dx = math.cos(i * angle_delta + start_angle)
            dy = math.sin(i * angle_delta + start_angle)
            co = self.make_3d(Vector((dx, dy)))
            self.add(co, True)

        self.calculate()

    def grid_divide(self, count_x, count_y):
        lst_poly = []
        dx = self.box_size.x / (count_x + 1)
        dy = self.box_size.y / (count_y + 1)
        cutter = Polygon.Shapes.Rectangle(dx, dy)
        master = Polygon.Polygon([c.co2 for c in self.coord])
        for i in range(count_x + 1):
            x0 = self.bbox[0].x + i * dx
            x1 = x0 + dx
            for j in range(count_y + 1):
                y0 = self.bbox[0].y + j * dy
                y1 = y0 + dy
                cutter.warpToBox(x0, x1, y0, y1)
                res_poly = master & cutter
                lst = self._polygon_to_smart(res_poly)
                lst_poly += lst

        return lst_poly

    def make_2d(self, pt_3d):
        if isinstance(pt_3d, SmartVec):
            pt_3d = pt_3d.co3
        v = self.matrix @ (pt_3d - self.center)
        return v.to_2d()

    def make_3d(self, pt_2d):
        if isinstance(pt_2d, SmartVec):
            pt_2d = pt_2d.co2
        v3 = self.inverse @ pt_2d.to_3d() + self.center
        return v3

    def make_face(self, mm):
        vlist = []
        for pt in self.coord:
            if pt.bm_vert is not None:
                if pt.bm_vert not in vlist:
                    vlist.append(pt.bm_vert)
                else:
                    print("Dup vert {} in {}".format(pt, self.coord))
            else:
                pt.bm_vert = mm.new_vert(pt.co3)
                vlist.append(pt.bm_vert)
        if len(vlist) > 2:
            return mm.new_face(vlist)
        else:
            print("< 3 verts")
        return None

    def make_verts(self, mm):
        for pt in self.coord:
            if pt.bm_vert is not None:
                pass
            else:
                pt.bm_vert = mm.new_vert(pt.co3)

    def project_to(self, v):
        """Change normal and project shape"""
        norm = v.normalized()
        for c in self.coord:
            dp = norm.dot((c.co3 - self.center))
            c.co3 = c.co3 - dp * norm
        self.calculate()

    def pt_inside(self, v):
        pt_ang = math.atan2(v.y, v.x)
        n = len(self.coord)
        i_last = n-1
        a_last = self.coord[i_last].winding - 2 * math.pi
        for i in range(n):
            a_cur = self.coord[i].winding
            if a_last <= pt_ang < a_cur:
                tri_p1 = Vector((0,0,0))  # center
                tri_p2 = self.coord[i_last].co2
                tri_p3 = self.coord[i].co2
                if mathutils.geometry.intersect_point_tri_2d(v, tri_p1, tri_p2, tri_p3):
                    return i_last, i
                return None
            i_last = i
            a_last = a_cur
        return None

    def rotate(self, angle):
        """2d rotation"""
        mat = Matrix.Rotation(angle, 2)
        for c in self.coord:
            c.co2 = mat @ c.co2
        self.update_3d()
        self.calculate()

    def scale(self, sx, sy):
        for pt in self.coord:
            pt.co2.x *= sx
            pt.co2.y *= sy
        for pt in self.bbox:
            pt.x *= sx
            pt.y *= sy

    def shift_2d(self, v):
        # careful, doing pt += will replace pt reference instead of updating in place
        for pt in self.coord:
            pt.co2.x += v.x
            pt.co2.y += v.y
        for pt in self.bbox:
            pt.x += v.x
            pt.y += v.y

    def shift_3d(self, v):
        for pt in self.coord:
            pt.co3 += v
        self.center += v

    def splice(self, idx, pt):
        sv = SmartVec(pt)
        if sv.co3 is None:
            sv.co3 = self.make_3d(pt)
        else:
            sv.co2 = self.make_2d(pt)
        sv.winding = math.atan2(sv.co2.y, sv.co2.x)
        self.coord.insert(idx, sv)
        return sv

    def split_edge(self, idx, n=1):
        a = self.coord[idx].co3
        b = self.coord[(idx+1) % len(self.coord)].co3
        for i in range(n):
            f = (i+1)/(n+1)
            vnew = (1-f) * a + f * b
            sv = SmartVec(vnew)
            self.coord.insert(idx+i+1, sv)
            sv.co2 = self.make_2d(vnew)

    def split_points(self, i, j):
        if abs(i-j) < 2:
            return []
        if i > j:
            j, i = i, j
        if (i == 0) and (j == len(self.coord)-1):
            return []

        new_poly = []
        n = len(self.coord)

        vlist1 = [self.coord[k % n] for k in range(i, j + 1)]
        poly = SmartPoly()
        poly.add(vlist1)
        poly.calculate()
        new_poly.append(poly)

        vlist2 = [self.coord[k % n] for k in range(j, i+n + 1)]
        poly = SmartPoly()
        poly.add(vlist2)
        poly.calculate()
        new_poly.append(poly)

        return new_poly

    def split_xy(self, pt, cut_x, mm):
        """Split horizontal or vertical - doing both x and y at once was complicated, so do one at a time
        makes new bmesh points to share as it goes, assumes self points have bmesh links already
        """
        cut = []
        cut_y = not cut_x
        n = len(self.coord)
        for i in range(n):
            a, b = self.coord[i].co2, self.coord[(i+1) % n].co2
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
        new_coord = [sv for sv in self.coord]
        cut.reverse()
        for i, dist, pos in cut:
            sv = SmartVec(pos)
            sv.co3 = self.make_3d(pos)
            new_coord.insert(i+1, sv)
            bmv = mm.new_vert(sv.co3)

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

        master_poly = SmartPoly()
        master_poly.add(new_coord, break_link=False)
        master_poly.calculate()

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
            elif (idx==0) and (next_idx==n-1): # adjacent points
                pass
            else:
                if e_next.dot(e_last) < -0.999: # don't double back over edge
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

    def update_3d(self):
        for pt in self.coord:
            pt.co3 = self.make_3d(pt.co2)
            if pt.bm_vert:
                pt.bm_vert.co = pt.co3
