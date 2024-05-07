import bpy, bmesh
import math
import mathutils, mathutils.geometry
from mathutils import Vector, Matrix
import functools
import operator
from ...utils import managed_bmesh_edit, crash_safe, face_bbox, sliding_clamp


def angle_of_verts(face, ref, norm, org):
    angles = []
    for v1 in face.verts:
        v2 = v1.co - org
        v2 = v2.normalized()
        crs = ref.cross(v2)
        dt = crs.dot(norm)
        y = math.copysign(crs.length, dt)
        x = ref.dot(v2)
        ang = math.atan2(y, x)
        if ang < 0:
            ang = 2*math.pi + ang
        angles.append(ang)
    return angles

def safe_bridge(bm, face, center_face):
    """Avoid twist that can happen with bmesh.ops.bridge_loops"""
    closest = {}
    face_orig = face.calc_center_median()
    center_face_orig = center_face.calc_center_median()
    face_angle = []
    center_angle = []
    ref = center_face.verts[0].co - center_face_orig
    ref = ref.normalized()
    center_angles = angle_of_verts(center_face, ref, center_face.normal, center_face_orig)
    # could project ref onto face in case the faces are not coplanar
    face_angles = angle_of_verts(face, ref, face.normal, face_orig)

    for i, a in enumerate(center_angles):
        dist = []
        for j, b in enumerate(face_angles):
            d = abs(a-b)
            if d > math.pi:
                d = 2*math.pi - d
            dist.append((i,j, d *180/math.pi))

        dist.sort(key=lambda t: t[2])
        closest[i] = dist[0][1]  # mark from center face to outside closest point

    n = len(center_face.verts)
    m = len(face.verts)
    faceverts = [v for v in face.verts]
    if face.normal.dot(center_face.normal) < 0:
        reverse_winding = True
    else:
        reverse_winding = False

    new_faces = []
    for i in range(n):
        j = (i+1) % n
        vlist = [center_face.verts[i], center_face.verts[j]]
        # come back on outside face
        k = closest[j]
        l = closest[i]
        if reverse_winding:  # untested?
            k, l = l, k
        if k < l: # wrapped
            k = k + m
        indices = list(range(k,l-1,-1))

        for i2 in indices:
            vlist.append(faceverts[i2 % m])

        vlist.reverse()
        new_faces.append(bm.faces.new(vlist))
    return new_faces


class CustomEdge:
    def __init__(self, p0, v, idx, slope, intercept, inside):
        self.p0 = p0
        self.v = v
        self.idx = idx
        self.slope = slope
        self.intercept = intercept
        self.inside = inside

    def __str__(self):
        s = "edge <{:.1f},{:.1f}> ".format(self.p0.x, self.p0.y)
        if self.slope is not None:
            s = s + "m={:.1f} b={:.1f}".format(self.slope, self.intercept)
        else:
            s = s + "vertical"
        return s

    def test_inside(self, pt):
        if self.slope is None:  # vertical
            if pt.x * self.inside > self.p0.x * self.inside:
                return True
            return False
        y = pt.x * self.slope + self.intercept
        if y * self.inside > pt.y * self.inside:
            return True
        return False


class CustomPoly:
    """Helper to manipulate virtual polygons where some verts exist and some don't"""
    def __init__(self):
        self.coord3d = []
        self.indices = []
        self.changed = []
        self.center = Vector((0,0,0))
        self.normal = Vector((0,0,1))
        self.matrix = Matrix.Identity(3)
        self.inverse = Matrix.Identity(3)
        self.bbox = [Vector((0,0)), Vector((0,0))]
        self.edges = []
        self.coord2d = []
        self.xdir = Vector((1,0,0))
        self.ydir = Vector((0,1,0))
        self.box_size = Vector((0,0))

    def __str__(self):
        s = ["<{:.1f},{:.1f},{:.1f}>".format(c.x, c.y, c.z) for c in self.coord3d]
        return "Poly[" + ",".join(s) + "]"

    def debug(self):
        print(self)
        print("bbox", self.bbox)
        print("size", self.box_size)
        print(self.matrix)
        for e in self.edges:
            print(e)

    def add(self, coord, index):
        self.coord3d.append(coord)
        self.indices.append(index)
        self.changed.append(False)

    def from_face(self, face):
        for v in face.verts:
            self.add(v.co, v.index)
        self.prepare()

    def prepare(self):
        """Precalculate values"""
        n = len(self.coord3d)
        self.center = functools.reduce(operator.add, self.coord3d) / n
        v1 = self.coord3d[0] - self.center
        v2 = self.coord3d[1] - self.center
        self.normal = v1.cross(v2).normalized()

        if self.normal[2] < -0.99:
            self.ydir = -self.ydir
        elif self.normal[2] < 0.99:
            self.xdir = Vector((0,0,1)).cross(self.normal).normalized()
            self.ydir = self.normal.cross(self.xdir).normalized()

        # matrix to rotate flat, transpose brings us back
        self.matrix[0] = self.xdir
        self.matrix[1] = self.ydir
        self.matrix[2] = self.normal
        self.inverse = self.matrix.transposed()

        for v3 in self.coord3d:
            v = self.matrix @ (v3 - self.center)
            self.coord2d.append(v.to_2d())

        n = len(self.coord2d)
        for i in range(n):
            j = (i+1) % n
            p0 = self.coord2d[i]
            p1 = self.coord2d[j]
            v = p1-p0
            if v.x == 0:  # vertical line
                if p0.x > self.center.x:
                    inside = -1
                else:
                    inside = 1
                edge = CustomEdge(p0, p1, i, None, None, inside)
            else:
                slope = v.y/v.x
                intercept = p1.y - slope*p1.x
                if v[0] > 0:
                    inside = 1
                else:
                    inside = -1
                edge = CustomEdge(p0, v, i, slope, intercept, inside)
            self.edges.append(edge)
            self.bbox[0].x = min(p0.x, self.bbox[0].x)
            self.bbox[0].y = min(p0.y, self.bbox[0].y)
            self.bbox[1].x = max(p0.x, self.bbox[1].x)
            self.bbox[1].y = max(p1.y, self.bbox[1].y)
        self.box_size = self.bbox[1] - self.bbox[0]

    def generate_poly(self, xyz, ctr, n_sides, start_angle):
        angle_delta = (2 * math.pi) / n_sides
        for i in range(n_sides):
            dx = math.cos(i * angle_delta + start_angle)
            dy = math.sin(i * angle_delta + start_angle)
            co = ctr + dx * xyz[0] + dy * xyz[1]
            self.add(co,None)

        self.prepare()

    def stretch_to(self, min_xy, max_xy):
        diag_target = max_xy - min_xy
        diag_now = self.box_size
        scale_x = diag_target.x/diag_now.x
        scale_y = diag_target.y/diag_now.y
        shift = (min_xy + max_xy)/2 - (self.bbox[1] + self.bbox[0])/2

        for i in range(len(self.coord2d)):
            co = self.coord2d[i]
            co.x = co.x * scale_x
            co.y = co.y * scale_y
            self.coord2d[i] = co + shift
            v3 = self.inverse @ co.to_3d() + self.center
            self.coord3d[i] = v3
            self.changed[i] = True

        # recalculate all
        self.prepare()

    def slice_2d(self, pt, direction):
        """slice into 2 polygons with the line defined"""
        # make sure cutting segment is bigger than the polygon
        # blender 2d intersection works on segments not lines
        big = self.box_size.x + self.box_size.y  # save on square roots, any size bigger than diagonal is good
        a = pt - big * direction
        b = pt + big * direction
        splits = []
        cur = []

        for i in range(n):  # should find 2 intersections
            c = self.coord2d[i]
            d = self.coord2d[(i + 1) % n]
            pt_cd = mathutils.geometry.intersect_line_line_2d(a, b, c, d)

            if pt_cd is None:  # between intersections, just accumulate points
                cur.append(i)
                continue

            if pt_cd == c:  # hit a vertex
                cur.append(i)
                splits.append(cur)
                cur = [i]
            elif pt_cd == d:  # hit second vertex, handle both here
                j = (i+1) % n
                cur.append(i)
                cur.append(j)
                splits.append(cur)
                cur = []
            else:  # accumulate i and add a new point
                cur.append(i)
                cur.append(pt_cd)
                splits.append(cur)
                cur = [pt_cd]

        if len(cur):
            splits.append(cur)

        if len(splits) < 2:
            return [self]
        if len(splits) == 3:  # started in middle of span
            splits = splits[2] + splits[0], splits[1]
        # convex poly can only have up to 3 splits present

        polys = [CustomPoly(), CustomPoly()]
        for i in range(2):
            cur = splits[i]
            for idx_or_pt in cur:
                if isinstance(idx_or_pt, Vector):
                    v3 = self.make_3d(idx_or_pt)
                    polys[i].add(v3, None)
                else:
                    polys[i].add(self.coord3d[idx_or_pt], self.indices[idx_or_pt])

        for p in polys:
            p.prepare()

        return polys

    def match(self, pt):
        for i in range(len(self.coord2d)):
            if pt == self.coord2d[i]:
                return self.indices[i]
        return None

    def slice_rect_3(self, axis_to_cut, offset, size):
        assert self.is_oriented_rect(), "slice_rect_3 only works on rectangles"
        polys = []
        if axis_to_cut=="x":
            x2d = Vector((1,0))
            a = self.bbox[0]
            b = Vector((a.x, self.bbox[1].y))
            new_pts = [
                a + x2d * offset,
                a + x2d * (offset + size),
                b + x2d * (offset + size),
                b + x2d * offset,
            ]
            if offset > 0:
                p = CustomPoly()
                p.add(self.make_3d(a), self.match(a))
                p.add(self.make_3d(new_pts[0]), None)
                p.add(self.make_3d(new_pts[3]), None)
                p.add(self.make_3d(b), self.match(b))
                polys.append(p)
            p = CustomPoly()
            for v in new_pts:
                p.add(self.make_3d(v), None)
            polys.append(p)
            if offset+size < self.box_size.x:
                c = a + x2d * self.box_size.x
                d = b + x2d * self.box_size.x
                p = CustomPoly()
                p.add(self.make_3d(new_pts[1]), None)
                p.add(self.make_3d(c), self.match(c))
                p.add(self.make_3d(d), self.match(d))
                p.add(self.make_3d(new_pts[2]), None)
                polys.append(p)
        else:
            y2d = Vector((0,1))
            a = self.bbox[0]
            b = Vector((self.bbox[1].x, a.y))
            new_pts = [
                a + y2d * offset,
                b + y2d * offset,
                b + y2d * (offset + size),
                a + y2d * (offset + size),
            ]
            if offset > 0:
                p = CustomPoly()
                p.add(self.make_3d(a), self.match(a))
                p.add(self.make_3d(b), self.match(b))
                p.add(self.make_3d(new_pts[1]), None)
                p.add(self.make_3d(new_pts[0]), None)
                polys.append(p)
            p = CustomPoly()
            for v in new_pts:
                p.add(self.make_3d(v), None)
            polys.append(p)
            if offset + size < self.box_size.y:
                c = a + y2d * self.box_size.y
                d = b + y2d * self.box_size.y
                p = CustomPoly()
                p.add(self.make_3d(new_pts[3]), None)
                p.add(self.make_3d(new_pts[2]), None)
                p.add(self.make_3d(d), self.match(d))
                p.add(self.make_3d(c), self.match(c))
                polys.append(p)
        for p in polys:
            p.prepare()
        return polys

    def make_3d(self, v2d):
        v3 = self.inverse @ v2d.to_3d() + self.center
        return v3

    def is_oriented_rect(self):
        """Test for simple architecture rectangles"""
        n = len(self.edges)
        if n != 4:
            return False

        for i in range(n):
            edge = self.edges[i]
            if (edge.slope is not None) and (abs(edge.slope) != 0):
                return False

        return True

    def calc_area(self):
        n = len(self.coord2d)-1
        a = 0
        c = self.coord2d
        for i in range(1, n):
            a = a + mathutils.geometry.area_tri(c[0], c[i], c[i+1])
        return a

    def create_bmface(self, bm, dctNew):
        """Use dctNew to accumulate created verts that might be shared
        between new polygons"""
        vlist = []
        for i in range(len(self.coord3d)):
            if self.indices[i] is None:  # probably new
                v = dctNew.get(tuple(self.coord3d[i]), None)
                if v is None:  # definitely new
                    v = bm.verts.new(self.coord3d[i])
                    dctNew[tuple(self.coord3d[i])] = v
            else:
                bm.verts.ensure_lookup_table()
                v = bm.verts[self.indices[i]]

            if len(vlist):
                if v is vlist[-1]:  # oops, repeated vertex
                    continue
            vlist.append(v)

        if vlist[-1] is vlist[0]:  # just in case wrapped onto self
            vlist = vlist[:-1]

        face = bm.faces.new(vlist)
        return face, dctNew


@crash_safe
def face_divide(context, oper):
    """Create a center patch inside face
    applies to selected faces, takes FaceDivideProps
    shrinks offset then size for faces that are too small
    """
    props = oper.props
    # ('has_extrude', 'extrude_prop')
    obj = context.object
    ox, oy = props.offset_x, props.offset_y
    sx, sy = props.size_x, props.size_y
    ns = props.inner_sides

    log_list = []
    with managed_bmesh_edit(obj) as bm:
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        sel_faces = [face for face in bm.faces if face.select]
        if len(sel_faces)==0:
            oper.report({"OPERATOR"}, "Select some faces first")
            return

        for face in sel_faces:
            control_points = [v.co for v in face.verts]
            # logging information
            deleted_index = face.index
            control_indices = [v.index for v in face.verts]
            log_list.append((deleted_index, control_indices, control_points))

            # helper polygon
            control_poly = CustomPoly()
            control_poly.from_face(face)

            max_size_x = control_poly.box_size.x
            max_size_y = control_poly.box_size.y

            # force offset and size to fit boxes inside each other
            face_ox, face_sx = sliding_clamp(ox, sx, max_size_x)
            face_oy, face_sy = sliding_clamp(oy, sy, max_size_y)

            # calcs in 2d
            x2d = Vector((1,0))
            y2d = Vector((0,1))
            inner_min = control_poly.bbox[0] + face_ox * x2d + face_oy * y2d
            inner_max = inner_min + face_sx * x2d + face_sy * y2d
            inner_center = (inner_min + inner_max)/2

            if ns == 4 and control_poly.is_oriented_rect() and (props.extrude_distance == 0):
                # special architectural case, keep rectangles
                new_polygons = []
                cut_polys = control_poly.slice_rect_3('x', face_ox, face_sx)
                if face_ox == 0:
                    cut_next = cut_polys[0]
                    new_polygons = new_polygons + cut_polys[1:]
                else:
                    cut_next = cut_polys[1]
                    new_polygons.append(cut_polys[0])
                    if len(cut_polys) > 2:
                        new_polygons.append(cut_polys[2])

                cut_polys = cut_next.slice_rect_3('y', face_oy, face_sy)
                n_new = len(new_polygons)  # offset to find the center
                new_polygons = new_polygons + cut_polys

                dctNew = {}
                new_faces = [p.create_bmface(bm, dctNew)[0] for p in new_polygons]
                if face_oy == 0:
                    center_face = new_faces[n_new]  # first of second cut series
                else:
                    center_face = new_faces[n_new + 1] # second of second cut series

            else:  # bridge edge loops
                angle_delta = (2 * math.pi)/ns
                # odd or even, make symmetrical around vertical axis, odd point at top
                start_angle = math.pi / 2
                if ns % 2 == 0:  # even sides, put flat at top
                    start_angle = start_angle - 0.5 * angle_delta

                center_poly = CustomPoly()
                origin = control_poly.make_3d(inner_center)
                center_poly.generate_poly(control_poly.matrix, origin, ns, start_angle)
                center_poly.stretch_to(inner_min, inner_max)

                center_face, dctNew = center_poly.create_bmface(bm, {})
                center_face.normal_update()
                new_faces = safe_bridge(bm, face, center_face)

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            if props.extrude_distance != 0:
                # not actually extruding, just offset new face
                # bmesh.ops.extrude_discrete_faces(bm, faces=center_face)
                for v in center_face.verts:
                    v.co = v.co + center_face.normal * props.extrude_distance

                # curves can make non-flat faces
                test_faces = [f for f in new_faces if (f is not center_face) and f.is_valid]
                bmesh.ops.connect_verts_nonplanar(bm, faces=test_faces)

        bmesh.ops.delete(bm, geom=sel_faces, context="FACES_ONLY")




