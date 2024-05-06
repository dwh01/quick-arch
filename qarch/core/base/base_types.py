import bpy, bmesh
import math
import mathutils, mathutils.geometry
from mathutils import Vector
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




class CustomPoly:
    """Helper to manipulate virtual polygons where some verts exist and some don't"""
    def __init__(self):
        self.coords = []
        self.indices = []

    def __str__(self):
        s = ["Poly["] + ["<{:.1f},{:.1f},{:.1f}>".format(c[0], c[1], c[2]) for c in self.coords]
        return ",".join(s) + "]"

    def add(self, coord, index):
        self.coords.append(coord)
        self.indices.append(index)

    def calc_center(self):
        n = len(self.coords)
        self.center = functools.reduce(operator.add, self.coords) / n

    def generate_poly(self, xyz, ctr, n_sides, start_angle):
        angle_delta = (2 * math.pi) / n_sides
        for i in range(n_sides):
            dx = math.cos(i * angle_delta + start_angle)
            dy = math.sin(i * angle_delta + start_angle)
            co = ctr + dx * xyz[0] + dy * xyz[1]
            self.coords.append(co)
            self.indices.append(None)

    def scale_to(self, min_xyz, max_xyz):
        n = len(self.coords)
        center = functools.reduce(operator.add, self.coords) / n
        ctr_box = (min_xyz + max_xyz)/2
        shift = ctr_box - center

        if shift.length > 0:
            for i in range(n):
                self.coords[i] = self.coords[i] + shift

        min_pt, max_pt, xyz = face_bbox(self.coords)
        diag_target = max_xyz - min_xyz
        diag_now = max_pt - min_pt
        scale = [1,1,1]
        for i in range(3):
            if diag_now[i] == 0:
                scale[i] = 1
            else:
                scale[i] = diag_target[i]/diag_now[i]
        for i in range(n):
            vec = self.coords[i] - ctr_box
            for j in range(3):
                vec[j] = vec[j]*scale[j]
            self.coords[i] = vec + ctr_box

        self.calc_center()

    def slice(self, pt, direction):
        """slice into 2 polygons with the line defined"""
        a = pt #Vector(pt)
        b = a + direction
        n = len(self.coords)
        splits = []
        cur = []
        #print("self:", self.coords)
        #print("pt",pt,"dir",direction)
        for i in range(n):  # should find 2 intersections
            c = self.coords[i]
            d = self.coords[(i + 1) % n]
            tup = mathutils.geometry.intersect_line_line(a, b, c, d)
            if tup is None:
                cur.append(i)
                continue
            pt_cd = tup[1]
            dist_cd = (d - c).length
            dist_isect = (pt_cd - c).length

            if 0 == round(dist_isect, 6):
                cur.append(i)
                splits.append(cur)
                cur = [i]
            elif round(dist_isect,6) == round(dist_cd,6):
                j = (i+1) % n
                cur.append(i)
                cur.append(j)
                splits.append(cur)
                cur = []
            elif 0 < dist_isect < dist_cd:
                cur.append(i)
                cur.append(pt_cd)
                splits.append(cur)
                cur = [pt_cd]
            else:
                cur.append(i)

        if len(cur):
            splits.append(cur)
        #print(splits)
        if len(splits) < 2:
            return [self]
        if len(splits) == 3:
            splits = splits[2] + splits[0], splits[1]
        # convex poly can only have up to 3 splits present

        polys = [CustomPoly(), CustomPoly()]
        for i in range(2):
            cur = splits[i]
            for idx_or_pt in cur:
                if isinstance(idx_or_pt, Vector):
                    polys[i].add(idx_or_pt, None)
                else:
                    polys[i].add(self.coords[idx_or_pt], self.indices[idx_or_pt])

        for p in polys: # for sorting
            p.calc_center()

        return polys

    def is_oriented_rect(self, xyz):
        """Test for simple architecture"""
        n = len(self.coords)
        if n != 4:
            return False

        for i in range(n):
            e = self.coords[(i+1) % n] - self.coords[i]
            xdot = (abs(e.dot(xyz[0])) > 0.99)
            ydot = (abs(e.dot(xyz[1])) > 0.99)
            if not (xdot or ydot):
                return False

        return True

    def calc_area(self):
        n = len(self.coords)-1
        a = 0
        c = self.coords
        for i in range(1, n):
            a = a + mathutils.geometry.area_tri(c[0], c[i], c[i+1])
        return a

    def create_bmface(self, bm, dctNew):
        """Use dctNew to accumulate created verts that might be shared
        between new polygons"""
        vlist = []
        for i in range(len(self.coords)):
            if self.indices[i] is None:  # probably new
                v = dctNew.get(tuple(self.coords[i]), None)
                if v is None:  # definitely new
                    v = bm.verts.new(self.coords[i])
                    dctNew[tuple(self.coords[i])] = v
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
            for co, idx in zip(control_points, control_indices):
                control_poly.add(co, idx)
            control_poly.calc_center()

            min_pt, max_pt, xyz = face_bbox(control_points)  # coordinate system box
            diagonal = max_pt - min_pt
            max_size_x = diagonal.dot(xyz[0])
            max_size_y = diagonal.dot(xyz[1])

            # force offset and size to fit boxes inside each other
            face_ox, face_sx = sliding_clamp(ox, sx, max_size_x)
            face_oy, face_sy = sliding_clamp(oy, sy, max_size_y)

            inner_min = min_pt + face_ox * xyz[0] + face_oy * xyz[1]
            inner_max = inner_min + face_sx * xyz[0] + face_sy * xyz[1]
            inner_center = (inner_min + inner_max)/2

            if ns == 4 and control_poly.is_oriented_rect(xyz) and (props.extrude_distance==0):  # special architectural case, keep rectangles
                new_polygons = []
                cut_polys = control_poly.slice(inner_min, xyz[1])
                cut_polys.sort(key = lambda p: p.center.dot(xyz[0]))
                if len(cut_polys)>1:
                    new_polygons.append(cut_polys[0])  # left
                cut_polys = cut_polys[-1].slice(inner_max, xyz[1])
                cut_polys.sort(key=lambda p: p.center.dot(xyz[0]))
                if len(cut_polys)>1:
                    new_polygons.append(cut_polys[-1])  # right
                cut_polys = cut_polys[0].slice(inner_max, xyz[0])
                cut_polys.sort(key=lambda p: p.center.dot(xyz[1]))
                if len(cut_polys) > 1:
                    new_polygons.append(cut_polys[-1])  # top
                cut_polys = cut_polys[0].slice(inner_min, xyz[0])
                cut_polys.sort(key=lambda p: p.center.dot(xyz[1]))
                if len(cut_polys) > 1:
                    new_polygons.append(cut_polys[0])  # bottom
                    center_poly = cut_polys[-1]
                else:
                    center_poly = cut_polys[0]
                new_polygons.append(center_poly)
                new_polygons = [p for p in new_polygons if p.calc_area() > 0.000001]
                dctNew = {}
                new_faces = [p.create_bmface(bm, dctNew)[0] for p in new_polygons]
                center_face = new_faces[-1]

            else:  # bridge edge loops
                angle_delta = (2 * math.pi)/ns
                # odd or even, make symmetrical around vertical axis, odd point at top
                start_angle = math.pi / 2
                if ns % 2 == 0:  # even sides, put flat at top
                    start_angle = start_angle - 0.5 * angle_delta

                center_poly = CustomPoly()
                center_poly.generate_poly(xyz, inner_center, ns, start_angle)
                center_poly.scale_to(inner_min, inner_max)

                center_face, dctNew = center_poly.create_bmface(bm, {})
                center_face.normal_update()
                new_faces = safe_bridge(bm, face, center_face)

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            if props.extrude_distance != 0:
                # not actually extruding, just offset new face
                # bmesh.ops.extrude_discrete_faces(bm, faces=center_face)
                for v in center_face.verts:
                    v.co = v.co + xyz[2] * props.extrude_distance

                # curves can make non-flat faces
                test_faces = [f for f in new_faces if (f is not center_face) and f.is_valid]
                bmesh.ops.connect_verts_nonplanar(bm, faces=test_faces)

        bmesh.ops.delete(bm, geom=sel_faces, context="FACES_ONLY")




