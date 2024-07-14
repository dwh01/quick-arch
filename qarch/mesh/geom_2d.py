import mathutils
from mathutils import Matrix, Vector
import itertools
import functools
import operator
import bisect
import math


def _closest_point(pt, lst2):
    """Return index in lst2 of point closest to pt"""
    dist = [(pt-p).length for p in lst2]
    lst = list(enumerate(dist))
    lst.sort(key=lambda t: t[1])
    return lst[0][0]


def _segment_lengths(lst1):
    """Find segment lengths, return list"""
    lst = []
    n = len(lst1)
    for i in range(n):
        j = (i+1) % n
        e = lst1[j]-lst1[i]
        lst.append(e.length)
    return lst


def _segment_winding(lst1):
    n = len(lst1)
    ctr = functools.reduce(operator.add, lst1) / n
    lst = []
    for i in range(n):
        j = (i+1) % n
        vj = lst1[j]-ctr
        vi = lst1[i]-ctr
        sinth = vj.normalized().cross(vi.normalized()).length
        if sinth==0 and vj.length:
            c = (lst1[j]-lst1[i]).length / ((vj.length + vi.length)/2)  # s/r = theta
        else:
            c = math.asin(sinth)
        lst.append(c)
    return lst


def bridge_points_by_circumfrence(lst1, lst2, coord_sys):
    """Work around the lists trying to match fractional distance covered
    :param list(Vector) lst1: 3D points
    :param list(Vector) lst2: 3D points
    :return lst(tuple): list of index pairs to connect (matches length of shortest input list)
    """
    n1 = len(lst1)
    n2 = len(lst2)
    # work with shortest list as lst 1
    if n2 < n1:
        b_swap = True  # remember to switch back return value
        lst1, lst2 = lst2, lst1
        n1, n2 = n2, n1
    else:
        b_swap = False

    # find best start on lst2 (closest)
    roll_idx = coord_sys.first_corner_index(lst2)
    n2 = len(lst2)
    lst2 = lst2[roll_idx:] + lst2[:roll_idx]

    # segment lengths
    len1 = _segment_lengths(lst1)
    len2 = _segment_lengths(lst2)

    # get cumulative lengths
    sum1 = list(itertools.accumulate(len1))
    sum2 = list(itertools.accumulate(len2))

    # make fractions, but use integers to avoid floating point error in bisect
    fr1 = [0]+[round(1000*l/sum1[-1]) for l in sum1]
    fr2 = [0]+[round(1000*l/sum2[-1]) for l in sum2]
    if max(fr1) > max(fr2):
        print("bridge problem")
        print(fr1)
        print(fr2)

    # now we match fractions
    lst_link = []
    for i in range(n1):
        f_find = fr1[i]
        i_found = bisect.bisect_left(fr2, f_find) # >= find
        # if i_found == n2 not possible because both lists end in 1, and found position is to left of existing
        if i_found == 0:  # must be exact match of 0 on first point
            lst_link.append([0, roll_idx])  # have to add idx back to list 2
        else:
            j_found = i_found - 1
            d_j = f_find - fr2[j_found]
            d_i = fr2[i_found] - f_find
            if d_j < d_i:
                idx = j_found
            else:
                idx = i_found

            if b_swap:
                lst_link.append([(idx + roll_idx) % n2, i])
            else:
                lst_link.append([i, (idx + roll_idx) % n2])

    #print(lst1, lst2, roll_idx)
    #print(fr1, fr2)
    #print(lst_link)
    return lst_link


def generate_arc_points(ctr, r, theta0, step, n_step, thickness):
    """Create points along an arc
    :param Vector(2) ctr: center of arc
    :param float r: radius of arc
    :param float theta0: start angle of arc
    :param float step: angular step of arc
    :param int n_step: number of points to add
    :param float thickness: radial offset for second, inner set of points or 0 for none
    :return list, list: list of outer points, list of inner points, ccw ordered
    """
    lst_pts = []
    lst_pts2 = []
    for i in range(n_step):
        t = step * i + theta0
        vr = Vector((math.cos(t), math.sin(t)))
        v = ctr + r * vr
        lst_pts.append(v)
        if thickness > 0:
            offset = thickness * vr
            lst_pts2.append(lst_pts[-1] - offset)
    return lst_pts, lst_pts2


def generate_arch(w, h, n_sides, arch_type, thickness, drop_sides=0):
    """arch_type_list =
    ("JACK", "Jack", "Flat", 1),
    ("ROMAN", "Roman", "Round/Oval (1 pt)", 2),
    ("GOTHIC", "Gothic", "Gothic pointed (2 pt)", 3),
    ("OVAL", "Oval", "Victorian oval (3 pt)", 4),
    ("TUDOR", "Tudor", "Tudor pointed (4 pt)", 5),

    Thickness 0 means just a single poly (or line for JACK)
    Otherwise make a frameed arch
    returns lst1, lst2, lst_ctr, lst3
    where lst1 has exterior of arch
    lst2 has interior if framed
    lst_ctr is the uv origin for each segment quad
    lst3 is extra points for the Jack arch "fill" polygon
    """
    # thanks to ThisIsCarpentry.com for classic geometric construction algorithms
    lst_pts = []  # outer arch
    lst_pts2 = []  # for thickness case, inner arch
    lst_ctr = []  # center of uv for each arch frame polygon
    lst_pts3 = []  # points to make a 'center', for Jack only

    if arch_type == 'JACK':
        # we really need thickness to make a single Jack arch polygon
        if thickness == 0:
            thickness = h/10
        # points are spaced in angle, not in distance
        theta_0 = math.atan2(h, w/2)
        theta_1 = math.pi - theta_0
        step = (theta_1 - theta_0) / n_sides

        for i in range(0, n_sides + 1, n_sides):  # skipping flat points
            t = step * i + theta_0
            if t == math.pi/2:
                x = 0
            else:
                x = h / math.tan(t)
            lst_pts.append(Vector((x, h)))
            if thickness > 0:
                h1 = h - thickness
                if t == math.pi / 2:
                    x = 0
                else:
                    x = h1 / math.tan(t)
                lst_pts2.append(Vector((x, h1)))

        lst_ctr.append(Vector((0, 0)))

    elif arch_type == 'ROMAN':
        r = w**2/(8*h) + h/2
        d = h-r
        if round(d, 3) == 0:  # full circular arc
            theta = math.pi
        else:
            theta = 2 * math.atan2(w/2, -d)
        theta_0 = math.pi/2 - theta/2
        step = theta / n_sides

        ctr = Vector((0, d))
        lst_pts, lst_pts2 = generate_arc_points(ctr, r, theta_0, step, n_sides+1, thickness)
        lst_ctr = [ctr] * n_sides

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

        ctr = Vector((c, d))
        step = (theta-theta_start) / n_arc
        lst_pts, lst_pts2 = generate_arc_points(ctr, r_arc, theta_start, step, n_arc+1, thickness)
        if thickness > 0: # correct last point
            ipt = mathutils.geometry.intersect_line_line_2d(lst_pts[-1], Vector((0, 0)), lst_pts2[-1], lst_pts2[-2])
            lst_pts2[-1] = ipt
        lst_ctr = [ctr] * n_arc

        theta_1 = math.pi - theta  # for downward stroke
        ctr = Vector((-c, d))
        lst1, lst2 = generate_arc_points(ctr, r_arc, theta_1+step, step, n_arc, thickness)
        lst_pts.extend(lst1)
        lst_pts2.extend(lst2)
        lst_ctr = lst_ctr + [ctr]*n_arc

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

        if n_corner > 0:
            step = theta_0 / n_corner
            ctr = Vector((c, 0))
            lst1, lst2 = generate_arc_points(ctr, r_corner, 0, step, n_corner+1, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_corner)

        if n_center > 0:
            step = (2 * theta) / n_center
            if n_corner == 0:
                c_start = 0
            else:
                c_start = 1
            ctr = Vector((0, -d))
            n_step = n_center - c_start
            lst1, lst2 = generate_arc_points(ctr, r_center, theta_0 + c_start*step, step, n_step + 1, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_center)

        if n_corner > 0:
            step = theta_0 / n_corner
            ctr = Vector((-c, 0))
            lst1, lst2 = generate_arc_points(ctr, r_corner, theta_1 + step, step, n_corner, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_corner)

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

        # we sweep points up from horizontal, not from center
        theta_0 = theta_corner
        theta_1 = math.pi - theta_corner

        if n_corner > 0:
            step = theta_0 / n_corner
            ctr = Vector((cc, 0))
            lst1, lst2 = generate_arc_points(ctr, r_corner, 0, step, n_corner+1, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_corner)

        if n_center > 0:
            if n_corner == 0:
                c_start = 0
            else:
                c_start = 1
            step = (theta_peak - theta_0) / n_center
            ctr = Vector((res.x, res.y))
            n_step = n_center - c_start
            lst1, lst2 = generate_arc_points(ctr, r_center, theta_0 + c_start*step, step, n_step + 1, thickness)
            if thickness > 0: # correct last point
                if len(lst2) > 1:
                    ipt = mathutils.geometry.intersect_line_line_2d(lst1[-1], Vector((0, 0)), lst2[-1], lst2[-2])
                else:
                    ipt = mathutils.geometry.intersect_line_line_2d(lst1[-1], Vector((0, 0)), lst2[-1], lst_pts2[-1])
            lst2[-1] = ipt
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_center)

            ctr = Vector((-res.x, res.y))
            n_step = n_center-1
            lst1, lst2 = generate_arc_points(ctr, r_center, math.pi - theta_peak + step, step, n_step + 1, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_center)

        if n_corner > 0:
            step = theta_0 / n_corner
            ctr = Vector((-cc, 0))
            n_step = n_corner - 1
            lst1, lst2 = generate_arc_points(ctr, r_corner, theta_1 + step, step, n_step + 1, thickness)
            lst_pts.extend(lst1)
            lst_pts2.extend(lst2)
            lst_ctr.extend([ctr] * n_corner)

    if thickness > 0:
        # drop frame left
        lst_pts3.append(Vector((lst_pts2[-1].x, -drop_sides)))
        lst_pts3.append(lst_pts2[-1])
        lst_pts3.append(lst_pts[-1])
        lst_pts3.append(Vector((lst_pts[-1].x, -drop_sides)))
        # center
        lst_pts3.append(Vector((lst_pts2[0].x, -drop_sides)))
        lst_pts3.append(lst_pts2[0])
        lst_pts3.append(lst_pts2[-1])
        lst_pts3.append(Vector((lst_pts2[-1].x, -drop_sides)))
        # right
        lst_pts3.append(Vector((lst_pts[0].x, -drop_sides)))
        lst_pts3.append(lst_pts[0])
        lst_pts3.append(lst_pts2[0])
        lst_pts3.append(Vector((lst_pts2[0].x, -drop_sides)))
    else:
        # center
        lst_pts3.append(Vector((lst_pts[0].x, -drop_sides)))
        lst_pts3.append(lst_pts[0])
        lst_pts3.append(lst_pts[-1])
        lst_pts3.append(Vector((lst_pts[-1].x, -drop_sides)))

    return lst_pts, lst_pts2, lst_ctr, lst_pts3


def generate_inset(coord, normal, thickness):
    """Takes SmartPoint or Vector3 coord, makes parallel offset lines and finds intersections
    Small corners may be eliminated by the neighboring sides, check return length before bridge by number!

    :param list coord: list of Vector(3) or SmartPoint
    :param Vector normal: normal direction to determine "inside"
    :param float thickness: distance to offset points
    :return list[Vector]: list of inset points
    """
    lst_v_in = []
    n = len(coord)
    for i in range(n):
        j = (i+1) % n
        e = coord[j] - coord[i]
        e.normalize()
        v_in = normal.cross(e).normalized()
        lst_v_in.append(v_in)

    lst_pts = []
    b_skip = False
    for i in range(n):
        if b_skip:
            b_skip = False
            continue
        h = (i+n-1) % n
        j = (i+1) % n
        m = (i+2) % n
        a = coord[h] + lst_v_in[h]*thickness
        b = coord[i] + lst_v_in[h]*thickness
        c = coord[i] + lst_v_in[i]*thickness
        d = coord[j] + lst_v_in[i]*thickness
        pts = mathutils.geometry.intersect_line_line(a, b, c, d)
        if pts is not None:
            # make sure we don't have a small edge disappearing
            # should test multiple next points, but we just test one
            c = coord[j] + lst_v_in[j] * thickness
            d = coord[m] + lst_v_in[j] * thickness
            pts2 = mathutils.geometry.intersect_line_line(a, b, c, d)
            if pts2 is not None:
                dist1 = (pts[0] - a).length
                dist2 = (pts2[0] - a).length
                if dist2 < dist1:
                    lst_pts.append(pts2[0])
                    b_skip = True
                else:
                    lst_pts.append(pts[0])
            else:
                lst_pts.append(pts[0])
    return lst_pts


def generate_ngon(n_sides, start_angle):
    """Create regular points (circle) with n_sides
    :param int n_sides: number of sides on shape
    :param float start_angle: clocking to first point
    :return list(Vector): points of n-gon
    """
    lst_pts = []
    angle_delta = (2 * math.pi) / n_sides
    for i in range(n_sides):
        dx = math.cos(i * angle_delta + start_angle)
        dy = math.sin(i * angle_delta + start_angle)
        lst_pts.append(Vector((dx,dy)))
    return lst_pts


def generate_revolve(bottom_pt, points, r_origin, r_axis, n_steps, vz):
    """Make surface of revolution points
    :param Vector bottom_pt: provide offset along r_axis for start of revolution points
    :param Vector r_origin: world point to rotate around
    :param Vector r_axis: rotation axis
    :param int n_steps: number of steps around
    :param float vz: shift polygon away from axis by this much
    :return list[Vector]: nested points [[column points]]
    """
    rot_theta = 2 * math.pi / n_steps
    mat_r = Matrix.Rotation(rot_theta, 3, r_axis)
    pts_rel = [sv - r_origin for sv in points]
    lst_pts = [pts_rel]
    for i in range(1, n_steps):
        p_rot = [mat_r @ p for p in lst_pts[-1]]
        lst_pts.append(p_rot)

    v = bottom_pt - r_origin
    v_align = v.dot(r_axis) * r_axis  # shift along axis to start point
    for lst in lst_pts:  # delayed adding origin since we rotated previous list each time
        for i in range(len(lst)):
            lst[i] = lst[i] + r_origin - v_align + vz * r_axis

    return lst_pts


def generate_super(x, sx, px, y, sy, py, n, resolution, start_angle):
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
    :return list(Vector): points of n-gon
    """
    lst = []

    def radius(theta):
        a = math.fabs(math.cos(x*theta/4)/sx)**px
        b = math.fabs(math.sin(y*theta/4)/sy)**py
        return math.pow(a+b, -1/n)

    dtheta = 2*math.pi/resolution
    for i in range(int(resolution)):
        theta = i*dtheta
        r = radius(theta)

        theta = theta + start_angle
        v = Vector((r*math.cos(theta), r*math.sin(theta)))
        lst.append(v)
    return lst



