import bpy, bmesh
import math
import mathutils, mathutils.geometry
from mathutils import Vector, Matrix
import functools
import operator
from ...utils import managed_bmesh_edit, crash_safe, face_bbox, sliding_clamp

do_debug_print = True

def angle_of_points(pts, ref, norm, org):
    angles = []
    for v1 in pts:
        v2 = v1 - org
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


def find_face_by_verts(bm, vlist):
    face = None
    for test_face in vlist[0].link_faces:
        b_found = True
        b_order = True
        for i, v in enumerate(test_face.verts):
            if v not in vlist:
                b_found = False
                break
            if v is not vlist[i]:
                b_order = False
        if b_found:
            if b_order:
                face = test_face
            else:
                bmesh.ops.delete(bm, geom=[test_face], context="FACES_ONLY")
            break
    return face


def safe_bridge(bm, verts, center_face):
    """Avoid twist that can happen with bmesh.ops.bridge_loops"""
    closest = {}
    face_orig = functools.reduce(operator.add, [v.co for v in verts]) / len(verts)
    face_normal = (verts[1].co-verts[0].co).cross(verts[2].co-verts[0].co).normalized()

    center_face_orig = center_face.calc_center_median()
    ref = center_face.verts[0].co - center_face_orig
    ref = ref.normalized()
    points = [v.co for v in center_face.verts]
    center_angles = angle_of_points(points, ref, center_face.normal, center_face_orig)
    # could project ref onto face in case the faces are not coplanar
    points = [v.co for v in verts]
    face_angles = angle_of_points(points, ref, face_normal, face_orig)

    center_sort = list(zip(center_angles, center_face.verts))
    outer_sort = list(zip(face_angles, verts))
    center_sort.sort(key=lambda a: a[0])
    outer_sort.sort(key=lambda a: a[0])

    if abs(center_sort[0][0] - (outer_sort[-1][0]-2*math.pi)) < abs(center_sort[0][0] - outer_sort[0][0]):
        first_outer = -1  # this seems to cause a failure mode with all faces being triangles to the first outer point
        first_outer = 0
    else:
        first_outer = 0

    n_inner = len(center_face.verts)
    n_outer = len(verts)
    wrap = {-1: -2*math.pi, n_outer: 2*math.pi}
    new_faces = []
    j_outer = 0
    for i_inner in range(n_inner):
        j_inner = (i_inner+1) % n_inner

        i_outer = first_outer
        j_outer = first_outer
        delta_angle = outer_sort[i_outer][0] - center_sort[i_inner][0]
        for j in range(i_outer, n_outer+1):
            w = wrap.get(j, 0)
            if j > -1:
                j = j % n_outer
            j_angle = (outer_sort[j][0]+w) - center_sort[i_inner][0]
            if (delta_angle < 0) and (delta_angle <= j_angle < math.pi/2):
                j_outer = j
                delta_angle = j_angle
            else:
                break

        if j_outer < i_outer:
            j_outer = j_outer + n_outer
        lst_outer = [outer_sort[j % n_outer][1] for j in range(i_outer, j_outer+1)]
        lst_inner = [center_sort[i_inner][1], center_sort[j_inner][1]]
        lst_outer.reverse()
        # for next face
        first_outer = j_outer

        vlist2 = lst_inner + lst_outer
        vlist = []
        for v in vlist2:
            if v not in vlist:
                vlist.append(v)

        if len(vlist) < 3:
            print(f"i {i_inner}, {i_outer}, o {j_outer}, {j_inner}")
            print("vlist size < 3", [v.co for v in vlist])
        else:
            face = find_face_by_verts(bm, vlist)
            if face is None:
                new_faces.append(bm.faces.new(vlist))
            else:
                new_faces.append(face)

    first_vert = list(new_faces[0].verts)[-1]
    last_vert = list(new_faces[-1].verts)[2]
    if first_vert is not last_vert:  # closure triangle
        lst_inner = [center_sort[j_inner][1]]
        lst_outer = [first_vert, last_vert]
        vlist = lst_inner + lst_outer

        face = find_face_by_verts(bm, vlist)
        if face is None:
            new_faces.append(bm.faces.new(vlist))
        else:
            new_faces.append(face)

    for face in new_faces:
        face.normal_update()
        if face.normal.dot(center_face.normal) < 0:
            face.normal_flip()
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
    def __init__(self, name="poly"):
        self.name = name
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
        return self.name+"[" + ",".join(s) + "]"

    def debug(self):
        print(self)
        print("{} points, {} edges".format(len(self.coord2d), len(self.edges)))
        print("bbox", self.bbox)
        print("size", self.box_size)
        print(self.matrix)

    def add(self, coord, index):
        self.coord3d.append(coord)
        self.indices.append(index)
        self.changed.append(False)

    def from_verts(self, verts):
        for v in verts:
            self.add(v.co, v.index)
        self.prepare()

    def prepare(self, norm=Vector((0,0,1))):
        """Precalculate values, norm is used for degenerate polys"""
        n = len(self.coord3d)
        self.center = functools.reduce(operator.add, self.coord3d) / n

        v1 = (self.coord3d[0] - self.center).normalized()
        v2 = (self.coord3d[1] - self.center).normalized()
        self.normal = v1.cross(v2)
        if self.normal.length==0:
            print("replace norm with +z")
            self.normal = norm
        self.normal.normalize()

        if self.normal[2] < -0.99:
            print("negative y")
            self.ydir = -self.ydir
        elif self.normal[2] < 0.99:
            self.xdir = Vector((0,0,1)).cross(self.normal).normalized()
            self.ydir = self.normal.cross(self.xdir).normalized()
            print("new x",self.xdir)
            print("new y", self.ydir)
            print("new z", self.normal)

        # enforce ccw winding
        # pointing could be wrong if first 2 points are wrong,
        # but usually it is points 3 and 4 of a rectangle that are reversed
        angles = angle_of_points(self.coord3d, self.xdir, self.normal, self.center)
        lst = list(zip(angles, self.coord3d, self.indices))
        lst.sort(key=lambda a: a[0])
        self.coord3d = [a[1] for a in lst]
        self.indices = [a[2] for a in lst]

        # matrix to rotate flat, transpose brings us back
        self.matrix[0] = self.xdir
        self.matrix[1] = self.ydir
        self.matrix[2] = self.normal
        self.inverse = self.matrix.transposed()

        self.coord2d=[]
        for v3 in self.coord3d:
            v = self.matrix @ (v3 - self.center)
            self.coord2d.append(v.to_2d())

        n = len(self.coord2d)
        self.edges = []
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
            self.bbox[1].x = max(p1.x, self.bbox[1].x)
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

        n = len(self.coord2d)
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

    def create_bmface(self, bm, dctNew, dctOld, opid):
        """Use dctNew to accumulate created verts that might be shared
        between new polygons. dctOld contains existing verts to use
        """
        if do_debug_print:
            ("Make face from")
            self.debug()
        key_sequence = bm.verts.layers.int['sequence']
        key_opid = bm.verts.layers.int['opid']
        vlist = []
        bAnyNew = False
        offset= dctOld['offset']
        for i in range(len(self.coord3d)):
            v = dctNew.get(tuple(self.coord3d[i]), None)
            if v is None:
                if (i+offset) in dctOld:  # just move existing vert
                    v = dctOld[i+offset]
                    v.co = self.coord3d[i]
                    dctOld['used'].append(i+offset)
                else:  # make new
                    v = bm.verts.new(self.coord3d[i])
                    v[key_sequence] = i+offset
                    v[key_opid] = opid
                    bAnyNew = True
                dctNew[tuple(self.coord3d[i])] = v

            if len(vlist):
                if v is vlist[-1]:  # oops, repeated vertex
                    continue
            vlist.append(v)
        dctOld['offset'] = offset + len(self.coord3d)

        if vlist[-1] is vlist[0]:  # just in case wrapped onto self
            vlist = vlist[:-1]

        if do_debug_print:
            ("face from verts {}".format(vlist))
        if bAnyNew:
            face = bm.faces.new(vlist)
        else:
            # find existing face using these verts
            face = find_face_by_verts(bm, vlist)
            if face is None:
                face = bm.faces.new(vlist)
            else:
                if do_debug_print:
                    print("was found")

        return face, dctNew


@crash_safe
def face_divide(oper, context, opid):
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
        key_sequence = bm.verts.layers.int['sequence']
        key_opid = bm.verts.layers.int['opid']

        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        sel_faces = [f for f in bm.faces if f.select]  # for later deletion
        remove_verts = []

        lst_cp = [  # where this operation will be applied
            [v.index for v in face.verts] for face in bm.faces if face.select
        ]
        if len(lst_cp) == 0:  # called programmatically with control points selected
            lst_cp = [[v.index for v in bm.verts if v.select]]

        if len(lst_cp[0]) == 0:
            oper.report({"OPERATOR"}, "Select some vertices first")
            return

        dctOld = {}  # used to move instead of create
        for v in bm.verts:
            if v[key_opid] == opid:
                dctOld[v[key_sequence]] = v
        dctOld['offset'] = 0  # each polygon needs to know how many already consumed
        dctOld['used'] = []  # so we can delete verts we don't need any more
        if do_debug_print:
            print("\n\nexisting for {}".format(opid))
            print(dctOld)
            print()
        for control_points in lst_cp:
            verts = [bm.verts[i] for i in control_points]
            # helper polygon
            control_poly = CustomPoly('control')
            control_poly.from_verts(verts)
            if do_debug_print:
                print("control points {}".format(control_points))
                control_poly.debug()

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
                # special architectural case, keep rectangles with 3x3 grid
                # some cells may be zero width, that's ok and needed for later adjustment
                new_faces = []
                grid_verts = []
                i_sequence = 0
                for y in [control_poly.bbox[0].y, inner_min.y, inner_max.y, control_poly.bbox[1].y]:
                    for x in [control_poly.bbox[0].x, inner_min.x, inner_max.x, control_poly.bbox[1].x]:
                        v2 = Vector((x, y))
                        v3 = control_poly.make_3d(v2)
                        if i_sequence in dctOld:
                            grid_verts.append(dctOld[i_sequence])
                            grid_verts[-1].co = v3
                            dctOld['used'].append(i_sequence)
                        else:
                            grid_verts.append(bm.verts.new(v3))
                            grid_verts[-1][key_sequence] = i_sequence
                            grid_verts[-1][key_opid] =opid
                        i_sequence = i_sequence + 1

                for i in range(3):
                    for j in range(3):
                        k = i*4+j
                        cell = [k, k+1, k+5, k+4]
                        vlist = [grid_verts[idx] for idx in cell]
                        face = find_face_by_verts(bm, vlist)
                        if face is None:
                            new_faces.append(bm.faces.new(vlist))
                        else:
                            new_faces.append(face)

                center_face = new_faces[4]
                for face in new_faces:
                    face.normal_update()
                    if face.normal.dot(control_poly.normal) < 0:
                        face.normal_flip()

            else:  # bridge edge loops
                # copy verts if not in dctOld
                v_outer= []
                for i in range(len(verts)):
                    if i in dctOld:
                        v_outer.append(dctOld[i])
                        v_outer[-1].co = verts[i].co
                        dctOld['used'].append(i)
                    else:
                        v_outer.append(bm.verts.new(verts[i].co))
                        v_outer[-1][key_sequence] = i
                        v_outer[-1][key_opid] = opid

                #control_poly.debug()
                angle_delta = (2 * math.pi)/ns
                # odd or even, make symmetrical around vertical axis, odd point at top
                start_angle = math.pi / 2
                if ns % 2 == 0:  # even sides, put flat at top
                    start_angle = start_angle - 0.5 * angle_delta

                center_poly = CustomPoly()
                origin = control_poly.make_3d(inner_center)
                center_poly.generate_poly(control_poly.matrix, origin, ns, start_angle)
                center_poly.stretch_to(inner_min, inner_max)

                center_face, dctNew = center_poly.create_bmface(bm, {}, dctOld, opid)
                center_face.normal_update()
                safe_bridge(bm, v_outer, center_face)

            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            if props.extrude_distance != 0:
                # not actually extruding, just offset new face
                # bmesh.ops.extrude_discrete_faces(bm, faces=center_face)
                for v in center_face.verts:
                    v.co = v.co + center_face.normal * props.extrude_distance

        used = set(dctOld['used'])
        del dctOld['used']  # so we can do set math on keys
        del dctOld['offset']
        was = set(dctOld.keys())
        to_remove = was - used
        if len(to_remove):
            remove_verts = [dctOld[k] for k in list(to_remove)]

        if len(sel_faces):
            bmesh.ops.delete(bm, geom=sel_faces, context="FACES_ONLY")
        if len(remove_verts):
            bmesh.ops.delete(bm, geom=remove_verts, context="VERTS")




