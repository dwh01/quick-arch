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
        if thickness != 0:
            offset = thickness * vr
            lst_pts2.append(lst_pts[-1] - offset)
    return lst_pts, lst_pts2


def mirror(lst_pts, n_rev):
    rev = [Vector((-p.x, p.y)) for p in lst_pts[:n_rev]]
    rev.reverse()
    return rev


def generate_arch(w, h, brick_size, arch_type, thickness, drop_sides=0):
    """arch_type_list =
    ('SQUARE', "Square (0 pt)", "Flat", 0)
    ("JACK", "Jack (1 pt)", "Flat", 1),
    ("ROMAN", "Roman", "Round/Oval (1 pt)", 2),
    ("GOTHIC", "Gothic", "Gothic pointed (2 pt)", 3),
    ("OVAL", "Oval", "Victorian oval (3 pt)", 4),
    ("TUDOR", "Tudor", "Tudor pointed (4 pt)", 5),
    ("TRIANGLE", "Triangle", "Triangle", 6),
    ("ARABIC", "Arabic", "Pointed S-Curve (4 pt)", 7),
    ("DUTCH", "Dutch", "Rounded S-Curve (4 pt)", 8)

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
    lst_pts3 = []  # points to make a 'center', for Jack and square only

    if arch_type == 'SQUARE':
        # not an arch, just a flat lintel
        # we really need thickness
        if thickness == 0:
            jthickness = h / 10
        else:
            jthickness = thickness
        n_step = (w/2) / brick_size

        x0 = w/2
        y0 = h
        for i in range(int(math.floor(n_step))):
            dx = i*brick_size
            lst_pts.append(Vector((x0-dx, y0)))
            lst_pts2.append(Vector((x0 - dx, y0 - jthickness)))

        if lst_pts[-1][0] > 0.001:
            n_rev = len(lst_pts)
        else:
            n_rev = len(lst_pts)-1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        # make square
        if thickness==0:
            lst_pts.insert(0, Vector((lst_pts[0].x, 0)))
            lst_pts.append(Vector((lst_pts[-1].x, 0)))  # make square
        else:
            drop_sides = drop_sides + (h - thickness)

        lst_ctr = []  # not radial

        if thickness == 0:
            lst_pts2 = []
            end_pts = [lst_pts[-1], lst_pts[0]]
        else:
            end_pts = [lst_pts2[-1], lst_pts2[-1] + Vector((thickness,0)),
                   lst_pts2[0] - Vector((thickness,0)), lst_pts2[0]]

    if arch_type == 'JACK':
        # we really need thickness to make a single Jack arch polygon
        if thickness == 0:
            jthickness = h/10
        else:
            jthickness = thickness
        n_step = (w / 2) / brick_size
        n_arc = int(math.floor(n_step)) + 1

        x0 = w / 2
        y0 = h
        for i in range(n_arc):
            dx = i * brick_size
            v = Vector((x0 - dx, y0))
            lst_pts.append(v)

            y1 = y0 - jthickness
            x1 = v.x/v.y * y1
            lst_pts2.append(Vector((x1,y1)))

        if lst_pts[-1][0] > 0.001:
            n_rev = len(lst_pts)
        else:
            n_rev = len(lst_pts)-1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)

        if thickness==0:
            lst_pts.insert(0, Vector((lst_pts[0].x, 0)))
            lst_pts.append(Vector((lst_pts[-1].x, 0)))  # make square
        else:
            drop_sides = drop_sides + (h-thickness)

        lst_ctr = [Vector((0,0))] * (len(lst_pts)-1)  # one less quad than points

        if thickness > 0:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            lstpts2 = []
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'ROMAN':
        r = w**2/(8*h) + h/2
        d = h-r
        if round(d, 3) == 0:  # full circular arc
            theta = math.pi/2
        else:
            theta = math.atan2(w/2, -d)
        theta_0 = math.pi/2 - theta
        circ = r*theta
        n_step = circ / brick_size
        n_arc = int(math.floor(n_step)) + 1
        step = brick_size / r

        ctr = Vector((0, d))
        lst_pts, lst_pts2 = generate_arc_points(ctr, r, theta_0, step, n_arc, thickness)
        if lst_pts[-1].x > 0.001:
            n_rev = len(lst_pts)
        else:
            n_rev = len(lst_pts) - 1

        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)

        lst_ctr = [ctr] * (len(lst_pts) - 1)  # one less quad than points

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'GOTHIC':
        a = w/4
        b = h/2
        c = a - b**2/a
        if c <= 0:  # normal gothic arch
            d = 0  # center on springline
            r_arc = w/2 - c
            theta_start = 0
            theta_end = math.atan2(h, -c)  # angle from horizontal to peak
        else:  # segmented pointed arch, center dropped
            c1 = c
            p1 = Vector((a,b))
            p2 = Vector((c,0))
            p3 = Vector((-a,0))
            p4 = Vector((-a,-1))
            p_i = mathutils.geometry.intersect_line_line(p1, p2, p3, p4)[0]
            c = p_i.x
            d = p_i.y
            p5 = Vector([0, h])
            p_end = (p5 - p_i.to_2d())
            r_arc = p_end.length
            p6 = Vector([w/2, 0]) - p_i.to_2d()
            theta_start = math.atan2(p6.y, p6.x)
            theta_end = math.atan2(p_end.y, p_end.x)

        theta = theta_end  # angle from horizontal to peak
        circ = r_arc * (theta_end - theta_start)
        n_step = circ / brick_size
        n_arc = int(math.floor(n_step)) + 1
        ctr = Vector((c, d))
        step = brick_size / r_arc

        lst_pts, lst_pts2 = generate_arc_points(ctr, r_arc, theta_start, step, n_arc, thickness)
        lst_ctr = [ctr] * (len(lst_pts) - 1)  # one less quad than points
        # force point with 3d intersection in case segment fell short of the midline
        res = mathutils.geometry.intersect_line_line(Vector((0,h+1)).to_3d(), Vector((0, 0)).to_3d(), lst_pts[-1].to_3d(), lst_pts[-2].to_3d())
        lst_pts[-1] = res[0].to_2d()
        if thickness > 0:  # correct last point
            for i in range(1, len(lst_pts2)):
                pt = lst_pts2[i]
                if pt.x < 0:
                    ipt = mathutils.geometry.intersect_line_line_2d(lst_pts[-1], Vector((0, 0)), pt, lst_pts2[i-1])
                    if ipt is None:
                        pt.x = 0
                    else:
                        pt.x = 0
                        pt.y = ipt.y
            if lst_pts2[-1].x > 0.001:
                pt = mathutils.geometry.intersect_line_line(lst_pts2[-1].to_3d(), lst_pts2[-2].to_3d(), Vector((0, 0, 0)),
                                                            Vector((0, h, 0)))
                if pt:
                    pt = pt[0].to_2d()
                    lst_pts2[-1] = pt

        # because we forced point, we know to skip one
        n_rev = len(lst_pts) - 1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        lst_ctr2 = mirror(lst_ctr, n_rev)
        lst_ctr2.reverse()
        lst_ctr = lst_ctr + lst_ctr2

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'OVAL':
        r_corner = 2 * (h / 3)
        c = w / 2 - r_corner
        alpha = math.atan2(h/3, c)
        a = math.sqrt((h/3)**2 + c**2)/2
        b = a/math.sin(alpha)
        d = b - h/3
        r_center = h + d
        theta = math.atan2(c, d)  # angle from center line

        # corner; radius is smaller, use half brick size spacing ?
        cbrick = brick_size
        ctr = Vector((c, 0))
        circ = r_corner * (math.pi/2 - theta)
        n_step = circ / cbrick
        step = cbrick / r_corner
        n_arc = int(math.floor(n_step)) + 1
        # let's start slightly rotated so that the corner transition happens flush on a step
        # the drop sides routine will fill in under with a wedge
        # theta_0 = (math.pi/2 - theta) - (n_arc-1)*step
        corner1, corner2 = generate_arc_points(ctr, r_corner, 0, step, n_arc, thickness)
        lst_ctr = [ctr] * (len(corner1)-1)

        # center
        ctr = Vector((0, -d))
        circ = r_center * theta
        n_step = circ / brick_size
        step = brick_size / r_center
        n_arc = int(math.floor(n_step)) + 1
        # but we can skip the existing point at the end of corner
        n_arc = n_arc - 1
        theta_0 = (math.pi/2 - theta) + step
        center1, center2 = generate_arc_points(ctr, r_center, theta_0, step, n_arc, thickness)
        lst_ctr = lst_ctr + [ctr] * len(center1)  # no -1 because we use the end of the corner as a point

        lst_pts = corner1 + center1
        lst_pts2 = corner2 + center2

        if lst_pts[-1][0] > 0.001:
            n_rev = len(lst_pts)
        else:
            n_rev = len(lst_pts)-1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        lst_ctr2 = mirror(lst_ctr, n_rev)
        if n_rev == len(lst_pts):  # there is an extra quad
            lst_ctr = lst_ctr + [lst_ctr[-1]] + lst_ctr2
        else:
            lst_ctr = lst_ctr + lst_ctr2

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

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

        # corner; radius is smaller, use 1/3 brick size spacing?
        cbrick = brick_size
        ctr = Vector((cc, 0))
        circ = r_corner * theta_corner
        n_step = circ / cbrick
        step = cbrick / r_corner
        n_arc = int(math.floor(n_step)) + 1
        # let's start slightly rotated so that the corner transition happens flush on a step
        # the drop sides routine will fill in under with a wedge
        theta_0 = theta_corner - (n_arc - 1) * step
        corner1, corner2 = generate_arc_points(ctr, r_corner, theta_0, step, n_arc, thickness)
        lst_ctr = [ctr] * (len(corner1) - 1)

        # center
        ctr = Vector((res.x, res.y))
        theta = theta_peak - theta_corner
        circ = r_center * theta
        n_step = circ / brick_size
        step = brick_size / r_center
        n_arc = int(math.floor(n_step)) + 1
        # but we can skip the existing point at the end of corner
        n_arc = n_arc - 1
        theta_0 = theta_corner + step
        center1, center2 = generate_arc_points(ctr, r_center, theta_0, step, n_arc, thickness)
        lst_ctr = lst_ctr + [ctr] * len(center1)  # no -1 because we use the end of the corner as a point

        lst_pts = corner1 + center1
        lst_pts2 = corner2 + center2

        # force point with 3d intersection in case segment fell short of the midline
        res = mathutils.geometry.intersect_line_line(Vector((0, h + 1)).to_3d(), Vector((0, 0)).to_3d(),
                                                     lst_pts[-1].to_3d(), lst_pts[-2].to_3d())
        if res:
            lst_pts[-1] = res[0].to_2d()
        if thickness > 0:  # correct last point
            ipt = mathutils.geometry.intersect_line_line(lst_pts[-1].to_3d(), Vector((0, 0, 0)), lst_pts2[-1].to_3d(), lst_pts2[-2].to_3d())
            if ipt:
                lst_pts2[-1] = ipt[0].to_2d()

        # because we forced point, we know to skip one
        n_rev = len(lst_pts) - 1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        lst_ctr2 = mirror(lst_ctr, n_rev)
        lst_ctr = lst_ctr + lst_ctr2

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'TRIANGLE':
        # not an arch, just a triangle
        alpha = math.atan2(h, w/2)
        hypot = math.sqrt((w/2)**2 + h**2)
        short_stop = 0
        short_start = 0
        if thickness > 0:  # triangular caps needed
            short_stop = thickness * math.tan(alpha)
            short_start = thickness / math.tan(alpha)
            hypot = hypot - short_stop - short_start
        n_step = hypot / brick_size

        vstep = Vector((-w/2, h)).normalized()
        vstep = vstep * brick_size
        vinside = Vector((-h, -w/2)).normalized()
        vinside = vinside * thickness

        v0 = Vector((w / 2, 0))
        if thickness > 0:
            lst_pts.append(v0)
            lst_pts2.append(v0 + Vector((-thickness, 0)))
            v0 = v0 + vstep.normalized()*short_start

        n_arc = int(math.floor(n_step))+1
        for i in range(n_arc):
            lst_pts.append(v0)
            if thickness:
                lst_pts2.append(v0 + vinside)
            v0 = v0 + vstep

        if thickness > 0:
            v0 = Vector((0, h))
            lst_pts.append(v0)
            v0 = v0 - Vector((0, thickness/math.cos(alpha)))
            lst_pts2.append(v0)
            n_rev = len(lst_pts) - 1
        else:
            if lst_pts[-1][0] > 0.001:
                n_rev = len(lst_pts)
            else:
                n_rev = len(lst_pts) - 1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)

        if thickness:
            end_pts = [lst_pts[-1], lst_pts[-1] + Vector((thickness, 0)),
                       lst_pts[0] - Vector((thickness, 0)), lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'ARABIC':
        hh = 3/4 * h
        if h/w < 0.5:
            return generate_arch(w, h, brick_size, "TUDOR", thickness, drop_sides)
        if h / w > 0.8:
            r = h/2 * 0.8/(h/w)
        else:
            r = h/2
        a = 2 * hh * r**2 / (hh**2 + r)
        g = r * (hh**2 - r**2) / (hh**2 + r**2)
        ctr_corner = Vector((w / 2 - r, 0))
        r_corner = r
        theta = math.atan2(a, g)
        # transition point
        p1 = ctr_corner + Vector((math.cos(theta), math.sin(theta))) * r_corner
        p2 = (Vector((0,h)) + p1) / 2  # midpoint
        v = p2 - p1
        vperp = Vector((v.y, -v.x))
        p3 = p2 + vperp
        ipt = mathutils.geometry.intersect_line_line(p2.to_3d(), p3.to_3d(), p1.to_3d(), ctr_corner.to_3d())
        ctr_center = ipt[0].to_2d()
        r_center = (ctr_center - p1).length
        theta_0 = 0

        ctr = ctr_corner
        circ = r_corner * (theta - theta_0)
        n_step = circ / brick_size
        n_arc = int(math.floor(n_step)) + 1
        step = brick_size / r_corner
        corner1, corner2 = generate_arc_points(ctr, r_corner, theta_0, step, n_arc, thickness)
        lst_ctr = [ctr] * (len(corner1) - 1)

        r_center = r_center + thickness
        ctr = ctr_center
        theta_0 = math.pi + theta
        theta_1 = math.pi + math.atan2(ctr_center.y-h, ctr_center.x)
        theta = theta_0 - theta_1
        circ = r_center * theta
        n_step = circ / brick_size
        n_arc = int(math.floor(n_step))
        step = brick_size / r_center
        center2, center1 = generate_arc_points(ctr, r_center, theta_0, -step, n_arc, thickness)
        if thickness > 0:
            cap = None
            for i in range(len(center1)):
                if center1[i].x <= brick_size/2:  # cap
                    cap = i
                    break
            if cap:
                pt = mathutils.geometry.intersect_line_line(center1[cap].to_3d(), center1[cap-1].to_3d(), Vector((0, 0, 0)),
                                                            Vector((0, h, 0)))
                if pt:
                    center1 = center1[:cap + 1]
                    center2 = center2[:cap + 1]
                    center1.append(pt[0].to_2d())
                    center2.append(center2[-1])
                else:
                    print("could not project to center with cap")
            else:
                pt = mathutils.geometry.intersect_line_line(center1[-1].to_3d(), center1[-2].to_3d(), Vector((0, 0, 0)),
                                                            Vector((0, h, 0)))
                if pt:
                    center1[-1] = pt[0].to_2d()
                else:
                    print("could not project to center")
                center1[-1].y = h  # projecting nearly parallel can have errors

            if center2[-1].x > 0.001:
                pt = mathutils.geometry.intersect_line_line(center2[-1].to_3d(), center2[-2].to_3d(), Vector((0, 0, 0)),
                                                            Vector((0, h, 0)))
                if pt:
                    pt = pt[0].to_2d()
                    if cap:
                        center2[-1] = pt
                    else:
                        center2.append(pt)
                        center1.append(center1[-1])

            for p in center2:
                if p.x < 0:  # project back to centerline
                    res = mathutils.geometry.intersect_line_line_2d(Vector((0,0)), Vector((0,h)), p, ctr)
                    if res:
                        p.x = 0
                        p.y = res.y
                    else:
                        p.x = 0
        if thickness == 0:
            center1, center2 = center2, center1

        lst_ctr = lst_ctr + [ctr] * len(center1)

        lst_pts = corner1 + center1
        lst_pts2 = corner2 + center2
        lst_pts[-1].x = 0

        n_rev = len(lst_pts) - 1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        lst_ctr2 = mirror(lst_ctr, n_rev)
        lst_ctr = lst_ctr + lst_ctr2

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    elif arch_type == 'DUTCH':
        ht = h-thickness
        a = (ht/2)**2
        b = (w/4)**2
        d = (b-a)/ht  # offset from midpoint
        r = ht/2 + d
        theta = math.atan2(w/4, d)  # from vertical
        # because inverted, the pts_2 list controls at first
        r_corner = r + thickness

        circ = r_corner*theta
        ctr = Vector((w/2, r_corner))  # inverted curve at corner
        n_step = circ/brick_size
        n_arc = int(math.floor(n_step)) + 1
        step = brick_size / r_corner

        # want nearly flush at bottom, so let round-off lengthen the transition point
        # note reversal of corner 1 and 2
        corner2, corner1 = generate_arc_points(ctr, r_corner, 3 * math.pi / 2, -step, n_arc, thickness)
        if thickness == 0:
            corner1, corner2 = corner2, corner1
        lst_ctr = [ctr] * (len(corner1) - 1)

        circ = r * theta
        n_step = circ / brick_size
        n_arc = int(math.floor(n_step))  # + 1  share last point
        step = brick_size / r
        ctr = Vector((0,h-r))
        theta_0 = math.pi/2 - theta + step

        center1, center2 = generate_arc_points(ctr, r, theta_0, step, n_arc, thickness)
        lst_ctr = lst_ctr + [ctr] * len(center1)

        lst_pts = corner1 + center1
        lst_pts2 = corner2 + center2
        if thickness > 0:  # adjust end to meet trim
            for i in range(len(lst_pts)):
                if lst_pts2[i].x < w/2 - thickness:
                    v = lst_pts2[i] - lst_pts2[i-1]
                    dx = (w/2-thickness) - lst_pts2[i-1].x
                    dy = dx * v.y/v.x
                    pt = lst_pts2[i-1] + Vector((dx, dy))
                    lst_pts2.insert(i, pt)
                    lst_pts.insert(0, lst_pts2[0])
                    lst_pts2 = lst_pts2[1:]
                    lst_pts2.insert(0, Vector((w/2-thickness, 0)))
                    for j in range(i+1):
                        lst_pts2[j].x = pt.x
                    break

        if lst_pts[-1][0] > 0.001:
            n_rev = len(lst_pts)
        else:
            n_rev = len(lst_pts) - 1
        lst_pts = lst_pts + mirror(lst_pts, n_rev)
        lst_pts2 = lst_pts2 + mirror(lst_pts2, n_rev)
        lst_ctr2 = mirror(lst_ctr, n_rev)
        if n_rev == len(lst_pts):  # there is an extra quad
            lst_ctr = lst_ctr + [lst_ctr[-1]] + lst_ctr2
        else:
            lst_ctr = lst_ctr + lst_ctr2

        if thickness:
            end_pts = [lst_pts[-1], lst_pts2[-1], lst_pts2[0], lst_pts[0]]
        else:
            end_pts = [lst_pts[-1], lst_pts[0]]

    if len(end_pts) == 4:
        # drop frame left
        lst_pts3.append(end_pts[0])
        lst_pts3.append(Vector((end_pts[0].x, end_pts[1].y-drop_sides)))
        lst_pts3.append(Vector((end_pts[1].x, end_pts[1].y - drop_sides)))
        lst_pts3.append(end_pts[1])
        # center
        lst_pts3.append(end_pts[1])
        lst_pts3.append(Vector((end_pts[1].x, end_pts[1].y - drop_sides)))
        lst_pts3.append(Vector((end_pts[2].x, end_pts[1].y - drop_sides)))
        lst_pts3.append(end_pts[2])
        # right
        lst_pts3.append(end_pts[2])
        lst_pts3.append(Vector((end_pts[2].x, end_pts[1].y - drop_sides)))
        lst_pts3.append(Vector((end_pts[3].x, end_pts[1].y-drop_sides)))
        lst_pts3.append(end_pts[3])
    else:
        # center
        lst_pts3.append(end_pts[0])
        lst_pts3.append(Vector((end_pts[0].x, end_pts[1].y - drop_sides)))
        lst_pts3.append(Vector((end_pts[1].x, end_pts[1].y-drop_sides)))
        lst_pts3.append(end_pts[1])


    return lst_pts, lst_pts2, lst_ctr, lst_pts3


def generate_keystone(w, h, arch_type, thickness, key_width, key_below, key_above):
    """uses arch calculations but just for keystone
    key_width is at top of arch
    key_below is how far below arch to descend
    key_above is how far above arch to rise
    """
    # thanks to ThisIsCarpentry.com for classic geometric construction algorithms
    lst_pts = []  # outer arch
    lst_ctr = []  # center of uv for each arch frame polygon

    if thickness == 0:
        thickness = h / 10

    if arch_type == 'JACK':
       ctr = Vector((0, 0))
    elif arch_type == 'ROMAN':
        r = w ** 2 / (8 * h) + h / 2
        d = h - r
        ctr = Vector((0, d))
    elif arch_type == 'GOTHIC':
        a = w / 4
        b = h / 2
        c = a - b ** 2 / a
        if c <= 0:  # normal gothic arch
            d = 0  # center on springline
        else:  # segmented pointed arch, center dropped
            c1 = c
            p1 = Vector((a, b))
            p2 = Vector((c, 0))
            p3 = Vector((-a, 0))
            p4 = Vector((-a, -1))
            p_i = mathutils.geometry.intersect_line_line(p1, p2, p3, p4)[0]
            c = p_i.x
            d = p_i.y
        ctr = Vector((0, d))
    elif arch_type == 'OVAL':
        r_corner = 2 * (h / 3)
        c = w / 2 - r_corner
        alpha = math.atan2(h / 3, c)
        a = math.sqrt((h / 3) ** 2 + c ** 2) / 2
        b = a / math.sin(alpha)
        d = b - h / 3
        ctr = Vector((0, -d))
    elif arch_type == 'TUDOR':
        r_corner = 2 * (h / 3)
        cc = w / 2 - r_corner
        # angle of ray 1, starting from top center, away from centerline
        alpha = math.atan2(h / 3, w / 2)

        p1 = Vector((-r_corner * math.sin(alpha), h - r_corner * math.cos(alpha)))
        p2 = (p1 + Vector((cc, 0))) / 2
        # angle of ray 3, start from midpoint between c and p1
        beta = math.atan2(p2.y, cc - p2.x)
        dir_beta = Vector((-math.sin(beta), -math.cos(beta)))

        a = Vector((0, h, 0))
        b = p1.to_3d()
        c = p2.to_3d()
        d = (p2 + dir_beta).to_3d()
        res = mathutils.geometry.intersect_line_line(a, b, c, d)[0]
        ctr = Vector((0, res.y))

    theta = math.atan2(key_width / 2, h - ctr.y)  # flip x and y we want angle from vertical not from 0

    theta_0 = math.pi / 2 - theta
    theta_1 = math.pi / 2 + theta

    y = h - thickness - key_below
    x = y / math.tan(theta_0)
    lst_pts.append(Vector((x, y)) + ctr)
    y1 = h + key_above
    x = y1 / math.tan(theta_0)
    lst_pts.append(Vector((x, y1)) + ctr)
    x = y1 / math.tan(theta_1)
    lst_pts.append(Vector((x, y1)) + ctr)
    x = y / math.tan(theta_1)
    lst_pts.append(Vector((x, y)) + ctr)
    lst_ctr.append(ctr)

    return lst_pts, lst_ctr


def generate_inset(coord, normal, thickness, side_list=[]):
    """Takes SmartPoint or Vector3 coord, makes parallel offset lines and finds intersections
    Small corners may be eliminated by the neighboring sides, check return length before bridge by number!

    :param list coord: list of Vector(3) or SmartPoint
    :param Vector normal: normal direction to determine "inside"
    :param float thickness: distance to offset points
    :return list[Vector]: list of inset points
    """
    lst_v_in = []
    lst_dist = []
    n = len(coord)
    if len(side_list)==0:
        side_list = list(range(n))
    for i in range(n):
        j = (i+1) % n
        e = coord[j] - coord[i]
        e.normalize()
        v_in = normal.cross(e).normalized()
        lst_v_in.append(v_in)
        if i in side_list:
            lst_dist.append(thickness)
        else:
            lst_dist.append(0)

    lst_pts = []
    b_skip = False
    for i in range(n):
        if b_skip:
            b_skip = False
            continue
        h = (i+n-1) % n
        j = (i+1) % n
        m = (i+2) % n
        a = coord[h] + lst_v_in[h]*lst_dist[h]
        b = coord[i] + lst_v_in[h]*lst_dist[h]
        c = coord[i] + lst_v_in[i]*lst_dist[i]
        d = coord[j] + lst_v_in[i]*lst_dist[i]
        pts = mathutils.geometry.intersect_line_line(a, b, c, d)
        if pts is not None:
            # make sure we don't have a small edge disappearing
            # should test multiple next points, but we just test one
            e = coord[j] + lst_v_in[j] * lst_dist[j]
            f = coord[m] + lst_v_in[j] * lst_dist[j]
            pts2 = mathutils.geometry.intersect_line_line(c, d, e, f)
            if pts2 is not None:
                vi = pts2[0] - pts[0]
                ve = d - c
                if vi.dot(ve) < 0: # flipped means overshoot
                    pts3 = mathutils.geometry.intersect_line_line(pts[0], b, e, pts2[0])
                    lst_pts.append(pts3[0])
                    b_skip = True
                else:
                    lst_pts.append(pts[0])
            else:
                lst_pts.append(pts[0])
    return lst_pts


def generate_ngon(n_sides, start_angle, total_angle=2*math.pi):
    """Create regular points (circle) with n_sides
    :param int n_sides: number of sides on shape
    :param float start_angle: clocking to first point
    :param float total_angle: 2*pi for full circle
    :return list(Vector): points of n-gon
    """
    lst_pts = []
    angle_delta = (2 * math.pi) / n_sides
    for i in range(n_sides):
        if i * angle_delta > total_angle:
            break
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


def flip_profile(lst_pts, flip):
    # vertical flip
    vtop = lst_pts[-1]
    rval = []
    if flip in ['flip_y', 'flip_xy']:
        for pt in lst_pts:
            v = pt-vtop
            v.y = -v.y
            rval.append(v)
        rval.reverse()
    else:
        rval = lst_pts

    if flip in ['flip_x', 'flip_xy']:
        for v in rval:
            v.x = -v.x
    return rval


def shift_profile(lst_pts, v):
    return [p+v for p in lst_pts]


def generate_profile(ht, profile_type):
    lst_pts = []
    if profile_type == 'cyma':
        lst0 = generate_profile(ht / 2, 'ovolo')
        lst1 = generate_profile(ht / 2, 'cavetto')
        lst_pts = lst0
        v0 = lst0[-1]
        for v in lst1[1:]:
            v1 = v + v0
            lst_pts.append(v1)

    elif profile_type == 'cyma_reversa':
        lst0 = generate_profile(ht/2, 'cavetto')
        lst1 = generate_profile(ht / 2, 'ovolo')
        lst_pts = lst0
        v0 = lst0[-1]
        for v in lst1[1:]:
            v1 = v + v0
            lst_pts.append(v1)

    elif profile_type == 'ovolo':
        cell = ht / 5
        r0 = 5 * cell
        theta_0 = -math.atan2(5, 1.5)
        theta_1 = 0
        n = 3
        ctr0 = Vector((-1.5 * cell, 5*cell))
        step = (theta_1 - theta_0) / n
        lst1, unused = generate_arc_points(ctr0, r0, theta_0, step, n+1, 0)
        lst_pts = lst1

    elif profile_type == 'cavetto':
        cell = ht / 5
        r0 = 5 * cell
        theta_0 = math.pi
        theta_1 = math.pi - math.atan2(5, 1.5)
        n = 3
        ctr0 = Vector((5.25*cell, 0))
        step = (theta_1 - theta_0) / n
        lst1, unused = generate_arc_points(ctr0, r0, theta_0, step, n+1, 0)
        lst_pts = lst1

    elif profile_type == 'scotia':
        h0 = 3.5/5 * ht
        h1 = 1.5/5 * ht
        lst0 = generate_profile(h0, 'cavetto')
        lst1 = generate_profile(h1, 'cavetto')
        lst_pts = flip_profile(lst0, 'flip_y')
        v0 = lst_pts[-1]
        for v in lst1[1:]:
            v1 = v + v0
            lst_pts.append(v1)

    elif profile_type in ['torus', 'astragal']:
        r0 = ht/2
        n = 6
        theta_0 = -math.pi/2
        theta_1 = math.pi/2
        step = (theta_1 - theta_0)/n
        ctr0 = Vector((0, r0))
        lst0, unused = generate_arc_points(ctr0, r0, theta_0, step, n+1, 0)
        lst_pts = lst0

    elif profile_type == 'corona':
        cell = ht/5
        r0 = 1.25 * cell
        n = 3
        ctr0 = Vector((r0, 4 * cell))
        theta_0 = math.pi
        theta_1 = math.pi - math.atan2(cell, r0)
        step = (theta_1 - theta_0)/n
        lst0, unused = generate_arc_points(ctr0, r0, theta_0, step, n + 1, 0)
        lst0.insert(0, Vector((0,0)))
        lst_pts = lst0

    else:
        assert False, profile_type

    return lst_pts


def generate_order(ht, order):
    # common divisions
    a = ht / 5
    ped_ht = a
    b = 4 / 5 * a
    entab_ht = b
    col_ht = 4 * b

    ped_base = ped_ht / 5
    ped_cap = 1 / 5 * (ped_ht - ped_base)

    ratio = 7/10  # w/h for cavetto, cyma, ovolo
    corona = (1.25 - math.cos(math.atan2(1, 1.25)))/5

    if order == 'TUSCAN':
        D = col_ht/6
        modulo = D/2
        m = modulo/12
        D_ent = modulo + 7 * m

        ped_radius = 4.5*m + D/2

        ped_base_molding = [
            ('start', 0, 0), ('step', ped_radius + 4*m, 0),
            ('step', 0, 5 * m), ('step', -2*m, 0),
            ('step', 0, m), ('start', 0, 'last')
        ]

        h1 = 2 * m / ratio
        ped_middle_molding = [
            ('start', 0, 'last'), ('step', ped_radius + 2 * m, 0),
            ('cavetto', "flip_y", h1),
            ('step', 0, ped_ht - D/2 - h1),
            ('start', 0, 'last')
        ]

        w1 = ratio * 4 * m
        w2 = (4 * m - w1) / 2
        ped_cap_molding = [
            ('start', 0, 'last'), ('step', ped_radius + w2, 0),
            ('cyma_reversa', w1, 4 * m),
            ('step', w2, 0), ('step', 0, 2 * m),
            ('start', 0, 'last')
        ]

        col_base_molding = [
            ('start', 0, ped_ht), ('step', ped_radius, 0),
            ('step', 0, 6 * m), ('step', -2.5 * m, 0),
            ('torus', 0, 5 * m), ('step', -m/3, 0),
            ('step', 0, m),
            ('start', 0, 'last')
        ]

        w1 = (4.5 - 2.5 - 1/3) * m
        h1 = w1/ratio
        h2 = D/2 + 1.5*m
        w2 = D/2 - D_ent/2
        h3 = 0.5 * m / ratio
        col_middle_molding = [
            ('start', 0, 'last'), ('step', D/2+w1, 0),
            ('cavetto', 'flip_y', h1),
            ('step', 0, col_ht/3 - h1),  # straight
            ('step', -w2, col_ht * 2 / 3 - h2 - h3),  # entasis
            ('cavetto', 0.5 * m, h3),
            ('step', 0, 0.5 * m),
            ('torus', 0, m),
            ('start', 0, 'last')
        ]

        w1 = ratio * 3 * m
        w2 = corona * 3 * m
        w3 = 5 * m - w1 - w2
        col_cap_molding = [
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', 0, 4 * m),
            ('step', m, 0), ('step', 0, m),
            ('ovolo', w1, 3 * m), ('step', w3, 0),
            ('corona', w2, 3 * m), ('step', 0, m),
            ('start', 0, 'last')
        ]

        w1 = 10 * m * corona
        ent_base_molding = [
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('corona', w1, 10 * m), ('step', 0, 2 * m),
            ('start', 0, 'last')
        ]

        ent_middle_molding = [  # frieze
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', 0, 14 * m),
            ('start', 0, 'last')
        ]

        w1 = 3 * m * ratio
        w2 = 3.5 * m - w1
        w3 = 4 * m * ratio
        ent_cap_molding = [  # crown
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', m, 0), ('step', 0, m),
            ('ovolo', w1, 3 * m), ('step', w2, 0),
            ('step', 0, 0.5 * m), ('step', 4.5 * m, 0),
            ('step', 0, -1.5 * m), ('step', 3 * m, 2.25 * m),
            ('step', 0, -0.75 * m), ('step', m, 0),
            ('step', 0, 6 * m),
            ('step', 0.5 * m, 0), ('step', 0, 0.5 * m),
            ('step', m, 0), ('step', 0, m),
            ('ovolo', w3, 4 * m),
            ('start', 0, 'last')
        ]

    if order == 'DORIC':
        D = col_ht/7
        modulo = D / 2
        m = modulo / 12
        D_ent = modulo + 8 * m

        ped_radius = 5 * m + D / 2
        w1 = (3 * modulo + 7 * m) / 2
        w2 = 2 * m * ratio
        w3 = 3 * m - w2 - ratio * m
        h1 = 0.5 * m
        ped_base_molding = [
            ('start', 0, 0), ('step', w1, 0),
            ('step', 0, 4 * m), ('step', -0.5 * m, 0),
            ('step', 0, 1.5 * m), ('step', -w3, 0),
            ('cyma_reversa', "flip_x", 2 * m),
            ('torus', 0, m), ('step', -m, 0),
            ('step', 0, h1),
            ('start', 0, 'last')
            ]

        h1 = 8 * m
        h2 = ped_ht - 6 * m - h1
        w1 = ratio * m
        ped_middle_molding = [
            ('start', 0, 'last'), ('step', ped_radius + w1, 0),
            ('cavetto', "flip_y", m),
            ('step', 0, h2 - m),
            ('start', 0, 'last')
        ]

        w2 = 1.5 * m * ratio
        w3 = 4 * m - w2
        w4 = 1.5 * m * ratio
        ped_cap_molding = [
            ('start', 0, 'last'), ('step', ped_radius + w1, 0),
            ('cyma_reversa', w2, 1.5 * m),
            ('step', w3, 0), ('step', 0, 2.5 * m),
            ('cyma', w4, 1.5 * m),
            ('step', 2 * m - w4, 0), ('step', 0, 0.5 * m),
            ('start', 0, 'last'),
        ]

        w1 = ratio * 2 * m
        w2 = 3 * m - w1
        col_base_molding = [
            ('start', 0, 'last'), ('step', ped_radius, 0),
            ('step', 0, 6 * m), ('step', -2 * m, 0),
            ('torus', 0, 4 * m),
            ('step', 0, m), ('step', -w2, 0),
            ('step', 0, m),
            ('start', 0, 'last'),
        ]

        h1 = 2 * m
        w1 = h1 * ratio
        w2 = (D - D_ent)/2
        h3 = 1.5 * m
        w3 = h3 * ratio
        h4 = 1.5 * m + h3
        col_middle_molding = [
            ('start', 0, 'last'), ('step', modulo + w1, 0),
            ('cavetto', "flip_y", h1),
            ('step', 0, col_ht/3 - h1),  # straight
            ('step', -w2, col_ht * 2/3 - h4),  # entasis
            ('cavetto', w3, h3), ('step', 0, 0.5 * m),
            ('torus', 0.5 * m, m),
            ('start', 0, 'last'),
        ]

        w1 = 2.5 * m * ratio
        w2 = m * ratio
        w3 = 3 * m - w2 - w1
        col_cap_molding = [
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', 0, 4 * m),
            ('step', 0.5 * m, 0), ('step', 0, 0.5 * m),
            ('step', 0.5 * m, 0), ('step', 0, 0.5 * m),
            ('step', 0.5 * m, 0), ('step', 0, 0.5 * m),
            ('ovolo', w1, 2.5 * m),
            ('step', w3, 0), ('step', 0, 2.5 * m),
            ('cyma', w2, m), ('step', 0, 0.5 * m),
            ('start', 0, 'last'),
        ]

        ent_base_molding = [
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', 0, 10 * m), ('step', 1.5 * m, 0),
            ('step', 0, 2 * m),
            ('start', 0, 'last')
        ]

        ent_middle_molding = [  # frieze
            ('start', 0, 'last'), ('step', D_ent/2, 0),
            ('step', 0, 18 * m),
            ('start', 0, 'last')
        ]

        h1 = 2.5 * m
        w1 = h1 * ratio
        w2 = 5.5 * m - w1
        h3 = 2 * m
        w3 = h3 * ratio
        w4 = 3 * m * ratio
        w5 = 5.5 * m - w4 - w3
        ent_cap_molding = [  # crown
            ('start', 0, 'last'), ('step', D_ent/2 + 1.5 * m, 0),
            ('step', 0, 2 * m),
            ('cyma', w1, h1), ('step', 0, 3 * m),
            ('step', w2, 0),
            ('step', 0, 0.5 * m), ('step', 8 * m, 0),
            ('step', 0, -0.5 * m), ('step', 0.5 * m, 0),
            ('step', 0, -m), ('step', m, 0),
            ('step', 0, 0.5 * m), ('step', 0.5 * m, 0),
            ('step', 0, 0.5 * m), ('step', 0.5 * m, 0),
            ('step', 0, 0.5 * m), ('step', 0.5 * m, 0),
            ('step', 0, -0.5 * m), ('step', 1.5 * m, 0),
            ('step', 0, 4 * m),
            ('ovolo', w3, h3), ('step', w5, 0),
            ('cavetto', w4, 3 * m), ('step', 0, m),
            ('start', 0, 'last')
        ]

    # make points
    rval = []
    v0 = Vector((0, 0))
    for lst in [ped_base_molding, ped_middle_molding, ped_cap_molding,
                col_base_molding, col_middle_molding, col_cap_molding,
                ent_base_molding, ent_middle_molding, ent_cap_molding]:
        pts = []
        for mold, dx, dy in lst:
            if mold == 'start':
                if dx == 'last':
                    dx = v0.x
                if dy == 'last':
                    dy = v0.y
                v0 = Vector((dx, dy))
                pts.append(v0)
            elif mold == 'step':
                v0 = v0 + Vector((dx, dy))
                pts.append(v0)
            else:
                arc = generate_profile(dy, mold)
                if isinstance(dx, str):
                    arc = flip_profile(arc, dx)
                arc = shift_profile(arc, v0)
                pts.extend(arc)
                v0 = pts[-1]
        rval.append(pts)

    return rval
